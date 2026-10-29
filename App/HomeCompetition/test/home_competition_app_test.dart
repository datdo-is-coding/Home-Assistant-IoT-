import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/services/app_preferences_service.dart';
import 'package:home_competition/features/home/home_screen.dart';
import 'package:home_competition/features/actionbox/add_device_flow.dart';
import 'package:home_competition/app/home_competition_app.dart';
import 'package:home_competition/app/app_router.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/repositories/smart_home_repository.dart';
import 'package:home_competition/widgets/device_card.dart';
import 'package:home_competition/widgets/quick_control_sheet.dart';
import 'package:home_competition/widgets/smart_home_scaffold.dart';
import 'package:home_competition/features/devices/device_detail_screen.dart';

class _FirebaseUiClient extends GatewayClient {
  _FirebaseUiClient({required super.client}) : super(persistSession: false);
  @override
  bool get usesFirebase => true;
  @override
  Future<Map<String, dynamic>> request(String path,
      {Map<String, dynamic>? body, String? method, Duration? timeout}) {
    if (path == '/api/commissioning/context')
      return Future.value({'profile': 'legacy'});
    return super.request(path, body: body, method: method, timeout: timeout);
  }
}

class _CountingPreferences extends AppPreferencesService {
  int homeNameReads = 0;
  @override
  Future<String> loadHomeName(
      {String? gatewayUrl,
      String? userId,
      String defaultValue = 'My Home'}) async {
    homeNameReads++;
    return 'Nhà thử nghiệm';
  }
}

