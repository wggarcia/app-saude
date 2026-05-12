import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

class FuncionarioAuthService {
  static const String _tokenKey = 'funcionario_token';

  static Future<Map<String, dynamic>> login(
      String cpf, String dataNascimento) async {
    final cpfLimpo = cpf.replaceAll(RegExp(r'[^0-9]'), '');
    final uri = Uri.parse('${Config.baseUrl}/api/funcionario/login');
    final response = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'cpf': cpfLimpo, 'data_nascimento': dataNascimento}),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final token = data['token']?.toString();
      if (token == null || token.isEmpty) {
        throw Exception('Token nao encontrado na resposta.');
      }
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_tokenKey, token);
      return data;
    } else {
      String msg = 'CPF ou data de nascimento invalidos.';
      try {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        if (body['detail'] != null) msg = body['detail'].toString();
        if (body['erro'] != null) msg = body['erro'].toString();
        if (body['message'] != null) msg = body['message'].toString();
      } catch (_) {}
      throw Exception(msg);
    }
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  static Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  static Future<bool> isLoggedIn() async {
    final token = await getToken();
    return token != null && token.isNotEmpty;
  }
}
