import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'empresa_auth_service.dart';

class EmpresaSstService {
  static Future<Map<String, String>> _headers() async {
    final token = await EmpresaAuthService.token();
    if (token == null || token.isEmpty) throw Exception('Sessão expirada.');
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  static Future<Map<String, dynamic>> dashboard() async {
    final response = await http.get(
      Uri.parse('${Config.baseUrl}/api/sst/dashboard'),
      headers: await _headers(),
    );
    if (response.statusCode == 401) {
      await EmpresaAuthService.logout();
      throw Exception('Sessão expirada. Faça login novamente.');
    }
    if (response.statusCode != 200) {
      throw Exception('Erro ao carregar painel SST (${response.statusCode}).');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }
}
