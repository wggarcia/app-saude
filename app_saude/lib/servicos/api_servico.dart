import 'public_api_service.dart';

class ApiServico {
  static Future<Map<String, dynamic>> resumoPublico() {
    return PublicApiService.fetchResumo();
  }
}
