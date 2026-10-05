import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> asMap(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};

double? readNumber(dynamic value) {
  final number = value is num ? value.toDouble() : double.tryParse('$value');
  return number != null && number.isFinite ? number : null;
}

class GatewayException implements Exception {
  final String message;
  final int? statusCode;
  const GatewayException(this.message, [this.statusCode]);
  @override
  String toString() => message;
}

class GatewayClient extends ChangeNotifier {
  GatewayClient({http.Client? client, this.persistSession = true})
      : _client = client ?? http.Client();
  final http.Client _client;
  final bool persistSession;
  static const _vault = MethodChannel('sic/session');
  String serverUrl = '';
  String _token = '';
  Map<String, dynamic> user = {}, nodes = {}, pending = {};
  bool connected = false, loading = false;
  String? error;
  DateTime? updatedAt;
  int _generation = 0;
  bool _disposed = false;
  /// Tracks in-flight relay commands so refresh() won't overwrite optimistic state.
  /// Key: 'nodeId::channelIdx', Value: the optimistic relay value (0 or 1).
  final Map<String, int> _pendingRelays = {};
  bool get authenticated => _token.isNotEmpty;
  bool get isAdmin => user['role'] == 'admin';
  bool get _android =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  static Uri normalizeServerUrl(String value) {
    var input = value.trim();
    if (input.isEmpty) throw const GatewayException('Nhập địa chỉ Gateway');
    if (!input.contains('://')) input = 'http://$input';
    final uri = Uri.tryParse(input);
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/') ||
        RegExp(r'\s').hasMatch(input) ||
        uri.port < 1 ||
        uri.port > 65535) {
      throw const GatewayException(
          'Địa chỉ không hợp lệ. Ví dụ: http://192.168.1.10:8000');
    }
    return uri.replace(path: '');
  }

  Future<void> restore() async {
    if (!persistSession) return;
    final prefs = await SharedPreferences.getInstance();
    serverUrl = prefs.getString('gateway_server_url') ?? '';
    // Remove credentials left in plaintext by the previous app.
    await prefs.remove('gateway_api_key');
    await prefs.remove('gateway_auth_token');
    if (_android) {
      try {
        final saved = await _vault.invokeMethod<String>('read');
        if (saved != null) {
          final data = asMap(jsonDecode(saved));
          serverUrl = normalizeServerUrl('${data['url']}').toString();
          _token = data['token'] as String? ?? '';
        }
      } on Exception {
        await _vault.invokeMethod<void>('delete');
      }
    }
    if (authenticated) {
      try {
        user = asMap((await request('/api/auth/me'))['user']);
        await refresh();
      } on GatewayException catch (e) {
        error = e.message;
      }
    }
  }

  Future<Map<String, dynamic>> _send(String url, String path, String token,
      {Map<String, dynamic>? body,
      Duration timeout = const Duration(seconds: 10),
      List<int>? bytes,
      String? filename}) async {
    try {
      final req = http.Request(body == null && bytes == null ? 'GET' : 'POST',
          Uri.parse('$url$path'))
        ..followRedirects = false
        ..headers['Accept'] = 'application/json';
      if (token.isNotEmpty) req.headers['Authorization'] = 'Bearer $token';
      if (body != null) {
        req.headers['Content-Type'] = 'application/json';
        req.body = jsonEncode(body);
      }
      if (bytes != null) {
        req.headers['Content-Type'] = 'application/octet-stream';
        req.headers['X-Filename'] = filename!;
        req.bodyBytes = bytes;
      }
      final res = await (() async =>
              http.Response.fromStream(await _client.send(req)))()
          .timeout(timeout);
      if (res.statusCode == 401) {
        throw const GatewayException(
            'Phiên đăng nhập hết hạn hoặc thông tin không đúng.', 401);
      }
      if (res.statusCode == 403) {
        throw const GatewayException(
            'Tài khoản không có quyền thực hiện thao tác này.', 403);
      }
      if (res.statusCode == 429) {
        throw const GatewayException(
            'Thử lại sau ít phút: quá nhiều lần đăng nhập.', 429);
      }
      if (res.statusCode < 200 || res.statusCode >= 300) {
        throw GatewayException(
            'Gateway trả về lỗi ${res.statusCode}.', res.statusCode);
      }
      final data = jsonDecode(utf8.decode(res.bodyBytes));
      if (data is! Map<String, dynamic>) throw const FormatException();
      return data;
    } on GatewayException {
      rethrow;
    } on TimeoutException {
      throw const GatewayException(
          'Gateway chưa phản hồi. Kiểm tra Wi-Fi rồi thử lại.');
    } on FormatException {
      throw const GatewayException(
          'Phản hồi Gateway không hợp lệ. Kiểm tra địa chỉ và cổng.');
    } catch (_) {
      throw const GatewayException(
          'Không kết nối được Gateway. Kiểm tra mạng và địa chỉ.');
    }
  }

  Future<void> login(
      {required String url,
      required String username,
      required String password}) async {
    final target = normalizeServerUrl(url).toString();
    final response = await _send(target, '/api/auth/login', '',
        body: {'username': username.trim(), 'password': password});
    final token = response['token'];
    if (response['success'] != true || token is! String || token.isEmpty) {
      throw const GatewayException('Tên đăng nhập hoặc mật khẩu không đúng.');
    }
    await _acceptSession(target, token);
  }

  Future<void> loginWithKey({required String url, required String key}) async {
    if (key.trim().isEmpty) throw const GatewayException('Nhập API key');
    await _acceptSession(normalizeServerUrl(url).toString(), key.trim());
  }

  Future<void> _acceptSession(String url, String token) async {
    final me = await _send(url, '/api/auth/me', token);
    if (me['authenticated'] != true) {
      throw const GatewayException('Thông tin đăng nhập không hợp lệ.', 401);
    }
    if (persistSession) {
      if (_android) {
        await _vault.invokeMethod<void>(
            'write', jsonEncode({'url': url, 'token': token}));
      }
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('gateway_server_url', url);
    }
    _generation++;
    serverUrl = url;
    _token = token;
    user = asMap(me['user']);
    nodes = {};
    pending = {};
    error = null;
    connected = true;
    notifyListeners();
    await refresh();
  }

  Future<Map<String, dynamic>> request(String path,
      {Map<String, dynamic>? body, Duration? timeout}) async {
    if (!authenticated) {
      throw const GatewayException('Vui lòng đăng nhập.', 401);
    }
    final generation = _generation;
    try {
      return await _send(serverUrl, path, _token,
          body: body, timeout: timeout ?? const Duration(seconds: 10));
    } on GatewayException catch (e) {
      if (e.statusCode == 401 && generation == _generation) {
        await _clearSession();
      }
      rethrow;
    }
  }

  Future<void> refresh() async {
    if (loading || !authenticated) return;
    loading = true;
    final generation = _generation;
    notifyListeners();
    try {
      final data = await request('/api/nodes');
      if (generation != _generation) return;
      if (data['nodes'] is! Map) {
        throw const GatewayException('Gateway thiếu danh sách thiết bị.');
      }
      nodes = asMap(data['nodes']);
      pending = asMap(data['pending']);
      // Re-apply any in-flight relay commands so stale poll data
      // doesn't snap the UI back to pre-toggle state.
      _applyPendingRelays();
      connected = true;
      error = null;
      updatedAt = DateTime.now();
    } on GatewayException catch (e) {
      if (generation == _generation) {
        connected = false;
        error = e.message;
      }
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  /// Stamps every in-flight relay command onto the current nodes map.
  void _applyPendingRelays() {
    for (final entry in _pendingRelays.entries) {
      final parts = entry.key.split('::');
      if (parts.length != 2) continue;
      final nodeId = parts[0];
      final chIdx = int.tryParse(parts[1]);
      if (chIdx == null || !nodes.containsKey(nodeId)) continue;
      final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
      final rawRl = node['relay_state'];
      if (rawRl is List && rawRl.length > chIdx) {
        final rl = List<dynamic>.from(rawRl);
        rl[chIdx] = entry.value;
        node['relay_state'] = rl;
        nodes[nodeId] = node;
      }
    }
  }

  Future<Map<String, dynamic>> relay(
      String nodeId, String channel, bool on) async {
    final channelIdx = {'ch1': 0, 'ch2': 1}[channel];
    dynamic originalValue;
    final pendingKey = channelIdx != null ? '$nodeId::$channelIdx' : null;

    // Optimistic local update + register as pending so refresh() preserves it.
    if (nodes.containsKey(nodeId) && channelIdx != null) {
      final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
      final rawRl = node['relay_state'];
      if (rawRl is List) {
        final rl = List<dynamic>.from(rawRl);
        if (rl.length > channelIdx) {
          originalValue = rl[channelIdx];
          rl[channelIdx] = on ? 1 : 0;
          node['relay_state'] = rl;
          nodes[nodeId] = node;
          _pendingRelays[pendingKey!] = on ? 1 : 0;
          notifyListeners();
        }
      }
    }

    try {
      final result = await request('/api/relay',
          body: {
            'node_id': nodeId,
            'channel': channel,
            'action': on ? 'turn_on' : 'turn_off'
          },
          timeout: const Duration(seconds: 15));
      // Command confirmed — clear pending before refresh so refresh reads
      // the real Gateway state. Then re-stamp the confirmed value in case
      // the Gateway hasn't persisted it yet (stale read).
      if (pendingKey != null) _pendingRelays.remove(pendingKey);
      await refresh();
      // Re-apply confirmed value in case refresh returned stale data.
      if (channelIdx != null && nodes.containsKey(nodeId)) {
        final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
        final rawRl = node['relay_state'];
        if (rawRl is List && rawRl.length > channelIdx) {
          final rl = List<dynamic>.from(rawRl);
          rl[channelIdx] = on ? 1 : 0;
          node['relay_state'] = rl;
          nodes[nodeId] = node;
          notifyListeners();
        }
      }
      return result;
    } catch (e) {
      // Rollback optimistic update on failure.
      if (pendingKey != null) _pendingRelays.remove(pendingKey);
      if (channelIdx != null && originalValue != null && nodes.containsKey(nodeId)) {
        final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
        final rawRl = node['relay_state'];
        if (rawRl is List && rawRl.length > channelIdx) {
          final rl = List<dynamic>.from(rawRl);
          rl[channelIdx] = originalValue;
          node['relay_state'] = rl;
          nodes[nodeId] = node;
          notifyListeners();
        }
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>> updateDevice({
    required String deviceId,
    String? name,
    String? room,
    String? location,
    String? description,
    String? ch1Name,
    String? ch1Type,
    List<String>? ch1Aliases,
    String? ch2Name,
    String? ch2Type,
    List<String>? ch2Aliases,
  }) async {
    final body = <String, dynamic>{
      'device_id': deviceId,
      if (name != null) 'name': name,
      if (room != null) 'room': room,
      if (location != null) 'location': location,
      if (description != null) 'description': description,
      if (ch1Name != null) 'ch1_name': ch1Name,
      if (ch1Type != null) 'ch1_type': ch1Type,
      if (ch1Aliases != null) 'ch1_aliases': ch1Aliases,
      if (ch2Name != null) 'ch2_name': ch2Name,
      if (ch2Type != null) 'ch2_type': ch2Type,
      if (ch2Aliases != null) 'ch2_aliases': ch2Aliases,
    };
    final result = await request('/api/device/update',
        body: body, timeout: const Duration(seconds: 15));
    if (result['success'] != true) {
      throw GatewayException(
          '${result['error'] ?? 'Không thể cập nhật thiết bị'}');
    }
    await refresh();
    return result;
  }

  Future<Map<String, dynamic>> addDeviceAlias({
    required String deviceId,
    required String alias,
    String? channel,
  }) async {
    final cleanAlias = alias.trim().toLowerCase();
    final body = <String, dynamic>{
      'device_id': deviceId,
      'alias': cleanAlias,
      'action': 'add',
      if (channel != null) 'channel': channel,
    };
    debugPrint('[VOCAB][TX] sending vocabulary to gateway: payload=$body');
    final result = await request('/api/device/alias',
        body: body, timeout: const Duration(seconds: 15));
    if (result['success'] != true) {
      throw GatewayException('${result['error'] ?? 'Không thể thêm khẩu lệnh'}');
    }
    await refresh();
    return result;
  }

  Future<Map<String, dynamic>> removeDeviceAlias({
    required String deviceId,
    required String alias,
    String? channel,
  }) async {
    final cleanAlias = alias.trim().toLowerCase();
    final body = <String, dynamic>{
      'device_id': deviceId,
      'alias': cleanAlias,
      'action': 'remove',
      if (channel != null) 'channel': channel,
    };
    debugPrint('[VOCAB][TX] sending remove vocabulary to gateway: payload=$body');
    final result = await request('/api/device/alias',
        body: body, timeout: const Duration(seconds: 15));
    if (result['success'] != true) {
      throw GatewayException('${result['error'] ?? 'Không thể xóa khẩu lệnh'}');
    }
    await refresh();
    return result;
  }

  Future<Map<String, dynamic>> getVoiceVocabularyDiagnostics() async {
    return await request('/api/voice/vocabulary');
  }

  Future<void> deleteDevice(String deviceId) async {
    final result = await request('/api/device/delete',
        body: {'device_id': deviceId}, timeout: const Duration(seconds: 15));
    if (result['success'] != true) {
      throw GatewayException('${result['error'] ?? 'Không thể xóa thiết bị'}');
    }
    nodes.remove(deviceId);
    notifyListeners();
    await refresh();
  }

  Future<Map<String, dynamic>> provisionDevice({
    required String deviceId,
    required String mac,
    String? name,
    String? room,
    String? location,
    String? description,
    String? rl1,
    String? rl2,
  }) async {
    final body = <String, dynamic>{
      'device_id': deviceId,
      'mac': mac,
      if (name != null) 'name': name,
      if (room != null) 'room': room,
      if (location != null) 'location': location,
      if (description != null) 'description': description,
      if (rl1 != null) 'rl1': rl1,
      if (rl2 != null) 'rl2': rl2,
    };
    final result = await request('/api/provision',
        body: body, timeout: const Duration(seconds: 15));
    if (result['success'] != true) {
      throw GatewayException(
          '${result['error'] ?? 'Không thể ghép nối thiết bị'}');
    }
    pending.remove(deviceId);
    pending.remove(mac);
    notifyListeners();
    await refresh();
    return result;
  }

  Future<void> uploadFirmware(String filename, List<int> bytes) async {
    if (!isAdmin) {
      throw const GatewayException(
          'Chỉ quản trị viên được cập nhật firmware.', 403);
    }
    if (!RegExp(r'^[a-zA-Z0-9_.-]+\.bin$').hasMatch(filename) ||
        bytes.isEmpty ||
        bytes.length > 10 * 1024 * 1024) {
      throw const GatewayException(
          'Chọn file .bin tối đa 10 MB, tên không dấu.');
    }
    final data = await _send(serverUrl, '/api/ota/upload', _token,
        bytes: bytes, filename: filename, timeout: const Duration(seconds: 60));
    if (data['success'] != true) {
      throw GatewayException('${data['error'] ?? 'Tải firmware thất bại'}');
    }
  }

  Future<void> _clearSession() async {
    _generation++;
    _token = '';
    user = {};
    nodes = {};
    pending = {};
    connected = false;
    updatedAt = null;
    if (persistSession && _android) await _vault.invokeMethod<void>('delete');
    notifyListeners();
  }

  Future<void> logout() async {
    try {
      if (authenticated) await request('/api/auth/logout', body: {});
    } on GatewayException {
      /* Local credentials are cleared even without a network. */
    }
    await _clearSession();
  }

  @override
  void dispose() {
    _disposed = true;
    _client.close();
    super.dispose();
  }
}
