import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/repositories/smart_home_repository.dart';
import 'package:home_competition/providers/smart_home_providers.dart';

Map<String, dynamic> _createMockNodes() {
  return {
    'node_1': {
      'name': 'ActionBox Phòng khách',
      'room': 'living_room',
      'status': 'online',
      'relay_state': [0, 0],
      'channels': {
        'ch1': {'name': 'Đèn trần', 'device_type': 'light', 'aliases': ['đèn phòng khách']},
        'ch2': {'name': 'Quạt trần', 'device_type': 'fan', 'aliases': ['quạt phòng khách']},
      },
      'pzem': {'power': 45.0, 'voltage': 220.0, 'current': 0.2, 'energy': 1.5},
    },
    'node_2': {
      'name': 'ActionBox Phòng ngủ',
      'room': 'bedroom',
      'status': 'online',
      'relay_state': [0, 0],
      'channels': {
        'ch1': {'name': 'Đèn ngủ', 'device_type': 'light', 'aliases': ['đèn phòng ngủ']},
        'ch2': {'name': 'Quạt ngủ', 'device_type': 'fan', 'aliases': ['quạt phòng ngủ']},
      },
      'pzem': {'power': 10.0, 'voltage': 220.0, 'current': 0.05, 'energy': 0.5},
    },
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('M3 Task T12: Snapshot Diffing & Immutable Object Reuse Tests', () {
    test('Test F2: Two consecutive refreshes with identical snapshot emit 0 data events on all 6 streams', () async {
      final mockNodes = _createMockNodes();
      final mockClient = MockClient((req) async {
        if (req.url.path == '/api/nodes') {
          return http.Response(
            jsonEncode({'nodes': mockNodes, 'pending': {}}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 200, headers: {'content-type': 'application/json'});
      });

      final client = GatewayClient(client: mockClient, persistSession: false);
      client.serverUrl = 'http://gateway.local:8000';
      client.connected = true;
      client.nodes = Map<String, dynamic>.from(mockNodes);

      final repo = GatewaySmartHomeRepository(client);

      // Drain initial microtask emissions
      await Future<void>.delayed(const Duration(milliseconds: 50));

      int devEmissions = 0;
      int roomEmissions = 0;
      int abEmissions = 0;
      int voiceEmissions = 0;
      int sceneEmissions = 0;
      int autoEmissions = 0;

      final s1 = repo.watchDevices().listen((_) => devEmissions++);
      final s2 = repo.watchRooms().listen((_) => roomEmissions++);
      final s3 = repo.watchActionBoxes().listen((_) => abEmissions++);
      final s4 = repo.watchVocabulary().listen((_) => voiceEmissions++);
      final s5 = repo.watchScenes().listen((_) => sceneEmissions++);
      final s6 = repo.watchAutomations().listen((_) => autoEmissions++);

      // Drain subscription microtasks
      await Future<void>.delayed(const Duration(milliseconds: 50));

      // Reset counters after initial subscription
      devEmissions = 0;
      roomEmissions = 0;
      abEmissions = 0;
      voiceEmissions = 0;
      sceneEmissions = 0;
      autoEmissions = 0;

      // First refresh with identical snapshot
      await client.refresh();
      await Future<void>.delayed(const Duration(milliseconds: 30));

      // Second refresh with identical snapshot
      await client.refresh();
      await Future<void>.delayed(const Duration(milliseconds: 30));

      expect(devEmissions, 0, reason: 'Devices stream must emit 0 events on identical refresh');
      expect(roomEmissions, 0, reason: 'Rooms stream must emit 0 events on identical refresh');
      expect(abEmissions, 0, reason: 'ActionBoxes stream must emit 0 events on identical refresh');
      expect(voiceEmissions, 0, reason: 'Vocabulary stream must emit 0 events on identical refresh');
      expect(sceneEmissions, 0, reason: 'Scenes stream must emit 0 events on identical refresh');
      expect(autoEmissions, 0, reason: 'Automations stream must emit 0 events on identical refresh');

      await s1.cancel();
      await s2.cancel();
      await s3.cancel();
      await s4.cancel();
      await s5.cancel();
      await s6.cancel();
      repo.dispose();
      client.dispose();
    });

    test('Test Single Channel Toggle: toggling ch1 of node1 creates exactly 1 new Device instance; all other devices keep 100% identical reference', () async {
      final mockNodes = _createMockNodes();
      final client = GatewayClient(persistSession: false);
      client.serverUrl = 'http://gateway.local:8000';
      client.connected = true;
      client.nodes = Map<String, dynamic>.from(mockNodes);

      final repo = GatewaySmartHomeRepository(client);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      final oldDev1_1 = repo.deviceMap['node_1::ch1'];
      final oldDev1_2 = repo.deviceMap['node_1::ch2'];
      final oldDev2_1 = repo.deviceMap['node_2::ch1'];
      final oldDev2_2 = repo.deviceMap['node_2::ch2'];

      expect(oldDev1_1, isNotNull);
      expect(oldDev1_2, isNotNull);
      expect(oldDev2_1, isNotNull);
      expect(oldDev2_2, isNotNull);
      expect(oldDev1_1!.isOn, false);

      // Apply relay toggle on node_1::ch1
      final res = repo.applyEvent('relay_state', {
        'node_id': 'node_1',
        'relay_state': [1, 0],
      });

      expect(res.devicesChanged, true);

      final newDev1_1 = repo.deviceMap['node_1::ch1'];
      final newDev1_2 = repo.deviceMap['node_1::ch2'];
      final newDev2_1 = repo.deviceMap['node_2::ch1'];
      final newDev2_2 = repo.deviceMap['node_2::ch2'];

      expect(newDev1_1!.isOn, true);
      expect(identical(newDev1_1, oldDev1_1), false, reason: 'Toggled device must be updated instance');

      // Crucial: ALL OTHER DEVICES MUST RETAIN 100% OBJECT IDENTITY!
      expect(identical(newDev1_2, oldDev1_2), true, reason: 'Untouched channel on same node must keep identical reference');
      expect(identical(newDev2_1, oldDev2_1), true, reason: 'Devices on other nodes must keep identical reference');
      expect(identical(newDev2_2, oldDev2_2), true, reason: 'Devices on other nodes must keep identical reference');

      repo.dispose();
      client.dispose();
    });

    test('Test Loading/Error isolation: changing gateway.loading or gateway.error emits 0 data events and re-instantiates 0 devices', () async {
      final mockNodes = _createMockNodes();
      final client = GatewayClient(persistSession: false);
      client.serverUrl = 'http://gateway.local:8000';
      client.connected = true;
      client.nodes = Map<String, dynamic>.from(mockNodes);

      final repo = GatewaySmartHomeRepository(client);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      final initialDev1 = repo.deviceMap['node_1::ch1'];
      final initialDev2 = repo.deviceMap['node_2::ch1'];

      int emissions = 0;
      final sub = repo.watchDevices().listen((_) => emissions++);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      emissions = 0;

      // Change loading
      client.loading = true;
      client.notifyListeners();
      await Future<void>.delayed(const Duration(milliseconds: 20));

      client.loading = false;
      client.notifyListeners();
      await Future<void>.delayed(const Duration(milliseconds: 20));

      // Change error
      client.error = 'Temporary gateway warning';
      client.notifyListeners();
      await Future<void>.delayed(const Duration(milliseconds: 20));

      client.error = null;
      client.notifyListeners();
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(emissions, 0, reason: 'Data streams must not emit when only loading/error status changes');
      expect(identical(repo.deviceMap['node_1::ch1'], initialDev1), true);
      expect(identical(repo.deviceMap['node_2::ch1'], initialDev2), true);

      await sub.cancel();
      repo.dispose();
      client.dispose();
    });

    test('Test Filtered IDs stability: returns identical List<String> instance when IDs did not change', () {
      final container = ProviderContainer(overrides: [
        smartHomeRepositoryProvider.overrideWith((ref) => InMemorySmartHomeRepository()),
      ]);
      addTearDown(container.dispose);

      final ids1 = container.read(filteredDeviceIdsProvider);
      final ids2 = container.read(filteredDeviceIdsProvider);

      expect(identical(ids1, ids2), true, reason: 'Cached filtered IDs list instance must be preserved');
    });

    test('Test Automations stream is not re-emitted during syncFromGateway', () async {
      final mockNodes = _createMockNodes();
      final client = GatewayClient(persistSession: false);
      client.serverUrl = 'http://gateway.local:8000';
      client.connected = true;
      client.nodes = Map<String, dynamic>.from(mockNodes);

      final repo = GatewaySmartHomeRepository(client);
      await Future<void>.delayed(const Duration(milliseconds: 30));

      int autoEmissions = 0;
      final sub = repo.watchAutomations().listen((_) => autoEmissions++);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      autoEmissions = 0;

      // Perform sync
      repo.applySnapshot(client.nodes);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(autoEmissions, 0, reason: 'Automations must not emit on syncFromGateway');
      await sub.cancel();
      repo.dispose();
      client.dispose();
    });
  });

  group('M3 Task T12: Widget Rebuild Isolation Test', () {
    testWidgets('Card Rebuild Isolation: Widget observing Device A does NOT rebuild when Device B toggles or receives telemetry', (WidgetTester tester) async {
      final mockNodes = _createMockNodes();
      final client = GatewayClient(persistSession: false);
      client.serverUrl = 'http://gateway.local:8000';
      client.connected = true;
      client.nodes = Map<String, dynamic>.from(mockNodes);

      final repo = GatewaySmartHomeRepository(client);

      int cardABuildCount = 0;
      int cardBBuildCount = 0;

      final container = ProviderContainer(overrides: [
        gatewayClientProvider.overrideWith((ref) => client),
        smartHomeRepositoryProvider.overrideWithValue(repo),
      ]);
      addTearDown(container.dispose);
      addTearDown(repo.dispose);
      addTearDown(client.dispose);

      final testWidget = UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                Consumer(
                  builder: (context, ref, _) {
                    cardABuildCount++;
                    final devA = ref.watch(deviceProvider('node_1::ch1'));
                    return Text('CardA: ${devA?.name} - ${devA?.isOn} - ${devA?.powerWatts}');
                  },
                ),
                Consumer(
                  builder: (context, ref, _) {
                    cardBBuildCount++;
                    final devB = ref.watch(deviceProvider('node_1::ch2'));
                    return Text('CardB: ${devB?.name} - ${devB?.isOn} - ${devB?.powerWatts}');
                  },
                ),
              ],
            ),
          ),
        ),
      );

      await tester.pumpWidget(testWidget);
      await tester.pump(const Duration(milliseconds: 50));

      expect(cardABuildCount, 1);
      expect(cardBBuildCount, 1);
      expect(find.text('CardA: Đèn trần - false - 45.0'), findsOneWidget);
      expect(find.text('CardB: Quạt trần - false - null'), findsOneWidget);

      // Now toggle Device B (node_1::ch2) ONLY!
      repo.applyEvent('relay_state', {
        'node_id': 'node_1',
        'channel': 'ch2',
        'state': 1,
      });

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 20));

      expect(find.text('CardB: Quạt trần - true - null'), findsOneWidget);
      expect(cardBBuildCount, 2, reason: 'Card B must rebuild when Device B toggles');
      expect(cardABuildCount, 1, reason: 'Card A MUST NOT rebuild when Device B toggles!');

      // Now send telemetry for Device B (node_1::ch2) ONLY!
      repo.applyEvent('node_telemetry', {
        'node_id': 'node_1',
        'channel': 'ch2',
        'power': 65.5,
      });

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 20));

      expect(find.text('CardB: Quạt trần - true - 65.5'), findsOneWidget);
      expect(cardBBuildCount, 3, reason: 'Card B must rebuild when Device B receives telemetry');
      expect(cardABuildCount, 1, reason: 'Card A MUST NOT rebuild when Device B receives telemetry!');
    });
  });
}
