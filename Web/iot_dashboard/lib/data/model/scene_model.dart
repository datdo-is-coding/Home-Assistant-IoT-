import 'package:flutter/material.dart';

class SceneAction {
  final String boxId;
  final String channelKey;
  final bool targetState;

  const SceneAction({
    required this.boxId,
    required this.channelKey,
    required this.targetState,
  });
}

class SceneModel {
  final String id;
  final String name;
  final String description;
  final IconData icon;
  final Color color;
  final List<SceneAction> actions;
  final bool isActive;

  const SceneModel({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.color,
    this.actions = const [],
    this.isActive = false,
  });

  SceneModel copyWith({
    String? id,
    String? name,
    String? description,
    IconData? icon,
    Color? color,
    List<SceneAction>? actions,
    bool? isActive,
  }) {
    return SceneModel(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      icon: icon ?? this.icon,
      color: color ?? this.color,
      actions: actions ?? this.actions,
      isActive: isActive ?? this.isActive,
    );
  }
}
