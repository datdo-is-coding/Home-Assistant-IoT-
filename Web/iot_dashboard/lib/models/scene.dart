import 'package:flutter/material.dart';

class Scene {
  final String id;
  final String name;
  final IconData icon;
  final String description;
  final int deviceCount;

  const Scene({
    required this.id,
    required this.name,
    required this.icon,
    required this.description,
    required this.deviceCount,
  });
}
