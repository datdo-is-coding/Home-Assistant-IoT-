import 'package:flutter/foundation.dart';

enum WeatherMode { auto, sunny, rainy, stormy, cloudy }

class WeatherState {
  static final WeatherState _instance = WeatherState._internal();
  factory WeatherState() => _instance;
  WeatherState._internal();

  final ValueNotifier<WeatherMode> currentMode = ValueNotifier<WeatherMode>(WeatherMode.auto);
  final ValueNotifier<String> activeCondition = ValueNotifier<String>('sunny'); // 'sunny', 'rainy', 'stormy', 'cloudy'

  void setMode(WeatherMode mode) {
    currentMode.value = mode;
    if (mode != WeatherMode.auto) {
      activeCondition.value = mode.name;
    }
  }

  void updateFromApi(String desc) {
    if (currentMode.value != WeatherMode.auto) return;
    final lower = desc.toLowerCase();
    if (lower.contains('mưa') || lower.contains('rain') || lower.contains('dông')) {
      if (lower.contains('dông') || lower.contains('storm') || lower.contains('sấm')) {
        activeCondition.value = 'stormy';
      } else {
        activeCondition.value = 'rainy';
      }
    } else if (lower.contains('mây') || lower.contains('cloud') || lower.contains('u ám')) {
      activeCondition.value = 'cloudy';
    } else {
      activeCondition.value = 'sunny';
    }
  }
}
