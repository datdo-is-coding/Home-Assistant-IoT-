import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SessionScope {
  final String gatewayUrl;
  final String userId;
  final int generation;

  const SessionScope({
    required this.gatewayUrl,
    required this.userId,
    required this.generation,
  });

  static const empty = SessionScope(gatewayUrl: '', userId: '', generation: 0);

  bool matches(String url, String uid) =>
      gatewayUrl == url && userId == uid;

  Map<String, dynamic> toJson() => {
        'gateway_url': gatewayUrl,
        'user_id': userId,
        'generation': generation,
      };

  factory SessionScope.fromJson(Map<String, dynamic> json) => SessionScope(
        gatewayUrl: json['gateway_url'] as String? ?? '',
        userId: json['user_id'] as String? ?? '',
        generation: json['generation'] as int? ?? 0,
      );

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is SessionScope &&
          runtimeType == other.runtimeType &&
          gatewayUrl == other.gatewayUrl &&
          userId == other.userId &&
          generation == other.generation;

  @override
  int get hashCode => Object.hash(gatewayUrl, userId, generation);

  @override
  String toString() => 'SessionScope($gatewayUrl, $userId, gen:$generation)';
}

class CachedSnapshot {
  final SessionScope scope;
  final int revision;
  final DateTime capturedAt;
  final Map<String, dynamic> user;
  final Map<String, dynamic> nodes;
  final Map<String, dynamic> pending;

  CachedSnapshot({
    required this.scope,
    this.revision = 1,
    required this.capturedAt,
    this.user = const {},
    this.nodes = const {},
    this.pending = const {},
  });

  Map<String, dynamic> toJson() => {
        'scope': scope.toJson(),
        'revision': revision,
        'captured_at': capturedAt.toIso8601String(),
        'user': user,
        'nodes': nodes,
        'pending': pending,
      };

  factory CachedSnapshot.fromJson(Map<String, dynamic> json) {
    final scopeJson = json['scope'];
    final scope = scopeJson is Map<String, dynamic>
        ? SessionScope.fromJson(scopeJson)
        : (scopeJson is Map
            ? SessionScope.fromJson(Map<String, dynamic>.from(scopeJson))
            : SessionScope.empty);
    final rawCapturedAt = json['captured_at'] as String?;
    final capturedAt = rawCapturedAt != null
        ? DateTime.tryParse(rawCapturedAt) ?? DateTime.now()
        : DateTime.now();

    return CachedSnapshot(
      scope: scope,
      revision: json['revision'] as int? ?? 1,
      capturedAt: capturedAt,
      user: json['user'] is Map
          ? Map<String, dynamic>.from(json['user'] as Map)
          : const {},
      nodes: json['nodes'] is Map
          ? Map<String, dynamic>.from(json['nodes'] as Map)
          : const {},
      pending: json['pending'] is Map
          ? Map<String, dynamic>.from(json['pending'] as Map)
          : const {},
    );
  }
}

class GatewayCacheService {
  final Duration debounceDuration;
  final Map<String, Timer> _debounceTimers = {};
  final Map<String, CachedSnapshot> _pendingWrites = {};

  GatewayCacheService({
    this.debounceDuration = const Duration(milliseconds: 500),
  });

  static String scopeKey(String gatewayUrl, String userId) {
    final normUrl =
        gatewayUrl.trim().toLowerCase().replaceAll(RegExp(r'/+$'), '');
    final normUser = userId.trim().toLowerCase();
    return '$normUrl::$normUser';
  }

  static String _prefKey(String gatewayUrl, String userId) =>
      'gw_snapshot_${scopeKey(gatewayUrl, userId)}';

  static String _lastUserKey(String gatewayUrl) {
    final normUrl =
        gatewayUrl.trim().toLowerCase().replaceAll(RegExp(r'/+$'), '');
    return 'gw_last_user_$normUrl';
  }

  Future<void> saveSnapshot(CachedSnapshot snapshot,
      {bool immediate = false}) async {
    final key = scopeKey(snapshot.scope.gatewayUrl, snapshot.scope.userId);
    _pendingWrites[key] = snapshot;

    if (immediate || debounceDuration == Duration.zero) {
      _debounceTimers[key]?.cancel();
      _debounceTimers.remove(key);
      await _flushKey(key);
      return;
    }

    _debounceTimers[key]?.cancel();
    _debounceTimers[key] = Timer(debounceDuration, () {
      _flushKey(key);
    });
  }

