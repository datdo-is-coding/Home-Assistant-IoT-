import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// Default [FirebaseOptions] for use with Firebase.initializeApp.
class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      case TargetPlatform.windows:
        throw UnsupportedError('Firebase chưa hỗ trợ Windows trong bản này.');
      case TargetPlatform.linux:
        throw UnsupportedError('Firebase chưa hỗ trợ Linux trong bản này.');
      default:
        return android;
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyAhH7Hf3tPkZ_19MXZ4q1ohB_3h_5AYs6Q',
    appId: '1:369954212466:web:fff6de666b3c77d46290eb',
    messagingSenderId: '369954212466',
    projectId: 'home-companion-fed2e',
    authDomain: 'home-companion-fed2e.firebaseapp.com',
    storageBucket: 'home-companion-fed2e.firebasestorage.app',
    databaseURL: 'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyAhH7Hf3tPkZ_19MXZ4q1ohB_3h_5AYs6Q',
    appId: '1:369954212466:android:fff6de666b3c77d46290eb',
    messagingSenderId: '369954212466',
    projectId: 'home-companion-fed2e',
    storageBucket: 'home-companion-fed2e.firebasestorage.app',
    databaseURL: 'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyAhH7Hf3tPkZ_19MXZ4q1ohB_3h_5AYs6Q',
    appId: '1:369954212466:ios:fff6de666b3c77d46290eb',
    messagingSenderId: '369954212466',
    projectId: 'home-companion-fed2e',
    storageBucket: 'home-companion-fed2e.firebasestorage.app',
    iosBundleId: 'com.dtv.homeassistant.dtvHomeAssistant',
    databaseURL: 'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app',
  );

  static const FirebaseOptions macos = FirebaseOptions(
    apiKey: 'AIzaSyAhH7Hf3tPkZ_19MXZ4q1ohB_3h_5AYs6Q',
    appId: '1:369954212466:ios:fff6de666b3c77d46290eb',
    messagingSenderId: '369954212466',
    projectId: 'home-companion-fed2e',
    storageBucket: 'home-companion-fed2e.firebasestorage.app',
    iosBundleId: 'com.dtv.homeassistant.dtvHomeAssistant',
    databaseURL: 'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app',
  );
}
