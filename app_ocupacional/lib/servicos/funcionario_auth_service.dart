import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

class FuncionarioAuthService {
  static const _tokenKey = 'funcionario_token';

  static Future<Map<String, dynamic>> login(
    String cpf,
    String dataNascimento,
  ) async {
    final cpfLimpo = cpf.replaceAll(RegExp(r'[^0-9]'), '');
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/funcionario/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'cpf': cpfLimpo, 'data_nascimento': dataNascimento}),
    );
    if (response.statusCode != 200) {
      throw Exception(
        'Falha no login do trabalhador (${response.statusCode}).',
      );
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final token = data['token']?.toString();
    if (token == null || token.isEmpty) {
      throw Exception('Token ausente no login.');
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
    return data;
  }

  static Future<String?> token() async =>
      (await SharedPreferences.getInstance()).getString(_tokenKey);

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}
