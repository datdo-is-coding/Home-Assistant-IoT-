import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/device_lifecycle.dart';
import 'gateway_cache_service.dart';
import 'gateway_event_stream.dart';

Map<String, dynamic> asMap(dynamic value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};

double? readNumber(dynamic value) {
  final number = value is num ? value.toDouble() : double.tryParse('$value');
  return number != null && number.isFinite ? number : null;
}

int? channelIndex(String channel) {
  final lower = channel.toLowerCase();
  return {'ch1': 0, 'ch2': 1, 'ch3': 2}[lower] ?? int.tryParse(lower);
}

class GatewayException implements Exception {
  final String message;
  final int? statusCode;
  const GatewayException(this.message, [this.statusCode]);
  @override
  String toString() => message;
}

class _QueuedRelayIntent {
  final bool targetState;
  final Completer<Map<String, dynamic>> completer;
  final int generation;
  final dynamic originalValue;

  _QueuedRelayIntent({
    required this.targetState,
    required this.completer,
    required this.generation,
    this.originalValue,
  });
}

class GatewayClient extends ChangeNotifier {
  GatewayClient({
    http.Client? client,
    this.persistSession = true,
    GatewayCacheService? cacheService,
  })  : _client = client ?? http.Client(),
        cacheService = cacheService ?? GatewayCacheService();

  final http.Client _client;
  final bool persistSession;
  final GatewayCacheService cacheService;
  static const _vault = MethodChannel('sic/session');

  String serverUrl = '';
  String _token = '';
  Map<String, dynamic> user = {}, nodes = {}, pending = {};
  bool connected = false, loading = false, isStale = false;
  String? error;
  DateTime? updatedAt;
  int _generation = 0;
  bool _disposed = false;

  GatewayEventStream? _eventStream;
  GatewayEventStream? get eventStream => _eventStream;
  bool get isSseConnected => _eventStream?.isConnected ?? false;

  final _eventStreamCtrl = StreamController<GatewayEvent>.broadcast();
  Stream<GatewayEvent> get eventStreamBroadcast => _eventStreamCtrl.stream;

  final Map<String, int> _pendingRelays = {};
  final Map<String, bool> _activeDispatches = {};
  final Map<String, _QueuedRelayIntent> _nextIntent = {};

  bool get usesFirebase => false;

  bool get authenticated => _token.isNotEmpty;
  String get token => _token;
  bool get isAdmin => user['role'] == 'admin';
  bool get _android =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  int get generation => _generation;
  String get currentUserId =>
      user['id']?.toString() ?? user['username']?.toString() ?? '';
  SessionScope get currentScope => SessionScope(
        gatewayUrl: serverUrl,
        userId: currentUserId,
        generation: _generation,
      );
  Map<String, int> get pendingRelays => Map.unmodifiable(_pendingRelays);

  bool get hasOnlineSubBox => onlineSubBoxes.isNotEmpty;

  List<Map<String, dynamic>> get onlineSubBoxes {
    final result = <Map<String, dynamic>>[];
    for (final entry in nodes.entries) {
      final node = asMap(entry.value);
      final key = entry.key.toLowerCase();
      final nodeId =
          (node['node_id'] ?? node['device_id'] ?? '').toString().toLowerCase();
      final name = (node['name'] ?? '').toString().toLowerCase();
      final hw = (node['hardware'] ?? asMap(node['firmware'])['hardware'] ?? '')
          .toString()
          .toLowerCase();
      final model =
          (node['model'] ?? node['board_model'] ?? hw).toString().toLowerCase();
      final type =
          (node['device_type'] ?? node['type'] ?? '').toString().toLowerCase();
      final isSubbox = key.startsWith('sb') ||
          nodeId.startsWith('sb') ||
          model.contains('subbox') ||
          type.contains('subbox') ||
          name.contains('subbox');
      final isOnline = node['online'] == true || node['status'] == 'online';
      if (isSubbox && isOnline) {
        final copy = Map<String, dynamic>.from(node);
        if (!copy.containsKey('id') && !copy.containsKey('node_id')) {
          copy['id'] = entry.key;
        }
        result.add(copy);
      }
    }
    return result;
  }

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

