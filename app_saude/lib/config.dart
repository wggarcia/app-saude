import 'package:flutter/foundation.dart';

class Config {
  static const String _overrideBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '',
  );
  static const String productionBaseUrl = 'https://app-saude-p9n8.onrender.com';
  static const String localBaseUrl = 'http://127.0.0.1:8000';
  static const String androidEmulatorBaseUrl = 'http://10.0.2.2:8000';
  static const String mapboxPublicToken = String.fromEnvironment(
    'MAPBOX_PUBLIC_TOKEN',
    defaultValue:
        'pk.eyJ1Ijoid2ZnZ2FyY2lhIiwiYSI6ImNtbjgxNHV1NjA1eTUyd29jYjRhaXg1bGYifQ.N4JTgjeO7QIb_7m2LijOAQ',
  );
  static const bool useLocalApi = bool.fromEnvironment(
    'USE_LOCAL_API',
    defaultValue: false,
  );

  static String get baseUrl {
    if (_overrideBaseUrl.isNotEmpty) {
      return _overrideBaseUrl;
    }
    if (!useLocalApi) {
      return productionBaseUrl;
    }
    if (!kDebugMode) {
      return productionBaseUrl;
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      return androidEmulatorBaseUrl;
    }
    return localBaseUrl;
  }
}
