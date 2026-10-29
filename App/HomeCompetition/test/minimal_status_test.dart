import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:home_competition/core/theme/app_theme.dart';
import 'package:home_competition/models/device.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/widgets/connectivity_dot.dart';
import 'package:home_competition/widgets/device_card.dart';
import 'package:home_competition/widgets/home_connection_name.dart';

class _StatusClient extends GatewayClient {
  _StatusClient() : super(persistSession: false);
  @override
  bool get usesFirebase => true;

  void connection(bool value, [String? failure]) {
    connected = value;
    error = failure;
    notifyListeners();
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('house name reports cloud error and recovery without a banner',
      (tester) async {
    final client = _StatusClient()..connection(true);
    addTearDown(client.dispose);
    await tester.pumpWidget(ProviderScope(
      overrides: [gatewayClientProvider.overrideWith((ref) => client)],
      child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: HomeConnectionName())),
    ));
    await tester.pumpAndSettle();
    final name = find.byKey(const ValueKey('home-connection-name'));
    expect(tester.widget<Text>(name).style?.color, AppColors.light.online);
    client.connection(true, 'Không đồng bộ được Firebase.');
    await tester.pump();
    expect(tester.widget<Text>(name).style?.color, AppColors.light.warning);
    await tester.tap(name);
    await tester.pumpAndSettle();
    expect(find.text('Không đồng bộ được Firebase.'), findsOneWidget);
    expect(find.text('Thử lại'), findsOneWidget);
    await tester.tap(find.text('Đóng'));
    await tester.pumpAndSettle();
    client.connection(true);
    await tester.pump();
    expect(tester.widget<Text>(name).style?.color, AppColors.light.online);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  const device = Device(
      id: 'coffee',
      name: 'Máy pha cà phê',
      type: DeviceType.custom,
      roomId: 'Phòng ngủ');

  Future<void> card(WidgetTester tester, Device value,
      {ValueChanged<bool>? toggle,
      VoidCallback? open,
      double scale = 1}) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
          body: MediaQuery(
        data: MediaQueryData(textScaler: TextScaler.linear(scale)),
        child: SizedBox(
            width: 160,
            height: scale > 1 ? 220 : 180,
            child: DeviceCard(
                device: value,
                onTap: open ?? () {},
                onToggle: toggle ?? (_) {},
                onFavoriteToggle: () {})),
      )),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('online dot stays green when an online device is switched off',
      (tester) async {
    final semantics = tester.ensureSemantics();
    for (final on in [true, false]) {
      await card(tester, device.copyWith(isOn: on));
      final dot = find.byType(ConnectivityDot);
      expect(tester.getSemantics(dot).label, contains('Trực tuyến'));
      final indicator = tester.widget<Container>(
          find.descendant(of: dot, matching: find.byType(Container)));
      expect((indicator.decoration as BoxDecoration).color,
          AppColors.light.online);
    }
    await card(tester, device.copyWith(online: false, isOn: true));
    expect(tester.getSemantics(find.byType(ConnectivityDot)).label,
        contains('Ngoại tuyến'));
    expect(tester.widget<Switch>(find.byType(Switch)).onChanged, isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    semantics.dispose();
  });

  testWidgets('minimal tile keeps pending feedback and separate switch action',
      (tester) async {
    final toggles = <bool>[];
    var opened = 0;
    await card(tester, device, toggle: toggles.add, open: () => opened++);
    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(toggles, [true]);
    expect(opened, 0);
    await card(tester,
        device.copyWith(isOn: true, metadata: {'command_pending': true}));
    expect(find.text('Đang bật…'), findsOneWidget);
    expect(find.textContaining('Dòng điện:'), findsNothing);
    await card(tester, device.copyWith(name: 'Máy pha cà phê phòng ngủ'),
        scale: 1.6);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
