import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:home_competition/features/core_v1/core_client.dart';
import 'package:home_competition/features/actionbox/connected_add_device.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';

class CoreCloud extends GatewayClient {
  CoreCloud() : super(persistSession: false) {
    serverUrl = 'https://test.firebasedatabase.app';
  }
  @override
  bool get usesFirebase => true;
  @override
  Future<Map<String, dynamic>> request(String path,
          {Map<String, dynamic>? body,
          String? method,
          Duration? timeout}) async =>
      {
        'profile': 'core-v1',
        'snapshot': {
          'home_id': 'home',
          'rooms': [
            {'room_id': 'room', 'home_id': 'home', 'name': 'Phòng ngủ'}
          ],
          'nodes': [
            {
              'node_id': 1,
              'factory_id': 'HC-001122334401',
              'home_id': 'home',
              'room_id': 'room',
              'model': 'HC-S1',
              'product_type': 'SUB_BOX',
              'registration': 'REGISTERED',
              'availability': 'ONLINE'
            }
          ]
        },
        'defaults': {
          'channel': 11,
          'mqtt_uri': 'mqtts://broker',
          'ota_pubkey': '04',
          'parents': {
            '1': {'sta_mac': '001122334401'}
          }
        }
      };
}

void main() {
  test(
      'Core client uses cloud callback and accepts empty RTDB arrays disappearing',
      () async {
    final calls = <String>[];
    final client = CoreClient('https://test.firebasedatabase.app', 'firebase',
        httpClient: MockClient(
            (_) async => throw StateError('Local HTTP must not run')),
        requestTransport: (path, {required method, body, query}) async {
      calls.add(path);
      return {'home_id': 'home'};
    });
    addTearDown(client.dispose);
    await client.connect('home');
    expect(calls, ['/states/snapshot']);
    expect(client.snapshot!.nodes, isEmpty);
    expect(client.connected, isTrue);
  });
  testWidgets(
      'Firebase chooses existing Core secure provisioning for Core firmware',
      (tester) async {
    final cloud = CoreCloud();
    addTearDown(cloud.dispose);
    await tester.pumpWidget(ProviderScope(
        overrides: [gatewayClientProvider.overrideWith((ref) => cloud)],
        child: const MaterialApp(home: ConnectedAddDeviceScreen())));
    await tester.pumpAndSettle();
    expect(find.text('Phòng ngủ'), findsOneWidget);
    await tester.tap(find.text('Đăng ký ActionBox'));
    await tester.pumpAndSettle();
    expect(find.text('Mã thiết bị'), findsOneWidget);
    expect(find.text('Mã thiết lập trên nhãn Box'), findsOneWidget);
    expect(find.textContaining('Chức năng này chưa có'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
