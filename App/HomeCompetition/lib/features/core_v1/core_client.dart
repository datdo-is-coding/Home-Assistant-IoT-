import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class CoreException implements Exception {
  final String code, message;
  const CoreException(this.code, this.message);
  @override
  String toString() => message;
}

class CoreHome {
  final String id, name;
  CoreHome.fromJson(Map<String, dynamic> d)
      : id = d['home_id'] as String,
        name = d['name'] as String;
}

class CoreRoomData {
  final String id, homeId, name;
  CoreRoomData.fromJson(Map<String, dynamic> d)
      : id = d['room_id'] as String,
        homeId = d['home_id'] as String,
        name = d['name'] as String;
}

class CoreNodeData {
  final int id;
  final int? parentId;
  final String factoryId,
      homeId,
      model,
      productType,
      registration,
      availability,
      firmware;
  final String? roomId;
  final int configRev;
  CoreNodeData.fromJson(Map<String, dynamic> d)
      : id = d['node_id'] as int,
        parentId = d['parent_id'] as int?,
        factoryId = d['factory_id'] as String,
        homeId = d['home_id'] as String,
        roomId = d['room_id'] as String?,
        model = d['model'] as String,
        productType = d['product_type'] as String,
        registration = d['registration'] as String,
        availability = d['availability'] as String? ?? 'STALE',
        firmware = d['firmware'] as String? ?? 'Chưa báo cáo',
        configRev = d['config_rev'] as int? ?? 0;
  bool get isSubBox => productType == 'SUB_BOX';
}

class CoreDevice {
  final String id, homeId, name, kind;
  final String? channelId;
  CoreDevice.fromJson(Map<String, dynamic> d)
      : id = d['device_id'] as String,
        homeId = d['home_id'] as String,
        name = d['name'] as String,
        kind = d['kind'] as String,
        channelId = d['channel_id'] as String?;
}

class CoreChannel {
  final String id, availability;
  final int nodeId, number, faults, configRev;
  final bool? on;
  final double? current;
  final String? deviceId;
  CoreChannel.fromJson(Map<String, dynamic> d)
      : id = d['channel_id'] as String,
        nodeId = d['node_id'] as int,
        number = d['number'] as int,
        on = d['relay_state'] == null ? null : d['relay_state'] == 1,
        current = d['ct_valid'] == 1
            ? (d['current_rms_a'] as num?)?.toDouble()
            : null,
        availability = d['availability'] as String? ?? 'STALE',
        faults = d['fault_flags'] as int? ?? 0,
        configRev = d['config_rev'] as int? ?? 0,
        deviceId = d['device_id'] as String?;
  bool get online => availability == 'ONLINE';
  String reportedLabel(bool fresh) => !fresh || !online
      ? 'STALE'
      : on == null
          ? 'Chưa có trạng thái'
          : on!
              ? 'ON'
              : 'OFF';
}

class CoreSnapshot {
  final String homeId;
  final List<CoreRoomData> rooms;
  final List<CoreNodeData> nodes;
  final List<CoreDevice> devices;
  final List<CoreChannel> channels;
  CoreSnapshot.fromJson(Map<String, dynamic> d)
      : homeId = d['home_id'] as String,
        rooms = (d['rooms'] as List? ?? const [])
            .map((v) => CoreRoomData.fromJson(v as Map<String, dynamic>))
            .toList(),
        nodes = (d['nodes'] as List? ?? const [])
            .map((v) => CoreNodeData.fromJson(v as Map<String, dynamic>))
            .toList(),
        devices = (d['devices'] as List? ?? const [])
            .map((v) => CoreDevice.fromJson(v as Map<String, dynamic>))
            .toList(),
        channels = (d['channels'] as List? ?? const [])
            .map((v) => CoreChannel.fromJson(v as Map<String, dynamic>))
            .toList();
}

class CoreArtifact {
  final String id, model, version;
  final int size;
  CoreArtifact.fromJson(Map<String, dynamic> d)
      : id = d['artifact_id'] as String,
        model = d['model'] as String,
        version = d['version'] as String,
        size = d['size'] as int;
}

class CoreOtaTarget {
  final int nodeId;
  final String status, version, model;
  final String? reason;
  final double percent;
  CoreOtaTarget.fromJson(Map<String, dynamic> d)
      : nodeId = d['node_id'] as int,
        status = d['status'] as String,
        version = d['version'] as String,
        model = d['model'] as String,
        reason = d['reason'] as String?,
        percent = (d['transfer_percent'] as num).toDouble();
  bool get terminal =>
      ['SUCCEEDED', 'FAILED', 'ROLLED_BACK', 'ABORTED'].contains(status);
}

class CoreOtaJob {
  final String id;
  final double created;
  final List<CoreOtaTarget> targets;
  CoreOtaJob.fromJson(Map<String, dynamic> d)
      : id = d['job_id'] as String,
        created = (d['created'] as num).toDouble(),
        targets = (d['targets'] as List)
            .map((v) => CoreOtaTarget.fromJson(v as Map<String, dynamic>))
            .toList();
}