  Future<void> restoreLocalSession() async {
    if (!persistSession) return;
    final prefs = await SharedPreferences.getInstance();
    serverUrl = prefs.getString('gateway_server_url') ?? '';

    await prefs.remove('gateway_api_key');
    await prefs.remove('gateway_auth_token');

    if (_android) {
      try {
        final saved = await _vault.invokeMethod<String>('read');
        if (saved != null) {
          final data = asMap(jsonDecode(saved));
          if (data['url'] != null) {
            serverUrl = normalizeServerUrl('${data['url']}').toString();
          }
          _token = data['token'] as String? ?? '';
          if (data['user'] is Map) {
            user = asMap(data['user']);
          }
        }
      } on Exception {
        await _vault.invokeMethod<void>('delete');
      }
    }

    if (serverUrl.isNotEmpty) {
      final snapshot =
          await cacheService.loadSnapshotForGateway(serverUrl, currentUserId);
      if (snapshot != null) {
        if (user.isEmpty && snapshot.user.isNotEmpty) {
          user = Map<String, dynamic>.from(snapshot.user);
        }
        nodes = Map<String, dynamic>.from(snapshot.nodes);
        pending = Map<String, dynamic>.from(snapshot.pending);
        updatedAt = snapshot.capturedAt;
      }
    }

    connected = false;
    isStale = true;
    notifyListeners();
  }

  Future<void> revalidateSession() async {
    if (!authenticated) return;
    final currentGen = _generation;
    loading = true;
    notifyListeners();
    try {
      final me = await request('/api/auth/me');
      if (currentGen != _generation) return;
      if (me['authenticated'] != true) {
        throw const GatewayException(
            'Phiên đăng nhập hết hạn hoặc thông tin không đúng.', 401);
      }
      user = asMap(me['user']);

      final data = await request('/api/nodes');
      if (currentGen != _generation) return;
      if (data['nodes'] is! Map) {
        throw const GatewayException('Gateway thiếu danh sách thiết bị.');
      }
      nodes = asMap(data['nodes']);
      pending = asMap(data['pending']);

      _applyPendingRelays();
      connected = true;
      isStale = false;
      error = null;
      updatedAt = DateTime.now();

      _saveSnapshotToCache();
      startEventStream();
    } on GatewayException catch (e) {
      if (currentGen != _generation) return;
      if (e.statusCode == 401) {
        await _clearSession();
        error = e.message;
      } else {
        connected = false;
        error = e.message;
      }
    } catch (_) {
      if (currentGen != _generation) return;
      connected = false;
      error = 'Không kết nối được Gateway. Kiểm tra mạng và địa chỉ.';
    } finally {
      if (currentGen == _generation) {
        loading = false;
        notifyListeners();
      } else if (!authenticated) {
        loading = false;
      }
    }
  }

  void startEventStream() {
    if (!authenticated || serverUrl.isEmpty) return;
    if (_eventStream != null && !_eventStream!.isClosed) {
      if (_eventStream!.isPaused) {
        _eventStream!.resume();
      }
      return;
    }
    _eventStream?.dispose();
    _eventStream = GatewayEventStream(
      gatewayUrl: () => serverUrl,
      tokenProvider: () => _token,
      httpClientFactory: () => _client,
      closeClientOnDisconnect: false, // REST owns this shared client.
      onEvent: (event) {
        _handleSseEvent(event);
        if (!_eventStreamCtrl.isClosed) {
          _eventStreamCtrl.add(event);
        }
      },
      onGapDetected: () {
        refresh();
      },
      onConnected: () {
        refresh();
        notifyListeners();
      },
      onDisconnected: () {
        notifyListeners();
      },
    );
    _eventStream!.connect();
  }

