import 'package:flutter/material.dart';

class Room {
  final String id;
  final String name;
  final IconData icon;
  final double? temperature;
  final double? humidity;

  const Room({
    required this.id,
    required this.name,
    this.icon = Icons.meeting_room_rounded,
    this.temperature,
    this.humidity,
  });

  Room copyWith({
    String? id,
    String? name,
    IconData? icon,
    double? temperature,
    double? humidity,
  }) {
    return Room(
      id: id ?? this.id,
      name: name ?? this.name,
      icon: icon ?? this.icon,
      temperature: temperature ?? this.temperature,
      humidity: humidity ?? this.humidity,
    );
  }
}
