import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';
import 'package:dtv_energy_flutter/app/smart_home_app.dart';
import 'package:dtv_energy_flutter/providers/smart_home_providers.dart';
import 'package:dtv_energy_flutter/repositories/smart_home_repository.dart';

void main() {
  late GatewayClient client;
  setUp(() async {
    client = GatewayClient(persistSession: false, client: MockClient((request) async {
      if (request.url.path == '/api/auth/me') {
        return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
      }
      return http.Response('{"nodes":{},"pending":{}}', 200);
    }));
    await client.loginWithKey(url: 'http://gateway:8000', key: 'test-session');
  });
  testWidgets('SmartHomeApp launches with calm Apple Home-inspired tabs and responds to interactions', (tester) async {
    tester.view.physicalSize = const Size(390, 844); // iPhone 14 / modern phone
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
        child: const SmartHomeApp(),
      ),
    );

    // Initial pump and settle
    await tester.pumpAndSettle();

    // 1. Verify Home Screen Header
    expect(find.text('My Home'), findsOneWidget);
    expect(find.textContaining('thiết bị'), findsWidgets);

    // 2. Verify Bottom Navigation Destinations
    expect(find.text('Nhà'), findsOneWidget);
    expect(find.text('Thiết bị'), findsOneWidget);
    expect(find.text('Kịch bản'), findsOneWidget);
    expect(find.text('Cài đặt'), findsOneWidget);

    // 3. Verify Room Filter Chips
    expect(find.text('Tất cả'), findsOneWidget);
    expect(find.text('Phòng khách'), findsWidgets);

    // 4. Navigate to Tab 2: Devices Screen
    await tester.tap(find.text('Thiết bị'));
    await tester.pumpAndSettle();
    expect(find.text('Thiết bị trong nhà'), findsOneWidget);
    expect(find.text('Tìm thiết bị, phòng...'), findsOneWidget);

    // 5. Navigate to Tab 3: Automation Screen
    await tester.tap(find.text('Kịch bản'));
    await tester.pumpAndSettle();
    expect(find.text('Tự động hóa'), findsOneWidget);
    expect(find.text('Ngữ cảnh một chạm'), findsOneWidget);
    expect(find.text('Chào buổi sáng'), findsOneWidget);

    // 6. Navigate to Tab 4: Settings Screen
    await tester.tap(find.byIcon(Icons.settings_outlined));
    await tester.pumpAndSettle();
    expect(find.text('Giao diện & Hiển thị'), findsOneWidget);
    expect(find.text('Chế độ màu (Theme)'), findsOneWidget);
    expect(find.text('Sáng'), findsOneWidget);
    expect(find.text('Tối'), findsOneWidget);

    // 7. Switch Theme to Dark Mode
    await tester.tap(find.text('Tối'));
    await tester.pumpAndSettle();

    // 8. Return to Home Screen
    await tester.tap(find.byIcon(Icons.home_outlined));
    await tester.pumpAndSettle();
    expect(find.text('My Home'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('SmartHomeApp displays truthful empty state when Gateway has 0 devices', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [gatewayClientProvider.overrideWith((ref) => client)],
        child: const SmartHomeApp(),
      ),
    );

    await tester.pumpAndSettle();

    // Truthful empty state verifies no mock devices are shown in production flow
    expect(find.text('Chưa có thiết bị nào trong khu vực này'), findsOneWidget);
    expect(find.text('Thêm thiết bị'), findsWidgets);
    expect(find.text('Đèn trần phòng khách'), findsNothing);
    expect(find.text('Quạt trần phòng khách'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
