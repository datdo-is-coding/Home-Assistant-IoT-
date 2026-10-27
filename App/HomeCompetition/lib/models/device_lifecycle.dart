import 'dart:convert';
import 'dart:typed_data';

const int wireV2MaxFrameLen = 250;
const int wireV2MaxChunkLen = 160;
const int wireV2MaxConfigLen = 4096;
const double wireV2ReassemblyTimeoutSec = 10.0;
const int wireV2MaxConcurrentOpsActionBox = 1;
const int wireV2MaxConcurrentOpsSubBox = 2;

const Map<String, int> supportedBoardModels = {
  'actionbox_v1': 2,
  'actionbox_v2': 3,
  'subbox_v1': 0,
};

enum LifecycleState {
  unclaimed,
  claiming,
  claimed,
  resetting,
  decommissioned,
}

enum ConnectivityState {
  unknown,
  connecting,
  online,
  offline,
}

enum FaultKind {
  none,
  overCurrent,
  overTemperature,
  relayWelded,
  meterFault,
  systemFault,
}

enum DeviceOperationKind {
  identify,
  reboot,
  networkReset,
  factoryReset,
  removeFromHome,
  configure,
  claim,
}

enum DeviceOperationState {
  accepted,
  awaitingConfirmation,
  running,
  awaitingReconnect,
  succeeded,
  failed,
  timedOut,
}

enum LedPattern {
  fault,
  awaitingFactoryReset,
  awaitingNetworkReset,
  claiming,
  configApplying,
  unclaimed,
  identify,
  offline,
  connecting,
  ready,
  off,
}

class DeviceLifecycleException implements Exception {
  final String message;
  const DeviceLifecycleException(this.message);

  @override
  String toString() => 'DeviceLifecycleException: $message';
}

class UnknownModelException extends DeviceLifecycleException {
  const UnknownModelException(super.message);
}

class UnsupportedProtocolException extends DeviceLifecycleException {
  const UnsupportedProtocolException(super.message);
}

class OldEpochException extends DeviceLifecycleException {
  const OldEpochException(super.message);
}

class DuplicateUidException extends DeviceLifecycleException {
  const DuplicateUidException(super.message);
}

class StaleTimestampException extends DeviceLifecycleException {
  const StaleTimestampException(super.message);
}

class OversizeFragmentException extends DeviceLifecycleException {
  const OversizeFragmentException(super.message);
}

class OversizeConfigException extends DeviceLifecycleException {
  const OversizeConfigException(super.message);
}

class CrcMismatchException extends DeviceLifecycleException {
  const CrcMismatchException(super.message);
}

class DeviceDescriptor {
  final String deviceUid;
  final String boardModel;
  final String boardRevision;
  final int protocolVersion;
  final List<String> capabilities;
  final String homeId;
  final int ownerEpoch;
  final String bootId;
  final int configRevision;

  const DeviceDescriptor({
    required this.deviceUid,
    required this.boardModel,
    required this.boardRevision,
    required this.protocolVersion,
    required this.capabilities,
    required this.homeId,
    required this.ownerEpoch,
    required this.bootId,
    required this.configRevision,
  });

  int get channelCount {
    final norm = boardModel.trim().toLowerCase();
    return supportedBoardModels[norm] ?? -1;
  }

