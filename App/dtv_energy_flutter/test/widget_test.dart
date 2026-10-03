import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dtv_energy_flutter/main.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';

void main() {
  setUpAll(() async {
    final configFile = File('.dart_tool/package_config.json');
    final packages =
        jsonDecode(await configFile.readAsString())['packages'] as List;
    final flutter = packages.firstWhere((p) => p['name'] == 'flutter');
    final root = Directory.fromUri(
            configFile.absolute.uri.resolve(flutter['rootUri'] as String))
        .uri;
    final fonts = root.resolve('../../bin/cache/artifacts/material_fonts/');
    final loader = FontLoader('Roboto');
    for (final name in ['Roboto-Regular.ttf', 'Roboto-Bold.ttf']) {
      loader.addFont(File.fromUri(fonts.resolve(name))
          .readAsBytes()
          .then(ByteData.sublistView));
    }
    await loader.load();
    final icons = FontLoader('MaterialIcons');
    icons.addFont(File.fromUri(fonts.resolve('MaterialIcons-Regular.otf'))
        .readAsBytes()
        .then(ByteData.sublistView));
    await icons.load();
  });
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    appTheme.value = ThemeMode.light;
  });

  testWidgets('connection form is usable on a small phone', (tester) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const DTVEnergyApp());
    expect(find.text('Ngôi nhà của bạn'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Kết nối'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Kết nối'));
    await tester.pump();
    expect(find.text('Nhập địa chỉ Gateway'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'home, device, energy and settings remain usable at phone/tablet sizes',
      (tester) async {
    final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path.endsWith('/telemetry'))
            return http.Response(
                '{"telemetry":[{"power":52.8,"recorded_at":"2026-10-02T03:30:00Z"},{"power":42.0,"recorded_at":"2026-10-02T03:29:00Z"}]}',
                200);
          if (req.url.path == '/api/auth/me')
            return http.Response(
                jsonEncode({
                  'authenticated': true,
                  'user': {'id': 1, 'fullname': 'Tuấn', 'role': 'admin'}
                }),
                200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          return http.Response(
              jsonEncode({
                'nodes': {
                  'AB1': {
                    'name': 'ActionBox phòng khách',
                    'room': 'livingroom',
                    'status': 'online',
                    'relay_state': [1, 0],
                    'channels': {
                      'ch2': {'name': 'Quạt trần', 'device_type': 'fan'},
                      'ch1': {'name': 'Đèn phòng khách', 'device_type': 'light'}
                    },
                    'last_telemetry': {
                      'voltage': 220.5,
                      'current': .24,
                      'power': 52.8,
                      'energy': 1.24
                    }
                  },
                  'AB2': {
                    'name': 'ActionBox phòng ngủ',
                    'room': 'bedroom',
                    'status': 'offline',
                    'relay_state': [0, 1],
                    'channels': {
                      'ch1': {'name': 'Đèn đầu giường', 'device_type': 'light'},
                      'ch2': {'name': 'Quạt phòng ngủ', 'device_type': 'fan'}
                    }
                  },
                },
                'pending': {}
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'});
        }));
    await client.loginWithKey(url: 'http://test:8000', key: 'test');
    addTearDown(client.dispose);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.devicePixelRatio = 1;
    for (final size in [
      const Size(390, 844),
      const Size(360, 800),
      const Size(800, 1000)
    ]) {
      tester.view.physicalSize = size;
      await tester.pumpWidget(DTVEnergyApp(client: client));
      await tester.pump(const Duration(milliseconds: 400));
      for (final label in ['Nhà', 'Thiết bị', 'Điện năng', 'Cài đặt']) {
        await tester.tap(find.descendant(
            of: find.byType(NavigationBar), matching: find.text(label)));
        await tester.pump(const Duration(milliseconds: 400));
        expect(tester.takeException(), isNull, reason: '$size / $label');
        if (size.width == 390) {
          client.updatedAt = DateTime(2026, 10, 2, 10, 30);
          client.notifyListeners();
          await tester.pump();
          final name = {
            'Nhà': 'home',
            'Thiết bị': 'devices',
            'Điện năng': 'energy',
            'Cài đặt': 'settings'
          }[label];
          await expectLater(find.byType(Scaffold).first,
              matchesGoldenFile('goldens/$name.png'));
        }
      }
    }
    tester.view.physicalSize = const Size(360, 800);
    tester.platformDispatcher.textScaleFactorTestValue = 1.5;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    for (final label in ['Nhà', 'Thiết bị', 'Điện năng', 'Cài đặt']) {
      await tester.tap(find.descendant(
          of: find.byType(NavigationBar), matching: find.text(label)));
      await tester.pump(const Duration(milliseconds: 400));
      expect(tester.takeException(), isNull, reason: 'Large text / $label');
    }
    tester.platformDispatcher.clearTextScaleFactorTestValue();
    await tester.tap(find.descendant(
        of: find.byType(NavigationBar), matching: find.text('Thiết bị')));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('ActionBox phòng khách'));
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Số đo gần nhất'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pageBack();
    await tester.pump(const Duration(milliseconds: 400));
    tester.view.physicalSize = const Size(390, 844);
    appTheme.value = ThemeMode.dark;
    await tester.pump();
    await tester.tap(find.descendant(
        of: find.byType(NavigationBar), matching: find.text('Nhà')));
    await tester.pump(const Duration(milliseconds: 400));
    client.updatedAt = DateTime(2026, 10, 2, 10, 30);
    client.notifyListeners();
    await tester.pump();
    await expectLater(find.byType(Scaffold).first,
        matchesGoldenFile('goldens/home-dark.png'));
    client.connected = false;
    client.error = 'Không kết nối được Gateway. Kiểm tra mạng và địa chỉ.';
    client.notifyListeners();
    await tester.pump();
    for (final toggle in tester.widgetList<Switch>(find.byType(Switch))) {
      expect(toggle.onChanged, isNull);
    }
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
