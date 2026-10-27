import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/services/device_provisioning_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('sic/provisioning');
  late DeviceProvisioningService service;
  final List<MethodCall> log = [];

  setUp(() {
    log.clear();
    service = DeviceProvisioningService(channel: channel);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (MethodCall methodCall) async {
      log.add(methodCall);
      switch (methodCall.method) {
        case 'connectSetupNetwork':
          return true;
        case 'provisionSubBox':
          return <String, dynamic>{
            'status': 'SUCCESS',
            'ssid': methodCall.arguments['ssid'],
            'gateway_host': methodCall.arguments['gateway_host'],
            'room_name': methodCall.arguments['room_name'],
          };
        case 'cancelProvisioning':
          return null;
        default:
          return null;
      }
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
    service.dispose();
  });

  group('DeviceProvisioningService Happy Path', () {
    test('connectSetupNetwork calls native bridge and emits events', () async {
      final events = <ProvisioningProgressEvent>[];
      final sub = service.provisioningEvents.listen(events.add);

      await service.connectSetupNetwork('siciot_sub_1A2B3C', 'testpassword123');

      expect(log, hasLength(1));
      expect(log.first.method, equals('connectSetupNetwork'));
      expect(log.first.arguments, equals({
        'ssid': 'siciot_sub_1A2B3C',
        'password': 'testpassword123',
      }));

      expect(events, hasLength(2));
      expect(events[0].step, equals(ProvisioningStep.connectingAp));
      expect(events[1].step, equals(ProvisioningStep.connectingAp));

      await sub.cancel();
    });

    test('provisionSubBox calls native bridge, verifies, and returns result', () async {
      final events = <ProvisioningProgressEvent>[];
      final sub = service.provisioningEvents.listen(events.add);

      final result = await service.provisionSubBox(
        ssid: 'Home-WiFi-2.4G',
        password: 'secure-wifi-pass',
        gatewayHost: '192.168.1.100',
        gatewayPort: 8883,
        pop: 'SIC-123456',
        roomName: 'Phòng khách',
        roomType: 1,
      );

      expect(log, hasLength(1));
      expect(log.first.method, equals('provisionSubBox'));
      expect(log.first.arguments, equals({
        'ssid': 'Home-WiFi-2.4G',
        'password': 'secure-wifi-pass',
        'gateway_host': '192.168.1.100',
        'gateway_port': 8883,
        'pop': 'SIC-123456',
        'room_name': 'Phòng khách',
        'room_type': 1,
      }));

      expect(result['status'], equals('SUCCESS'));
      expect(result['ssid'], equals('Home-WiFi-2.4G'));
      expect(result['gateway_host'], equals('192.168.1.100'));
      expect(result['room_name'], equals('Phòng khách'));

      final dto = SubBoxProvisionResult.fromMap(result);
      expect(dto.status, equals('SUCCESS'));
      expect(dto.ssid, equals('Home-WiFi-2.4G'));
      expect(dto.gatewayHost, equals('192.168.1.100'));

      expect(events.map((e) => e.step).toList(), equals([
        ProvisioningStep.handshake,
        ProvisioningStep.sendingConfig,
        ProvisioningStep.verifying,
        ProvisioningStep.completed,
      ]));

      await sub.cancel();
    });

    test('cancelProvisioning calls native bridge without error', () async {
      await service.cancelProvisioning();
      expect(log, hasLength(1));
      expect(log.first.method, equals('cancelProvisioning'));
    });
  });

  group('DeviceProvisioningService Error Mapping', () {
    test('maps SETUP_NETWORK_TIMEOUT to SetupNetworkTimeoutException', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(
          code: 'SETUP_NETWORK_TIMEOUT',
          message: 'SoftAP connection timed out after 30s',
        );
      });

      final events = <ProvisioningProgressEvent>[];
      final sub = service.provisioningEvents.listen(events.add);

      expect(
        () => service.connectSetupNetwork('siciot_sub_1A2B3C', 'pass'),
        throwsA(isA<SetupNetworkTimeoutException>()),
      );

      await Future.delayed(Duration.zero);
      expect(events.last.step, equals(ProvisioningStep.failed));
      expect(events.last.error, isA<SetupNetworkTimeoutException>());
      await sub.cancel();
    });

    test('maps PROOF_REJECTED to ProofRejectedException', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(
          code: 'PROOF_REJECTED',
          message: 'Setup code POP rejected',
        );
      });

      final events = <ProvisioningProgressEvent>[];
      final sub = service.provisioningEvents.listen(events.add);

      expect(
        () => service.provisionSubBox(
          ssid: 'Home-WiFi',
          password: 'pass',
          gatewayHost: '192.168.1.50',
          pop: 'WRONG-POP',
        ),
        throwsA(isA<ProofRejectedException>()),
      );

      await Future.delayed(Duration.zero);
      expect(events.last.step, equals(ProvisioningStep.failed));
      expect(events.last.error, isA<ProofRejectedException>());
      await sub.cancel();
    });

    test('maps WIFI_DISCONNECTED to WifiDisconnectedException', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(
          code: 'WIFI_DISCONNECTED',
          message: 'Setup network lost',
        );
      });

      expect(
        () => service.provisionSubBox(
          ssid: 'Home-WiFi',
          password: 'pass',
          gatewayHost: '192.168.1.50',
          pop: 'POP-123',
        ),
        throwsA(isA<WifiDisconnectedException>()),
      );
    });

    test('maps PERMISSION_DENIED to PermissionDeniedException', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(
          code: 'PERMISSION_DENIED',
          message: 'Permission denied for network change',
        );
      });

      expect(
        () => service.connectSetupNetwork('siciot_sub_test', 'pass'),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('maps generic error to ProvisioningFailedException', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
        throw PlatformException(
          code: 'PROVISIONING_FAILED',
          message: 'Failed to write config',
        );
      });

      expect(
        () => service.provisionSubBox(
          ssid: 'Home-WiFi',
          password: 'pass',
          gatewayHost: '192.168.1.50',
          pop: 'POP-123',
        ),
        throwsA(isA<ProvisioningFailedException>()),
      );
    });
  });

  group('Progress Event Stream & DTO tests', () {
    test('SubBoxProvisionRequest serialization', () {
      const req = SubBoxProvisionRequest(
        ssid: 'MyWiFi',
        password: 'Pass',
        gatewayHost: '10.0.0.1',
        gatewayPort: 1883,
        pop: 'SETUP123',
        roomName: 'Bếp',
        roomType: 2,
      );
      final map = req.toMap();
      expect(map['ssid'], equals('MyWiFi'));
      expect(map['password'], equals('Pass'));
      expect(map['gateway_host'], equals('10.0.0.1'));
      expect(map['gateway_port'], equals(1883));
      expect(map['pop'], equals('SETUP123'));
      expect(map['room_name'], equals('Bếp'));
      expect(map['room_type'], equals(2));
    });

    test('ProvisioningProgressEvent stepName matches wire name', () {
      final ev = ProvisioningProgressEvent(
        step: ProvisioningStep.handshake,
        message: 'Handshaking',
      );
      expect(ev.stepName, equals('HANDSHAKE'));
      expect(ev.message, equals('Handshaking'));
      expect(ev.timestamp, isNotNull);
      expect(ev.toString(), contains('HANDSHAKE: Handshaking'));
    });
  });
}
