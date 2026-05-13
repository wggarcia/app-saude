import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

class EmpresaSession {
  const EmpresaSession({
    required this.token,
    required this.empresaNome,
    required this.principalNome,
    required this.destination,
  });

  final String token;
  final String empresaNome;
  final String principalNome;
  final String destination;

  factory EmpresaSession.fromJson(Map<String, dynamic> data) {
    return EmpresaSession(
      token: data['token']?.toString() ?? '',
      empresaNome: data['empresa_nome']?.toString() ?? 'Empresa',
      principalNome: data['principal_nome']?.toString() ?? 'Usuário',
      destination: data['destination']?.toString() ?? '/dashboard-empresa/',
    );
  }
}

class SessaoEmUsoException implements Exception {
  const SessaoEmUsoException(this.message);
  final String message;

  @override
  String toString() => message;
}

class EmpresaAuthService {
  static const _tokenKey = 'empresa_token';
  static const _empresaNomeKey = 'empresa_nome';
  static const _principalNomeKey = 'empresa_principal_nome';
  static const _deviceIdKey = 'empresa_device_id';

  static Future<EmpresaSession> login(
    String email,
    String senha, {
    bool forceLogin = false,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final deviceId = await _deviceId(prefs);
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/login-empresa-api'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'email': email.trim(),
        'senha': senha,
        'device_id': deviceId,
        'device_name': 'App Ocupacional',
        if (forceLogin) 'force_login': true,
      }),
    );

    final data = _jsonMap(response.body);
    if (response.statusCode == 409 && data['codigo'] == 'sessao_em_uso') {
      throw SessaoEmUsoException(
        data['mensagem']?.toString() ?? 'Sessão em uso em outro dispositivo.',
      );
    }
    if (response.statusCode != 200) {
      throw Exception(
        data['mensagem']?.toString() ??
            data['erro']?.toString() ??
            'Falha no login da empresa (${response.statusCode}).',
      );
    }

    final session = EmpresaSession.fromJson(data);
    if (session.token.isEmpty) {
      throw Exception('Token ausente no login da empresa.');
    }

    await prefs.setString(_tokenKey, session.token);
    await prefs.setString(_empresaNomeKey, session.empresaNome);
    await prefs.setString(_principalNomeKey, session.principalNome);
    return session;
  }

  static Future<String?> token() async {
    return (await SharedPreferences.getInstance()).getString(_tokenKey);
  }

  static Future<String?> empresaNome() async {
    return (await SharedPreferences.getInstance()).getString(_empresaNomeKey);
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_empresaNomeKey);
    await prefs.remove(_principalNomeKey);
  }

  static Map<String, dynamic> _jsonMap(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) return decoded;
    } catch (_) {
      return {};
    }
    return {};
  }

  static Future<String> _deviceId(SharedPreferences prefs) async {
    final existing = prefs.getString(_deviceIdKey);
    if (existing != null && existing.isNotEmpty) return existing;
    final id = 'app-ocupacional-${DateTime.now().millisecondsSinceEpoch}';
    await prefs.setString(_deviceIdKey, id);
    return id;
  }
}
