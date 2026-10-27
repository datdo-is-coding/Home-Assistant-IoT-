import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Dịch vụ lưu trữ tuỳ chọn người dùng bền vững (ThemeMode, Tên nhà, Danh sách yêu thích).
/// Hỗ trợ phân vùng (session scope) theo từng cặp (gatewayUrl, userId).
class AppPreferencesService {
  final SharedPreferences? _prefsInstance;

  AppPreferencesService([this._prefsInstance]);

  static const String themeModeKey = 'app_theme_mode';

  static String scopeKey(String? gatewayUrl, String? userId) {
    final normUrl = (gatewayUrl ?? '')
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'/+$'), '');
    final normUser = (userId ?? '').trim().toLowerCase();
    return '$normUrl::$normUser';
  }

  static String homeNameKey(String? gatewayUrl, String? userId) =>
      'pref_home_name::${scopeKey(gatewayUrl, userId)}';

  static String favoriteIdsKey(String? gatewayUrl, String? userId) =>
      'pref_favorite_ids::${scopeKey(gatewayUrl, userId)}';

  Future<SharedPreferences> _getPrefs() async {
    return _prefsInstance ?? await SharedPreferences.getInstance();
  }

  /// Lưu ThemeMode được chọn
  Future<void> saveThemeMode(ThemeMode mode) async {
    final prefs = await _getPrefs();
    final value = switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
    };
    await prefs.setString(themeModeKey, value);
  }

  /// Tải ThemeMode đã lưu, mặc định là light
  Future<ThemeMode> loadThemeMode({ThemeMode defaultMode = ThemeMode.light}) async {
    final prefs = await _getPrefs();
    final raw = prefs.getString(themeModeKey);
    return switch (raw) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      'system' => ThemeMode.system,
      _ => defaultMode,
    };
  }

  /// Lưu tên ngôi nhà theo tài khoản & gateway hiện tại
  Future<void> saveHomeName(
    String homeName, {
    String? gatewayUrl,
    String? userId,
  }) async {
    final prefs = await _getPrefs();
    await prefs.setString(homeNameKey(gatewayUrl, userId), homeName.trim());
  }

  /// Tải tên ngôi nhà theo tài khoản & gateway, mặc định 'My Home'
  Future<String> loadHomeName({
    String? gatewayUrl,
    String? userId,
    String defaultValue = 'My Home',
  }) async {
    final prefs = await _getPrefs();
    final val = prefs.getString(homeNameKey(gatewayUrl, userId));
    if (val == null || val.trim().isEmpty) {
      return defaultValue;
    }
    return val.trim();
  }

  /// Lưu danh sách ID thiết bị yêu thích theo tài khoản & gateway
  Future<void> saveFavoriteIds(
    Set<String> favoriteIds, {
    String? gatewayUrl,
    String? userId,
  }) async {
    final prefs = await _getPrefs();
    await prefs.setStringList(
      favoriteIdsKey(gatewayUrl, userId),
      favoriteIds.toList(),
    );
  }

  /// Tải danh sách ID thiết bị yêu thích theo tài khoản & gateway
  Future<Set<String>> loadFavoriteIds({
    String? gatewayUrl,
    String? userId,
  }) async {
    final prefs = await _getPrefs();
    final list = prefs.getStringList(favoriteIdsKey(gatewayUrl, userId));
    if (list == null) return <String>{};
    return Set<String>.from(list);
  }

  /// Xóa toàn bộ tuỳ chọn của một scope khi cần
  Future<void> clearScopePreferences({
    String? gatewayUrl,
    String? userId,
  }) async {
    final prefs = await _getPrefs();
    await prefs.remove(homeNameKey(gatewayUrl, userId));
    await prefs.remove(favoriteIdsKey(gatewayUrl, userId));
  }
}
