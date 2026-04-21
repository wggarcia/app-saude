import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class AlertaInboxService {
  static const _seenKey = 'soluscrt_seen_government_alerts_v1';

  static Future<List<int>> _loadSeen() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_seenKey);
      if (raw == null || raw.isEmpty) {
        return <int>[];
      }
      final list = (jsonDecode(raw) as List<dynamic>)
          .map((item) => item as int)
          .toList();
      return list;
    } catch (_) {
      return <int>[];
    }
  }

  static Future<void> _saveSeen(List<int> ids) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_seenKey, jsonEncode(ids));
    } catch (_) {}
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
    }

    return newAlerts;
  }
}
