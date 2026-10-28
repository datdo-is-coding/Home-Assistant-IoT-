import 'package:flutter/material.dart';

class DeviceModel {
  final String id;
  final String name;
  final String icon;
  bool isOn;
  double powerWatts;
  Color? color;
  List<double>? hourlyKwh;

  DeviceModel({
    required this.id,
    required this.name,
    required this.icon,
    this.isOn = false,
    this.powerWatts = 0,
    this.color,
    this.hourlyKwh,
  });

  double getTotalUntilCurrentHour(int currentHour) {
    if (hourlyKwh == null || hourlyKwh!.isEmpty) return 0.0;
    final validLength = (currentHour + 1).clamp(1, hourlyKwh!.length);
    return hourlyKwh!
        .sublist(0, validLength)
        .fold(0.0, (sum, val) => sum + val);
  }
}

