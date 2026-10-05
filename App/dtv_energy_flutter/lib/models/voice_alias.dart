class VoiceVocabularyItem {
  final String deviceId;
  final String deviceName;
  final List<String> aliases;

  const VoiceVocabularyItem({
    required this.deviceId,
    required this.deviceName,
    required this.aliases,
  });

  VoiceVocabularyItem copyWith({
    String? deviceId,
    String? deviceName,
    List<String>? aliases,
  }) {
    return VoiceVocabularyItem(
      deviceId: deviceId ?? this.deviceId,
      deviceName: deviceName ?? this.deviceName,
      aliases: aliases ?? this.aliases,
    );
  }
}
