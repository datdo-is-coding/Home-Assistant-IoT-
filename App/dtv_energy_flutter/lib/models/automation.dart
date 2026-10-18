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

  factory Automation.fromJson(Map<String, dynamic> json) {
    final iconCode = json['iconCode'] as int? ?? Icons.auto_awesome_rounded.codePoint;
    final fontFamily = json['fontFamily'] as String?;
    final fontPackage = json['fontPackage'] as String?;
    return Automation(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      // ignore: non_const_argument_for_const_parameter
      icon: IconData(iconCode, fontFamily: fontFamily ?? 'MaterialIcons', fontPackage: fontPackage),
      triggerText: json['triggerText'] as String? ?? '',
      deviceCount: json['deviceCount'] as int? ?? 0,
      enabled: json['enabled'] as bool? ?? true,
    );
  }
}
