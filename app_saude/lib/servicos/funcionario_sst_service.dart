import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import 'funcionario_auth_service.dart';

class FuncionarioSSTService {
  static Future<Map<String, String>> _headers() async {
    final token = await FuncionarioAuthService.getToken();
    if (token == null) throw Exception('Nao autenticado.');
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  static Future<dynamic> _get(String path) async {
    final headers = await _headers();
    final uri = Uri.parse('${Config.baseUrl}$path');
    final response = await http.get(uri, headers: headers);
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else if (response.statusCode == 401) {
      await FuncionarioAuthService.logout();
      throw Exception('Sessao expirada. Faca login novamente.');
    } else {
      throw Exception('Erro na requisicao $path (${response.statusCode}).');
    }
  }

  static Future<Map<String, dynamic>> getDashboard() async {
    final result = await _get('/api/funcionario/dashboard');
    return result as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> getMeuPerfil() async {
    final result = await _get('/api/funcionario/meu-perfil');
    return result as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> getMeusAsos() async {
    final result = await _get('/api/funcionario/meus-asos');
    return result as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> getMeusTreinamentos() async {
    final result = await _get('/api/funcionario/meus-treinamentos');
    return result as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> getMeusEpis() async {
    final result = await _get('/api/funcionario/meus-epis');
    return result as Map<String, dynamic>;
  }
}
