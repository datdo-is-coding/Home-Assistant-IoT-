import 'dart:convert';
import 'dart:io';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/firebase_core_platform_interface.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/firebase_options.dart';

class AndroidFirebaseHost extends MockFirebaseApp {
  AndroidFirebaseHost(this.config);
  final Map<String, dynamic> config;

  @override
  Future<List<CoreInitializeResponse>> initializeCore() async {
    final project = config['project_info'] as Map;
    final client = (config['client'] as List).singleWhere((c) =>
        c['client_info']['android_client_info']['package_name'] ==
        'com.dtv.homeassistant.dtv_home_assistant');
    return [
      CoreInitializeResponse(
        name: '[DEFAULT]',
        options: CoreFirebaseOptions(
          apiKey: client['api_key'][0]['current_key'],
          appId: client['client_info']['mobilesdk_app_id'],
          messagingSenderId: project['project_number'],
          projectId: project['project_id'],
          databaseURL: project['firebase_url'],
          storageBucket: project['storage_bucket'],
        ),
        pluginConstants: {},
      )
    ];
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Map<String, dynamic> config;
  setUp(() {
    config =
        jsonDecode(File('android/app/google-services.json').readAsStringSync());
    MethodChannelFirebase.appInstances.clear();
    MethodChannelFirebase.isCoreInitialized = false;
    FirebasePlatform.instance = MethodChannelFirebase();
  });
  tearDown(() => TestFirebaseCoreHostApi.setUp(null));

  test(
      'Android bundled configuration initializes and retries without duplicate-app',
      () async {
    TestFirebaseCoreHostApi.setUp(AndroidFirebaseHost(config));
    final app =
        await Firebase.initializeApp(options: DefaultFirebaseOptions.android);
    expect(app.options.databaseURL, DefaultFirebaseOptions.android.databaseURL);
    final retry =
        await Firebase.initializeApp(options: DefaultFirebaseOptions.android);
    expect(retry.name, app.name);
  });

  test('reproduces old APK failure when native database URL is absent',
      () async {
    (config['project_info'] as Map).remove('firebase_url');
    TestFirebaseCoreHostApi.setUp(AndroidFirebaseHost(config));
    await expectLater(
      Firebase.initializeApp(options: DefaultFirebaseOptions.android),
      throwsA(isA<FirebaseException>()
          .having((e) => e.code, 'code', 'duplicate-app')),
    );
  });
}