  factory DeviceDescriptor.fromJson(
    Map<String, dynamic> json, {
    int currentEpoch = 1,
    Set<String>? existingUids,
  }) {
    final rawModel = (json['board_model'] as String? ?? '').trim().toLowerCase();
    if (!supportedBoardModels.containsKey(rawModel)) {
      throw UnknownModelException('Unknown board model: ${json['board_model']}');
    }

    final protocolVersion = json['protocol_version'] as int? ?? 0;
    if (protocolVersion != 2) {
      throw UnsupportedProtocolException(
        'Unsupported protocol version $protocolVersion, expected 2',
      );
    }

    final ownerEpoch = json['owner_epoch'] as int? ?? 0;
    final currentReq = json['current_epoch'] as int? ?? currentEpoch;
    if (ownerEpoch < currentReq) {
      throw OldEpochException('Stale owner epoch $ownerEpoch < $currentReq');
    }

    final deviceUid = (json['device_uid'] as String? ?? '').trim();
    if (deviceUid.isEmpty) {
      throw const DeviceLifecycleException('device_uid is required');
    }

    if (existingUids != null && existingUids.contains(deviceUid)) {
      throw DuplicateUidException('Duplicate device_uid: $deviceUid');
    }
    if (json.containsKey('existing_uids')) {
      final list = (json['existing_uids'] as List<dynamic>?)
          ?.map((e) => e.toString())
          .toSet();
      if (list != null && list.contains(deviceUid)) {
        throw DuplicateUidException('Duplicate device_uid in existing_uids: $deviceUid');
      }
    }

    return DeviceDescriptor(
      deviceUid: deviceUid,
      boardModel: rawModel,
      boardRevision: json['board_revision'] as String? ?? '',
      protocolVersion: protocolVersion,
      capabilities: (json['capabilities'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      homeId: json['home_id'] as String? ?? '',
      ownerEpoch: ownerEpoch,
      bootId: json['boot_id'] as String? ?? '',
      configRevision: json['config_revision'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'device_uid': deviceUid,
        'board_model': boardModel,
        'board_revision': boardRevision,
        'protocol_version': protocolVersion,
        'capabilities': capabilities,
        'home_id': homeId,
        'owner_epoch': ownerEpoch,
        'boot_id': bootId,
        'config_revision': configRevision,
      };
}

class CommissioningCandidate {
  final String deviceUid;
  final String boardModel;
  final String boardRevision;
  final int protocolVersion;
  final List<String> capabilities;
  final int channelCount;
  final String subboxId;
  final int rssi;
  final double firstSeen;
  final double lastSeen;
  final double setupWindowExpiresAt;
  final double ttlExpiresAt;
  final String state;

  const CommissioningCandidate({
    required this.deviceUid,
    required this.boardModel,
    required this.boardRevision,
    required this.protocolVersion,
    required this.capabilities,
    required this.channelCount,
    required this.subboxId,
    required this.rssi,
    required this.firstSeen,
    required this.lastSeen,
    required this.setupWindowExpiresAt,
    required this.ttlExpiresAt,
    required this.state,
  });

  bool isExpired([double? nowSec]) {
    final now = nowSec ?? (DateTime.now().millisecondsSinceEpoch / 1000.0);
    if (state.trim().toLowerCase() == 'expired') return true;
    if (ttlExpiresAt > 0.0 && now > ttlExpiresAt) return true;
    if (setupWindowExpiresAt > 0.0 && now > setupWindowExpiresAt) return true;
    return false;
  }

  factory CommissioningCandidate.fromJson(Map<String, dynamic> json) {
    final boardModel = (json['board_model'] as String? ?? json['model'] as String? ?? '').trim();
    int chCount = json['channel_count'] as int? ?? -1;
    if (chCount < 0 && boardModel.isNotEmpty) {
      chCount = supportedBoardModels[boardModel.toLowerCase()] ?? -1;
    }

    return CommissioningCandidate(
      deviceUid: (json['device_uid'] as String? ?? json['uid'] as String? ?? '').trim(),
      boardModel: boardModel,
      boardRevision: (json['board_revision'] as String? ?? json['revision'] as String? ?? '').trim(),
      protocolVersion: json['protocol_version'] as int? ?? 2,
      capabilities: (json['capabilities'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      channelCount: chCount,
      subboxId: (json['subbox_id'] as String? ?? json['subbox'] as String? ?? '').trim(),
      rssi: json['rssi'] as int? ?? 0,
      firstSeen: (json['first_seen'] as num?)?.toDouble() ?? 0.0,
      lastSeen: (json['last_seen'] as num?)?.toDouble() ?? 0.0,
      setupWindowExpiresAt:
          (json['setup_window_expires_at'] as num? ?? json['setup_expires_at'] as num?)?.toDouble() ?? 0.0,
      ttlExpiresAt:
          (json['ttl_expires_at'] as num? ?? json['expires_at'] as num?)?.toDouble() ?? 0.0,
      state: (json['state'] as String? ?? 'unclaimed').trim(),
    );
  }

  Map<String, dynamic> toJson() => {
        'device_uid': deviceUid,
        'board_model': boardModel,
        'board_revision': boardRevision,
        'protocol_version': protocolVersion,
        'capabilities': capabilities,
        'channel_count': channelCount,
        'subbox_id': subboxId,
        'rssi': rssi,
        'first_seen': firstSeen,
        'last_seen': lastSeen,
        'setup_window_expires_at': setupWindowExpiresAt,
        'ttl_expires_at': ttlExpiresAt,
        'state': state,
      };
}

DeviceOperationKind parseDeviceOperationKind(String val) {
  switch (val.trim().toLowerCase()) {
    case 'identify':
      return DeviceOperationKind.identify;
    case 'reboot':
      return DeviceOperationKind.reboot;
    case 'network_reset':
      return DeviceOperationKind.networkReset;
    case 'factory_reset':
      return DeviceOperationKind.factoryReset;
    case 'remove_from_home':
      return DeviceOperationKind.removeFromHome;
    case 'configure':
      return DeviceOperationKind.configure;
    case 'claim':
      return DeviceOperationKind.claim;
    default:
      throw ArgumentError('Unknown OperationKind: $val');
  }
}

String formatDeviceOperationKind(DeviceOperationKind kind) {
  switch (kind) {
    case DeviceOperationKind.identify:
      return 'identify';
    case DeviceOperationKind.reboot:
      return 'reboot';
    case DeviceOperationKind.networkReset:
      return 'network_reset';
    case DeviceOperationKind.factoryReset:
      return 'factory_reset';
    case DeviceOperationKind.removeFromHome:
      return 'remove_from_home';
    case DeviceOperationKind.configure:
      return 'configure';
    case DeviceOperationKind.claim:
      return 'claim';
  }
}

DeviceOperationState parseDeviceOperationState(String val) {
  switch (val.trim().toLowerCase()) {
    case 'accepted':
      return DeviceOperationState.accepted;
    case 'awaiting_confirmation':
      return DeviceOperationState.awaitingConfirmation;
    case 'running':
      return DeviceOperationState.running;
    case 'awaiting_reconnect':
      return DeviceOperationState.awaitingReconnect;
    case 'succeeded':
      return DeviceOperationState.succeeded;
    case 'failed':
      return DeviceOperationState.failed;
    case 'timed_out':
      return DeviceOperationState.timedOut;
    default:
      throw ArgumentError('Unknown OperationState: $val');
  }
}

String formatDeviceOperationState(DeviceOperationState state) {
  switch (state) {
    case DeviceOperationState.accepted:
      return 'accepted';
    case DeviceOperationState.awaitingConfirmation:
      return 'awaiting_confirmation';
    case DeviceOperationState.running:
      return 'running';
    case DeviceOperationState.awaitingReconnect:
      return 'awaiting_reconnect';
    case DeviceOperationState.succeeded:
      return 'succeeded';
    case DeviceOperationState.failed:
      return 'failed';
    case DeviceOperationState.timedOut:
      return 'timed_out';
  }
}

class DeviceOperation {
  final DeviceOperationKind kind;
  final String operationId;
  final String deviceUid;
  final DeviceOperationState state;
  final String? errorCode;
  final String? errorMessage;
  final double expiresAt;
  final Map<String, dynamic>? metadata;

  const DeviceOperation({
    required this.kind,
    required this.operationId,
    required this.deviceUid,
    required this.state,
    this.errorCode,
    this.errorMessage,
    this.expiresAt = 0.0,
    this.metadata,
  });

  bool isExpired(double nowSec) => expiresAt > 0.0 && nowSec > expiresAt;

  factory DeviceOperation.fromJson(Map<String, dynamic> json) {
    return DeviceOperation(
      kind: parseDeviceOperationKind(json['kind'] as String? ?? ''),
      operationId: (json['operation_id'] as String? ?? '').trim(),
      deviceUid: (json['device_uid'] as String? ?? '').trim(),
      state: parseDeviceOperationState(json['state'] as String? ?? ''),
      errorCode: json['error_code'] as String?,
      errorMessage: json['error_message'] as String? ?? json['error'] as String?,
      expiresAt: (json['expires_at'] as num?)?.toDouble() ?? 0.0,
      metadata: json['metadata'] is Map
          ? Map<String, dynamic>.from(json['metadata'] as Map)
          : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'kind': formatDeviceOperationKind(kind),
        'operation_id': operationId,
        'device_uid': deviceUid,
        'state': formatDeviceOperationState(state),
        'error_code': errorCode,
        'error_message': errorMessage,
        'expires_at': expiresAt,
        'metadata': metadata,
      };
}

class WireV2ConfigBegin {
  final String operationId;
  final int configRevision;
  final int totalLen;
  final int chunkCount;
  final int crc32;

  const WireV2ConfigBegin({
    required this.operationId,
    required this.configRevision,
    required this.totalLen,
    required this.chunkCount,
    required this.crc32,
  });

  factory WireV2ConfigBegin.fromJson(Map<String, dynamic> json) {
    final total = json['total_len'] as int? ?? 0;
    if (total > wireV2MaxConfigLen) {
      throw OversizeConfigException('Config total_len $total exceeds $wireV2MaxConfigLen');
    }
    return WireV2ConfigBegin(
      operationId: json['operation_id'] as String? ?? '',
      configRevision: json['config_revision'] as int? ?? 0,
      totalLen: total,
      chunkCount: json['chunk_count'] as int? ?? 0,
      crc32: json['crc32'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'operation_id': operationId,
        'config_revision': configRevision,
        'total_len': totalLen,
        'chunk_count': chunkCount,
        'crc32': crc32,
      };
}

class WireV2ConfigChunk {
  final String operationId;
  final int chunkIndex;
  final Uint8List payload;

  WireV2ConfigChunk({
    required this.operationId,
    required this.chunkIndex,
    required this.payload,
  }) {
    if (payload.length > wireV2MaxChunkLen) {
      throw OversizeFragmentException(
        'Chunk payload length ${payload.length} exceeds $wireV2MaxChunkLen',
      );
    }
  }

  factory WireV2ConfigChunk.fromJson(Map<String, dynamic> json) {
    Uint8List p;
    if (json.containsKey('chunk_payload_hex')) {
      final hex = json['chunk_payload_hex'] as String;
      final len = hex.length ~/ 2;
      p = Uint8List(len);
      for (int i = 0; i < len; i++) {
        p[i] = int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16);
      }
    } else if (json.containsKey('payload_base64')) {
      p = Uint8List.fromList(base64Decode(json['payload_base64'] as String));
    } else if (json.containsKey('payload')) {
      final list = json['payload'] as List<dynamic>;
      p = Uint8List.fromList(list.map((e) => e as int).toList());
    } else {
      p = Uint8List(0);
    }

    final declaredSize = json['chunk_size'] as int? ?? json['payload_len'] as int? ?? p.length;
    if (declaredSize > wireV2MaxChunkLen || p.length > wireV2MaxChunkLen) {
      throw OversizeFragmentException(
        'Chunk size $declaredSize exceeds $wireV2MaxChunkLen',
      );
    }

    return WireV2ConfigChunk(
      operationId: json['operation_id'] as String? ?? '',
      chunkIndex: json['chunk_index'] as int? ?? 0,
      payload: p,
    );
  }

  Map<String, dynamic> toJson() => {
        'operation_id': operationId,
        'chunk_index': chunkIndex,
        'payload_base64': base64Encode(payload),
      };
}

class WireV2ConfigCommit {
  final String operationId;
  final int configRevision;
  final int crc32;

  const WireV2ConfigCommit({
    required this.operationId,
    required this.configRevision,
    required this.crc32,
  });

  factory WireV2ConfigCommit.fromJson(Map<String, dynamic> json) {
    return WireV2ConfigCommit(
      operationId: json['operation_id'] as String? ?? '',
      configRevision: json['config_revision'] as int? ?? 0,
      crc32: json['crc32'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'operation_id': operationId,
        'config_revision': configRevision,
        'crc32': crc32,
      };
}

final List<int> _crc32LookupTable = () {
  final table = List<int>.filled(256, 0);
  for (int i = 0; i < 256; i++) {
    int c = i;
    for (int k = 0; k < 8; k++) {
      c = (c & 1) != 0 ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[i] = c;
  }
  return table;
}();

int calculateCrc32(List<int> bytes) {
  int crc = 0xFFFFFFFF;
  for (final b in bytes) {
    final index = (crc ^ b) & 0xFF;
    crc = (crc >>> 8) ^ _crc32LookupTable[index];
  }
  return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF;
}

LedPattern resolveLedPattern({
  required LifecycleState lifecycle,
  required ConnectivityState connectivity,
  FaultKind fault = FaultKind.none,
  DeviceOperationKind? activeOpKind,
  DeviceOperationState? activeOpState,
  int elapsedInStateMs = 0,
}) {
  // 1. Fault has highest priority
  if (fault != FaultKind.none) {
    return LedPattern.fault;
  }

  // 2. Awaiting reset confirmation (max 5s)
  if (activeOpState == DeviceOperationState.awaitingConfirmation) {
    if (activeOpKind == DeviceOperationKind.factoryReset) {
      return LedPattern.awaitingFactoryReset;
    }
    if (activeOpKind == DeviceOperationKind.networkReset) {
      return LedPattern.awaitingNetworkReset;
    }
  }

  // 3. Setup / Claim / Lifecycle
  if (activeOpKind == DeviceOperationKind.configure &&
      activeOpState == DeviceOperationState.running) {
    return LedPattern.configApplying;
  }
  if (activeOpKind == DeviceOperationKind.claim) {
    return LedPattern.claiming;
  }
  if (lifecycle == LifecycleState.claiming) {
    return LedPattern.claiming;
  }
  if (lifecycle == LifecycleState.unclaimed ||
      lifecycle == LifecycleState.decommissioned) {
    return LedPattern.unclaimed;
  }

  // 4. Identify (max 15s)
  if (activeOpKind == DeviceOperationKind.identify &&
      activeOpState == DeviceOperationState.running) {
    if (elapsedInStateMs < 15000) {
      return LedPattern.identify;
    }
  }

  // 5. Connectivity (when claimed)
  if (connectivity == ConnectivityState.connecting) {
    return LedPattern.connecting;
  }
  if (connectivity == ConnectivityState.offline ||
      connectivity == ConnectivityState.unknown) {
    return LedPattern.offline;
  }

  // 6. Ready (Claimed & Online)
  if (lifecycle == LifecycleState.claimed &&
      connectivity == ConnectivityState.online) {
    if (elapsedInStateMs < 2000) {
      return LedPattern.ready;
    }
    return LedPattern.off;
  }

  return LedPattern.off;
}

bool statusLedIsActive(LedPattern pattern, int elapsedMs) {
  if (elapsedMs < 0) {
    elapsedMs = 0;
  }

  switch (pattern) {
    case LedPattern.fault:
      final phase = elapsedMs % 3600;
      return (phase < 1600) && ((phase % 400) < 200);

    case LedPattern.awaitingFactoryReset:
      final phase = elapsedMs % 3000;
      return (phase < 2000) && ((phase % 400) < 200);

    case LedPattern.awaitingNetworkReset:
      final phase = elapsedMs % 2200;
      return (phase < 1200) && ((phase % 400) < 200);

    case LedPattern.claiming:
      return (elapsedMs % 500) < 250;

    case LedPattern.configApplying:
      final phase = elapsedMs % 1600;
      return (phase < 800) && ((phase % 400) < 200);

    case LedPattern.unclaimed:
      return (elapsedMs % 1000) < 500;

    case LedPattern.identify:
      final phase = elapsedMs % 3000;
      return (phase < 1200) && ((phase % 400) < 200);

    case LedPattern.offline:
      final phase = elapsedMs % 2800;
      return (phase < 800) && ((phase % 400) < 200);

    case LedPattern.connecting:
      final phase = elapsedMs % 1400;
      return (phase < 400) && ((phase % 400) < 200);

    case LedPattern.ready:
      return elapsedMs < 2000;

    case LedPattern.off:
      return false;
  }
}

enum CommandVerification {
  success,
  partial,
  failed,
  timeout,
  confirmedLoad,
  ackOnly,
  mismatch,
  fault,
  alreadyInState;

  static CommandVerification fromString(String? val) {
    switch (val?.toLowerCase()) {
      case 'confirmed_load':
        return CommandVerification.confirmedLoad;
      case 'ack_only':
        return CommandVerification.ackOnly;
      case 'already_in_state':
        return CommandVerification.alreadyInState;
      case 'timeout':
        return CommandVerification.timeout;
      case 'failed':
        return CommandVerification.failed;
      case 'fault':
        return CommandVerification.fault;
      case 'partial':
        return CommandVerification.partial;
      case 'mismatch':
        return CommandVerification.mismatch;
      case 'success':
      default:
        return CommandVerification.success;
    }
  }

  String get value {
    switch (this) {
      case CommandVerification.confirmedLoad:
        return 'confirmed_load';
      case CommandVerification.ackOnly:
        return 'ack_only';
      case CommandVerification.alreadyInState:
        return 'already_in_state';
      case CommandVerification.timeout:
        return 'timeout';
      case CommandVerification.failed:
        return 'failed';
      case CommandVerification.fault:
        return 'fault';
      case CommandVerification.partial:
        return 'partial';
      case CommandVerification.mismatch:
        return 'mismatch';
      case CommandVerification.success:
        return 'success';
    }
  }
}

class CommandResult {
  final String commandId;
  final String requestedState;
  final String? confirmedState;
  final CommandVerification verification;
  final String? error;
  final double powerBefore;
  final double powerAfter;
  final double delta;
  final String? channel;
  final String? nodeId;

  const CommandResult({
    required this.commandId,
    required this.requestedState,
    this.confirmedState,
    required this.verification,
    this.error,
    this.powerBefore = 0.0,
    this.powerAfter = 0.0,
    this.delta = 0.0,
    this.channel,
    this.nodeId,
  });

  bool get isSuccess {
    return (verification == CommandVerification.success ||
            verification == CommandVerification.confirmedLoad ||
            verification == CommandVerification.ackOnly ||
            verification == CommandVerification.alreadyInState) &&
        error == null;
  }

  factory CommandResult.fromJson(Map<String, dynamic> json) {
    return CommandResult(
      commandId: (json['command_id'] ?? '').toString(),
      requestedState: (json['requested_state'] ?? '').toString(),
      confirmedState: json['confirmed_state']?.toString(),
      verification: CommandVerification.fromString(json['verification']?.toString()),
      error: json['error']?.toString(),
      powerBefore: (json['power_before'] as num?)?.toDouble() ?? 0.0,
      powerAfter: (json['power_after'] as num?)?.toDouble() ?? 0.0,
      delta: (json['delta'] as num?)?.toDouble() ?? 0.0,
      channel: json['channel']?.toString(),
      nodeId: json['node_id']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
    'command_id': commandId,
    'requested_state': requestedState,
    'confirmed_state': confirmedState,
    'verification': verification.value,
    'is_success': isSuccess,
    'error': error,
    'power_before': powerBefore,
    'power_after': powerAfter,
    'delta': delta,
    'channel': channel,
    'node_id': nodeId,
  };
}

class ChannelTelemetry {
  final String channelId;
  final double sampleTime;
  final bool validity;
  final double powerW;
  final double voltageV;
  final double currentA;
  final double energyWh;

  const ChannelTelemetry({
    required this.channelId,
    required this.sampleTime,
    required this.validity,
    this.powerW = 0.0,
    this.voltageV = 0.0,
    this.currentA = 0.0,
    this.energyWh = 0.0,
  });

  factory ChannelTelemetry.fromJson(Map<String, dynamic> json) {
    return ChannelTelemetry(
      channelId: (json['channel_id'] ?? '').toString(),
      sampleTime: (json['sample_time'] as num?)?.toDouble() ?? 0.0,
      validity: json['validity'] == true || json['valid'] == true,
      powerW: (json['power_w'] as num?)?.toDouble() ?? (json['power'] as num?)?.toDouble() ?? 0.0,
      voltageV: (json['voltage_v'] as num?)?.toDouble() ?? (json['voltage'] as num?)?.toDouble() ?? 0.0,
      currentA: (json['current_a'] as num?)?.toDouble() ?? (json['current'] as num?)?.toDouble() ?? 0.0,
      energyWh: (json['energy_wh'] as num?)?.toDouble() ?? (json['energy'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() => {
    'channel_id': channelId,
    'sample_time': sampleTime,
    'validity': validity,
    'power_w': powerW,
    'voltage_v': voltageV,
    'current_a': currentA,
    'energy_wh': energyWh,
  };
}