  Future<void> _flushKey(String key) async {
    final snapshot = _pendingWrites.remove(key);
    _debounceTimers.remove(key);
    if (snapshot == null) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      final pKey = _prefKey(snapshot.scope.gatewayUrl, snapshot.scope.userId);
      final jsonString = jsonEncode(snapshot.toJson());
      await prefs.setString(pKey, jsonString);
      if (snapshot.scope.userId.isNotEmpty) {
        await prefs.setString(
            _lastUserKey(snapshot.scope.gatewayUrl), snapshot.scope.userId);
      }
    } catch (e) {
      debugPrint('[GatewayCacheService] Error saving snapshot: $e');
    }
  }

  Future<void> flush() async {
    for (final timer in _debounceTimers.values) {
      timer.cancel();
    }
    _debounceTimers.clear();
    final keys = List<String>.from(_pendingWrites.keys);
    for (final key in keys) {
      await _flushKey(key);
    }
  }

  Future<CachedSnapshot?> loadSnapshot(
      String gatewayUrl, String userId) async {
    final key = scopeKey(gatewayUrl, userId);
    if (_pendingWrites.containsKey(key)) {
      return _pendingWrites[key];
    }

    final pKey = _prefKey(gatewayUrl, userId);
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(pKey);
      if (raw == null || raw.isEmpty) return null;

      final dynamic decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('Invalid snapshot JSON structure');
      }
      return CachedSnapshot.fromJson(decoded);
    } catch (e) {
      debugPrint(
          '[GatewayCacheService] Corrupted cache detected for $key, clearing: $e');
      await clearScope(gatewayUrl, userId);
      return null;
    }
  }

  Future<CachedSnapshot?> loadSnapshotForGateway(String gatewayUrl,
      [String? userId]) async {
    if (gatewayUrl.isEmpty) return null;
    final prefs = await SharedPreferences.getInstance();
    var uid = (userId != null && userId.isNotEmpty)
        ? userId
        : (prefs.getString(_lastUserKey(gatewayUrl)) ?? '');

    if (uid.isNotEmpty) {
      final snap = await loadSnapshot(gatewayUrl, uid);
      if (snap != null) return snap;
    }

    final normUrl =
        gatewayUrl.trim().toLowerCase().replaceAll(RegExp(r'/+$'), '');
    final prefix = 'gw_snapshot_$normUrl::';
    final keys = prefs.getKeys().where((k) => k.startsWith(prefix));
    for (final k in keys) {
      try {
        final raw = prefs.getString(k);
        if (raw != null && raw.isNotEmpty) {
          final decoded = jsonDecode(raw);
          if (decoded is Map<String, dynamic>) {
            return CachedSnapshot.fromJson(decoded);
          }
        }
      } catch (_) {
        await prefs.remove(k);
      }
    }
    return null;
  }

  Future<void> clearScope(String gatewayUrl, String userId) async {
    final key = scopeKey(gatewayUrl, userId);
    _debounceTimers[key]?.cancel();
    _debounceTimers.remove(key);
    _pendingWrites.remove(key);

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_prefKey(gatewayUrl, userId));
      final lastUserK = _lastUserKey(gatewayUrl);
      if (prefs.getString(lastUserK) == userId) {
        await prefs.remove(lastUserK);
      }
    } catch (e) {
      debugPrint('[GatewayCacheService] Error clearing scope: $e');
    }
  }

  Future<void> clearAll() async {
    for (final timer in _debounceTimers.values) {
      timer.cancel();
    }
    _debounceTimers.clear();
    _pendingWrites.clear();

    try {
      final prefs = await SharedPreferences.getInstance();
      final keys = prefs
          .getKeys()
          .where(
              (k) => k.startsWith('gw_snapshot_') || k.startsWith('gw_last_user_'))
          .toList();
      for (final k in keys) {
        await prefs.remove(k);
      }
    } catch (e) {
      debugPrint('[GatewayCacheService] Error clearing all cache: $e');
    }
  }

  void dispose() {
    for (final timer in _debounceTimers.values) {
      timer.cancel();
    }
    _debounceTimers.clear();
    _pendingWrites.clear();
  }
}
