import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class AlertaInboxService {
  static const _seenKey = 'soluscrt_seen_government_alerts_v1';
  static const _inboxKey = 'soluscrt_government_alert_inbox_v1';
  static List<int> _memorySeen = <int>[];
  static List<Map<String, dynamic>> _memoryInbox = <Map<String, dynamic>>[];

  static Future<List<int>> _loadSeen() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_seenKey);
      if (raw == null || raw.isEmpty) {
        return _memorySeen;
      }
      final list = (jsonDecode(raw) as List<dynamic>)
          .map((item) => item as int)
          .toList();
      _memorySeen = list;
      return list;
    } catch (_) {
      return _memorySeen;
    }
  }

  static Future<void> _saveSeen(List<int> ids) async {
    _memorySeen = ids;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_seenKey, jsonEncode(ids));
    } catch (_) {}
  }

  static Future<List<Map<String, dynamic>>> loadInbox() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_inboxKey);
      if (raw == null || raw.isEmpty) {
        return _memoryInbox;
      }
      final list = (jsonDecode(raw) as List<dynamic>)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
      _memoryInbox = list;
      return list;
    } catch (_) {
      return _memoryInbox;
    }
  }

  static Future<void> _saveInbox(List<Map<String, dynamic>> items) async {
    _memoryInbox = items;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_inboxKey, jsonEncode(items));
    } catch (_) {}
  }

  static String _alertKey(Map<String, dynamic> alerta) {
    final id = (alerta['id'] as num?)?.toInt();
    if (id != null && id > 0) {
      return 'id:$id';
    }
    final title = (alerta['titulo'] ?? '').toString().trim();
    final message = (alerta['mensagem'] ?? '').toString().trim();
    final createdAt =
        (alerta['criado_em'] ?? alerta['received_at'] ?? '').toString().trim();
    return '$title|$message|$createdAt';
  }

  static Map<String, dynamic> _normalizeAlert(
    Map<String, dynamic> alerta, {
    bool unread = true,
    bool isPush = false,
  }) {
    final normalized = Map<String, dynamic>.from(alerta);
    normalized['inbox_key'] = _alertKey(normalized);
    normalized['unread'] = unread;
    normalized['from_push'] = isPush;
    normalized['received_at'] =
        (normalized['received_at'] ?? DateTime.now().toIso8601String())
            .toString();
    normalized['gravidade'] =
        (normalized['gravidade'] ?? normalized['nivel'] ?? 'moderada')
            .toString()
            .toLowerCase();
    normalized['titulo'] =
        (normalized['titulo'] ?? 'Comunicado oficial').toString();
    normalized['mensagem'] = (normalized['mensagem'] ?? '').toString();
    return normalized;
  }

  static Future<void> syncAlerts(List<dynamic> alertas) async {
    final inbox = await loadInbox();
    final byKey = <String, Map<String, dynamic>>{
      for (final item in inbox)
        _alertKey(item): Map<String, dynamic>.from(item),
    };

    for (final item in alertas) {
      final alerta = _normalizeAlert(
        Map<String, dynamic>.from(item as Map),
        unread: false,
      );
      final key = alerta['inbox_key'].toString();
      final existing = byKey[key];
      byKey[key] = {
        ...?existing,
        ...alerta,
        'unread': existing?['unread'] ?? false,
      };
    }

    final merged = byKey.values.toList()
      ..sort((a, b) => (b['received_at'] ?? '')
          .toString()
          .compareTo((a['received_at'] ?? '').toString()));
    await _saveInbox(merged.take(60).toList());
  }

  static Future<List<Map<String, dynamic>>> captureNewAlerts(
      List<dynamic> alertas) async {
    final seen = await _loadSeen();
    final newAlerts = alertas
        .map((item) => Map<String, dynamic>.from(item as Map))
        .where((item) => !seen.contains((item['id'] as num?)?.toInt() ?? -1))
        .toList();

    if (newAlerts.isNotEmpty) {
      final updated = <int>{
        ...seen,
        ...newAlerts.map((item) => (item['id'] as num?)?.toInt() ?? -1),
      }.where((id) => id >= 0).toList();
      await _saveSeen(updated);

      final inbox = await loadInbox();
      final byKey = <String, Map<String, dynamic>>{
        for (final item in inbox)
          _alertKey(item): Map<String, dynamic>.from(item),
      };
      for (final item in newAlerts) {
        final alerta = _normalizeAlert(item, unread: true);
        byKey[alerta['inbox_key'].toString()] = alerta;
      }
      final merged = byKey.values.toList()
        ..sort((a, b) => (b['received_at'] ?? '')
            .toString()
            .compareTo((a['received_at'] ?? '').toString()));
      await _saveInbox(merged.take(60).toList());
    } else {
      await syncAlerts(alertas);
    }

    return newAlerts;
  }

  static Future<void> storeRemoteNotification({
    required String title,
    required String message,
    Map<String, dynamic>? data,
  }) async {
    final inbox = await loadInbox();
    final alerta = _normalizeAlert(
      {
        'id': data?['id'],
        'titulo': title,
        'mensagem': message,
        'estado': data?['estado'],
        'cidade': data?['cidade'],
        'bairro': data?['bairro'],
        'nivel': data?['nivel'],
        'gravidade': data?['gravidade'] ?? data?['nivel'],
        'orgao': data?['orgao'] ?? 'Governo SolusCRT',
        'criado_em': data?['criado_em'],
        'received_at': DateTime.now().toIso8601String(),
      },
      unread: true,
      isPush: true,
    );

    final key = alerta['inbox_key'].toString();
    final byKey = <String, Map<String, dynamic>>{
      for (final item in inbox)
        _alertKey(item): Map<String, dynamic>.from(item),
    };
    byKey[key] = alerta;
    final merged = byKey.values.toList()
      ..sort((a, b) => (b['received_at'] ?? '')
          .toString()
          .compareTo((a['received_at'] ?? '').toString()));
    await _saveInbox(merged.take(60).toList());
  }

  static Future<void> markAsRead(Map<String, dynamic> alerta) async {
    final inbox = await loadInbox();
    final target = _alertKey(alerta);
    final updated = inbox
        .map((item) => _alertKey(item) == target
            ? {...item, 'unread': false}
            : Map<String, dynamic>.from(item))
        .toList();
    await _saveInbox(updated);
  }

  static Future<void> markAllAsRead() async {
    final inbox = await loadInbox();
    await _saveInbox(inbox.map((item) => {...item, 'unread': false}).toList());
  }

  static Future<int> unreadCount() async {
    final inbox = await loadInbox();
    return inbox.where((item) => item['unread'] == true).length;
  }

  static Future<void> forgetAlert(int id) async {
    final seen = await _loadSeen();
    await _saveSeen(seen.where((item) => item != id).toList());
  }
}
