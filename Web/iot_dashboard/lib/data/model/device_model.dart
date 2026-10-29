import 'package:flutter/material.dart';

class DeviceModel {
  final String id;
  final String name;
  final String icon;
  bool isOn;
  double powerWatts;
  Color? color;
  List<double>? hourlyKwh;

  // Thuộc tính mở rộng liên kết phần cứng và Firebase RTDB
  final String? boxId;
  final String? channelKey;
  final String? deviceType;
  final double voltage;
  final double current;
  final double energyKwh;
  final bool online;
  final String roomName;
  bool isFavorite;

  DeviceModel({
    required this.id,
    required this.name,
    required this.icon,
    this.isOn = false,
    this.powerWatts = 0,
    this.color,
    this.hourlyKwh,
    this.boxId,
    this.channelKey,
    this.deviceType,
    this.voltage = 220.0,
    this.current = 0.0,
    this.energyKwh = 0.0,
    this.online = true,
    this.roomName = '',
    this.isFavorite = false,
  });

  double getTotalUntilCurrentHour(int currentHour) {
    if (hourlyKwh == null || hourlyKwh!.isEmpty) return 0.0;
    final validLength = (currentHour + 1).clamp(1, hourlyKwh!.length);
    return hourlyKwh!
        .sublist(0, validLength)
        .fold(0.0, (sum, val) => sum + val);
  }

  IconData get iconData {
    switch (deviceType?.toLowerCase()) {
      case 'light':
      case 'lamp':
        return Icons.lightbulb_rounded;
      case 'fan':
        return Icons.air_rounded;
      case 'socket':
      case 'outlet':
        return Icons.power_rounded;
      case 'airconditioner':
      case 'ac':
        return Icons.ac_unit_rounded;
      case 'curtain':
        return Icons.curtains_rounded;
      case 'sensor':
        return Icons.sensors_rounded;
      case 'tv':
        return Icons.tv_rounded;
      default:
        if (icon == 'mode_fan_off' || icon == 'air') return Icons.air_rounded;
        if (icon == 'lightbulb') return Icons.lightbulb_rounded;
        if (icon == 'ac_unit') return Icons.ac_unit_rounded;
        if (icon == 'tv') return Icons.tv_rounded;
        return Icons.devices_other_rounded;
    }
  }

  String get currentText {
    if (!online) return 'Dòng điện: mất kết nối';
    if (current <= 0) return 'Dòng điện: 0.00 A';
    return 'Dòng điện: ${current.toStringAsFixed(2)} A';
  }

  String get measurementText {
    if (!online) return 'Thiết bị ngoại tuyến';
    return '${voltage.toStringAsFixed(0)}V · ${current.toStringAsFixed(2)}A · ${powerWatts.toStringAsFixed(1)}W';
  }

  String get stateText {
    if (!online) return 'Ngoại tuyến';
    if (!isOn) return 'Đã tắt';
    if (powerWatts > 0) return 'Bật · ${powerWatts.toStringAsFixed(1)} W';
    return 'Đang bật';
  }

  DeviceModel copyWith({
    String? id,
    String? name,
    String? icon,
    bool? isOn,
    double? powerWatts,
    Color? color,
    List<double>? hourlyKwh,
    String? boxId,
    String? channelKey,
    String? deviceType,
    double? voltage,
    double? current,
    double? energyKwh,
    bool? online,
    String? roomName,
    bool? isFavorite,
  }) {
    return DeviceModel(
      id: id ?? this.id,
      name: name ?? this.name,
      icon: icon ?? this.icon,
      isOn: isOn ?? this.isOn,
      powerWatts: powerWatts ?? this.powerWatts,
      color: color ?? this.color,
      hourlyKwh: hourlyKwh ?? this.hourlyKwh,
      boxId: boxId ?? this.boxId,
      channelKey: channelKey ?? this.channelKey,
      deviceType: deviceType ?? this.deviceType,
      voltage: voltage ?? this.voltage,
      current: current ?? this.current,
      energyKwh: energyKwh ?? this.energyKwh,
      online: online ?? this.online,
      roomName: roomName ?? this.roomName,
      isFavorite: isFavorite ?? this.isFavorite,
    );
  }
}
