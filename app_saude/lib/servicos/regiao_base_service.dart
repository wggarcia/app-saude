import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class RegiaoBaseService {
  static const _key = 'soluscrt_regiao_base_v1';
  static const _modoKey = 'soluscrt_monitoramento_modo_v1';
  static Map<String, dynamic>? _memoryBase;
  static String _memoryMode = 'base';

  static Future<void> registrarObservacao({
    required Map<String, dynamic> local,
    required double latitude,
    required double longitude,
  }) async {
    final cidade = (local['cidade'] ?? '').toString().trim();
    final estado = (local['estado'] ?? '').toString().trim();
    final bairro = (local['bairro'] ?? '').toString().trim();

    if (cidade.isEmpty || estado.isEmpty) {
      return;
    }

    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_key);
      final data = raw == null
          ? <String, dynamic>{'regions': <Map<String, dynamic>>[]}
          : jsonDecode(raw) as Map<String, dynamic>;

      final List<dynamic> existing =
          (data['regions'] as List<dynamic>? ?? <dynamic>[]);
      final regions = existing
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
      final regionKey =
          '${bairro.toLowerCase()}|${cidade.toLowerCase()}|${estado.toLowerCase()}';
      final now = DateTime.now().toIso8601String();

      final index = regions.indexWhere((item) => item['key'] == regionKey);
      if (index >= 0) {
        final current = regions[index];
        final currentCount = (current['count'] as num?)?.toInt() ?? 0;
        final currentLat =
            (current['latitude'] as num?)?.toDouble() ?? latitude;
        final currentLon =
            (current['longitude'] as num?)?.toDouble() ?? longitude;
        final nextCount = currentCount + 1;
        current['count'] = nextCount;
        current['latitude'] =
            ((currentLat * currentCount) + latitude) / nextCount;
        current['longitude'] =
            ((currentLon * currentCount) + longitude) / nextCount;
        current['last_seen'] = now;
        current['bairro'] = bairro;
        current['cidade'] = cidade;
        current['estado'] = estado;
        regions[index] = current;
      } else {
        regions.add({
          'key': regionKey,
          'bairro': bairro,
          'cidade': cidade,
          'estado': estado,
          'latitude': latitude,
          'longitude': longitude,
          'count': 1,
          'last_seen': now,
        });
      }

      await prefs.setString(_key, jsonEncode({'regions': regions}));
      _memoryBase = regions.first;
    } catch (_) {
      _memoryBase = {
        'key':
            '${bairro.toLowerCase()}|${cidade.toLowerCase()}|${estado.toLowerCase()}',
        'bairro': bairro,
        'cidade': cidade,
        'estado': estado,
        'latitude': latitude,
        'longitude': longitude,
        'count': 1,
        'last_seen': DateTime.now().toIso8601String(),
      };
    }
  }

  static Future<Map<String, dynamic>?> obterRegiaoBase() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_key);
      if (raw == null) {
        return _memoryBase;
      }

      final data = jsonDecode(raw) as Map<String, dynamic>;
      final List<dynamic> existing =
          (data['regions'] as List<dynamic>? ?? <dynamic>[]);
      if (existing.isEmpty) {
        return _memoryBase;
      }

      final regions = existing
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
      regions.sort((a, b) {
        final countCompare = ((b['count'] as num?)?.toInt() ?? 0)
            .compareTo((a['count'] as num?)?.toInt() ?? 0);
        if (countCompare != 0) {
          return countCompare;
        }
        return (b['last_seen']?.toString() ?? '')
            .compareTo(a['last_seen']?.toString() ?? '');
      });
      _memoryBase = regions.first;
      return regions.first;
    } catch (_) {
      return _memoryBase;
    }
  }

  static bool estaForaDaRegiaoBase({
    required Map<String, dynamic>? regiaoBase,
    required Map<String, dynamic>? localAtual,
  }) {
    if (regiaoBase == null || localAtual == null) {
      return false;
    }

    final cidadeBase =
        (regiaoBase['cidade'] ?? '').toString().trim().toLowerCase();
    final estadoBase =
        (regiaoBase['estado'] ?? '').toString().trim().toLowerCase();
    final cidadeAtual =
        (localAtual['cidade'] ?? '').toString().trim().toLowerCase();
    final estadoAtual =
        (localAtual['estado'] ?? '').toString().trim().toLowerCase();

    if (cidadeBase.isEmpty ||
        estadoBase.isEmpty ||
        cidadeAtual.isEmpty ||
        estadoAtual.isEmpty) {
      return false;
    }

    return cidadeBase != cidadeAtual || estadoBase != estadoAtual;
  }

  static Future<void> salvarModoMonitoramento(String modo) async {
    _memoryMode = modo;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_modoKey, modo);
    } catch (_) {}
  }

  static Future<String> obterModoMonitoramento() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_modoKey) ?? _memoryMode;
    } catch (_) {
      return _memoryMode;
    }
  }
}
