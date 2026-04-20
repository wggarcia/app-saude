import 'package:geolocator/geolocator.dart';

class LocationSnapshot {
  const LocationSnapshot({
    required this.latitude,
    required this.longitude,
    required this.source,
  });

  final double latitude;
  final double longitude;
  final String source;
}

class LocationService {
  static const Map<String, dynamic> referenciaPublicaInicial = {
    'bairro': 'Centro',
    'cidade': 'Rio de Janeiro',
    'estado': 'RJ',
    'latitude': -22.9068,
    'longitude': -43.1729,
  };

  static Future<void> _ensurePermission() async {
    final enabled = await Geolocator.isLocationServiceEnabled();
    if (!enabled) {
      throw Exception('Ative a localizacao do aparelho para continuar.');
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      throw Exception('Permissao de localizacao negada.');
    }
  }

  static Future<Position?> getCurrentPositionOrNull() async {
    try {
      await _ensurePermission();
      return await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.medium,
        timeLimit: const Duration(seconds: 12),
      );
    } catch (_) {
      try {
        await _ensurePermission();
        return await Geolocator.getLastKnownPosition();
      } catch (_) {
        return null;
      }
    }
  }

  static Future<LocationSnapshot> getBestEffortLocation({
    Map<String, dynamic>? fallbackRegion,
  }) async {
    final current = await getCurrentPositionOrNull();
    if (current != null) {
      return LocationSnapshot(
        latitude: current.latitude,
        longitude: current.longitude,
        source: 'current',
      );
    }

    final fallbackLat = (fallbackRegion?['latitude'] as num?)?.toDouble();
    final fallbackLon = (fallbackRegion?['longitude'] as num?)?.toDouble();
    if (fallbackLat != null && fallbackLon != null) {
      return LocationSnapshot(
        latitude: fallbackLat,
        longitude: fallbackLon,
        source: 'base',
      );
    }

    return const LocationSnapshot(
      latitude: -22.9068,
      longitude: -43.1729,
      source: 'public_reference',
    );
  }
}
