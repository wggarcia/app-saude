import 'dart:async';

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
  static const _maxLastKnownAge = Duration(minutes: 30);
  static const _maxSubmissionAge = Duration(minutes: 5);
  static const _maxSubmissionAccuracyMeters = 500.0;

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

  static Future<bool> solicitarPermissaoInicial() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (!enabled) {
        return false;
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return false;
      }

      await _requestPreciseLocationIfNeeded();
      return true;
    } catch (_) {
      return false;
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
        final lastKnown = await Geolocator.getLastKnownPosition();
        if (_isFresh(lastKnown)) {
          return lastKnown;
        }
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  static Future<LocationSnapshot> getCurrentLocationForSubmission() async {
    try {
      await _ensurePermission();
      await _requestPreciseLocationIfNeeded();
      final current = await _getCurrentPositionResilient();
      _validateSubmissionPosition(current);
      return LocationSnapshot(
        latitude: current.latitude,
        longitude: current.longitude,
        source: 'current',
      );
    } catch (error) {
      throw Exception(_humanLocationError(error));
    }
  }

  static Future<Position> _getCurrentPositionResilient() async {
    try {
      return await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.best,
        timeLimit: const Duration(seconds: 20),
      );
    } catch (firstError) {
      try {
        return await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.high,
          timeLimit: const Duration(seconds: 25),
        );
      } catch (secondError) {
        try {
          return await _getCurrentPositionFromStream();
        } catch (streamError) {
          throw Exception(
            'gps_falhou current=$firstError retry=$secondError stream=$streamError',
          );
        }
      }
    }
  }

  static Future<Position> _getCurrentPositionFromStream() async {
    const settings = LocationSettings(
      accuracy: LocationAccuracy.best,
      distanceFilter: 0,
      timeLimit: Duration(seconds: 35),
    );

    return Geolocator.getPositionStream(locationSettings: settings)
        .where((position) => position.latitude != 0 || position.longitude != 0)
        .first
        .timeout(const Duration(seconds: 38));
  }

  static Future<void> _requestPreciseLocationIfNeeded() async {
    try {
      final status = await Geolocator.getLocationAccuracy();
      if (status == LocationAccuracyStatus.reduced) {
        await Geolocator.requestTemporaryFullAccuracy(
          purposeKey: 'RegistrarSintomaAtual',
        );
      }
    } catch (_) {
      // Android and older iOS versions may not support the temporary prompt.
    }
  }

  static void _validateSubmissionPosition(Position position) {
    final timestamp = position.timestamp;
    final age = DateTime.now().difference(timestamp).abs();
    if (age > _maxSubmissionAge) {
      throw Exception('gps_antigo_${age.inSeconds}s');
    }

    if (position.accuracy > _maxSubmissionAccuracyMeters) {
      throw Exception('gps_impreciso_${position.accuracy.round()}m');
    }
  }

  static String _humanLocationError(Object error) {
    final raw = error.toString();

    if (raw.contains('gps_antigo')) {
      return 'O iPhone retornou uma localizacao antiga. Abra o app Mapas por alguns segundos, volte ao SolusCRT e toque em Enviar novamente.';
    }
    if (raw.contains('gps_impreciso')) {
      final meters = RegExp(r'gps_impreciso_(\d+)m').firstMatch(raw)?.group(1);
      return 'O GPS atual esta impreciso${meters == null ? '' : ' (${meters}m)'}. Ative Localizacao Precisa e tente em area aberta ou perto de uma janela.';
    }
    if (raw.contains('deniedForever')) {
      return 'A permissao de localizacao esta bloqueada. Abra Ajustes > SolusCRT Saude > Localizacao e marque Durante o Uso com Localizacao Precisa.';
    }
    if (raw.contains('denied')) {
      return 'Permissao de localizacao negada. Autorize o SolusCRT Saude a usar localizacao Durante o Uso.';
    }
    if (raw.contains('Location services are disabled') ||
        raw.contains('Ative a localizacao')) {
      return 'O servico de localizacao do iPhone esta desligado. Ative Localizacao nos Ajustes do aparelho.';
    }
    if (raw.contains('TimeoutException') || raw.contains('timeout')) {
      return 'O iPhone nao entregou uma posicao GPS dentro do tempo limite. No simulador, escolha uma localizacao em Debug > Simulate Location. No iPhone real, abra o app Mapas por alguns segundos e tente novamente. Detalhe tecnico: $raw';
    }
    if (raw.contains('gps_falhou')) {
      return 'O iPhone nao retornou localizacao atual pelo metodo direto nem pelo monitoramento em tempo real. No simulador, configure Debug > Simulate Location. No iPhone real, confirme Ajustes > Privacidade e Seguranca > Servicos de Localizacao ligado. Detalhe tecnico: $raw';
    }

    return 'Nao foi possivel confirmar seu GPS atual agora. O envio foi bloqueado para nao registrar seu sintoma na cidade errada. Detalhe tecnico: $raw';
  }

  static bool _isFresh(Position? position) {
    final timestamp = position?.timestamp;
    if (timestamp == null) {
      return false;
    }
    return DateTime.now().difference(timestamp).abs() <= _maxLastKnownAge;
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

  static Future<bool> abrirAjustesLocalizacao() async {
    try {
      final abriuApp = await Geolocator.openAppSettings();
      if (abriuApp) {
        return abriuApp;
      }
      return Geolocator.openLocationSettings();
    } catch (_) {
      return false;
    }
  }
}