class CoreEvent {
  final int id;
  final String kind;
  final double created;
  final Map<String, dynamic> data;
  CoreEvent.fromJson(Map<String, dynamic> d)
      : id = d['event_id'] as int,
        kind = d['kind'] as String,
        created = (d['created'] as num).toDouble(),
        data = d['data'] as Map<String, dynamic>;
}

typedef CoreRequestTransport = Future<Map<String, dynamic>> Function(
    String path,
    {required String method,
    Map<String, dynamic>? body,
    Map<String, String>? query});

class CoreClient extends ChangeNotifier {
  final Uri base;
  final String _token;
  final http.Client _http;
  final CoreRequestTransport? _requestTransport;
  CoreSnapshot? snapshot;
  String? error;
  bool connected = false, _disposed = false, _checking = false;
  int _generation = 0;
  String? _home;
  DateTime? updatedAt;
  WebSocket? _socket;
  Timer? _retry, _commands, _watchdog;
  final Map<String, String> pending = {},
      commandStatus = {},
      commandReason = {};
  final Map<String, ({String key, bool state})> _uncertain = {};
  CoreClient(String url, this._token,
      {http.Client? httpClient, CoreRequestTransport? requestTransport})
      : base = Uri.parse(url),
        _requestTransport = requestTransport,
        _http = httpClient ?? http.Client() {
    if (!['http', 'https'].contains(base.scheme) ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        base.hasQuery ||
        base.hasFragment ||
        (base.path.isNotEmpty && base.path != '/')) {
      throw const CoreException('invalid_url', 'Địa chỉ Gateway không hợp lệ');
    }
    if (_token.isEmpty)
      throw const CoreException(
          'unauthorized', 'Nhập access token do quản trị viên cấp.');
  }
  bool get fresh =>
      connected &&
      updatedAt != null &&
      DateTime.now().difference(updatedAt!) < const Duration(seconds: 10);
  Uri uri(String path, [Map<String, String>? query]) =>
      base.replace(path: '/api/v1$path', queryParameters: query);
  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  Future<Map<String, dynamic>> request(String path,
      {String method = 'GET',
      Map<String, dynamic>? body,
      Map<String, String>? query}) async {
    final transport = _requestTransport;
    if (transport != null) {
      return transport(path, method: method, body: body, query: query);
    }
    final req = http.Request(method, uri(path, query))
      ..followRedirects = false
      ..headers['Authorization'] = 'Bearer $_token'
      ..headers['Accept'] = 'application/json';
    if (body != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(body);
    }
    try {
      final response =
          await (() async => http.Response.fromStream(await _http.send(req)))()
              .timeout(const Duration(seconds: 15));
      Map<String, dynamic>? d;
      try {
        d = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      } on Object {
        // Ignore JSON decode error on non-json error responses
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final e = d?['error'] as Map<String, dynamic>?;
        throw CoreException(
            e?['code'] as String? ?? 'http_${response.statusCode}',
            e?['message'] as String? ??
                'Gateway trả lỗi ${response.statusCode}.');
      }
      if (d == null)
        throw const CoreException(
            'invalid_response', 'Phản hồi Gateway không hợp lệ.');
      return d;
    } on CoreException {
      rethrow;
    } on TimeoutException {
      throw const CoreException('timeout',
          'Gateway chưa phản hồi; kết quả thay đổi chưa xác định. Kiểm tra trước khi thử lại.');
    } on Object {
      throw const CoreException('connection',
          'Không kết nối được Gateway. Kiểm tra mạng và địa chỉ.');
    }
  }

  Future<void> refresh(String home) async {
    final generation = _generation;
    final d = await request('/states/snapshot', query: {'home_id': home});
    if (_disposed ||
        generation != _generation ||
        (_home != null && _home != home)) return;
    final next = CoreSnapshot.fromJson(d);
    if (next.homeId != home)
      throw const CoreException(
          'invalid_response', 'Snapshot không thuộc nhà đang chọn.');
    snapshot = next;
    updatedAt = DateTime.now();
    error = null;
    notifyListeners();
  }

