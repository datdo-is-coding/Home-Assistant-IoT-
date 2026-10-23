import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dtv_energy_flutter/models/device.dart';
import 'package:dtv_energy_flutter/models/device_lifecycle.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';
import 'package:dtv_energy_flutter/repositories/smart_home_repository.dart';

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
  });

  group('CommandResult & ChannelTelemetry Flutter Model Tests', () {
    test('CommandResult fromJson and toJson roundtrip', () {
      final jsonMap = {
        'command_id': 'cmd_123',
        'requested_state': 'ON',
        'confirmed_state': 'ON',
        'verification': 'confirmed_load',
        'error': null,
        'power_before': 10.0,
        'power_after': 65.5,
        'delta': 55.5,
        'channel': 'ch1',
        'node_id': 'AB_01',
      };

      final cmdRes = CommandResult.fromJson(jsonMap);
      expect(cmdRes.commandId, 'cmd_123');
      expect(cmdRes.requestedState, 'ON');
      expect(cmdRes.confirmedState, 'ON');
      expect(cmdRes.verification, CommandVerification.confirmedLoad);
      expect(cmdRes.isSuccess, true);
      expect(cmdRes.powerBefore, 10.0);
      expect(cmdRes.powerAfter, 65.5);
      expect(cmdRes.delta, 55.5);
      expect(cmdRes.channel, 'ch1');
      expect(cmdRes.nodeId, 'AB_01');

      final serialized = cmdRes.toJson();
      expect(serialized['command_id'], 'cmd_123');
      expect(serialized['verification'], 'confirmed_load');
      expect(serialized['is_success'], true);
    });

    test('CommandResult isSuccess is false on timeout, failure, or error', () {
      const failRes = CommandResult(
        commandId: 'cmd_fail',
        requestedState: 'ON',
        confirmedState: null,
        verification: CommandVerification.failed,
        error: 'relay_mismatch',
      );
      expect(failRes.isSuccess, false);
      expect(failRes.confirmedState, isNull);

      const timeoutRes = CommandResult(
        commandId: 'cmd_timeout',
        requestedState: 'ON',
        confirmedState: null,
        verification: CommandVerification.timeout,
      );
      expect(timeoutRes.isSuccess, false);
      expect(timeoutRes.confirmedState, isNull);
    });

    test('ChannelTelemetry fromJson and toJson roundtrip', () {
      final jsonMap = {
        'channel_id': 'ch1',
        'sample_time': 1700000000.0,
        'validity': true,
        'power_w': 45.2,
        'voltage_v': 220.5,
        'current_a': 0.205,
        'energy_wh': 12.8,
      };

      final telem = ChannelTelemetry.fromJson(jsonMap);
      expect(telem.channelId, 'ch1');
      expect(telem.sampleTime, 1700000000.0);
      expect(telem.validity, true);
      expect(telem.powerW, 45.2);
      expect(telem.voltageV, 220.5);
      expect(telem.currentA, 0.205);
      expect(telem.energyWh, 12.8);

      final outMap = telem.toJson();
      expect(outMap['channel_id'], 'ch1');
      expect(outMap['power_w'], 45.2);
    });
  });

  group('Device Model stateText Formatting Tests (No W into % or °C)', () {
    test('Pure relay fan displays W, not fan level Cấp %', () {
      const fan = Device(
        id: 'fan_relay',
        name: 'Quạt hút',
        type: DeviceType.fan,
        roomId: 'kitchen',
        isOn: true,
        online: true,
        value: 0.0,
        powerWatts: 55.4,
      );
      expect(fan.stateText, 'Bật · 55.4 W');
    });

    test('Pure relay AC displays W, not temperature °C', () {
      const ac = Device(
        id: 'ac_relay',
        name: 'Điều hòa công tắc',
        type: DeviceType.airConditioner,
        roomId: 'bedroom',
        isOn: true,
        online: true,
        value: 0.0,
        powerWatts: 850.0,
      );
      expect(ac.stateText, 'Bật · 850.0 W');
    });

    test('Relay device without power measurement displays Đang bật, never 0 W', () {
      const ac = Device(
        id: 'ac_no_meter',
        name: 'Điều hòa',
        type: DeviceType.airConditioner,
        roomId: 'bedroom',
        isOn: true,
        online: true,
        value: 0.0,
        powerWatts: null,
      );
      expect(ac.stateText, 'Đang bật');

      const fan = Device(
        id: 'fan_no_meter',
        name: 'Quạt',
        type: DeviceType.fan,
        roomId: 'bedroom',
        isOn: true,
        online: true,
        value: 0.0,
        powerWatts: 0.0,
      );
      expect(fan.stateText, 'Đang bật');
    });

    test('Pure relay light displays W, not percentage %', () {
      const light = Device(
        id: 'light_relay',
        name: 'Đèn tuýp',
        type: DeviceType.light,
        roomId: 'living_room',
        isOn: true,
        online: true,
        value: 0.0,
        powerWatts: 18.0,
      );
      expect(light.stateText, 'Bật · 18.0 W');
    });

    test('Dimmable light displays percentage %', () {
      const dimLight = Device(
        id: 'light_dim',
        name: 'Đèn chùm',
        type: DeviceType.light,
        roomId: 'living_room',
        isOn: true,
        online: true,
        value: 75.0,
        metadata: {'can_dim': true},
      );
      expect(dimLight.stateText, 'Bật · 75%');
    });

    test('Thermostat AC displays temperature °C', () {
      const ac = Device(
        id: 'ac_smart',
        name: 'Điều hòa Daikin',
        type: DeviceType.airConditioner,
        roomId: 'bedroom',
        isOn: true,
        online: true,
        value: 24.0,
        metadata: {'has_thermostat': true},
      );
      expect(ac.stateText, 'Làm mát · 24°C');
    });

    test('Offline and off state text', () {
      const offlineDev = Device(
        id: 'offline_dev',
        name: 'Đèn',
        type: DeviceType.light,
        roomId: 'living_room',
        isOn: true,
        online: false,
      );
      expect(offlineDev.stateText, 'Ngoại tuyến');

      const offDev = Device(
        id: 'off_dev',
        name: 'Đèn',
        type: DeviceType.light,
        roomId: 'living_room',
        isOn: false,
        online: true,
      );
      expect(offDev.stateText, 'Đã tắt');
    });
  });

  group('ActionBox V2 3-Channel Discovery in Repository Tests', () {
    test('Exposes all 3 channels for ActionBox V2', () async {
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
                  'AB_V2_01': {
                    'name': 'ActionBox V2 Board',
                    'hardware': 'ActionBox_V2',
                    'status': 'online',
                    'room': 'living_room',
                    'capabilities': ['relay_3ch'],
                    'relay_state': [1, 0, 1],
                    'pzem': {'power': 135.0},
                    'channels': {
                      'ch1': {'name': 'Đèn trần', 'device_type': 'light'},
                      'ch2': {'name': 'Quạt thông gió', 'device_type': 'fan'},
                      'ch3': {'name': 'Ổ cắm sạc', 'device_type': 'socket'},
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

      final ch1 = devices.firstWhere((d) => d.id == 'AB_V2_01::ch1');
      final ch2 = devices.firstWhere((d) => d.id == 'AB_V2_01::ch2');
      final ch3 = devices.firstWhere((d) => d.id == 'AB_V2_01::ch3');

      expect(ch1.channel, 'ch1');
      expect(ch2.channel, 'ch2');
      expect(ch3.channel, 'ch3');

      expect(ch1.isOn, true);
      expect(ch2.isOn, false);
      expect(ch3.isOn, true);

      // Value must be 0.0 for pure relays, power allocated without duplication
      expect(ch1.value, 0.0);
      expect(ch1.powerWatts, 135.0);
      expect(ch2.value, 0.0);
      expect(ch2.powerWatts, isNull);
      expect(ch3.value, 0.0);
      expect(ch3.powerWatts, isNull);

      final actionBoxes = await repo.getActionBoxes();
      expect(actionBoxes.length, 1);
      expect(actionBoxes.first.channels.length, 3);
    });
  });
}
