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
}
