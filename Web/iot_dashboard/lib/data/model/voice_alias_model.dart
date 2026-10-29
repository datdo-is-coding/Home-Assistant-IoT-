class VoiceAliasModel {
  final String boxId;
  final String channelKey;
  final String deviceName;
  final String roomName;
  final List<String> aliases;

  const VoiceAliasModel({
    required this.boxId,
    required this.channelKey,
    required this.deviceName,
    required this.roomName,
    required this.aliases,
  });

  VoiceAliasModel copyWith({
    String? boxId,
    String? channelKey,
    String? deviceName,
    String? roomName,
    List<String>? aliases,
  }) {
    return VoiceAliasModel(
      boxId: boxId ?? this.boxId,
      channelKey: channelKey ?? this.channelKey,
      deviceName: deviceName ?? this.deviceName,
      roomName: roomName ?? this.roomName,
      aliases: aliases ?? this.aliases,
    );
  }
}