  void _handleSseEvent(GatewayEvent event) {
    final nodeId =
        (event.data['node_id'] ?? event.data['device_id'])?.toString();
    switch (event.name) {
      case 'relay_state':
        if (nodeId != null && nodes.containsKey(nodeId)) {
          final rl = event.data['relay_state'];
          if (rl is List) {
            nodes[nodeId]['relay_state'] = rl;
          }
        }
        break;
      case 'node_status':
        if (nodeId != null && nodes.containsKey(nodeId)) {
          if (event.data.containsKey('online') ||
              event.data.containsKey('status')) {
            nodes[nodeId]['status'] = (event.data['online'] == true ||
                    event.data['status'] == 'online')
                ? 'online'
                : 'offline';
          }
          if (event.data.containsKey('relay_state') &&
              event.data['relay_state'] is List) {
            nodes[nodeId]['relay_state'] = event.data['relay_state'];
          }
        }
        break;
      case 'node_telemetry':
        if (nodeId != null && nodes.containsKey(nodeId)) {
          if (event.data['channels'] is! Map)
            nodes[nodeId]['pzem'] = event.data;
        }
        break;
      case 'device_deleted':
        if (nodeId != null) {
          nodes.remove(nodeId);
        }
        break;
      case 'device_claimed':
        refresh();
        break;
    }
  }

  Future<void> restore() async {
    await restoreLocalSession();
    if (authenticated) {
      await revalidateSession();
    }
  }

  void _saveSnapshotToCache({bool immediate = false}) {
    if (!persistSession || serverUrl.isEmpty) return;
    final snapshot = CachedSnapshot(
      scope: currentScope,
      revision: 1,
      capturedAt: updatedAt ?? DateTime.now(),
      user: Map<String, dynamic>.from(user),
      nodes: Map<String, dynamic>.from(nodes),
      pending: Map<String, dynamic>.from(pending),
    );
    cacheService.saveSnapshot(snapshot, immediate: immediate);
  }

