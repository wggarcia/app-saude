import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';

class ApiServico {
  static String? token;

  static Future<bool> login(String email, String senha) async {
    final response = await http.post(
      Uri.parse("${Config.baseUrl}/api/login"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "email": email,
        "senha": senha,
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      token = data["token"];
      return true;
    }

    return false;
  }

  static Future<bool> enviarSintomas(Map dados) async {
    final response = await http.post(
      Uri.parse("${Config.baseUrl}/api/registrar"),
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer $token"
      },
      body: jsonEncode(dados),
    );

    return response.statusCode == 200;
  }
}