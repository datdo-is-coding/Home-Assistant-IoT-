import 'device.dart';

bool isSubBoxNode(String id, Map<String, dynamic> node) =>
    id.toUpperCase().startsWith('SB') ||
    ['board_model', 'model', 'hardware', 'device_type', 'type', 'node_type']
        .any((key) => '${node[key] ?? ''}'.toLowerCase().contains('subbox'));

class ActionBoxChannel {
  final int index;
  final String channelKey;
  final String? deviceId;
  final String name;
  final DeviceType type;
  final bool configured;
  final bool isOn;
  final List<String> voiceAliases;
  final bool commandPending;

  const ActionBoxChannel({
    required this.index,
    required this.channelKey,
    this.deviceId,
    required this.name,
    this.type = DeviceType.light,
    this.configured = true,
    this.isOn = false,
    this.voiceAliases = const [],
    this.commandPending = false,
  });

  ActionBoxChannel copyWith({
    int? index,
    String? channelKey,
    String? deviceId,
    String? name,
    DeviceType? type,
    bool? configured,
    bool? isOn,
    List<String>? voiceAliases,
    bool? commandPending,
  }) {
    return ActionBoxChannel(
      index: index ?? this.index,
      channelKey: channelKey ?? this.channelKey,
      deviceId: deviceId ?? this.deviceId,
      name: name ?? this.name,
      type: type ?? this.type,
      configured: configured ?? this.configured,
      isOn: isOn ?? this.isOn,
      voiceAliases: voiceAliases ?? this.voiceAliases,
      commandPending: commandPending ?? this.commandPending,
    );
  }
}

class ActionBox {
  final String id;
  final String name;
  final String roomId;
  final bool online;
  final List<ActionBoxChannel> channels;
  final String firmwareVersion;
  final String ipAddress;
  final int signalStrength;
  final String boardModel;
  final String boardRevision;
  final String? subboxId;
  final int ownerEpoch;
  final List<String> capabilities;
  final int protocolVersion;
  final Map<String, dynamic> metadata;

  const ActionBox({
    required this.id,
    required this.name,
    required this.roomId,
    this.online = true,
    required this.channels,
    this.firmwareVersion = 'v2.1.0-esp32s3',
    this.ipAddress = '192.168.1.105',
    this.signalStrength = -58,
    this.boardModel = 'actionbox_v2',
    this.boardRevision = 'v2.1',
    this.subboxId,
    this.ownerEpoch = 1,
    this.capabilities = const ['relay', 'energy_meter'],
    this.protocolVersion = 2,
    this.metadata = const {},
  });

  bool get isSubBox =>
      id.toUpperCase().startsWith('SB') ||
      boardModel.toLowerCase().contains('subbox') ||
      metadata['type'] == 'subbox' ||
      metadata['node_type'] == 'subbox';

  ActionBox copyWith({
    String? id,
    String? name,
    String? roomId,
    bool? online,
    List<ActionBoxChannel>? channels,
    String? firmwareVersion,
    String? ipAddress,
    int? signalStrength,
    String? boardModel,
    String? boardRevision,
    String? subboxId,
    int? ownerEpoch,
    List<String>? capabilities,
    int? protocolVersion,
    Map<String, dynamic>? metadata,
  }) {
    return ActionBox(
      id: id ?? this.id,
      name: name ?? this.name,
      roomId: roomId ?? this.roomId,
      online: online ?? this.online,
      channels: channels ?? this.channels,
      firmwareVersion: firmwareVersion ?? this.firmwareVersion,
      ipAddress: ipAddress ?? this.ipAddress,
      signalStrength: signalStrength ?? this.signalStrength,
      boardModel: boardModel ?? this.boardModel,
      boardRevision: boardRevision ?? this.boardRevision,
      subboxId: subboxId ?? this.subboxId,
      ownerEpoch: ownerEpoch ?? this.ownerEpoch,
      capabilities: capabilities ?? this.capabilities,
      protocolVersion: protocolVersion ?? this.protocolVersion,
      metadata: metadata ?? this.metadata,
    );
  }
}
