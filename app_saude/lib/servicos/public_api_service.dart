import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';
import 'device_service.dart';

// Chave SharedPreferences para persistir o timestamp do último envio de sintomas.
const _kUltimoEnvioSintomas = 'sintoma_ultimo_envio_utc';
const _kCooldownHoras = 168; // 7 dias

class PublicApiService {
  static const _timeout = Duration(seconds: 12);

  static Uri _uri(String path, [Map<String, dynamic>? query]) {
    final base = Uri.parse(Config.baseUrl);
    return base.replace(
      path: path,
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
  }

  static Future<Map<String, dynamic>> fetchResumo() async {
    final response =
        await http.get(_uri('/api/public/resumo')).timeout(_timeout);
    if (response.statusCode != 200) {
      throw Exception('Não foi possível carregar o panorama nacional.');
    }
    return _decodeObject(response.body);
  }

  static Future<Map<String, dynamic>> fetchRadarLocal({
    double? latitude,
    double? longitude,
    String? cidade,
    String? estado,
    String? bairro,
  }) async {
    final query = <String, dynamic>{};
    if (latitude != null && longitude != null) {
      query['latitude'] = latitude;
      query['longitude'] = longitude;
    }
    if (cidade != null && cidade.isNotEmpty) {
      query['cidade'] = cidade;
    }
    if (estado != null && estado.isNotEmpty) {
      query['estado'] = estado;
    }
    if (bairro != null && bairro.isNotEmpty) {
      query['bairro'] = bairro;
    }

    final response = await http
        .get(
          _uri('/api/public/radar-local', query),
        )
        .timeout(_timeout);
    if (response.statusCode != 200) {
      throw Exception('Não foi possível carregar o radar da sua região.');
    }
    return _decodeObject(response.body);
  }

  static Future<List<dynamic>> fetchMapa({
    String? cidade,
    String? estado,
    String? bairro,
  }) async {
    final query = <String, dynamic>{};
    if (cidade != null && cidade.isNotEmpty) {
      query['cidade'] = cidade;
    }
    if (estado != null && estado.isNotEmpty) {
      query['estado'] = estado;
    }
    if (bairro != null && bairro.isNotEmpty) {
      query['bairro'] = bairro;
    }

    final response =
        await http.get(_uri('/api/public/mapa', query)).timeout(_timeout);
    if (response.statusCode != 200) {
      throw Exception('Não foi possível carregar o mapa público.');
    }
    final data = _decodeObject(response.body);
    return (data['hotspots'] as List<dynamic>? ?? <dynamic>[]);
  }

  static Future<List<dynamic>> fetchAlertas({
    String? cidade,
    String? estado,
    String? bairro,
    bool incluirGerais = true,
    bool usarFallbackEstado = true,
  }) async {
    final query = <String, dynamic>{};
    if (cidade != null && cidade.isNotEmpty) {
      query['cidade'] = cidade;
    }
    if (estado != null && estado.isNotEmpty) {
      query['estado'] = estado;
    }
    if (bairro != null && bairro.isNotEmpty) {
      query['bairro'] = bairro;
    }
    query['incluir_gerais'] = incluirGerais;

    final response =
        await http.get(_uri('/api/public/alertas', query)).timeout(_timeout);
    if (response.statusCode != 200) {
      return <dynamic>[];
    }
    final data = _decodeObject(response.body);
    final alertas = (data['alertas'] as List<dynamic>? ?? <dynamic>[]);
    if (alertas.isEmpty &&
        usarFallbackEstado &&
        estado != null &&
        estado.isNotEmpty &&
        ((cidade != null && cidade.isNotEmpty) ||
            (bairro != null && bairro.isNotEmpty))) {
      return fetchAlertas(
        estado: estado,
        incluirGerais: incluirGerais,
        usarFallbackEstado: false,
      );
    }
    return alertas;
  }

  static Future<Map<String, dynamic>> enviarSintomas({
    required Map<String, bool> sintomas,
    required double latitude,
    required double longitude,
    String locationSource = 'current',
    String? intensidadeFebre,
    String? intensidadeArticular,
    // Anamnese epidemiológica (todos opcionais — null = não respondeu)
    int? diasSintomas,
    bool? inicioAbrupto,
    bool? viagemAreaEndemica,
    bool? exposicaoAguaEnchente,
    bool? contatoRoedores,
    bool? contatoConfirmado,
    bool? vacinadoFebreAmarela,
    bool? temComorbidade,
  }) async {
    final deviceId = await DeviceService.getDeviceId();

    final body = <String, dynamic>{
      // Sintomas base
      'febre': sintomas['febre'] ?? false,
      'tosse': sintomas['tosse'] ?? false,
      'dor_corpo': sintomas['dor_corpo'] ?? false,
      'cansaco': sintomas['cansaco'] ?? false,
      'falta_ar': sintomas['falta_ar'] ?? false,
      // Sintomas expandidos — arbovirose
      'dor_cabeca': sintomas['dor_cabeca'] ?? false,
      'dor_articular': sintomas['dor_articular'] ?? false,
      'exantema': sintomas['exantema'] ?? false,
      'conjuntivite': sintomas['conjuntivite'] ?? false,
      'vomito_nausea': sintomas['vomito_nausea'] ?? false,
      'dor_abdominal': sintomas['dor_abdominal'] ?? false,
      'calafrios': sintomas['calafrios'] ?? false,
      'sudorese': sintomas['sudorese'] ?? false,
      // Sintomas expandidos — respiratorio
      'dor_garganta': sintomas['dor_garganta'] ?? false,
      'coriza': sintomas['coriza'] ?? false,
      'perda_olfato_paladar': sintomas['perda_olfato_paladar'] ?? false,
      // Sintomas expandidos — geral / urgencia
      'diarreia': sintomas['diarreia'] ?? false,
      'ictericia': sintomas['ictericia'] ?? false,
      'rigidez_nuca': sintomas['rigidez_nuca'] ?? false,
      'manchas_hemorragicas': sintomas['manchas_hemorragicas'] ?? false,
      // Intensidades (dropdowns)
      'intensidade_febre': intensidadeFebre ?? '',
      'intensidade_articular': intensidadeArticular ?? '',
      'latitude': latitude,
      'longitude': longitude,
      'location_source': locationSource,
    };

    // Anamnese — inclui apenas os campos respondidos (null = backend ignora)
    if (diasSintomas != null) body['dias_sintomas'] = diasSintomas;
    if (inicioAbrupto != null) body['inicio_abrupto'] = inicioAbrupto;
    if (viagemAreaEndemica != null) body['viagem_area_endemica'] = viagemAreaEndemica;
    if (exposicaoAguaEnchente != null) body['exposicao_agua_enchente'] = exposicaoAguaEnchente;
    if (contatoRoedores != null) body['contato_roedores'] = contatoRoedores;
    if (contatoConfirmado != null) body['contato_caso_confirmado'] = contatoConfirmado;
    if (vacinadoFebreAmarela != null) body['vacinado_febre_amarela'] = vacinadoFebreAmarela;
    if (temComorbidade != null) body['tem_comorbidade'] = temComorbidade;

    final response = await http
        .post(
          _uri('/api/public/registrar'),
          headers: {
            'Content-Type': 'application/json',
            'X-Device-Id': deviceId,
          },
          body: jsonEncode(body),
        )
        .timeout(_timeout);

    final data = _decodeObject(response.body);
    if (response.statusCode != 200) {
      throw Exception(
        _mensagemPublicaErro(
            data['codigo']?.toString(), data['erro']?.toString()),
      );
    }
    // Salva o timestamp apenas quando o servidor aceitou (status ok ou ja_considerado).
    await _salvarUltimoEnvio();
    return data;
  }

  static Future<void> registrarAceiteLegal({
    required String versao,
    required String aceitoEm,
  }) async {
    final deviceId = await DeviceService.getDeviceId();
    await http
        .post(
          _uri('/api/public/legal-consent'),
          headers: {
            'Content-Type': 'application/json',
            'X-Device-Id': deviceId,
          },
          body: jsonEncode({
            'device_id': deviceId,
            'versao': versao,
            'plataforma': 'app',
            'termos': true,
            'privacidade': true,
            'saude_localizacao': true,
            'aceito_em': aceitoEm,
          }),
        )
        .timeout(_timeout);
  }

  // ── Cooldown local: 1 envio de sintomas por 24 h ────────────────────────────

  /// Retorna quanto tempo falta para liberar o próximo envio.
  /// Retorna null se já pode enviar.
  static Future<Duration?> cooldownRestante() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kUltimoEnvioSintomas);
      if (raw == null) return null;
      final ultimo = DateTime.tryParse(raw);
      if (ultimo == null) return null;
      final proximo = ultimo.toUtc().add(const Duration(hours: _kCooldownHoras));
      final agora = DateTime.now().toUtc();
      if (agora.isBefore(proximo)) return proximo.difference(agora);
      return null;
    } catch (_) {
      return null;
    }
  }

  static Future<void> _salvarUltimoEnvio() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
          _kUltimoEnvioSintomas, DateTime.now().toUtc().toIso8601String());
    } catch (_) {}
  }

  static Map<String, dynamic> _decodeObject(String body) {
    try {
      final data = jsonDecode(body);
      if (data is Map<String, dynamic>) {
        return data;
      }
    } catch (_) {}
    throw Exception(
        'Serviço temporariamente indisponível. Tente novamente em instantes.');
  }

  static String _mensagemPublicaErro(String? codigo, String? fallback) {
    if (codigo == 'rate_limit_publico') {
      return 'Já recebemos um envio recente deste aparelho ou rede. Tente novamente mais tarde.';
    }
    if (fallback != null && fallback.toLowerCase().contains('antifraude')) {
      return 'Não foi possível validar este envio agora. Tente novamente mais tarde.';
    }
    return fallback ??
        'Não foi possível enviar agora. Tente novamente em instantes.';
  }

  static Future<void> registrarPushToken({
    required String token,
    required String deviceId,
    required String plataforma,
    String? estado,
    String? cidade,
    String? bairro,
  }) async {
    await http
        .post(
          _uri('/api/public/push-token'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'token': token,
            'device_id': deviceId,
            'plataforma': plataforma,
            'estado': estado,
            'cidade': cidade,
            'bairro': bairro,
          }),
        )
        .timeout(_timeout);
  }
}
