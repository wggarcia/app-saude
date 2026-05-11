import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import 'empresa_auth_service.dart';

class SSTService {
  static Future<Map<String, String>> _headers() async {
    final token = await EmpresaAuthService.getToken();
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
      await EmpresaAuthService.logout();
      throw Exception('Sessao expirada. Faca login novamente.');
    } else {
      throw Exception('Erro na requisicao $path (${response.statusCode}).');
    }
  }

  static Future<dynamic> getFuncionarios({int page = 1, String search = ''}) async {
    String path = '/api/sst/funcionarios?page=$page';
    if (search.isNotEmpty) path += '&search=${Uri.encodeComponent(search)}';
    return _get(path);
  }

  static Future<dynamic> getAsos() async => _get('/api/sst/asos');

  static Future<dynamic> getCats() async => _get('/api/sst/cats');

  static Future<Map<String, dynamic>> getDashboard() async {
    final result = await _get('/api/sst/dashboard');
    return result as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> getEsocialKpis() async {
    final result = await _get('/api/sst/esocial/kpis');
    return result as Map<String, dynamic>;
  }

  static Future<dynamic> getEsocialEventos() async =>
      _get('/api/sst/esocial/eventos');

  static Future<dynamic> getTreinamentos() async =>
      _get('/api/sst/treinamentos');

  static Future<Map<String, dynamic>> transmitirEvento(
      int eventoId) async {
    final headers = await _headers();
    final uri =
        Uri.parse('${Config.baseUrl}/api/sst/esocial/eventos/$eventoId/transmitir');
    final response = await http.post(uri, headers: headers);
    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else if (response.statusCode == 401) {
      await EmpresaAuthService.logout();
      throw Exception('Sessao expirada. Faca login novamente.');
    } else {
      throw Exception(
          'Erro ao transmitir evento (${response.statusCode}).');
    }
  }
}
