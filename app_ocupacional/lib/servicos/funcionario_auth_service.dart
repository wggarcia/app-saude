import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'fcm_service.dart';

/// Armazena dados de sessão em flutter_secure_storage (AES-256 no Android keystore /
/// iOS Keychain) — LGPD: token, email, nome e cargo nunca ficam em SharedPreferences.
class FuncionarioAuthService {
  static const _tokenKey   = 'funcionario_token';
  static const _emailKey   = 'funcionario_email';
  static const _nomeKey    = 'funcionario_nome';
  static const _cargoKey   = 'funcionario_cargo';
  static const _empresaKey = 'funcionario_empresa';
  static const _funcIdKey  = 'funcionario_id';

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
  );

  /// Login com email + senha
  static Future<Map<String, dynamic>> login(
    String email,
    String senha,
  ) async {
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/funcionario/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email.trim().toLowerCase(), 'senha': senha}),
    );
    if (response.statusCode != 200) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      throw Exception(body['erro'] ?? 'Falha no login (${response.statusCode}).');
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    await _salvarSessao(data);
    FcmService.registrarTokenNoBackend().ignore();
    return data;
  }

  /// Etapa 1: busca empresas vinculadas ao CPF
  static Future<Map<String, dynamic>> buscarCpf(String cpf) async {
    final cpfLimpo = cpf.replaceAll(RegExp(r'[^0-9]'), '');
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/funcionario/buscar-cpf'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'cpf': cpfLimpo}),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode != 200) {
      throw Exception(body['erro'] ?? 'CPF não encontrado (${response.statusCode}).');
    }
    return body;
  }

  /// Etapa 2: registro com o registro_token emitido na etapa 1 + email + senha.
  /// O token prova a posse do CPF validado — o backend deriva o funcionário
  /// dele e ignora qualquer funcionario_id cru (evita account takeover
  /// cross-tenant por enumeração de IDs).
  static Future<Map<String, dynamic>> registrar(
    String registroToken,
    String email,
    String senha,
  ) async {
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/funcionario/registrar'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'registro_token': registroToken,
        'email': email.trim().toLowerCase(),
        'senha': senha,
      }),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode != 201) {
      throw Exception(body['erro'] ?? 'Falha no registro (${response.statusCode}).');
    }
    await _salvarSessao(body);
    FcmService.registrarTokenNoBackend().ignore();
    return body;
  }

  static Future<void> _salvarSessao(Map<String, dynamic> data) async {
    final token = data['token']?.toString();
    if (token == null || token.isEmpty) throw Exception('Token ausente.');
    await _storage.write(key: _tokenKey,   value: token);
    await _storage.write(key: _emailKey,   value: data['email']?.toString() ?? '');
    await _storage.write(key: _nomeKey,    value: data['nome']?.toString() ?? '');
    await _storage.write(key: _cargoKey,   value: data['cargo']?.toString() ?? '');
    await _storage.write(key: _empresaKey, value: data['empresa_nome']?.toString() ?? '');
    final fid = data['funcionario_id'];
    if (fid != null) await _storage.write(key: _funcIdKey, value: fid.toString());
  }

  static Future<String?> token() async => _storage.read(key: _tokenKey);

  static Future<int?> funcId() async {
    final v = await _storage.read(key: _funcIdKey);
    return v != null ? int.tryParse(v) : null;
  }

  static Future<String?> emailSalvo() async => _storage.read(key: _emailKey);

  static Future<Map<String, String>> dadosSalvos() async {
    final vals = await Future.wait([
      _storage.read(key: _nomeKey),
      _storage.read(key: _cargoKey),
      _storage.read(key: _empresaKey),
      _storage.read(key: _emailKey),
    ]);
    return {
      'nome':    vals[0] ?? '',
      'cargo':   vals[1] ?? '',
      'empresa': vals[2] ?? '',
      'email':   vals[3] ?? '',
    };
  }

  static Future<void> logout() async {
    await _storage.deleteAll();
  }
}
