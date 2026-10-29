import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/models/device_lifecycle.dart';

Map<String, dynamic> loadFixture(String name) {
  final candidatePaths = [
    '../../tests/fixtures/device_lifecycle/$name',
    'tests/fixtures/device_lifecycle/$name',
    '../tests/fixtures/device_lifecycle/$name',
  ];
  File? file;
  for (final p in candidatePaths) {
    final f = File(p);
    if (f.existsSync()) {
      file = f;
      break;
    }
  }
  if (file == null) {
    throw StateError('Fixture $name not found in search paths: $candidatePaths');
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  group('Device Lifecycle Contract Tests', () {
    test('actionbox_v1_2ch fixture exposes two channels', () {
      final json = loadFixture('actionbox_v1_2ch.json');
      final desc = DeviceDescriptor.fromJson(json);

      expect(desc.channelCount, 2);
      expect(desc.boardModel, 'actionbox_v1');
      expect(desc.protocolVersion, 2);
      expect(desc.capabilities, contains('relay'));
      expect(desc.capabilities, contains('energy_meter'));
    });

    test('v2_exposes_three_channels', () {
      final json = loadFixture('actionbox_v2_3ch.json');
      final desc = DeviceDescriptor.fromJson(json);

      expect(desc.channelCount, 3);
      expect(desc.boardModel, 'actionbox_v2');
      expect(desc.protocolVersion, 2);
      expect(desc.capabilities, contains('voice'));
    });

    test('subbox_0relay fixture exposes zero channels', () {
      final json = loadFixture('subbox_0relay.json');
      final desc = DeviceDescriptor.fromJson(json);

      expect(desc.channelCount, 0);
      expect(desc.boardModel, 'subbox_v1');
      expect(desc.protocolVersion, 2);
    });

    test('unknown_model_rejected', () {
      final json = loadFixture('unknown_model.json');
      expect(
        () => DeviceDescriptor.fromJson(json),
        throwsA(isA<UnknownModelException>()),
      );
    });

    test('unknown_model_channel_count_returns_minus_one', () {
      const desc = DeviceDescriptor(
        deviceUid: 'unknown_01',
        boardModel: 'unknown_board_xyz',
        boardRevision: 'v1.0',
        protocolVersion: 2,
        capabilities: [],
        homeId: 'home_01',
        ownerEpoch: 1,
        bootId: 'boot_01',
        configRevision: 1,
      );
      expect(desc.channelCount, -1);
    });

    test('unsupported_protocol_rejected', () {
      final json = loadFixture('unsupported_protocol.json');
      expect(
        () => DeviceDescriptor.fromJson(json),
        throwsA(isA<UnsupportedProtocolException>()),
      );
    });

    test('old_epoch_rejected', () {
      final json = loadFixture('old_epoch.json');
      expect(
        () => DeviceDescriptor.fromJson(json),
        throwsA(isA<OldEpochException>()),
      );
    });

    test('duplicate_uid_rejected', () {
      final json = loadFixture('duplicate_uid.json');
      expect(
        () => DeviceDescriptor.fromJson(json),
        throwsA(isA<DuplicateUidException>()),
      );

      expect(
        () => DeviceDescriptor.fromJson(
          {
            'device_uid': 'ab2_dup',
            'board_model': 'actionbox_v2',
            'protocol_version': 2,
            'owner_epoch': 1,
          },
          existingUids: {'ab2_dup'},
        ),
        throwsA(isA<DuplicateUidException>()),
      );
    });

    test('stale_timestamp_rejected', () {
      final json = loadFixture('stale_timestamp.json');
      final op = DeviceOperation.fromJson(json);

      const nowSec = 1600000030.0;
      expect(op.isExpired(nowSec), isTrue);
    });

    test('oversize_fragment_rejected', () {
      final json = loadFixture('oversize_fragment.json');
      expect(
        () => WireV2ConfigChunk.fromJson(json),
        throwsA(isA<OversizeFragmentException>()),
      );

      expect(
        () => WireV2ConfigBegin.fromJson({'total_len': 5000}),
        throwsA(isA<OversizeConfigException>()),
      );
    });

    test('roundtrip JSON serialization', () {
      final json = loadFixture('actionbox_v2_3ch.json');
      final desc = DeviceDescriptor.fromJson(json);
      final serialized = desc.toJson();

      expect(serialized['device_uid'], desc.deviceUid);
      expect(serialized['board_model'], desc.boardModel);
      expect(serialized['channel_count'], isNull); // not in raw wire JSON
      expect(serialized['protocol_version'], 2);
      expect(serialized['capabilities'], desc.capabilities);

      final desc2 = DeviceDescriptor.fromJson(serialized);
      expect(desc2.deviceUid, desc.deviceUid);
      expect(desc2.boardModel, desc.boardModel);
      expect(desc2.channelCount, 3);
    });

    test('crc32 calculation matches standard test vector', () {
      // Standard IEEE 802.3 test vector for "123456789" is 0xCBF43926 (3421760262)
      final testVector = utf8.encode('123456789');
      final crc = calculateCrc32(testVector);
      expect(crc, 0xCBF43926);
    });

    test('led pattern resolver priorities', () {
      // Fault priority
      final pFault = resolveLedPattern(
        lifecycle: LifecycleState.claimed,
        connectivity: ConnectivityState.online,
        fault: FaultKind.relayWelded,
        activeOpKind: DeviceOperationKind.identify,
        activeOpState: DeviceOperationState.running,
      );
      expect(pFault, LedPattern.fault);

      // Reset priority
      final pReset = resolveLedPattern(
        lifecycle: LifecycleState.claimed,
        connectivity: ConnectivityState.online,
        fault: FaultKind.none,
        activeOpKind: DeviceOperationKind.factoryReset,
        activeOpState: DeviceOperationState.awaitingConfirmation,
      );
      expect(pReset, LedPattern.awaitingFactoryReset);

      // Claiming priority
      final pClaim = resolveLedPattern(
        lifecycle: LifecycleState.claiming,
        connectivity: ConnectivityState.unknown,
      );
      expect(pClaim, LedPattern.claiming);

      // Unclaimed priority
      final pUnclaimed = resolveLedPattern(
        lifecycle: LifecycleState.unclaimed,
        connectivity: ConnectivityState.unknown,
      );
      expect(pUnclaimed, LedPattern.unclaimed);

      // Identify priority
      final pIdentify = resolveLedPattern(
        lifecycle: LifecycleState.claimed,
        connectivity: ConnectivityState.offline,
        activeOpKind: DeviceOperationKind.identify,
        activeOpState: DeviceOperationState.running,
        elapsedInStateMs: 3000,
      );
      expect(pIdentify, LedPattern.identify);

      // Offline
      final pOffline = resolveLedPattern(
        lifecycle: LifecycleState.claimed,
        connectivity: ConnectivityState.offline,
      );
      expect(pOffline, LedPattern.offline);

      // Ready solid 2s then off
      final pReady = resolveLedPattern(
        lifecycle: LifecycleState.claimed,
        connectivity: ConnectivityState.online,
        elapsedInStateMs: 1500,
      );
      expect(pReady, LedPattern.ready);

      final pReadyOff = resolveLedPattern(
        lifecycle: LifecycleState.claimed,
        connectivity: ConnectivityState.online,
        elapsedInStateMs: 2500,
      );
      expect(pReadyOff, LedPattern.off);
    });

    test('statusLedIsActive timing waveform', () {
      // UNCLAIMED: 500ms ON / 500ms OFF
      expect(statusLedIsActive(LedPattern.unclaimed, 0), isTrue);
      expect(statusLedIsActive(LedPattern.unclaimed, 300), isTrue);
      expect(statusLedIsActive(LedPattern.unclaimed, 500), isFalse);
      expect(statusLedIsActive(LedPattern.unclaimed, 800), isFalse);
      expect(statusLedIsActive(LedPattern.unclaimed, 1000), isTrue);

      // READY: Solid ON for 2000ms
      expect(statusLedIsActive(LedPattern.ready, 0), isTrue);
      expect(statusLedIsActive(LedPattern.ready, 1999), isTrue);
      expect(statusLedIsActive(LedPattern.ready, 2000), isFalse);
    });
  });
}
