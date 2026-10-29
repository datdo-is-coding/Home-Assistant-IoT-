import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/widgets/quick_control_sheet.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/repositories/smart_home_repository.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  test('Each channel shows amps with relay off; zero is valid, stale/invalid is missing', () async {
    final client = GatewayClient(persistSession: false)..connected = true;
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    Map<String, dynamic> meter(num current, {bool valid = true, double? at}) => {
      'current_ma': current, 'voltage_v': 230, 'power_w': 0,
      'valid': valid, 'received_at': at ?? now,
    };
    client.nodes = {'AB_test': {'status': 'online', 'relay_state': [0, 0, 0],
      'pzem': {'current': 99, 'power': 999},
      'channels': {
        'ch1': {'name': 'Đèn cửa', 'telemetry': meter(1234)},
        'ch2': {'telemetry': meter(0)},
        'ch3': {'telemetry': meter(500, valid: false)},
      }}};
    final repo = GatewaySmartHomeRepository(client);
    addTearDown(() { repo.dispose(); client.dispose(); });
    var devices = await repo.getDevices();
    expect(devices[0].isOn, false);
    expect(devices[0].metadata['current'], 1.234);
    expect(devices[1].metadata['current'], 0);
    expect(devices[1].powerWatts, 0);
    expect(devices[2].metadata['current'], isNull);
    expect(devices[2].powerWatts, isNull);
    repo.applyEvent('node_telemetry', {'node_id': 'AB_test', 'channels': {
      'ch1': meter(0, valid: false), 'ch2': meter(2500), 'ch3': meter(1000, at: now - 30),
    }});
    devices = await repo.getDevices();
    expect(devices[0].metadata['current'], isNull);
    expect(devices[0].powerWatts, isNull);
    expect(devices[0].name, 'Đèn cửa');
    expect(devices[1].metadata['current'], 2.5);
    expect(devices[2].metadata['current'], isNull);
    client.connected = false;
    repo.applySnapshot(client.nodes);
    expect((await repo.getDevices())[1].metadata['current'], isNull);
  });
  testWidgets('Open quick control updates current and expires missing samples without changing relay', (tester) async {
    final client = GatewayClient(persistSession: false)..connected = true;
    Map<String, dynamic> meter(int value) => {'valid': true, 'current_ma': value,
      'power_w': null, 'voltage_v': null, 'received_at': DateTime.now().millisecondsSinceEpoch / 1000};
    client.nodes = {'AB_test': {'status': 'online', 'relay_state': [0, 0, 0], 'channels': {
      'ch1': {'name': 'Đèn trần', 'telemetry': meter(1234)}, 'ch2': {}, 'ch3': {}}}};
    final repo = GatewaySmartHomeRepository(client);
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => client), smartHomeRepositoryProvider.overrideWithValue(repo),
    ], child: MaterialApp(home: Scaffold(body: QuickControlSheet(
      device: repo.deviceMap['AB_test::ch1']!, onToggle: (_) {}, onValueChanged: (_) {},
    )))));
    await tester.pump();
    expect(find.text('Dòng điện: 1.234 A'), findsOneWidget);
    repo.applyEvent('node_telemetry', {'node_id': 'AB_test', 'channels': {'ch1': meter(2500)}});
    await tester.pump();
    await tester.pump();
    expect(find.text('Dòng điện: 2.500 A'), findsOneWidget);
    client.nodes['AB_test']['channels']['ch1']['telemetry']['received_at'] = DateTime.now().millisecondsSinceEpoch / 1000 - 30;
    await tester.pump(const Duration(seconds: 6));
    await tester.pump();
    expect(find.text('Dòng điện: chưa có mẫu'), findsOneWidget);
    expect(repo.deviceMap['AB_test::ch1']!.isOn, false);
    await tester.pumpWidget(const SizedBox());
    repo.dispose(); client.dispose();
  });

}
