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
  final double value; // brightness % (0-100), fan speed (0-3), temp (16-30), watts
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

  String get stateText {
    if (!online) return 'Ngoại tuyến';
    if (!isOn) return 'Đã tắt';
    switch (type) {
      case DeviceType.light:
        return 'Bật · ${value.toInt()}%';
      case DeviceType.fan:
        return 'Bật · Cấp ${value.toInt().clamp(1, 3)}';
      case DeviceType.socket:
        return value > 0 ? 'Bật · ${value.toStringAsFixed(1)}W' : 'Đang bật';
      case DeviceType.airConditioner:
        return 'Làm mát · ${value.toInt()}°C';
      case DeviceType.sensor:
        return '${value.toStringAsFixed(1)} °C';
      default:
        return 'Đang bật';
    }
  }
}
