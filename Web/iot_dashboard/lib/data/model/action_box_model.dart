import 'package:flutter/material.dart';

class ActionBoxChannelModel {
  final int index;
  final String channelKey; // 'ch1', 'ch2', 'ch3'
  final String name;
  final String deviceType; // 'light', 'fan', 'socket', 'airConditioner', 'custom'
  final bool state;
  final double voltage;
  final double current;
  final double power;
  final double energyKwh;

  const ActionBoxChannelModel({
    required this.index,
    required this.channelKey,
    required this.name,
    this.deviceType = 'light',
    this.state = false,
    this.voltage = 220.0,
    this.current = 0.0,
    this.power = 0.0,
    this.energyKwh = 0.0,
  });

  IconData get iconData {
    switch (deviceType.toLowerCase()) {
      case 'light':
      case 'lamp':
        return Icons.lightbulb_rounded;
      case 'fan':
        return Icons.mode_fan_off_rounded;
      case 'socket':
      case 'outlet':
        return Icons.power_rounded;
      case 'airconditioner':
      case 'ac':
        return Icons.ac_unit_rounded;
      default:
        return Icons.devices_other_rounded;
    }
  }

  Color get accentColor {
    switch (deviceType.toLowerCase()) {
      case 'light':
      case 'lamp':
        return const Color(0xFFF59E0B);
      case 'fan':
        return const Color(0xFF3B82F6);
      case 'socket':
      case 'outlet':
        return const Color(0xFF8B5CF6);
      case 'airconditioner':
      case 'ac':
        return const Color(0xFF06B6D4);
      default:
        return const Color(0xFF10B981);
    }
  }

  ActionBoxChannelModel copyWith({
    int? index,
    String? channelKey,
    String? name,
    String? deviceType,
    bool? state,
    double? voltage,
    double? current,
    double? power,
    double? energyKwh,
  }) {
    return ActionBoxChannelModel(
      index: index ?? this.index,
      channelKey: channelKey ?? this.channelKey,
      name: name ?? this.name,
      deviceType: deviceType ?? this.deviceType,
      state: state ?? this.state,
      voltage: voltage ?? this.voltage,
      current: current ?? this.current,
      power: power ?? this.power,
      energyKwh: energyKwh ?? this.energyKwh,
    );
  }
}

class ActionBoxModel {
  final String id;
  final String name;
  final String room;
  final bool online;
  final String ip;
  final String firmwareVersion;
  final String boardModel;
  final double totalPower;
  final double totalEnergyKwh;
  final int signalStrength;
  final DateTime? lastUpdated;
  final List<ActionBoxChannelModel> channels;

  const ActionBoxModel({
    required this.id,
    required this.name,
    required this.room,
    this.online = true,
    this.ip = '192.168.1.100',
    this.firmwareVersion = 'v2.1.0-esp32s3',
    this.boardModel = 'ActionBox_V2',
    this.totalPower = 0.0,
    this.totalEnergyKwh = 0.0,
    this.signalStrength = -55,
    this.lastUpdated,
    this.channels = const [],
  });

  bool get isSubBox =>
      id.toUpperCase().startsWith('SB') ||
      boardModel.toLowerCase().contains('subbox') ||
      name.toLowerCase().contains('subbox');

  ActionBoxModel copyWith({
    String? id,
    String? name,
    String? room,
    bool? online,
    String? ip,
    String? firmwareVersion,
    String? boardModel,
    double? totalPower,
    double? totalEnergyKwh,
    int? signalStrength,
    DateTime? lastUpdated,
    List<ActionBoxChannelModel>? channels,
  }) {
    return ActionBoxModel(
      id: id ?? this.id,
      name: name ?? this.name,
      room: room ?? this.room,
      online: online ?? this.online,
      ip: ip ?? this.ip,
      firmwareVersion: firmwareVersion ?? this.firmwareVersion,
      boardModel: boardModel ?? this.boardModel,
      totalPower: totalPower ?? this.totalPower,
      totalEnergyKwh: totalEnergyKwh ?? this.totalEnergyKwh,
      signalStrength: signalStrength ?? this.signalStrength,
      lastUpdated: lastUpdated ?? this.lastUpdated,
      channels: channels ?? this.channels,
    );
  }
}
