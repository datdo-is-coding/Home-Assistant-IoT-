import 'device.dart';

class ActionBoxChannel {
  final int index; // 0, 1, 2, 3
  final String channelKey; // ch1, ch2, ch3, ch4
  final String? deviceId;
  final String name;
  final DeviceType type;
  final bool configured;
  final bool isOn;

  const ActionBoxChannel({
    required this.index,
    required this.channelKey,
    this.deviceId,
    required this.name,
    this.type = DeviceType.light,
    this.configured = true,
    this.isOn = false,
  });

  ActionBoxChannel copyWith({
    int? index,
    String? channelKey,
    String? deviceId,
    String? name,
    DeviceType? type,
    bool? configured,
    bool? isOn,
  }) {
    return ActionBoxChannel(
      index: index ?? this.index,
      channelKey: channelKey ?? this.channelKey,
      deviceId: deviceId ?? this.deviceId,
      name: name ?? this.name,
      type: type ?? this.type,
      configured: configured ?? this.configured,
      isOn: isOn ?? this.isOn,
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
  final int signalStrength; // dBm, e.g. -58

  const ActionBox({
    required this.id,
    required this.name,
    required this.roomId,
    this.online = true,
    required this.channels,
    this.firmwareVersion = 'v1.4.2-esp32s3',
    this.ipAddress = '192.168.1.105',
    this.signalStrength = -58,
  });

  ActionBox copyWith({
    String? id,
    String? name,
    String? roomId,
    bool? online,
    List<ActionBoxChannel>? channels,
    String? firmwareVersion,
    String? ipAddress,
    int? signalStrength,
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
    );
  }
}
