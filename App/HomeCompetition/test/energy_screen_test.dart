import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/features/energy/energy_screen.dart';
import 'package:home_competition/models/device.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';

Device reading(String id,
        {double? power, bool online = true, double? energy}) =>
    Device(
      id: id,
      name: 'Thiết bị $id',
      type: DeviceType.light,
      roomId: 'room',
      online: online,
      powerWatts: power,
      metadata: {'energy': energy, 'current': 0.25},
    );

void main() {
  Future<void> show(WidgetTester tester, List<Device> devices,
      {double scale = 1}) async {
    final client = GatewayClient(persistSession: false)..connected = true;
    addTearDown(client.dispose);
    await tester.pumpWidget(ProviderScope(
        overrides: [
          gatewayClientProvider.overrideWith((ref) => client),
          devicesStreamProvider.overrideWith((ref) => Stream.value(devices)),
        ],
        child: MaterialApp(
            builder: (context, child) => MediaQuery(
                data: MediaQuery.of(context)
                    .copyWith(textScaler: TextScaler.linear(scale)),
                child: child!),
            home: const EnergyScreen())));
    await tester.pumpAndSettle();
  }

  testWidgets(
      'live bars use channel power shares; offline readings are excluded from power',
      (tester) async {
    await show(tester, [
      reading('A', power: 50, energy: 1),
      reading('B', power: 100, energy: 2),
      reading('C', power: 900, online: false, energy: 3)
    ]);
    expect(find.text('150.0 W'), findsOneWidget);
    expect(find.text('2/3 kênh có số đo mới'), findsOneWidget);
    expect(find.text('6.000 kWh'), findsOneWidget);
    expect(find.text('1.000 kWh'), findsOneWidget);
    expect(find.text('3.000 kWh'), findsOneWidget);
    expect(find.text('0.250 A'), findsNWidgets(2));
    final bars = tester
        .widgetList<LinearProgressIndicator>(
            find.byType(LinearProgressIndicator))
        .toList();
    expect(bars, hasLength(2));
    expect(bars[0].value, closeTo(1 / 3, 0.001));
    expect(bars[1].value, closeTo(2 / 3, 0.001));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'empty and unknown measurements stay explicit without invented zero readings',
      (tester) async {
    await show(tester, []);
    expect(find.text('— W'), findsOneWidget);
    expect(find.text('— kWh'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    await show(tester, [reading('A')]);
    expect(find.byType(LinearProgressIndicator), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'zero total remains finite and energy tab fits a narrow phone with large text',
      (tester) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await show(tester, [reading('A', power: 0, energy: 0)], scale: 1.6);
    expect(find.text('0.0 W'), findsWidgets);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    for (final bar in tester.widgetList<LinearProgressIndicator>(
        find.byType(LinearProgressIndicator))) {
      expect(bar.value, 0);
    }
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