  Future<Map<String, dynamic>> _send(String url, String path, String token,
      {Map<String, dynamic>? body,
      String? method,
      Duration timeout = const Duration(seconds: 10),
      List<int>? bytes,
      String? filename}) async {
    try {
      final req = http.Request(
          method ?? (body == null && bytes == null ? 'GET' : 'POST'),
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
        String msg = 'Gateway trả về lỗi ${res.statusCode}.';
        try {
          final errData = jsonDecode(utf8.decode(res.bodyBytes));
          if (errData is Map) {
            final code = errData['error_code']?.toString() ??
                errData['error']?.toString();
            final message = errData['message']?.toString();
            if (code != null && message != null && code != message) {
              msg = '[$code] $message';
            } else {
              msg = message ?? code ?? msg;
            }
          }
        } catch (_) {}
        throw GatewayException(msg, res.statusCode);
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

    _generation++;
    _pendingRelays.clear();
    for (final intent in _nextIntent.values) {
      if (!intent.completer.isCompleted) {
        intent.completer.complete({'cancelled': true, 'success': false});
      }
    }
    _nextIntent.clear();
    _activeDispatches.clear();

    serverUrl = url;
    _token = token;
    user = asMap(me['user']);
    nodes = {};
    pending = {};
    error = null;
    connected = true;
    isStale = false;
    loading = false;

    if (persistSession) {
      if (_android) {
        try {
          await _vault.invokeMethod<void>(
              'write', jsonEncode({'url': url, 'token': token, 'user': user}));
        } catch (_) {}
      }
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('gateway_server_url', url);
    }

    notifyListeners();
    await refresh();
    startEventStream();
  }

  Future<Map<String, dynamic>> request(String path,
      {Map<String, dynamic>? body, String? method, Duration? timeout}) async {
    if (!authenticated) {
      throw const GatewayException('Vui lòng đăng nhập.', 401);
    }
    final currentGen = _generation;
    try {
      final res = await _send(serverUrl, path, _token,
          body: body,
          method: method,
          timeout: timeout ?? const Duration(seconds: 10));
      if (currentGen != _generation) {
        throw const GatewayException('Phiên làm việc đã thay đổi');
      }
      return res;
    } on GatewayException catch (e) {
      if (e.statusCode == 401 && currentGen == _generation) {
        await _clearSession();
        error = e.message;
      }
      rethrow;
    }
  }

  Future<void> refresh() async {
    if (loading || !authenticated) return;
    loading = true;
    final currentGen = _generation;
    notifyListeners();
    try {
      final data = await request('/api/nodes');
      if (currentGen != _generation) return;
      if (data['nodes'] is! Map) {
        throw const GatewayException('Gateway thiếu danh sách thiết bị.');
      }
      nodes = asMap(data['nodes']);
      pending = asMap(data['pending']);

      _applyPendingRelays();
      connected = true;
      isStale = false;
      error = null;
      updatedAt = DateTime.now();

      _saveSnapshotToCache();
    } on GatewayException catch (e) {
      if (currentGen == _generation) {
        connected = false;
        error = e.message;
      }
    } catch (_) {
      if (currentGen == _generation) {
        connected = false;
        error = 'Không kết nối được Gateway. Kiểm tra mạng và địa chỉ.';
      }
    } finally {
      if (currentGen == _generation) {
        loading = false;
        notifyListeners();
      } else if (!authenticated) {
        loading = false;
      }
    }
  }

  void _applyPendingRelays() {
    for (final entry in _pendingRelays.entries) {
      final parts = entry.key.split('::');
      if (parts.length == 3) {
        final genStr = parts[0];
        final nodeId = parts[1];
        final channel = parts[2];
        if (genStr != '$_generation') continue;
        final chIdx = channelIndex(channel);
        if (chIdx == null || !nodes.containsKey(nodeId)) continue;
        final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
        final rawRl = node['relay_state'];
        final rl = rawRl is List ? List<dynamic>.from(rawRl) : <dynamic>[];
        while (rl.length <= chIdx) {
          rl.add(0);
        }
        rl[chIdx] = entry.value;
        node['relay_state'] = rl;
        nodes[nodeId] = node;
      } else if (parts.length == 2) {
        final nodeId = parts[0];
        final chIdx = int.tryParse(parts[1]);
        if (chIdx == null || !nodes.containsKey(nodeId)) continue;
        final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
        final rawRl = node['relay_state'];
        final rl = rawRl is List ? List<dynamic>.from(rawRl) : <dynamic>[];
        while (rl.length <= chIdx) {
          rl.add(0);
        }
        rl[chIdx] = entry.value;
        node['relay_state'] = rl;
        nodes[nodeId] = node;
      }
    }
  }

  dynamic _applyOptimisticRelay(
      String nodeId, String channel, bool on, int gen) {
    final chIdx = channelIndex(channel);
    dynamic originalValue;
    final pendingKey = chIdx != null ? '$gen::$nodeId::$channel' : null;

    if (nodes.containsKey(nodeId) && chIdx != null) {
      final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
      final rawRl = node['relay_state'];
      final rl = rawRl is List ? List<dynamic>.from(rawRl) : <dynamic>[];
      while (rl.length <= chIdx) {
        rl.add(0);
      }
      originalValue = rl[chIdx];
      rl[chIdx] = on ? 1 : 0;
      node['relay_state'] = rl;
      nodes[nodeId] = node;
      if (pendingKey != null) {
        _pendingRelays[pendingKey] = on ? 1 : 0;
      }
      notifyListeners();
    }
    return originalValue;
  }

  void _rollbackRelay(String nodeId, String channel, dynamic origVal, int gen) {
    if (gen != _generation) return;
    _pendingRelays.remove('$gen::$nodeId::$channel');
    final chIdx = channelIndex(channel);
    if (chIdx != null && origVal != null && nodes.containsKey(nodeId)) {
      final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
      final rawRl = node['relay_state'];
      if (rawRl is List && rawRl.length > chIdx) {
        final rl = List<dynamic>.from(rawRl);
        rl[chIdx] = origVal;
        node['relay_state'] = rl;
        nodes[nodeId] = node;
        notifyListeners();
      }
    }
  }

  void _confirmRelayInNodes(String nodeId, String channel, bool on) {
    final chIdx = channelIndex(channel);
    if (chIdx != null && nodes.containsKey(nodeId)) {
      final node = Map<String, dynamic>.from(asMap(nodes[nodeId]));
      final rawRl = node['relay_state'];
      final rl = rawRl is List ? List<dynamic>.from(rawRl) : <dynamic>[];
      while (rl.length <= chIdx) {
        rl.add(0);
      }
      rl[chIdx] = on ? 1 : 0;
      node['relay_state'] = rl;
      nodes[nodeId] = node;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>> relay(
      String nodeId, String channel, bool on) async {
    final currentGen = _generation;
    final channelKey = '$nodeId::$channel';

    final originalValue =
        _applyOptimisticRelay(nodeId, channel, on, currentGen);

    if (_activeDispatches[channelKey] == true) {
      final completer = Completer<Map<String, dynamic>>();
      final existing = _nextIntent[channelKey];
      _nextIntent[channelKey] = _QueuedRelayIntent(
        targetState: on,
        completer: completer,
        generation: currentGen,
        originalValue: originalValue,
      );
      if (existing != null && !existing.completer.isCompleted) {
        completer.future.then((res) {
          if (!existing.completer.isCompleted) existing.completer.complete(res);
        }).catchError((err) {
          if (!existing.completer.isCompleted) {
            existing.completer.completeError(err);
          }
        });
      }
      return completer.future;
    }

    _activeDispatches[channelKey] = true;
    bool actualFinalState = on;
    try {
      final res = await _executeSingleRelay(
          nodeId, channel, on, currentGen, originalValue);
      actualFinalState = on;
      return res;
    } catch (_) {
      actualFinalState = (originalValue == 1 || originalValue == true);
      rethrow;
    } finally {
      _drainNextIntent(nodeId, channel, actualFinalState);
    }
  }

  Future<Map<String, dynamic>> _executeSingleRelay(String nodeId,
      String channel, bool on, int currentGen, dynamic originalValue) async {
    final pendingKey = '$currentGen::$nodeId::$channel';
    try {
      final result = await request('/api/relay',
          body: {
            'node_id': nodeId,
            'channel': channel,
            'action': on ? 'turn_on' : 'turn_off',
          },
          timeout: const Duration(seconds: 15));

      if (currentGen != _generation) {
        return {'cancelled': true, 'success': false};
      }

      final verify = result['verify']?.toString().toLowerCase();
      const validVerifications = {
        'success',
        'ack_only',
        'confirmed_load',
        'already_in_state'
      };
      final isSuccess = result['success'] == true &&
          (verify == null || validVerifications.contains(verify));

      if (!isSuccess) {
        _rollbackRelay(nodeId, channel, originalValue, currentGen);
        throw GatewayException(
            result['error']?.toString() ?? 'Relay command failed on gateway');
      }

      _pendingRelays.remove(pendingKey);

      if (currentGen == _generation) {
        await refresh();
      }
      if (currentGen != _generation) {
        return {'cancelled': true, 'success': false};
      }

      _confirmRelayInNodes(nodeId, channel, on);
      return result;
    } catch (e) {
      if (currentGen == _generation) {
        _rollbackRelay(nodeId, channel, originalValue, currentGen);
      }
      if (currentGen != _generation) {
        return {'cancelled': true, 'success': false};
      }
      rethrow;
    }
  }

  void _drainNextIntent(String nodeId, String channel, bool lastState) {
    final channelKey = '$nodeId::$channel';
    final next = _nextIntent.remove(channelKey);
    if (next == null) {
      _activeDispatches.remove(channelKey);
      return;
    }

    if (next.generation != _generation) {
      _activeDispatches.remove(channelKey);
      if (!next.completer.isCompleted) {
        next.completer.complete({'cancelled': true, 'success': false});
      }
      return;
    }

    if (next.targetState == lastState) {
      _activeDispatches.remove(channelKey);
      if (!next.completer.isCompleted) {
        next.completer
            .complete({'success': true, 'verify': 'already_in_state'});
      }
      _drainNextIntent(nodeId, channel, lastState);
      return;
    }

    bool drainState = next.targetState;
    _executeSingleRelay(
      nodeId,
      channel,
      next.targetState,
      next.generation,
      next.originalValue,
    ).then((res) {
      drainState = next.targetState;
      if (!next.completer.isCompleted) next.completer.complete(res);
    }).catchError((err) {
      drainState = (next.originalValue == 1 || next.originalValue == true);
      if (!next.completer.isCompleted) next.completer.completeError(err);
    }).whenComplete(() {
      _drainNextIntent(nodeId, channel, drainState);
    });
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
    String? ch3Name,
    String? ch3Type,
    List<String>? ch3Aliases,
  }) async {
    final currentGen = _generation;
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
      if (ch3Name != null) 'ch3_name': ch3Name,
      if (ch3Type != null) 'ch3_type': ch3Type,
      if (ch3Aliases != null) 'ch3_aliases': ch3Aliases,
    };
    final result = await request('/api/device/update',
        body: body, timeout: const Duration(seconds: 15));
    if (currentGen != _generation) return {'cancelled': true, 'success': false};
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
    final currentGen = _generation;
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
    if (currentGen != _generation) return {'cancelled': true, 'success': false};
    if (result['success'] != true) {
      throw GatewayException(
          '${result['error'] ?? 'Không thể thêm khẩu lệnh'}');
    }
    await refresh();
    return result;
  }

  Future<Map<String, dynamic>> removeDeviceAlias({
    required String deviceId,
    required String alias,
    String? channel,
  }) async {
    final currentGen = _generation;
    final cleanAlias = alias.trim().toLowerCase();
    final body = <String, dynamic>{
      'device_id': deviceId,
      'alias': cleanAlias,
      'action': 'remove',
      if (channel != null) 'channel': channel,
    };
    debugPrint(
        '[VOCAB][TX] sending remove vocabulary to gateway: payload=$body');
    final result = await request('/api/device/alias',
        body: body, timeout: const Duration(seconds: 15));
    if (currentGen != _generation) return {'cancelled': true, 'success': false};
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
    final currentGen = _generation;
    final result = await request('/api/device/delete',
        body: {'device_id': deviceId}, timeout: const Duration(seconds: 15));
    if (currentGen != _generation) return;
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
    String? rl3,
  }) async {
    final currentGen = _generation;
    final body = <String, dynamic>{
      'device_id': deviceId,
      'mac': mac,
      if (name != null) 'name': name,
      if (room != null) 'room': room,
      if (location != null) 'location': location,
      if (description != null) 'description': description,
      if (rl1 != null) 'rl1': rl1,
      if (rl2 != null) 'rl2': rl2,
      if (rl3 != null) 'rl3': rl3,
    };
    final result = await request('/api/provision',
        body: body, timeout: const Duration(seconds: 15));
    if (currentGen != _generation) return {'cancelled': true, 'success': false};
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

  Future<List<CommissioningCandidate>> getCandidates() async {
    final res = await request('/api/commissioning/candidates');
    final list = res['candidates'] as List<dynamic>? ?? const [];
    return list
        .map((item) => CommissioningCandidate.fromJson(asMap(item)))
        .toList();
  }

  Future<({String host, int port})> getProvisioningTarget() async {
    final uri = Uri.tryParse(serverUrl);
    return (
      host: uri?.host.isNotEmpty == true ? uri!.host : '192.168.1.10',
      port: 8883
    );
  }

  Future<DeviceOperation> startClaim({
    required String candidateId,
    String? setupProof,
    required String subboxId,
    required String roomId,
    dynamic channels,
    String? name,
    String? idempotencyKey,
  }) async {
    final body = <String, dynamic>{
      'candidate_id': candidateId,
      if (setupProof != null && setupProof.isNotEmpty)
        'setup_proof': setupProof,
      'subbox_id': subboxId,
      'room_id': roomId,
      if (channels != null) 'channels': channels,
      if (name != null && name.isNotEmpty) 'name': name,
      if (idempotencyKey != null && idempotencyKey.isNotEmpty)
        'idempotency_key': idempotencyKey,
    };
    final res = await request(
      '/api/commissioning/claims',
      body: body,
      timeout: const Duration(seconds: 15),
    );
    final opData = res['operation'] is Map ? asMap(res['operation']) : res;
    return DeviceOperation.fromJson(opData);
  }

  Future<DeviceOperation> identifyDevice(String deviceUid) async {
    final res = await request(
      '/api/devices/$deviceUid/operations',
      body: {'kind': 'identify'},
      timeout: const Duration(seconds: 10),
    );
    final opData = res['operation'] is Map ? asMap(res['operation']) : res;
    return DeviceOperation.fromJson(opData);
  }

  Future<DeviceOperation> startDeviceOperation(
    String deviceUid,
    DeviceOperationKind kind, {
    bool confirmation = false,
    String? idempotencyKey,
  }) async {
    final body = <String, dynamic>{
      'kind': formatDeviceOperationKind(kind),
      if (confirmation) 'confirmation': true,
      if (idempotencyKey != null && idempotencyKey.isNotEmpty)
        'idempotency_key': idempotencyKey,
    };
    final res = await request(
      '/api/devices/$deviceUid/operations',
      body: body,
      timeout: const Duration(seconds: 15),
    );
    final opData = res['operation'] is Map ? asMap(res['operation']) : res;
    return DeviceOperation.fromJson(opData);
  }

  Future<DeviceOperation> removeDeviceFromHome(
    String deviceUid, {
    bool confirmation = true,
  }) async {
    final body = <String, dynamic>{
      'kind': 'remove_from_home',
      'confirmation': confirmation,
    };
    final res = await request(
      '/api/devices/$deviceUid/remove',
      body: body,
      timeout: const Duration(seconds: 15),
    );
    final opData = res['operation'] is Map ? asMap(res['operation']) : res;
    nodes.remove(deviceUid);
    notifyListeners();
    return DeviceOperation.fromJson(opData);
  }

  Future<DeviceOperation> getOperation(String operationId) async {
    final res = await request(
      '/api/operations/$operationId',
      timeout: const Duration(seconds: 10),
    );
    final opData = res['operation'] is Map ? asMap(res['operation']) : res;
    return DeviceOperation.fromJson(opData);
  }

  Future<DeviceOperation> pollOperation(
    String operationId, {
    Duration timeout = const Duration(seconds: 45),
    Duration interval = const Duration(milliseconds: 600),
  }) async {
    final sw = Stopwatch()..start();
    while (sw.elapsed < timeout) {
      final op = await getOperation(operationId);
      if (op.state == DeviceOperationState.succeeded ||
          op.state == DeviceOperationState.failed ||
          op.state == DeviceOperationState.timedOut) {
        return op;
      }
      await Future.delayed(interval);
    }
    return DeviceOperation(
      kind: DeviceOperationKind.claim,
      operationId: operationId,
      deviceUid: '',
      state: DeviceOperationState.timedOut,
      errorCode: 'TIMED_OUT',
      errorMessage: 'Quá thời gian chờ phản hồi từ thiết bị',
    );
  }

  Future<void> _clearSession() async {
    _generation++;
    final oldUrl = serverUrl;
    final oldUid = currentUserId;

    _token = '';
    user = {};
    nodes = {};
    pending = {};
    connected = false;
    isStale = false;
    loading = false;
    updatedAt = null;

    _eventStream?.dispose();
    _eventStream = null;

    _pendingRelays.clear();
    for (final intent in _nextIntent.values) {
      if (!intent.completer.isCompleted) {
        intent.completer.complete({'cancelled': true, 'success': false});
      }
    }
    _nextIntent.clear();
    _activeDispatches.clear();

    if (persistSession) {
      if (_android) {
        try {
          await _vault.invokeMethod<void>('delete');
        } catch (_) {}
      }
      if (oldUrl.isNotEmpty) {
        await cacheService.clearScope(oldUrl, oldUid);
      }
    }
    notifyListeners();
  }

  Future<void> logout() async {
    try {
      if (authenticated) await request('/api/auth/logout', body: {});
    } on GatewayException {
      // Ignore network errors during logout
    }
    await _clearSession();
  }

  @override
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _eventStream?.dispose();
    _eventStream = null;
    _eventStreamCtrl.close();
    for (final intent in _nextIntent.values) {
      if (!intent.completer.isCompleted) {
        intent.completer.complete({'cancelled': true, 'success': false});
      }
    }
    _nextIntent.clear();
    _activeDispatches.clear();
    cacheService.dispose();
    _client.close();
    super.dispose();
  }
}
