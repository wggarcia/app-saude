import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import '../main.dart' show appNavigatorKey;
import '../telas/funcionario/tela_login_funcionario.dart';
import 'funcionario_auth_service.dart';

class FuncionarioSstService {
  static Future<Map<String, String>> _headers() async {
    final token = await FuncionarioAuthService.token();
    if (token == null || token.isEmpty) throw Exception('Sessão expirada.');
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  static Future<Map<String, dynamic>> _get(String path) async {
    final response = await http.get(
      Uri.parse('${Config.baseUrl}$path'),
      headers: await _headers(),
    );
    if (response.statusCode == 401) {
      await FuncionarioAuthService.logout();
      // Redireciona automaticamente para login sem depender de BuildContext
      appNavigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const TelaLoginFuncionario()),
        (_) => false,
      );
      throw Exception('Sessão expirada. Faça login novamente.');
    }
    if (response.statusCode != 200) {
      throw Exception('Erro ao carregar $path (${response.statusCode})');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> _post(String path) async {
    final response = await http.post(
      Uri.parse('${Config.baseUrl}$path'),
      headers: await _headers(),
    );
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> dashboard() =>
      _get('/api/funcionario/dashboard');
  static Future<Map<String, dynamic>> perfil() =>
      _get('/api/funcionario/meu-perfil');
  static Future<Map<String, dynamic>> asos() =>
      _get('/api/funcionario/meus-asos');
  static Future<Map<String, dynamic>> treinamentos() =>
      _get('/api/funcionario/meus-treinamentos');
  static Future<Map<String, dynamic>> epis() =>
      _get('/api/funcionario/meus-epis');
  static Future<Map<String, dynamic>> solicitacoes() =>
      _get('/api/funcionario/minhas-solicitacoes');
  static Future<Map<String, dynamic>> notificacoes() =>
      _get('/api/funcionario/notificacoes');
  static Future<void> marcarLida(int id) =>
      _post('/api/funcionario/notificacoes/$id/lida');
  static Future<Map<String, dynamic>> reunioes() =>
      _get('/api/funcionario/reunioes');
}
