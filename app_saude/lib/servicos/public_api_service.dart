import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'device_service.dart';

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
      throw Exception('Nao foi possivel carregar o panorama nacional.');
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
      throw Exception('Nao foi possivel carregar o radar da sua regiao.');
    }
    return _decodeObject(response.body);
  }

  static Future<List<dynamic>> fetchMapa({
    String? cidade,
    String? estado,
  }) async {
    final query = <String, dynamic>{};
    if (cidade != null && cidade.isNotEmpty) {
      query['cidade'] = cidade;
    }
    if (estado != null && estado.isNotEmpty) {
      query['estado'] = estado;
    }

    final response =
        await http.get(_uri('/api/public/mapa', query)).timeout(_timeout);
    if (response.statusCode != 200) {
      throw Exception('Nao foi possivel carregar o mapa publico.');
    }
    final data = _decodeObject(response.body);
    return (data['hotspots'] as List<dynamic>? ?? <dynamic>[]);
  }

  static Future<List<dynamic>> fetchAlertas({
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
        await http.get(_uri('/api/public/alertas', query)).timeout(_timeout);
    if (response.statusCode != 200) {
      return <dynamic>[];
    }
    final data = _decodeObject(response.body);
    return (data['alertas'] as List<dynamic>? ?? <dynamic>[]);
  }

  static Future<Map<String, dynamic>> enviarSintomas({
    required Map<String, bool> sintomas,
    required double latitude,
    required double longitude,
    String locationSource = 'current',
  }) async {
    final deviceId = await DeviceService.getDeviceId();
    final response = await http
        .post(
          _uri('/api/public/registrar'),
          headers: {
            'Content-Type': 'application/json',
            'X-Device-Id': deviceId,
          },
          body: jsonEncode({
            'febre': sintomas['febre'] ?? false,
            'tosse': sintomas['tosse'] ?? false,
            'dor_corpo': sintomas['dor_corpo'] ?? false,
            'cansaco': sintomas['cansaco'] ?? false,
            'falta_ar': sintomas['falta_ar'] ?? false,
            'latitude': latitude,
            'longitude': longitude,
            'location_source': locationSource,
          }),
        )
        .timeout(_timeout);

    final data = _decodeObject(response.body);
    if (response.statusCode != 200) {
      throw Exception(
        _mensagemPublicaErro(
            data['codigo']?.toString(), data['erro']?.toString()),
      );
    }
    return data;
  }

  static Map<String, dynamic> _decodeObject(String body) {
    try {
      final data = jsonDecode(body);
      if (data is Map<String, dynamic>) {
        return data;
      }
    } catch (_) {}
    throw Exception(
        'Servico temporariamente indisponivel. Tente novamente em instantes.');
  }

  static String _mensagemPublicaErro(String? codigo, String? fallback) {
    if (codigo == 'rate_limit_publico') {
      return 'Ja recebemos um envio recente deste aparelho ou rede. Tente novamente mais tarde.';
    }
    if (fallback != null && fallback.toLowerCase().contains('antifraude')) {
      return 'Nao foi possivel validar este envio agora. Tente novamente mais tarde.';
    }
    return fallback ??
        'Nao foi possivel enviar agora. Tente novamente em instantes.';
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
