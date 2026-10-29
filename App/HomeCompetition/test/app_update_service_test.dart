import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:home_competition/services/app_update_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/app-updates');
  late Directory directory;
  late List<String> calls;
  late bool unmetered, rejectSignature;
  var downloads = 0, catalogs = 0;
  final bytes = Uint8List(1024);
  Map<String, Object> catalog() => {
        'schema': 1,
        'package': 'com.dtv.homeassistant.dtv_home_assistant',
        'version': '1.7.1',
        'version_code': 44,
        'size': 1024,
        'sha256': 'a' * 64,
        'url':
            'https://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/app-v1.7.1/HomeCompetition.apk',
      };

  setUp(() async {
    directory =
        await Directory.systemTemp.createTemp('homecompetition-update-test-');
    calls = [];
    downloads = 0;
    catalogs = 0;
    unmetered = true;
    rejectSignature = false;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      if (call.method == 'info')
        return {
          'version': '1.7.0',
          'versionCode': 43,
          'directory': directory.path,
          'unmetered': unmetered,
        };
      final args = Map<String, dynamic>.from(call.arguments as Map);
      expect(args['versionCode'], 44);
      expect(args['sha256'], 'a' * 64);
      expect(await File(args['path'] as String).length(), 1024);
      if (rejectSignature)
        throw PlatformException(
            code: 'UPDATE_VERIFY', message: 'Chữ ký gói cập nhật không khớp.');
      if (call.method == 'install') return 'permission_required';
      return null;
    });
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
    await directory.delete(recursive: true);
  });

  AppUpdateService service(
      {Map<String, Object>? data,
      Future<http.Response> Function(http.Request)? response}) {
    final result = AppUpdateService(
        enabled: true,
        channel: channel,
        loadRelease: () async {
          catalogs++;
          return data ?? catalog();
        },
        client: MockClient((request) async {
          downloads++;
          return response == null
              ? http.Response.bytes(bytes, 200)
              : await response(request);
        }));
    addTearDown(result.dispose);
    return result;
  }

  test('rejects unknown sources, malformed metadata and excessive size', () {
    for (final change in <Map<String, Object>>[
      {
        'url':
            'http://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/v/app.apk'
      },
      {'url': 'https://evil.example/app.apk'},
      {'url': 'https://github.com/someone/other/releases/download/v/app.apk'},
      {'url': 'https://user@home-companion-fed2e.web.app/app.apk'},
      {'version_code': 0},
      {'size': 200 * 1024 * 1024},
      {'sha256': 'invalid'},
      {'package': 'another.application'},
    ]) {
      expect(() => AppRelease.parse({...catalog(), ...change}),
          throwsFormatException);
    }
  });
  test('never downloads a downgrade', () async {
    final update = service(data: {...catalog(), 'version_code': 42});
    await update.check();
    expect(update.phase, AppUpdatePhase.current);
    expect(downloads, 0);
    expect(calls, ['info']);
  });
  test('automatically downloads and verifies before offering install',
      () async {
    final update = service();
    await update.install();
    expect(calls, isEmpty);
    await update.check();
    expect(update.phase, AppUpdatePhase.ready);
    expect(update.progress, 1);
    expect(calls, ['info', 'validate']);
    expect(update.canInstall, isTrue);
    await update.install();
    expect(calls.last, 'install');
    expect(update.phase, AppUpdatePhase.permissionRequired);
    update.resume();
    expect(update.phase, AppUpdatePhase.ready);
  });
  test('metered networks require a download tap', () async {
    unmetered = false;
    final update = service();
    await update.check();
    expect(update.phase, AppUpdatePhase.available);
    expect(downloads, 0);
    await update.download();
    expect(update.phase, AppUpdatePhase.ready);
  });
  test('a signature rejection deletes the APK and prevents installation',
      () async {
    rejectSignature = true;
    final update = service();
    await update.check();
    expect(update.phase, AppUpdatePhase.failed);
    expect(update.error, contains('Chữ ký'));
    expect(update.canInstall, isFalse);
    expect(await directory.list().toList(), isEmpty);
    await update.install();
    expect(calls, isNot(contains('install')));
  });
  test('truncated downloads are rejected', () async {
    final update = service(
        response: (_) async => http.Response.bytes(Uint8List(1000), 200));
    await update.check();
    expect(update.phase, AppUpdatePhase.failed);
    expect(update.canInstall, isFalse);
    expect(calls, isNot(contains('validate')));
  });
  test('redirects cannot leave the trusted download hosts', () async {
    final update = service(
        response: (_) async => http.Response('', 302,
            headers: {'location': 'https://evil.example/update.apk'}));
    await update.check();
    expect(downloads, 1);
    expect(update.phase, AppUpdatePhase.failed);
    expect(update.canInstall, isFalse);
  });
  test('cached packages are verified again without being downloaded twice',
      () async {
    final first = service();
    await first.check();
    expect(downloads, 1);
    final next = service();
    await next.check();
    expect(downloads, 1);
    expect(next.phase, AppUpdatePhase.ready);
    expect(calls.where((method) => method == 'validate').length, 2);
  });
  test('resume checks are throttled and a manual check bypasses the limit',
      () async {
    final update = service(data: {...catalog(), 'version_code': 43});
    await update.check();
    await update.check();
    expect(catalogs, 1);
    await update.check(force: true);
    expect(catalogs, 2);
  });
}