void main() {
  late GatewayClient client;
  setUp(() async {
    appRouter.go('/home');
    client = GatewayClient(
        persistSession: false,
        client: MockClient((request) async {
          if (request.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }));
    await client.loginWithKey(url: 'http://gateway:8000', key: 'test-session');
  });

  testWidgets(
      'scrolling home does not rebuild an unchanged visible device card',
      (tester) async {
    tester.view.physicalSize = const Size(390, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final repo = InMemorySmartHomeRepository();
    addTearDown(repo.dispose);
    addTearDown(client.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => client),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const MaterialApp(home: FeatureHomeScreen())));
    await tester.pumpAndSettle();
    final tracked =
        tester.widget<DeviceCard>(find.byType(DeviceCard).first).device.id;
    var cardBuilds = 0;
    final previous = debugOnRebuildDirtyWidget;
    debugOnRebuildDirtyWidget = (element, builtOnce) {
      if (element.widget case DeviceCard(device: final device)
          when device.id == tracked) cardBuilds++;
      previous?.call(element, builtOnce);
    };
    try {
      await tester.timedDrag(find.byKey(const PageStorageKey('home-scroll')),
          const Offset(0, -60), const Duration(milliseconds: 300));
      await tester.pumpAndSettle();
      expect(cardBuilds, 0);
      expect(
          (tester.widget<SliverGrid>(find.byType(SliverGrid).first).gridDelegate
                  as SliverGridDelegateWithFixedCrossAxisCount)
              .crossAxisCount,
          2);
      tester.view.physicalSize = const Size(800, 1000);
      await tester.pumpAndSettle();
      expect(
          (tester.widget<SliverGrid>(find.byType(SliverGrid).first).gridDelegate
                  as SliverGridDelegateWithFixedCrossAxisCount)
              .crossAxisCount,
          3);
      expect(tester.takeException(), isNull);
    } finally {
      debugOnRebuildDirtyWidget = previous;
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });
  testWidgets('quick controls cover the dock and open settings after closing',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final repo = InMemorySmartHomeRepository();
    addTearDown(repo.dispose);
    addTearDown(client.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => client),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const HomeCompetitionApp()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DeviceCard).first);
    await tester.pumpAndSettle();
    final sheet = find.byType(QuickControlSheet);
    expect(sheet, findsOneWidget);
    expect(
        Navigator.of(tester.element(sheet)),
        Navigator.of(tester.element(find.byType(SmartHomeScaffold)),
            rootNavigator: true));
    await tester
        .tap(find.descendant(of: sheet, matching: find.text('Cài đặt')));
    await tester.pumpAndSettle();
    expect(sheet, findsNothing);
    expect(find.byType(FeatureDeviceDetailScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('floating dock does not duplicate the phone status-bar inset',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    tester.view.padding = const FakeViewPadding(top: 44, bottom: 24);
    tester.view.viewPadding = const FakeViewPadding(top: 44, bottom: 24);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPadding);
    addTearDown(tester.view.resetViewPadding);
    final repo = InMemorySmartHomeRepository();
    addTearDown(repo.dispose);
    addTearDown(client.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => client),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const HomeCompetitionApp()));
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byType(NavigationBar)).height, 72);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
      'SmartHomeApp launches with calm Apple Home-inspired tabs and responds to interactions',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final mockRepo = InMemorySmartHomeRepository();
    addTearDown(mockRepo.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          gatewayClientProvider.overrideWith((ref) => client),
          smartHomeRepositoryProvider.overrideWithValue(mockRepo),
        ],
        child: const HomeCompetitionApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('My Home'), findsOneWidget);
    expect(find.byType(DeviceCard), findsWidgets);

    expect(find.text('Nhà'), findsOneWidget);
    expect(find.text('Thiết bị'), findsOneWidget);
    expect(find.text('Kịch bản'), findsOneWidget);
    expect(find.text('Cài đặt'), findsOneWidget);

    expect(find.text('Tất cả'), findsOneWidget);
    expect(find.text('Phòng khách'), findsWidgets);

    await tester.tap(find.text('Thiết bị'));
    await tester.pumpAndSettle();
    expect(find.text('Thiết bị'), findsNWidgets(2));
    expect(find.text('Tìm thiết bị'), findsOneWidget);

    await tester.tap(find.text('Kịch bản'));
    await tester.pumpAndSettle();
    expect(find.text('Tự động hóa'), findsOneWidget);
    expect(find.text('Ngữ cảnh'), findsOneWidget);
    expect(find.text('Chào buổi sáng'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.settings_outlined));
    await tester.pumpAndSettle();
    expect(find.text('Giao diện'), findsOneWidget);
    expect(find.text('Sáng'), findsOneWidget);
    expect(find.text('Tối'), findsOneWidget);

    await tester.tap(find.text('Tối'));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.home_outlined));
    await tester.pumpAndSettle();
    expect(find.text('My Home'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
      'SmartHomeApp displays truthful empty state when Gateway has 0 devices',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [gatewayClientProvider.overrideWith((ref) => client)],
        child: const HomeCompetitionApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Chưa có thiết bị nào trong khu vực này'), findsOneWidget);
    expect(find.text('Thêm thiết bị'), findsWidgets);
    expect(find.text('Đèn trần phòng khách'), findsNothing);
    expect(find.text('Quạt trần phòng khách'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'Firebase signed-in shell has an Overlay for status tooltip and report navigation',
      (tester) async {
    final cloud = _FirebaseUiClient(
        client: MockClient((request) async => http.Response(
            request.url.path == '/api/auth/me'
                ? '{"authenticated":true,"user":{"id":"cloud-user","role":"user"}}'
                : '{"nodes":{},"pending":{}}',
            200)));
    await cloud.loginWithKey(url: 'https://cloud.example', key: 'test');
    final repo = InMemorySmartHomeRepository();
    addTearDown(cloud.dispose);
    addTearDown(repo.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => cloud),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const HomeCompetitionApp()));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.textContaining('Hệ thống trực tuyến'), findsNothing);
    final name = find.byKey(const ValueKey('home-connection-name'));
    expect(name, findsOneWidget);
    await tester.longPress(name);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(name);
    await tester.pumpAndSettle();
    expect(find.text('Kết nối'), findsOneWidget);
    expect(find.text('Đã kết nối Firebase'), findsWidgets);
    await tester.tap(find.text('Đóng'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Điện năng'));
    await tester.pumpAndSettle();
    expect(find.text('Theo thiết bị'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('energy is a persistent bottom tab and preserves the home filter',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final repo = InMemorySmartHomeRepository();
    addTearDown(repo.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => client),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const HomeCompetitionApp()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Phòng khách').first);
    await tester.pumpAndSettle();
    final homePosition = tester
        .state<ScrollableState>(find
            .descendant(
                of: find.byType(FeatureHomeScreen),
                matching: find.byType(Scrollable))
            .first)
        .position;
    homePosition.jumpTo(homePosition.maxScrollExtent.clamp(0, 120));
    await tester.pump();
    final offset = homePosition.pixels;
    await tester.tap(find.widgetWithText(NavigationDestination, 'Điện năng'));
    await tester.pumpAndSettle();
    expect(find.byType(NavigationDestination), findsNWidgets(5));
    expect(find.text('Theo thiết bị'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsWidgets);
    await tester.tap(find.widgetWithText(NavigationDestination, 'Nhà'));
    await tester.pumpAndSettle();
    expect(homePosition.pixels, offset);
    expect(
        ProviderScope.containerOf(
                tester.element(find.byType(FeatureHomeScreen)))
            .read(selectedRoomIdProvider),
        'living_room');
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
      'Firebase add-device route opens the existing commissioning wizard',
      (tester) async {
    final cloud = _FirebaseUiClient(
        client: MockClient((request) async => http.Response(
            request.url.path == '/api/auth/me'
                ? '{"authenticated":true,"user":{"id":"cloud-user","role":"user"}}'
                : '{"nodes":{},"pending":{}}',
            200)));
    await cloud.loginWithKey(url: 'https://cloud.example', key: 'test');
    addTearDown(cloud.dispose);
    final repo = InMemorySmartHomeRepository();
    addTearDown(repo.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => cloud),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const HomeCompetitionApp()));
    appRouter.go('/actionbox/add-device');
    await tester.pumpAndSettle();
    expect(find.byType(AddDeviceFlowScreen), findsOneWidget);
    expect(find.byKey(const Key('step1_next_button')), findsOneWidget);
    expect(find.textContaining('Chức năng này chưa có dịch vụ'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
      'unchanged cloud status does not rebuild the app shell or reload the home name',
      (tester) async {
    final cloud = _FirebaseUiClient(
        client: MockClient((request) async => http.Response(
            request.url.path == '/api/auth/me'
                ? '{"authenticated":true,"user":{"id":"cloud-user","role":"user"}}'
                : '{"nodes":{},"pending":{}}',
            200)));
    await cloud.loginWithKey(url: 'https://cloud.example', key: 'test');
    final prefs = _CountingPreferences();
    final repo = InMemorySmartHomeRepository();
    addTearDown(cloud.dispose);
    addTearDown(repo.dispose);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => cloud),
      appPreferencesServiceProvider.overrideWithValue(prefs),
      smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: const HomeCompetitionApp()));
    await tester.pumpAndSettle();
    final beforeReads = prefs.homeNameReads;
    var appBuilds = 0;
    final previous = debugOnRebuildDirtyWidget;
    debugOnRebuildDirtyWidget = (element, builtOnce) {
      if (element.widget is HomeCompetitionApp) appBuilds++;
      previous?.call(element, builtOnce);
    };
    try {
      for (var i = 0; i < 10; i++) {
        cloud.updatedAt = DateTime.now();
        cloud.notifyListeners();
        await tester.pump();
      }
      expect(appBuilds, 0);
      expect(prefs.homeNameReads, beforeReads);
    } finally {
      debugOnRebuildDirtyWidget = previous;
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });
}
