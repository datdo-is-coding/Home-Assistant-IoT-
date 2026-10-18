import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dtv_energy_flutter/models/device.dart';
import 'package:dtv_energy_flutter/models/automation.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';
import 'package:dtv_energy_flutter/repositories/smart_home_repository.dart';

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
  });

  group('Smart Home Repository & Reactive Propagation Tests', () {
    late InMemorySmartHomeRepository repo;

    setUp(() {
      repo = InMemorySmartHomeRepository();
    });

    tearDown(() {
      repo.dispose();
    });

    test('Initial seeded data loads correctly', () async {
      final devices = await repo.getDevices();
      final rooms = await repo.getRooms();
      final actionBoxes = await repo.getActionBoxes();
      final automations = await repo.getAutomations();
      final scenes = await repo.getScenes();
      final vocab = await repo.getVocabulary();

      expect(devices.isNotEmpty, true);
      expect(rooms.length, 4);
      expect(actionBoxes.length, 2);
      expect(automations.isNotEmpty, true);
      expect(scenes.length, 4);
      expect(vocab.isNotEmpty, true);
    });

    test('Toggling device updates device state and syncs to ActionBox channel', () async {
      final initialDevices = await repo.getDevices();
      final dev = initialDevices.firstWhere((d) => d.id == 'dev_light_living');

      expect(dev.isOn, true);

      await repo.toggleDevice(dev.id, false);

      final updatedDevices = await repo.getDevices();
      final updatedDev = updatedDevices.firstWhere((d) => d.id == 'dev_light_living');
      expect(updatedDev.isOn, false);

      final actionBoxes = await repo.getActionBoxes();
      final ab = actionBoxes.firstWhere((b) => b.id == 'ab_01');
      final ch1 = ab.channels.firstWhere((c) => c.channelKey == 'ch1');
      expect(ch1.isOn, false);
    });

    test('ActionBox channel reconfiguration propagates across entire app (Device, Voice, Rooms)', () async {

      await repo.updateChannel(
        actionBoxId: 'ab_01',
        channelIndex: 0,
        name: 'Quạt làm mát phòng khách',
        type: DeviceType.fan,
        roomId: 'living_room',
        voiceAliases: ['quạt phòng khách', 'quạt trần gió'],
      );

      final actionBoxes = await repo.getActionBoxes();
      final ab = actionBoxes.firstWhere((b) => b.id == 'ab_01');
      final ch1 = ab.channels.first;
      expect(ch1.name, 'Quạt làm mát phòng khách');
      expect(ch1.type, DeviceType.fan);

      final devices = await repo.getDevices();
      final dev = devices.firstWhere((d) => d.actionBoxId == 'ab_01' && d.channel == 'ch1');
      expect(dev.name, 'Quạt làm mát phòng khách');
      expect(dev.type, DeviceType.fan);
      expect(dev.voiceAliases, contains('quạt phòng khách'));

      final vocab = await repo.getVocabulary();
      final vocabItem = vocab.firstWhere((v) => v.deviceId == dev.id);
      expect(vocabItem.deviceName, 'Quạt làm mát phòng khách');
      expect(vocabItem.aliases, contains('quạt phòng khách'));
    });

    test('Adding and removing voice aliases updates vocabulary dynamically', () async {
      const devId = 'dev_light_living';

      await repo.addAlias(devId, 'đèn góc sofa');
      var vocab = await repo.getVocabulary();
      var item = vocab.firstWhere((v) => v.deviceId == devId);
      expect(item.aliases, contains('đèn góc sofa'));

      await repo.removeAlias(devId, 'đèn góc sofa');
      vocab = await repo.getVocabulary();
      item = vocab.firstWhere((v) => v.deviceId == devId);
      expect(item.aliases.contains('đèn góc sofa'), false);
    });

    test('Automations and Scenes activation triggers device actions', () async {
      final automations = await repo.getAutomations();
      final auto = automations.first;

      await repo.toggleAutomation(auto.id, false);
      final updatedAutos = await repo.getAutomations();
      expect(updatedAutos.firstWhere((a) => a.id == auto.id).enabled, false);

      await repo.activateScene('scene_morning');
      final devices = await repo.getDevices();
      final livingLight = devices.firstWhere((d) => d.id == 'dev_light_living');
      expect(livingLight.isOn, true);
    });
  });

  group('GatewaySmartHomeRepository 3-Relay, Power & Scene Tests', () {
    test('Correctly parses 3-relay ActionBox and allocates board power only to primary channel', () async {
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB_3CH': {
                    'name': 'ActionBox Phòng Khách',
                    'status': 'online',
                    'room': 'phong_khach',
                    'capabilities': ['relay_3ch'],
                    'relay_state': [1, 0, 1],
                    'pzem': {'power': 120.0, 'voltage': 220.0, 'current': 0.55},
                    'channels': {
                      'ch1': {'name': 'Đèn trần', 'device_type': 'light'},
                      'ch2': {'name': 'Quạt trần', 'device_type': 'fan'},
                      'ch3': {'name': 'Ổ cắm phụ', 'device_type': 'socket'},
                    }
                  }
                },
                'pending': {},
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
      await client.refresh();
      final repo = GatewaySmartHomeRepository(client);
      addTearDown(repo.dispose);

      final devices = await repo.getDevices();
      expect(devices.length, 3);

      final ch1 = devices.firstWhere((d) => d.id == 'AB_3CH::ch1');
      final ch2 = devices.firstWhere((d) => d.id == 'AB_3CH::ch2');
      final ch3 = devices.firstWhere((d) => d.id == 'AB_3CH::ch3');

      expect(ch1.isOn, true);
      expect(ch2.isOn, false);
      expect(ch3.isOn, true);

      // Power allocation: board power (120W) is assigned only to ch1 (primary), avoiding R14 triple counting
      expect(ch1.value, 120.0);
      expect(ch1.metadata['power'], 120.0);
      expect(ch2.value, 0.0);
      expect(ch2.metadata['power'], 0.0);
      expect(ch3.value, 0.0);
      expect(ch3.metadata['power'], 0.0);

      // Total device value in room is 120W, not 360W
      final totalPower = devices.fold<double>(0.0, (sum, d) => sum + d.value);
      expect(totalPower, 120.0);

      final actionBoxes = await repo.getActionBoxes();
      expect(actionBoxes.length, 1);
      expect(actionBoxes.first.channels.length, 3);
      expect(actionBoxes.first.channels[2].channelKey, 'ch3');
      expect(actionBoxes.first.channels[2].isOn, true);
    });

    test('Assigns individual channel powers when reported separately', () async {
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB_INDIV': {
                    'name': 'ActionBox BL0942',
                    'status': 'online',
                    'room': 'phong_khach',
                    'relay_state': [1, 1],
                    'pzem': {'power': 150.0},
                    'channels': {
                      'ch1': {'name': 'Kênh 1', 'power': 45.0},
                      'ch2': {'name': 'Kênh 2', 'power': 105.0},
                    }
                  }
                },
                'pending': {},
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
      await client.refresh();
      final repo = GatewaySmartHomeRepository(client);
      addTearDown(repo.dispose);

      final devices = await repo.getDevices();
      final ch1 = devices.firstWhere((d) => d.id == 'AB_INDIV::ch1');
      final ch2 = devices.firstWhere((d) => d.id == 'AB_INDIV::ch2');

      expect(ch1.value, 45.0);
      expect(ch2.value, 105.0);
    });

    test('activateScene throws GatewayException when a target device fails', () async {
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB_FAIL': {
                    'name': 'ActionBox',
                    'status': 'online',
                    'room': 'phong_khach',
                    'relay_state': [1, 1],
                    'channels': {
                      'ch1': {'name': 'Đèn 1', 'device_type': 'light'},
                      'ch2': {'name': 'Đèn 2', 'device_type': 'light'},
                    }
                  }
                },
                'pending': {},
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          if (req.url.path == '/api/relay') {
            return http.Response(
              jsonEncode({
                'success': false,
                'verify': 'timeout',
                'error': 'Device unreachable',
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
      await client.refresh();
      final repo = GatewaySmartHomeRepository(client);
      addTearDown(repo.dispose);

      await expectLater(
        repo.activateScene('scene_all_off'),
        throwsA(isA<GatewayException>().having(
          (e) => e.message,
          'message',
          contains('Kích hoạt ngữ cảnh có một số thiết bị không phản hồi'),
        )),
      );
    });

    test('GatewaySmartHomeRepository loads and persists automations via SharedPreferences', () async {
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/nodes') {
            return http.Response('{"nodes":{},"pending":{}}', 200, headers: {'content-type': 'application/json'});
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test');

      final repo1 = GatewaySmartHomeRepository(client);
      addTearDown(repo1.dispose);

      const newAuto = Automation(
        id: 'auto_custom_1',
        name: 'Tự tắt đèn ban công lúc 22h',
        icon: Icons.lightbulb_outline,
        triggerText: '22:00 hàng ngày',
        deviceCount: 1,
        enabled: true,
      );
      await repo1.addAutomation(newAuto);
      final list1 = await repo1.getAutomations();
      expect(list1.any((a) => a.id == 'auto_custom_1'), isTrue);

      final repo2 = GatewaySmartHomeRepository(client);
      addTearDown(repo2.dispose);
      await Future.delayed(const Duration(milliseconds: 50));
      final list2 = await repo2.getAutomations();
      expect(list2.any((a) => a.id == 'auto_custom_1'), isTrue);
      expect(list2.firstWhere((a) => a.id == 'auto_custom_1').name, 'Tự tắt đèn ban công lúc 22h');
    });
  });
}
