import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum AppThemeMode {
  echoNightly,
  cyberpunkPurple,
  emeraldMatrix,
  solarGold,
}

class AppThemeData {
  final String name;
  final String description;
  final Color bg;
  final Color surface;
  final Color primary;
  final Color secondary;
  final IconData icon;

  const AppThemeData({
    required this.name,
    required this.description,
    required this.bg,
    required this.surface,
    required this.primary,
    required this.secondary,
    required this.icon,
  });
}

class ThemeService extends ChangeNotifier {
  static final ThemeService _instance = ThemeService._internal();
  factory ThemeService() => _instance;
  ThemeService._internal();

  static const String _themePrefKey = "app_selected_theme_mode";

  AppThemeMode _currentMode = AppThemeMode.echoNightly;
  AppThemeMode get currentMode => _currentMode;

  static const Map<AppThemeMode, AppThemeData> themes = {
    AppThemeMode.echoNightly: AppThemeData(
      name: "Echo Nightly",
      description: "Midnight Obsidian & Cyan Neon Glow",
      bg: Color(0xFF090D16),
      surface: Color(0xFF131B2E),
      primary: Color(0xFF00F2FE),
      secondary: Color(0xFF7C3AED),
      icon: Icons.nightlife_rounded,
    ),
    AppThemeMode.cyberpunkPurple: AppThemeData(
      name: "Cyberpunk Neon",
      description: "Fuchsia Glow & Deep Synthwave Purple",
      bg: Color(0xFF0D0614),
      surface: Color(0xFF1B0E2B),
      primary: Color(0xFFD946EF),
      secondary: Color(0xFF8B5CF6),
      icon: Icons.auto_awesome_rounded,
    ),
    AppThemeMode.emeraldMatrix: AppThemeData(
      name: "Emerald Matrix",
      description: "Cyber Emerald & Deep Forest Hacker Teal",
      bg: Color(0xFF04130D),
      surface: Color(0xFF0B2519),
      primary: Color(0xFF10B981),
      secondary: Color(0xFF059669),
      icon: Icons.terminal_rounded,
    ),
    AppThemeMode.solarGold: AppThemeData(
      name: "Solar Gold",
      description: "Amber Gold & Luxury Onyx Bronze",
      bg: Color(0xFF120E07),
      surface: Color(0xFF241C0F),
      primary: Color(0xFFF59E0B),
      secondary: Color(0xFFD97706),
      icon: Icons.wb_sunny_rounded,
    ),
  };

  AppThemeData get currentTheme => themes[_currentMode]!;

  Future<void> loadTheme() async {
    final prefs = await SharedPreferences.getInstance();
    final savedIndex = prefs.getInt(_themePrefKey) ?? 0;
    if (savedIndex >= 0 && savedIndex < AppThemeMode.values.length) {
      _currentMode = AppThemeMode.values[savedIndex];
      notifyListeners();
    }
  }

  Future<void> setTheme(AppThemeMode mode) async {
    _currentMode = mode;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_themePrefKey, mode.index);
  }
}
