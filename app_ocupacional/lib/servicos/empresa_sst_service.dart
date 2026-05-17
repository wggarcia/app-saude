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

  static Future<List<dynamic>> listarAssinaturas({
    String? tipoDocumento,
    String? status,
    int? objetoId,
  }) async {
    final params = <String, String>{};
    if (tipoDocumento != null) params['tipo_documento'] = tipoDocumento;
    if (status != null) params['status'] = status;
    if (objetoId != null) params['objeto_id'] = objetoId.toString();
    final uri = Uri.parse('${Config.baseUrl}/api/sst/assinaturas')
        .replace(queryParameters: params.isNotEmpty ? params : null);
    final response = await http.get(uri, headers: await _headers());
    if (response.statusCode == 401) {
      await EmpresaAuthService.logout();
      throw Exception('Sessão expirada. Faça login novamente.');
    }
    if (response.statusCode != 200) {
      throw Exception('Erro ao carregar assinaturas (${response.statusCode}).');
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return body['assinaturas'] as List<dynamic>;
  }

  static Future<Map<String, dynamic>> solicitarAssinatura({
    required String tipoDocumento,
    required int objetoId,
    String? signatarioNome,
    String? signatarioEmail,
    String? signatarioCpf,
    int validadeDias = 15,
  }) async {
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/api/sst/assinaturas'),
      headers: await _headers(),
      body: jsonEncode({
        'tipo_documento': tipoDocumento,
        'objeto_id': objetoId,
        if (signatarioNome != null) 'signatario_nome': signatarioNome,
        if (signatarioEmail != null) 'signatario_email': signatarioEmail,
        if (signatarioCpf != null) 'signatario_cpf': signatarioCpf,
        'validade_dias': validadeDias,
      }),
    );
    if (response.statusCode == 401) {
      await EmpresaAuthService.logout();
      throw Exception('Sessão expirada. Faça login novamente.');
    }
    if (response.statusCode != 201) {
      final err = jsonDecode(response.body);
      throw Exception(err['erro'] ?? 'Erro ao solicitar assinatura.');
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return body['assinatura'] as Map<String, dynamic>;
  }
}
