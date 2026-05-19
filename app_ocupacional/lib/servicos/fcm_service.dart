import 'dart:convert';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'funcionario_auth_service.dart';

/// Handler de mensagens em background (top-level obrigatório para FCM)
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // Firebase já exibe a notificação automaticamente quando app está fechado.
  // Aqui podemos logar ou armazenar localmente se necessário.
}

class FcmService {
  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;

  /// Inicializa FCM: solicita permissão, registra handlers e envia token ao backend.
  static Future<void> inicializar() async {
    // Handler para mensagens com app em background/fechado
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Solicita permissão (iOS obrigatório, Android 13+ obrigatório)
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.denied) {
      return; // usuário recusou — não cadastrar token
    }

    // Handler para mensagens com app em primeiro plano
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      // O app pode exibir snackbar ou atualizar badge aqui se necessário.
      // Por ora, o polling de 60s já cuida da lista de notificações.
    });

    // Obter token e enviar ao backend
    await registrarTokenNoBackend();
  }

  /// Obtém o token FCM atual e envia para o backend (requer JWT de funcionário).
  static Future<void> registrarTokenNoBackend() async {
    try {
      final token = await FuncionarioAuthService.token();
      if (token == null || token.isEmpty) return;

      final fcmToken = await _messaging.getToken();
      if (fcmToken == null || fcmToken.isEmpty) return;

      await http.post(
        Uri.parse('${Config.baseUrl}/api/funcionario/fcm-token'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({'fcm_token': fcmToken}),
      );
    } catch (_) {
      // Silencioso — push é funcionalidade adicional, não crítica
    }
  }
}
