import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class SubmissionGuardService {
  static const _key = 'soluscrt_last_symptom_submission_v1';
  static const cooldown = Duration(hours: 6);
  static DateTime? _memoryLastSubmission;

  static Future<Duration?> tempoRestante() async {
    final last = await _lastSubmission();
    if (last == null) {
      return null;
    }
    final elapsed = DateTime.now().difference(last);
    if (elapsed >= cooldown) {
      return null;
    }
    return cooldown - elapsed;
  }

  static Future<void> registrarEnvioConsiderado() async {
    final now = DateTime.now();
    _memoryLastSubmission = now;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        _key,
        jsonEncode({'created_at': now.toIso8601String()}),
      );
    } catch (_) {}
  }

  static Future<DateTime?> _lastSubmission() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_key);
      if (raw == null || raw.isEmpty) {
        return _memoryLastSubmission;
      }
      final data = jsonDecode(raw) as Map<String, dynamic>;
      final parsed = DateTime.tryParse(data['created_at']?.toString() ?? '');
      _memoryLastSubmission = parsed;
      return parsed;
    } catch (_) {
      return _memoryLastSubmission;
    }
  }
}
