import 'package:flutter/material.dart';

class Automation {
  final String id;
  final String name;
  final IconData icon;
  final String triggerText;
  final int deviceCount;
  final bool enabled;

  const Automation({
    required this.id,
    required this.name,
    required this.icon,
    required this.triggerText,
    required this.deviceCount,
    this.enabled = true,
  });

  Automation copyWith({
    String? id,
    String? name,
    IconData? icon,
    String? triggerText,
    int? deviceCount,
    bool? enabled,
  }) {
    return Automation(
      id: id ?? this.id,
      name: name ?? this.name,
      icon: icon ?? this.icon,
      triggerText: triggerText ?? this.triggerText,
      deviceCount: deviceCount ?? this.deviceCount,
      enabled: enabled ?? this.enabled,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'iconCode': icon.codePoint,
      'fontFamily': icon.fontFamily,
      'fontPackage': icon.fontPackage,
      'triggerText': triggerText,
      'deviceCount': deviceCount,
      'enabled': enabled,
    };
  }

  static IconData _iconFromCode(int? code) {
    if (code == null) return Icons.auto_awesome_rounded;
    if (code == Icons.nights_stay_rounded.codePoint) return Icons.nights_stay_rounded;
    if (code == Icons.thermostat_rounded.codePoint) return Icons.thermostat_rounded;
    if (code == Icons.directions_walk_rounded.codePoint) return Icons.directions_walk_rounded;
    if (code == Icons.schedule_rounded.codePoint) return Icons.schedule_rounded;
    if (code == Icons.bolt_rounded.codePoint) return Icons.bolt_rounded;
    if (code == Icons.power_rounded.codePoint) return Icons.power_rounded;
    if (code == Icons.sync_rounded.codePoint) return Icons.sync_rounded;
    if (code == Icons.lightbulb_rounded.codePoint) return Icons.lightbulb_rounded;
    if (code == Icons.mode_night_rounded.codePoint) return Icons.mode_night_rounded;
    return Icons.auto_awesome_rounded;
  }

  factory Automation.fromJson(Map<String, dynamic> json) {
    final iconCode = json['iconCode'] as int?;
    return Automation(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      icon: _iconFromCode(iconCode),
      triggerText: json['triggerText'] as String? ?? '',
      deviceCount: json['deviceCount'] as int? ?? 0,
      enabled: json['enabled'] as bool? ?? true,
    );
  }
}
