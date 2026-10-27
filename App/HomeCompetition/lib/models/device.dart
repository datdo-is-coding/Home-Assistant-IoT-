import 'package:flutter/material.dart';

enum DeviceType {
  light,
  fan,
  socket,
  airConditioner,
  curtain,
  sensor,
  tv,
  custom,
}

class Device {
  final String id;
  final String name;
  final DeviceType type;
  final String roomId;
  final String? actionBoxId;
  final String? channel;
  final bool online;
  final bool isOn;
  final double value;
  final double? powerWatts;
  final List<String> voiceAliases;
  final bool isFavorite;
  final Map<String, dynamic> metadata;

  const Device({
    required this.id,
    required this.name,
    required this.type,
    required this.roomId,
    this.actionBoxId,
    this.channel,
    this.online = true,
    this.isOn = false,
    this.value = 0.0,
    this.powerWatts,
    this.voiceAliases = const [],
    this.isFavorite = false,
    this.metadata = const {},
  });

  Device copyWith({
    String? id,
    String? name,
    DeviceType? type,
    String? roomId,
    String? actionBoxId,
    String? channel,
    bool? online,
    bool? isOn,
    double? value,
    double? powerWatts,
    List<String>? voiceAliases,
    bool? isFavorite,
    Map<String, dynamic>? metadata,
  }) {
    return Device(
      id: id ?? this.id,
      name: name ?? this.name,
      type: type ?? this.type,
      roomId: roomId ?? this.roomId,
      actionBoxId: actionBoxId ?? this.actionBoxId,
      channel: channel ?? this.channel,
      online: online ?? this.online,
      isOn: isOn ?? this.isOn,
      value: value ?? this.value,
      powerWatts: powerWatts ?? this.powerWatts,
      voiceAliases: voiceAliases ?? this.voiceAliases,
      isFavorite: isFavorite ?? this.isFavorite,
      metadata: metadata ?? this.metadata,
    );
  }

  IconData get iconData {
    switch (type) {
      case DeviceType.light:
        return Icons.lightbulb_rounded;
      case DeviceType.fan:
        return Icons.air_rounded;
      case DeviceType.socket:
        return Icons.power_rounded;
      case DeviceType.airConditioner:
        return Icons.ac_unit_rounded;
      case DeviceType.curtain:
        return Icons.curtains_rounded;
      case DeviceType.sensor:
        return Icons.sensors_rounded;
      case DeviceType.tv:
        return Icons.tv_rounded;
      case DeviceType.custom:
        return Icons.tune_rounded;
    }
  }

  double? get currentAmps {
    final current = metadata['current'];
    return online && current is num && current.isFinite && current >= 0 ? current.toDouble() : null;
  }

  String get currentText => !online ? 'Dòng điện: mất kết nối'
      : currentAmps == null ? 'Dòng điện: chưa có mẫu'
      : 'Dòng điện: ${currentAmps!.toStringAsFixed(3)} A';

  String get measurementText {
    final voltage = metadata['voltage'];
    return [currentText,
      if (online && voltage is num && voltage.isFinite) '${voltage.toStringAsFixed(0)} V',
      if (online && powerWatts != null && powerWatts!.isFinite) '${powerWatts!.toStringAsFixed(1)} W',
    ].join(' · ');
  }

  String get stateText {
    if (!online) return 'Ngoại tuyến';
    if (metadata['cloud_state'] == true) return 'Firebase: ${isOn ? "bật" : "tắt"} · chưa xác nhận tải';
    if (!isOn) return 'Đã tắt';

    final canDim = metadata['can_dim'] == true;
    final canSpeed = metadata['can_speed'] == true;
    final hasThermostat = metadata['has_thermostat'] == true;

    final hasPower = powerWatts != null && powerWatts! > 0;
    final powerStr = hasPower ? 'Bật · ${powerWatts!.toStringAsFixed(1)} W' : 'Đang bật';

    switch (type) {
      case DeviceType.light:
        if (canDim && value > 0) {
          return 'Bật · ${value.toInt()}%';
        }
        return powerStr;
      case DeviceType.fan:
        if (canSpeed && value > 0) {
          return 'Bật · Cấp ${value.toInt().clamp(1, 3)}';
        }
        return powerStr;
      case DeviceType.socket:
        return powerStr;
      case DeviceType.airConditioner:
        if (hasThermostat && value > 0) {
          return 'Làm mát · ${value.toInt()}°C';
        }
        return powerStr;
      case DeviceType.sensor:
        return '${value.toStringAsFixed(1)} °C';
      default:
        return powerStr;
    }
  }
}