  Future<void> connect(String home) async {
    if (_requestTransport != null) {
      _home = home;
      await refresh(home);
      connected = true;
      notifyListeners();
      return;
    }
    final generation = ++_generation;
    _retry?.cancel();
    _watchdog?.cancel();
    connected = false;
    if (_home != home) {
      snapshot = null;
      _home = home;
    }
    notifyListeners();
    await _socket?.close();
    if (_disposed || generation != _generation) return;
    try {
      await refresh(home);
      final ws = await WebSocket.connect(
              uri('/events', {'home_id': home})
                  .replace(scheme: base.scheme == 'https' ? 'wss' : 'ws')
                  .toString(),
              headers: {'Authorization': 'Bearer $_token'})
          .timeout(const Duration(seconds: 10));
      if (_disposed || generation != _generation) {
        await ws.close();
        return;
      }
      _socket = ws;
      _watchdog = Timer.periodic(const Duration(seconds: 3), (_) {
        if (updatedAt == null ||
            DateTime.now().difference(updatedAt!) >
                const Duration(seconds: 10)) {
          ws.close();
          _reconnect(home, generation);
        }
      });
      ws.listen((raw) {
        if (_disposed || generation != _generation) return;
        try {
          final event = jsonDecode(raw as String) as Map<String, dynamic>;
          if (event['type'] == 'snapshot') {
            final next =
                CoreSnapshot.fromJson(event['data'] as Map<String, dynamic>);
            if (next.homeId != home) throw const FormatException();
            snapshot = next;
            updatedAt = DateTime.now();
            connected = true;
            error = null;
            notifyListeners();
            unawaited(checkCommands());
          }
        } on Object {
          error = 'Dữ liệu realtime không hợp lệ';
          connected = false;
          notifyListeners();
        }
      },
          onDone: () => _reconnect(home, generation),
          onError: (Object e) => _reconnect(home, generation),
          cancelOnError: true);
    } on CoreException catch (e) {
      _reconnect(home, generation, e.message);
    } on Object {
      _reconnect(home, generation);
    }
  }

  void _reconnect(String home, int generation, [String? message]) {
    if (_disposed || generation != _generation) return;
    _watchdog?.cancel();
    connected = false;
    error = message ?? 'Mất kết nối — dữ liệu hiển thị có thể đã cũ';
    notifyListeners();
    _retry?.cancel();
    _retry = Timer(const Duration(seconds: 3), () => connect(home));
  }

  Future<void> command(String device, bool state) async {
    if (pending.containsKey(device))
      throw const CoreException('pending', 'Lệnh trước đang chờ xác nhận');
    final previous = _uncertain[device];
    if (previous != null && previous.state != state)
      throw const CoreException('uncertain',
          'Kiểm tra lệnh chưa xác định trước khi gửi trạng thái khác.');
    final random = Random.secure();
    final key = previous?.key ??
        List.generate(16,
                (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'))
            .join();
    _uncertain[device] = (key: key, state: state);
    pending[device] = '';
    commandStatus[device] = 'SENDING';
    notifyListeners();
    try {
      final result = await request(
          '/devices/${Uri.encodeComponent(device)}/command',
          method: 'POST',
          body: {'state': state, 'idempotency_key': key});
      if (_disposed) return;
      _validateCommandResult(result);
      pending[device] = result['command_id'] as String;
      commandStatus[device] = result['status'] as String;
      _uncertain.remove(device);
      _resolve(device, result);
      _commands ??=
          Timer.periodic(const Duration(seconds: 2), (_) => checkCommands());
    } on CoreException catch (e) {
      pending.remove(device);
      final ambiguous =
          ['timeout', 'connection', 'invalid_response'].contains(e.code) ||
              e.code.startsWith('http_5');
      commandStatus[device] = ambiguous ? 'UNKNOWN' : 'FAILED';
      commandReason[device] = e.message;
      if (!ambiguous) _uncertain.remove(device);
      rethrow;
    } finally {
      notifyListeners();
    }
  }

  bool hasUncertainCommand(String device) => _uncertain.containsKey(device);
  Future<void> retryUncertain(String device) =>
      command(device, _uncertain[device]!.state);
  void _validateCommandResult(Map<String, dynamic> result,
      [String? expectedId]) {
    final id = result['command_id'];
    if (id is! String ||
        id.isEmpty ||
        (expectedId != null && id != expectedId) ||
        !['RECEIVED', 'ACCEPTED', 'APPLIED', 'FAILED', 'TIMEOUT']
            .contains(result['status']) ||
        (result['reason'] != null && result['reason'] is! String)) {
      throw const CoreException(
          'invalid_response', 'Phản hồi trạng thái lệnh không hợp lệ.');
    }
  }

  void _resolve(String device, Map<String, dynamic> result) {
    commandStatus[device] = result['status'] as String;
    if (result['reason'] != null) {
      commandReason[device] = result['reason'] as String;
    } else {
      commandReason.remove(device);
    }
    if (['APPLIED', 'FAILED', 'TIMEOUT'].contains(result['status']))
      pending.remove(device);
  }

  Future<void> checkCommands() async {
    if (_checking || _disposed) return;
    _checking = true;
    try {
      for (final entry in Map<String, String>.from(pending).entries) {
        if (entry.value.isEmpty) continue;
        try {
          final result =
              await request('/commands/${Uri.encodeComponent(entry.value)}');
          if (_disposed) return;
          _validateCommandResult(result, entry.value);
          _resolve(entry.key, result);
          notifyListeners();
        } on CoreException {
          // Command will be retried or handled on next cycle
        }
      }
      if (pending.isEmpty) {
        _commands?.cancel();
        _commands = null;
      }
    } finally {
      _checking = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    ++_generation;
    _retry?.cancel();
    _commands?.cancel();
    _watchdog?.cancel();
    _socket?.close();
    _http.close();
    super.dispose();
  }
}
