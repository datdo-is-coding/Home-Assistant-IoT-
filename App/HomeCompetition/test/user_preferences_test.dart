import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:home_competition/features/devices/device_detail_screen.dart';
import 'package:home_competition/features/settings/settings_screen.dart';
import 'package:home_competition/models/device.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/repositories/smart_home_repository.dart';
import 'package:home_competition/services/app_preferences_service.dart';
import 'package:home_competition/services/gateway_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppPreferencesService & ThemeMode Persistence', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('ThemeMode saves to SharedPreferences and restores across app restart', () async {
      final service = AppPreferencesService();

      // Default when empty is light
      final initialMode = await service.loadThemeMode();
      expect(initialMode, ThemeMode.light);

      // Save dark mode
      await service.saveThemeMode(ThemeMode.dark);

      // Reload from fresh service instance
      final freshService = AppPreferencesService();
      final loadedMode = await freshService.loadThemeMode();
      expect(loadedMode, ThemeMode.dark);

      // Save system mode
      await freshService.saveThemeMode(ThemeMode.system);
      final systemMode = await AppPreferencesService().loadThemeMode();
      expect(systemMode, ThemeMode.system);
    });

    test('ThemeModeNotifier updates state and saves to AppPreferencesService', () async {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      // Initial state
      expect(container.read(themeModeProvider), ThemeMode.light);

      // Mutate state
      container.read(themeModeProvider.notifier).state = ThemeMode.dark;
      expect(container.read(themeModeProvider), ThemeMode.dark);

      // Verify written to storage
      final savedMode = await AppPreferencesService().loadThemeMode();
      expect(savedMode, ThemeMode.dark);

      // Create new container simulating app restart
      final newContainer = ProviderContainer();
      addTearDown(newContainer.dispose);

      // Give microtask queue time to run _loadTheme
      newContainer.read(themeModeProvider);
      await pumpEventQueue();

      expect(newContainer.read(themeModeProvider), ThemeMode.dark);
    });
  });

  group('Session Scope Isolation (Home Name & Favorites)', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('Home name is isolated per (gatewayUrl, userId) session scope', () async {
      final service = AppPreferencesService();

      // Save for Alice on Gateway 1
      await service.saveHomeName(
        'Nhà Phố Sài Gòn',
        gatewayUrl: 'http://gw1.local:8000',
        userId: 'alice',
      );

      // Save for Bob on Gateway 2
      await service.saveHomeName(
        'Căn Hộ Đà Lạt',
        gatewayUrl: 'http://gw2.local:8000',
        userId: 'bob',
      );

      // Load Alice's home name
      final aliceHome = await service.loadHomeName(
        gatewayUrl: 'http://gw1.local:8000',
        userId: 'alice',
      );
      expect(aliceHome, 'Nhà Phố Sài Gòn');

      // Load Bob's home name
      final bobHome = await service.loadHomeName(
        gatewayUrl: 'http://gw2.local:8000',
        userId: 'bob',
      );
      expect(bobHome, 'Căn Hộ Đà Lạt');

      // Unknown scope returns default
      final unknownHome = await service.loadHomeName(
        gatewayUrl: 'http://gw3.local:8000',
        userId: 'charlie',
      );
      expect(unknownHome, 'My Home');
    });

    test('Favorites are saved and isolated per session scope', () async {
      final service = AppPreferencesService();

      await service.saveFavoriteIds(
        {'dev1::ch1', 'dev1::ch2'},
        gatewayUrl: 'http://gw1.local:8000',
        userId: 'alice',
      );

      await service.saveFavoriteIds(
        {'dev9::ch1'},
        gatewayUrl: 'http://gw2.local:8000',
        userId: 'bob',
      );

      final aliceFavs = await service.loadFavoriteIds(
        gatewayUrl: 'http://gw1.local:8000',
        userId: 'alice',
      );
      expect(aliceFavs, {'dev1::ch1', 'dev1::ch2'});

      final bobFavs = await service.loadFavoriteIds(
        gatewayUrl: 'http://gw2.local:8000',
        userId: 'bob',
      );
      expect(bobFavs, {'dev9::ch1'});

      final emptyFavs = await service.loadFavoriteIds(
        gatewayUrl: 'http://gw1.local:8000',
        userId: 'eve',
      );
      expect(emptyFavs, isEmpty);
    });

    test('GatewaySmartHomeRepository loads, toggles, and persists favorites per user', () async {
      final prefsService = AppPreferencesService();
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((request) async {
          if (request.url.path == '/api/auth/me') {
            return http.Response(
              jsonEncode({
                'authenticated': true,
                'user': {'id': 'user_test', 'username': 'test_user', 'role': 'admin'},
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          if (request.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'node1': {
                    'name': 'Living Room Box',
                    'status': 'online',
                    'is_online': true,
                    'room': 'living',
                    'relay_state': [1, 0],
                    'channels': {
                      'ch1': {'name': 'Đèn trần', 'device_type': 'light'},
                      'ch2': {'name': 'Quạt bàn', 'device_type': 'fan'},
                    },
                  }
                },
                'pending': {},
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          if (request.url.path == '/api/events') {
            return http.Response('Not Found', 404);
          }
          return http.Response('{}', 200, headers: {'content-type': 'application/json; charset=utf-8'});
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'key123');
      await client.refresh();

      final repo = GatewaySmartHomeRepository(client, preferencesService: prefsService);
      addTearDown(repo.dispose);

      // Verify devices loaded
      final devices = await repo.getDevices();
      expect(devices.length, 2);
      expect(devices.firstWhere((d) => d.id == 'node1::ch1').isFavorite, false);

      // Toggle favorite on ch1
      await repo.toggleFavorite('node1::ch1');
      final updatedDevices = await repo.getDevices();
      expect(updatedDevices.firstWhere((d) => d.id == 'node1::ch1').isFavorite, true);

      // Check persisted to storage
      final storedFavs = await prefsService.loadFavoriteIds(
        gatewayUrl: client.serverUrl,
        userId: client.currentUserId,
      );
      expect(storedFavs.contains('node1::ch1'), true);

      // Create a second repo instance for the same user, verify favorites are loaded
      final repo2 = GatewaySmartHomeRepository(client, preferencesService: prefsService);
      addTearDown(repo2.dispose);
      await pumpEventQueue();

      final repo2Devices = await repo2.getDevices();
      expect(repo2Devices.firstWhere((d) => d.id == 'node1::ch1').isFavorite, true);
    });
  });

  group('Pure Relay & Power Measurement Truthful UX', () {
    test('Pure relay without can_dim never formats stateText with percent', () {
      const pureRelayLight = Device(
        id: 'box1::ch1',
        name: 'Đèn Tuýp',
        type: DeviceType.light,
        roomId: 'living',
        isOn: true,
        online: true,
        value: 80.0, // internal value should NOT produce % for pure relay
        metadata: {'can_dim': false},
      );

      // When powerWatts is null, it displays "Đang bật" without 0 W or %
      expect(pureRelayLight.stateText, 'Đang bật');
      expect(pureRelayLight.stateText.contains('%'), false);
      expect(pureRelayLight.stateText.contains('0 W'), false);

      // When powerWatts is reported > 0, it displays "Bật · 42.0 W"
      final measuredLight = pureRelayLight.copyWith(powerWatts: 42.0);
      expect(measuredLight.stateText, 'Bật · 42.0 W');
      expect(measuredLight.stateText.contains('%'), false);
    });

    test('Dimmable light with can_dim formats stateText with percent', () {
      const dimmableLight = Device(
        id: 'box1::ch1',
        name: 'Đèn Chùm Dimmer',
        type: DeviceType.light,
        roomId: 'living',
        isOn: true,
        online: true,
        value: 75.0,
        metadata: {'can_dim': true},
      );
      expect(dimmableLight.stateText, 'Bật · 75%');
    });

    test('Pure relay fan without can_speed never shows speed level', () {
      const pureFan = Device(
        id: 'box1::ch2',
        name: 'Quạt Hút',
        type: DeviceType.fan,
        roomId: 'kitchen',
        isOn: true,
        online: true,
        value: 2.0,
        metadata: {'can_speed': false},
      );
      expect(pureFan.stateText, 'Đang bật');
      expect(pureFan.stateText.contains('Cấp'), false);
    });

    test('Pure relay AC without has_thermostat never shows temperature degree', () {
      const pureAc = Device(
        id: 'box1::ch3',
        name: 'Aptomat Điều Hòa',
        type: DeviceType.airConditioner,
        roomId: 'bedroom',
        isOn: true,
        online: true,
        value: 24.0,
        metadata: {'has_thermostat': false},
      );
      expect(pureAc.stateText, 'Đang bật');
      expect(pureAc.stateText.contains('°C'), false);
    });
  });

  group('SettingsScreen Honest UX & Accessibility', () {
    late GatewayClient mockClient;

    setUp(() {
      SharedPreferences.setMockInitialValues({});
      mockClient = GatewayClient(
        client: MockClient((request) async {
          if (request.url.path == '/api/auth/me') {
            return http.Response('{"authenticated":true,"user":{"username":"tuan","role":"admin"}}', 200);
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
    });

    tearDown(() {
      mockClient.dispose();
    });

    testWidgets('SettingsScreen has NO fake push notification toggles and displays honest status card', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            gatewayClientProvider.overrideWith((ref) => mockClient),
          ],
          child: const MaterialApp(
            home: SettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // No fake switches exist
      expect(find.byType(SwitchListTile), findsNothing);
      expect(find.text('Cảnh báo thiết bị mất mạng'), findsNothing);
      expect(find.text('Thông báo cảm biến'), findsNothing);

      await tester.scrollUntilVisible(find.text('Thông báo'), 150,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Thông báo'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Chưa hỗ trợ thông báo đẩy'), findsOneWidget);
      await tester.tap(find.text('Đóng'));
      await tester.pumpAndSettle();
    });

    testWidgets('SettingsScreen allows editing home name and persists changes', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            gatewayClientProvider.overrideWith((ref) => mockClient),
          ],
          child: const MaterialApp(
            home: SettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Default home name displayed
      expect(find.text('My Home'), findsOneWidget);

      // Tap on home name setting tile
      await tester.tap(find.text('Tên ngôi nhà'));
      await tester.pumpAndSettle();

      // Dialog is open
      expect(find.text('Đổi tên ngôi nhà'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);

      // Enter new home name
      await tester.enterText(find.byType(TextField), 'Villa Biển Xanh');
      await tester.pump();

      // Tap "Lưu"
      await tester.tap(find.widgetWithText(FilledButton, 'Lưu'));
      await tester.pumpAndSettle();

      // Verified updated on UI
      expect(find.text('Villa Biển Xanh'), findsOneWidget);

      // Verify saved in AppPreferencesService
      final saved = await AppPreferencesService().loadHomeName(
        gatewayUrl: mockClient.serverUrl,
        userId: mockClient.currentUserId,
      );
      expect(saved, 'Villa Biển Xanh');
    });

    testWidgets('SettingsScreen tiles meet 48dp minimum touch target', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            gatewayClientProvider.overrideWith((ref) => mockClient),
          ],
          child: const MaterialApp(
            home: SettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final listTiles = tester.widgetList<ListTile>(find.byType(ListTile));
      expect(listTiles.isNotEmpty, true);

      // Check all rendered tiles have at least 48dp height
      for (final tileFinder in find.byType(ListTile).evaluate()) {
        final size = tester.getSize(find.byWidget(tileFinder.widget));
        expect(size.height, greaterThanOrEqualTo(48.0));
      }
    });

    testWidgets('SettingsScreen co-giãn tốt ở Text Scale 200% không bị RenderFlex overflow', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(() => tester.platformDispatcher.clearTextScaleFactorTestValue());

      tester.view.physicalSize = const Size(360 * 2.0, 640 * 2.0);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            gatewayClientProvider.overrideWith((ref) => mockClient),
          ],
          child: const MaterialApp(
            home: SettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify no overflow error occurred during render
      expect(tester.takeException(), isNull);
    });
  });

  group('DeviceDetailScreen Truthful UX, 200% Text Scale & Accessibility', () {
    testWidgets('DeviceDetailScreen displays "Dòng điện: chưa có mẫu" and NO slider for pure relay', (tester) async {
      const pureRelay = Device(
        id: 'box01::ch1',
        name: 'Đèn Ban Công',
        type: DeviceType.light,
        roomId: 'balcony',
        isOn: true,
        online: true,
        value: 0.0,
        metadata: {'can_dim': false},
      );

      final client = GatewayClient();
      addTearDown(client.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            devicesStreamProvider.overrideWith((ref) => Stream.value([pureRelay])),
            gatewayClientProvider.overrideWith((ref) => client),
          ],
          child: const MaterialApp(
            home: DeviceDetailScreen(deviceId: 'box01::ch1'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Pure relay must NOT have any slider
      expect(find.byType(Slider), findsNothing);

      // Power measurement is missing/0 -> shows truthful string
      expect(find.text('Dòng điện: chưa có mẫu'), findsOneWidget);

      // Verified 48dp minimum touch target on power button
      final powerButtonSize = tester.getSize(find.widgetWithText(FilledButton, 'Tắt nguồn'));
      expect(powerButtonSize.height, greaterThanOrEqualTo(48.0));
    });

    testWidgets('DeviceDetailScreen handles Text Scale 200% on small phone without RenderFlex overflow', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(() => tester.platformDispatcher.clearTextScaleFactorTestValue());

      tester.view.physicalSize = const Size(360 * 2.0, 640 * 2.0);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      const testDevice = Device(
        id: 'box01::ch1',
        name: 'Đèn Chùm Phòng Khách Rất Dài Và Sang Trọng',
        type: DeviceType.light,
        isOn: true,
        online: true,
        powerWatts: 85.5,
        roomId: 'Phòng khách chính tầng trệt',
        channel: 'ch1',
        voiceAliases: ['đèn phòng khách', 'đèn chùm lớn', 'đèn tiếp khách'],
        metadata: {'can_dim': false, 'mac': '30:ED:A0:BD:69:D4'},
      );

      final client = GatewayClient();
      addTearDown(client.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            devicesStreamProvider.overrideWith((ref) => Stream.value([testDevice])),
            gatewayClientProvider.overrideWith((ref) => client),
          ],
          child: const MaterialApp(
            home: DeviceDetailScreen(deviceId: 'box01::ch1'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Expand advanced tech row to stress-test text scale
      await tester.scrollUntilVisible(find.text('Cấu hình nâng cao (Kỹ thuật)'), 200);
      await tester.tap(find.text('Cấu hình nâng cao (Kỹ thuật)'));
      await tester.pumpAndSettle();

      // Verify no overflow error occurred
      expect(tester.takeException(), isNull);
    });
  });
}
