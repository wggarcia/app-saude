import 'dart:async';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'alerta_inbox_service.dart';
import 'device_service.dart';
import 'public_api_service.dart';
import 'regiao_base_service.dart';

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
    final notification = message.notification;
    if (notification == null) {
      return;
    }
    final data = Map<String, dynamic>.from(message.data);
    if (!data.containsKey('id') && data.containsKey('alerta_id')) {
      final raw = data['alerta_id']?.toString();
      data['id'] = raw != null ? int.tryParse(raw) : null;
    }
    await AlertaInboxService.storeRemoteNotification(
      title: notification.title ?? 'Comunicado oficial',
      message: notification.body ?? '',
      data: data,
    );
  } catch (_) {}
}

class PushService {
  static bool _initialized = false;
  static final List<StreamSubscription> _subscriptions = [];
  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();
  static String? _lastRegisteredRegionKey;

  // Exposed so screens can listen for incoming alerts.
  static final ValueNotifier<int> alertaRecebido = ValueNotifier<int>(0);

  static Future<void> initialize() async {
    if (_initialized) {
      return;
    }

    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
      await _setupLocalNotifications();
      await _requestPermission();

      // iOS: exibir banner/som/badge mesmo com o app em primeiro plano.
      // Sem isso o push chega silenciosamente quando o app está aberto.
      await FirebaseMessaging.instance.setForegroundNotificationPresentationOptions(
        alert: true,
        badge: true,
        sound: true,
      );

      await _registerToken();
      _subscriptions.addAll([
        FirebaseMessaging.instance.onTokenRefresh.listen((_) async {
          await _registerToken(force: true);
        }),
        FirebaseMessaging.onMessage.listen(_handleForegroundMessage),
        FirebaseMessaging.onMessageOpenedApp.listen(_captureRemoteMessage),
      ]);
      final initialMessage =
          await FirebaseMessaging.instance.getInitialMessage();
      if (initialMessage != null) {
        await _captureRemoteMessage(initialMessage);
      }
      _initialized = true;
    } catch (_) {
      // Push permanece opcional ate que Firebase/APNs estejam configurados.
    }
  }

  /// Cancela todos os listeners Firebase — chamar no dispose() da raiz do app.
  static Future<void> dispose() async {
    for (final sub in _subscriptions) {
      await sub.cancel();
    }
    _subscriptions.clear();
    _initialized = false;
  }

  static Future<void> _setupLocalNotifications() async {
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios = DarwinInitializationSettings();
    const settings = InitializationSettings(android: android, iOS: ios);
    await _localNotifications.initialize(settings);

    // Android 8+: canal precisa ser criado antes do primeiro show().
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(
          const AndroidNotificationChannel(
            'soluscrt_governo',
            'Alertas governamentais',
            description: 'Comunicados oficiais para a população',
            importance: Importance.max,
            playSound: true,
          ),
        );
  }

  static Future<void> _requestPermission() async {
    final messaging = FirebaseMessaging.instance;
    await messaging.requestPermission(alert: true, badge: true, sound: true);
    if (!kIsWeb && Platform.isAndroid) {
      await _localNotifications
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
    }
  }

  static Future<void> _registerToken({bool force = false}) async {
    final token = await FirebaseMessaging.instance.getToken();
    if (token == null || token.isEmpty) {
      return;
    }

    final deviceId = await DeviceService.getDeviceId();
    final base = await RegiaoBaseService.obterRegiaoBase();
    final regionKey =
        '${base?['estado'] ?? ''}|${base?['cidade'] ?? ''}|${base?['bairro'] ?? ''}';
    if (!force && _lastRegisteredRegionKey == regionKey) {
      return;
    }
    await PublicApiService.registrarPushToken(
      token: token,
      deviceId: deviceId,
      plataforma: kIsWeb
          ? 'web'
          : Platform.isIOS
              ? 'ios'
              : 'android',
      estado: base?['estado']?.toString(),
      cidade: base?['cidade']?.toString(),
      bairro: base?['bairro']?.toString(),
    );
    _lastRegisteredRegionKey = regionKey;
  }

  static Future<void> syncRegion({
    required String? estado,
    required String? cidade,
    required String? bairro,
  }) async {
    final token = await FirebaseMessaging.instance.getToken();
    if (token == null || token.isEmpty) {
      return;
    }

    final deviceId = await DeviceService.getDeviceId();
    final normalizedEstado = estado?.trim();
    final normalizedCidade = cidade?.trim();
    final normalizedBairro = bairro?.trim();
    final regionKey =
        '${normalizedEstado ?? ''}|${normalizedCidade ?? ''}|${normalizedBairro ?? ''}';
    if (_lastRegisteredRegionKey == regionKey) {
      return;
    }

    await PublicApiService.registrarPushToken(
      token: token,
      deviceId: deviceId,
      plataforma: kIsWeb
          ? 'web'
          : Platform.isIOS
              ? 'ios'
              : 'android',
      estado: normalizedEstado,
      cidade: normalizedCidade,
      bairro: normalizedBairro,
    );
    _lastRegisteredRegionKey = regionKey;
  }

  static Future<void> _handleForegroundMessage(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) {
      return;
    }

    await AlertaInboxService.storeRemoteNotification(
      title: notification.title ?? 'Comunicado oficial',
      message: notification.body ?? '',
      data: _normalizeData(message.data),
    );
    alertaRecebido.value++;

    const android = AndroidNotificationDetails(
      'soluscrt_governo',
      'Alertas governamentais',
      channelDescription: 'Comunicados oficiais para a população',
      importance: Importance.max,
      priority: Priority.high,
      playSound: true,
    );
    const ios = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );
    const details = NotificationDetails(android: android, iOS: ios);

    await _localNotifications.show(
      notification.hashCode,
      notification.title,
      notification.body,
      details,
    );
  }

  static Future<void> _captureRemoteMessage(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) {
      return;
    }
    await AlertaInboxService.storeRemoteNotification(
      title: notification.title ?? 'Comunicado oficial',
      message: notification.body ?? '',
      data: _normalizeData(message.data),
    );
    alertaRecebido.value++;
  }

  // Maps FCM data keys to the fields expected by AlertaInboxService.
  // FCM sends 'alerta_id' but the inbox uses 'id'.
  static Map<String, dynamic> _normalizeData(Map<String, dynamic> data) {
    final normalized = Map<String, dynamic>.from(data);
    if (!normalized.containsKey('id') && normalized.containsKey('alerta_id')) {
      final raw = normalized['alerta_id']?.toString();
      normalized['id'] = raw != null ? int.tryParse(raw) : null;
    }
    return normalized;
  }
}
