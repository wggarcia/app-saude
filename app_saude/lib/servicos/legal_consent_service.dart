import 'package:shared_preferences/shared_preferences.dart';

import 'public_api_service.dart';

class LegalConsentService {
  static const currentVersion = '2026.04.23';
  static const _acceptedVersionKey = 'soluscrt_legal_accepted_version';
  static const _acceptedAtKey = 'soluscrt_legal_accepted_at';

  static Future<bool> hasAcceptedCurrentTerms() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getString(_acceptedVersionKey) == currentVersion;
    } catch (_) {
      return false;
    }
  }

  static Future<void> acceptCurrentTerms() async {
    final prefs = await SharedPreferences.getInstance();
    final acceptedAt = DateTime.now().toIso8601String();
    await prefs.setString(_acceptedVersionKey, currentVersion);
    await prefs.setString(_acceptedAtKey, acceptedAt);
    try {
      await PublicApiService.registrarAceiteLegal(
        versao: currentVersion,
        aceitoEm: acceptedAt,
      );
    } catch (_) {
      // O aceite local libera o uso; o backend registra novamente em uma
      // proxima versao se o termo mudar ou se o usuario reinstalar o app.
    }
  }
}
