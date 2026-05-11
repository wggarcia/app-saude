import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

class EmpresaAuthService {
  static const String _tokenKey = 'empresa_token';

  static Future<Map<String, dynamic>> login(
      String email, String senha) async {
    final uri = Uri.parse('${Config.baseUrl}/api/login-empresa-api');
    final response = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'senha': senha}),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final token = data['token']?.toString() ??
          data['access_token']?.toString() ??
          data['access']?.toString();
      if (token == null || token.isEmpty) {
        throw Exception('Token nao encontrado na resposta.');
      }
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_tokenKey, token);
      return data;
    } else {
      String msg = 'Credenciais invalidas.';
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

  static Future<Map<String, dynamic>> getDadosEmpresa() async {
    final token = await getToken();
    if (token == null) throw Exception('Nao autenticado.');
    final uri = Uri.parse('${Config.baseUrl}/api/empresa/resumo');
    final response = await http.get(
      uri,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else if (response.statusCode == 401) {
      await logout();
      throw Exception('Sessao expirada. Faca login novamente.');
    } else {
      throw Exception('Erro ao buscar dados da empresa (${response.statusCode}).');
    }
  }
}
