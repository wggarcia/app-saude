import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

class FuncionarioAuthService {
  static const _tokenKey = 'funcionario_token';
  static const _emailKey = 'funcionario_email';
  static const _nomeKey = 'funcionario_nome';
  static const _cargoKey = 'funcionario_cargo';
  static const _empresaKey = 'funcionario_empresa';

  /// Login com email + senha (novo)
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
    return data;
  }

  /// Registro: funcionário cria conta no app usando CPF + email + senha
  static Future<Map<String, dynamic>> registrar(
    String cpf,
    String email,
    String senha,
  ) async {
    final cpfLimpo = cpf.replaceAll(RegExp(r'[^0-9]'), '');
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/funcionario/registrar'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'cpf': cpfLimpo,
        'email': email.trim().toLowerCase(),
        'senha': senha,
      }),
    );
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode != 201) {
      throw Exception(body['erro'] ?? 'Falha no registro (${response.statusCode}).');
    }
    await _salvarSessao(body);
    return body;
  }

  static Future<void> _salvarSessao(Map<String, dynamic> data) async {
    final token = data['token']?.toString();
    if (token == null || token.isEmpty) throw Exception('Token ausente.');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
    await prefs.setString(_emailKey, data['email']?.toString() ?? '');
    await prefs.setString(_nomeKey, data['nome']?.toString() ?? '');
    await prefs.setString(_cargoKey, data['cargo']?.toString() ?? '');
    await prefs.setString(_empresaKey, data['empresa_nome']?.toString() ?? '');
  }

  static Future<String?> token() async =>
      (await SharedPreferences.getInstance()).getString(_tokenKey);

  static Future<String?> emailSalvo() async =>
      (await SharedPreferences.getInstance()).getString(_emailKey);

  static Future<Map<String, String>> dadosSalvos() async {
    final prefs = await SharedPreferences.getInstance();
    return {
      'nome': prefs.getString(_nomeKey) ?? '',
      'cargo': prefs.getString(_cargoKey) ?? '',
      'empresa': prefs.getString(_empresaKey) ?? '',
      'email': prefs.getString(_emailKey) ?? '',
    };
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_emailKey);
    await prefs.remove(_nomeKey);
    await prefs.remove(_cargoKey);
    await prefs.remove(_empresaKey);
  }
}
