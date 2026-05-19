// Gerado a partir do GoogleService-Info.plist (projeto: soluscrt-apple)
// Android: adicionar google-services.json e atualizar os valores android abaixo.

import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) return web;
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions não configurado para esta plataforma.',
        );
    }
  }

  // Web — preencher se usar versão web futuramente
  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyDYq0OG26fgtINjPb-QI_iQttClCAuL11I',
    appId: '1:214032128491:web:PREENCHER_SE_USAR_WEB',
    messagingSenderId: '214032128491',
    projectId: 'soluscrt-apple',
    storageBucket: 'soluscrt-apple.firebasestorage.app',
  );

  // Android — valores extraídos do google-services.json
  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyAnO4a7n9iXIicReAjmdT3WnNlIsmQ8e6I',
    appId: '1:214032128491:android:0aded80a8528fa4f5761ae',
    messagingSenderId: '214032128491',
    projectId: 'soluscrt-apple',
    storageBucket: 'soluscrt-apple.firebasestorage.app',
  );

  // iOS — valores extraídos do GoogleService-Info.plist
  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyDYq0OG26fgtINjPb-QI_iQttClCAuL11I',
    appId: '1:214032128491:ios:c4b24b5500e8d31e5761ae',
    messagingSenderId: '214032128491',
    projectId: 'soluscrt-apple',
    storageBucket: 'soluscrt-apple.firebasestorage.app',
    iosBundleId: 'br.com.soluscrt.ocupacional',
  );
}
