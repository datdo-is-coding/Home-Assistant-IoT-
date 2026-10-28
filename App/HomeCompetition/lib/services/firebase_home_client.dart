import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'gateway_client.dart';

/// Adapts the existing RTDB channel schema to the device/room UI.
class FirebaseHomeClient extends GatewayClient {
  FirebaseHomeClient(
      {FirebaseAuth? auth, FirebaseDatabase? database, http.Client? cloudHttp})
      : _authOverride = auth,
        _databaseOverride = database,
        _cloudHttp = cloudHttp ?? http.Client(),
        super(persistSession: false);

  final http.Client _cloudHttp;
  final FirebaseAuth? _authOverride;
  final FirebaseDatabase? _databaseOverride;
  FirebaseAuth get auth => _authOverride ?? FirebaseAuth.instance;
  FirebaseDatabase get database =>
      _databaseOverride ?? FirebaseDatabase.instance;
  StreamSubscription<User?>? _authSub;
  StreamSubscription<DatabaseEvent>? _devicesSub, _connectionSub;
  Timer? _expiry;
  int _session = 0;
  bool _closed = false, _transportConnected = false, _hasSnapshot = false;
  Map<String, dynamic> _raw = {};
  final Map<String, double> _timestamps = {};
  final Map<String, DateTime> _observed = {};
  String? _commissioningGateway;

  @override
  bool get authenticated => auth.currentUser != null;
  @override
  String get currentUserId => auth.currentUser?.uid ?? '';
  @override
  int get generation => _session;
  @override
  bool get isSseConnected =>
      connected; // Existing UI uses this as stream health.
  @override
  bool get usesFirebase => true;
  @override
  bool get isAdmin => super.isAdmin || user['gateway_configure'] == true;

  @override
  Future<void> restoreLocalSession() async {
    serverUrl = database.databaseURL ??
        'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app';
    _authSub ??= auth.authStateChanges().listen((account) {
      unawaited(_setAccount(account));
    }, onError: _onError);
    await _setAccount(auth.currentUser);
  }

  Future<void> _setAccount(User? account) async {
    final session = ++_session;
    final oldDevices = _devicesSub;
    final oldConnection = _connectionSub;
    _devicesSub = null;
    _connectionSub = null;
    _expiry?.cancel();
    _raw = {};
    nodes = {};
    pending = {};
    user = {};
    _timestamps.clear();
    _observed.clear();
    _commissioningGateway = null;
    connected = _transportConnected = _hasSnapshot = false;
    isStale = true;
    error = null;
    updatedAt = null;
    notifyListeners();
    await oldDevices?.cancel();
    await oldConnection?.cancel();
    if (_closed || session != _session || account == null) return;
    user = {
      'id': account.uid,
      'username': account.email ?? account.displayName ?? 'Thành viên',
      'role': 'user'
    };
    try {
      final token = await account.getIdTokenResult();
      if (_closed || session != _session) return;
      user['role'] = token.claims?['role'] == 'admin' ? 'admin' : 'user';
      _connectionSub = database.ref('.info/connected').onValue.listen((event) {
        if (_closed || session != _session) return;
        _transportConnected = event.snapshot.value == true;
        _publish();
      }, onError: (Object e) {
        if (session == _session) _onError(e);
      });
      _devicesSub = database.ref('devices').onValue.listen((event) {
        if (_closed || session != _session) return;
        applyDevices(event.snapshot.value);
      }, onError: (Object e) {
        if (session == _session) _onError(e);
      });
      _expiry = Timer.periodic(const Duration(seconds: 5), (_) => _publish());
      notifyListeners();
    } catch (e) {
      if (session == _session) _onError(e);
    }
  }

  void _onError(Object failure) {
    if (_closed) return;
    connected = _hasSnapshot = false;
    isStale = true;
    error = failure is FirebaseException && failure.code == 'permission-denied'
        ? 'Tài khoản chưa được cấp quyền đọc dữ liệu Firebase.'
        : 'Không tải được dữ liệu Firebase. Kiểm tra kết nối và thử lại.';
    nodes = {};
    _raw = {};
    _timestamps.clear();
    _observed.clear();
    notifyListeners();
  }

  void applyDevices(Object? value, {DateTime? now}) {
    final time = now ?? DateTime.now();
    _raw = asMap(value);
    for (final entry in _raw.entries) {
      final stamp = readNumber(asMap(entry.value)['last_updated']);
      if (stamp != null) {
        if (_transportConnected &&
            _timestamps.containsKey(entry.key) &&
            _timestamps[entry.key] != stamp) {
          _observed[entry.key] = time;
        }
        _timestamps[entry.key] = stamp;
      }
    }
    _timestamps.removeWhere((key, _) => !_raw.containsKey(key));
    _observed.removeWhere((key, _) => !_raw.containsKey(key));
    _hasSnapshot = true;
    error = null;
    updatedAt = time;
    _publish(now: time);
  }

  void _publish({DateTime? now}) {
    if (_closed) return;
    connected = _transportConnected && _hasSnapshot;
    isStale = !connected;
    nodes =
        firebaseNodes(_raw, now: now ?? DateTime.now(), observed: _observed);
    notifyListeners();
  }

  @override
  Future<void> revalidateSession() async => refresh();
  @override
  void
      startEventStream() {} // RTDB owns subscriptions; never start Gateway SSE.
  @override
  Future<void> refresh() async {
    if (!authenticated) return;
    // onValue owns the snapshot. Reattach only after a cancelled/denied listener.
    if (error != null)
      await _setAccount(auth.currentUser);
    else
      _publish();
  }

  @override
  Future<void> login(
      {required String url,
      required String username,
      required String password}) async {
    await auth.signInWithEmailAndPassword(
        email: username.trim(), password: password);
  }

  @override
  Future<void> loginWithKey({required String url, required String key}) async =>
      throw const GatewayException('Hãy đăng nhập bằng tài khoản Firebase.');
  @override
  Future<void> logout() async {
    await auth.signOut();
    await _setAccount(null);
  }

  @override
  Future<Map<String, dynamic>> relay(
      String nodeId, String channel, bool on) async {
    _publish();
    if (!authenticated || !connected)
      throw const GatewayException('Firebase đang ngoại tuyến.');
    _key(nodeId);
    if (!RegExp(r'^ch[123]$').hasMatch(channel))
      throw const GatewayException('Kênh không hợp lệ.');
    final node = asMap(nodes[nodeId]);
    final ch = asMap(asMap(node['channels'])[channel]);
    if (node['status'] != 'online' || ch['state'] is! bool) {
      throw const GatewayException(
          'Chưa có trạng thái thiết bị mới để điều khiển.');
    }
    final session = _session;
    if (node['core_node_id'] is int) {
      if (ch['logical_device_id'] == null) {
        throw const GatewayException(
            'Hãy gán thiết bị cho kênh này trước khi điều khiển.');
      }
      final key =
          '${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(0x7fffffff)}';
      var command = await _commissioningRequest(
          '/api/v1/channels/command',
          'POST',
          {
            'node_id': node['core_node_id'],
            'channel': int.parse(channel.substring(2)),
            'on': on,
            'idempotency_key': key,
          },
          const Duration(seconds: 10));
      final deadline = DateTime.now().add(const Duration(seconds: 7));
      while (
          command['status'] == 'ACCEPTED' || command['status'] == 'RECEIVED') {
        if (_session != session || DateTime.now().isAfter(deadline)) {
          throw const GatewayException('Chưa nhận được xác nhận từ ActionBox.');
        }
        await Future<void>.delayed(const Duration(milliseconds: 250));
        command = await _commissioningRequest(
            '/api/v1/commands/${command['command_id']}',
            'GET',
            null,
            const Duration(seconds: 5));
      }
      if (_session != session || command['status'] != 'APPLIED') {
        throw const GatewayException('ActionBox chưa xác nhận thực hiện lệnh.');
      }
      return {
        'success': true,
        'status': 'relay_reported',
        'load_confirmed': false
      };
    }
    // Existing firmware consumes this field; a successful write is not a relay ACK.
    await _writeCloud('devices/$nodeId/channels/$channel/state', on);
    if (session != _session)
      throw const GatewayException('Phiên đăng nhập đã thay đổi.');
    return {
      'success': true,
      'status': 'cloud_written',
      'load_confirmed': false
    };
  }

  @override
  Future<Map<String, dynamic>> request(String path,
      {Map<String, dynamic>? body, String? method, Duration? timeout}) async {
    if (!authenticated)
      throw const GatewayException('Vui lòng đăng nhập.', 401);
    if (path == '/api/nodes') return {'nodes': nodes, 'pending': pending};
    if (path == '/api/auth/me') return {'authenticated': true, 'user': user};
    final verb = (method ?? (body == null ? 'GET' : 'POST')).toUpperCase();
    final coreRequest = (path == '/api/kws/config' &&
            ((verb == 'GET' && body == null) ||
                (verb == 'PUT' && body != null))) ||
        (path == '/api/device/update' &&
            body != null &&
            _raw[body['device_id']] is Map &&
            asMap(_raw[body['device_id']])['core_node_id'] is int);
    final commissioningRead = verb == 'GET' &&
        body == null &&
        (path == '/api/commissioning/candidates' ||
            path == '/api/commissioning/context' ||
            RegExp(r'^/api/v1/states/snapshot(?:\?home_id=[A-Za-z0-9_-]+)?$')
                .hasMatch(path) ||
            RegExp(r'^/api/v1/provisioning/CLAIM-[0-9a-f]{24}$')
                .hasMatch(path) ||
            RegExp(r'^/api/operations/[A-Za-z0-9_-]+$').hasMatch(path));
    final commissioningWrite = verb == 'POST' &&
        body != null &&
        (path == '/api/commissioning/claims' ||
            path == '/api/v1/nodes/claim' ||
            path == '/api/v1/provisioning/prepare' ||
            (RegExp(r'^/api/devices/[A-Za-z0-9_:-]+/operations$')
                    .hasMatch(path) &&
                body['kind'] == 'identify'));
    if (commissioningRead || commissioningWrite || coreRequest) {
      return _commissioningRequest(
          path, verb, body, timeout ?? const Duration(seconds: 15));
    }
    if (path == '/api/device/update' && body != null) {
      if (!isAdmin)
        throw const GatewayException(
            'Chỉ quản trị viên được sửa cấu hình.', 403);
      final id = body['device_id'].toString();
      _key(id);
      if (!_raw.containsKey(id))
        throw const GatewayException('Không tìm thấy thiết bị.');
      final updates = <String, Object?>{};
      for (final field in ['name', 'room', 'location', 'description']) {
        if (body.containsKey(field)) updates[field] = body[field];
      }
      for (final channel in ['ch1', 'ch2', 'ch3']) {
        for (final field in ['name', 'type']) {
          if (body.containsKey('${channel}_$field')) {
            updates['channels/$channel/${field == 'type' ? 'device_type' : field}'] =
                body['${channel}_$field'];
          }
        }
      }
      await _writeCloud('devices/$id', updates, patch: true);
      return {'success': true};
    }
    throw const GatewayException(
        'Chức năng này chưa có dịch vụ xử lý trên Firebase.');
  }

  Future<Map<String, dynamic>> _gatewayStatus() async {
    final uid = currentUserId;
    _key(uid);
    final access =
        asMap(await _cloudRest('gateway_access/$uid', method: 'GET'));
    final ids = access.entries
        .where((entry) => entry.value == true)
        .map((entry) => entry.key)
        .toList();
    if (ids.isEmpty) {
      throw const GatewayException(
          'Tài khoản chưa được liên kết với bộ trung tâm. Hãy cấp quyền ghép nối cho tài khoản.');
    }
    if (ids.length != 1) {
      throw const GatewayException(
          'Tài khoản có nhiều bộ trung tâm. Hãy cấu hình một bộ trung tâm để ghép nối.');
    }
    final id = ids.single;
    _key(id);
    if (_commissioningGateway != null && _commissioningGateway != id) {
      throw const GatewayException(
          'Bộ trung tâm đã thay đổi. Hãy đăng nhập lại trước khi ghép nối.');
    }
    final status =
        asMap(await _cloudRest('gateways/$id/status', method: 'GET'));
    final lastSeen = readNumber(status['last_seen']);
    final age = lastSeen == null
        ? null
        : DateTime.now().millisecondsSinceEpoch - lastSeen;
    if (status['online'] != true || age == null || age < -5000 || age > 30000) {
      throw const GatewayException(
          'Bộ trung tâm đang ngoại tuyến. Hãy kiểm tra kết nối rồi quét lại.');
    }
    _commissioningGateway = id;
    return status;
  }

  Future<Map<String, dynamic>> _commissioningRequest(String path, String method,
      Map<String, dynamic>? body, Duration timeout) async {
    final limit = timeout > const Duration(seconds: 30)
        ? const Duration(seconds: 30)
        : timeout;
    final session = _session;
    final uid = currentUserId;
    final clock = Stopwatch()..start();
    void checkSession() {
      if (_closed ||
          session != _session ||
          currentUserId != uid ||
          !connected) {
        throw const GatewayException(
            'Phiên đăng nhập hoặc kết nối đã thay đổi.');
      }
      if (clock.elapsed >= limit) {
        throw const GatewayException(
            'Hết thời gian chờ ghép nối. Hãy quét lại hoặc thử lại để kiểm tra trạng thái.');
      }
    }

    Future<Map<String, dynamic>> exchange() async {
      checkSession();
      await _gatewayStatus();
      checkSession();
      final random = Random.secure();
      final id = List.generate(
              16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'))
          .join();
      final mailbox = 'gateway_rpc/$_commissioningGateway';
      final now = DateTime.now().millisecondsSinceEpoch;
      final expiresAt = now + (limit - clock.elapsed).inMilliseconds;
      await _cloudRest('$mailbox/requests/$uid/$id',
          value: {
            'request_id': id,
            'method': method,
            'path': path,
            'body': body ?? <String, dynamic>{},
            'created_at': now,
            'expires_at': expiresAt,
          },
          deadline: DateTime.fromMillisecondsSinceEpoch(expiresAt));
      while (true) {
        checkSession();
        final response =
            await _cloudRest('$mailbox/responses/$uid/$id', method: 'GET');
        checkSession();
        if (response != null) {
          final envelope = asMap(response);
          final code = envelope['status_code'];
          if (envelope['request_id'] != id ||
              code is! int ||
              envelope['body'] is! Map) {
            throw const GatewayException(
                'Phản hồi ghép nối không hợp lệ. Hãy thử lại.');
          }
          final result = asMap(envelope['body']);
          if (code < 200 || code >= 300 || result['success'] == false) {
            throw GatewayException(
                '${result['message'] ?? result['error'] ?? 'Không thể ghép nối thiết bị.'}',
                code);
          }
          if (result['profile'] == 'core-v1' &&
              (path == '/api/kws/config' ||
                  asMap(result['capabilities'])['configure'] == true)) {
            if (path == '/api/kws/config') {
              result['sources'] ??= <dynamic>[];
              result['bindings'] ??= <dynamic>[];
              result['sync'] ??= <String, dynamic>{};
            }
            user['gateway_configure'] = true;
            notifyListeners();
          }
          return result;
        }
        final remaining = limit - clock.elapsed;
        await Future<void>.delayed(remaining < const Duration(milliseconds: 250)
            ? remaining
            : const Duration(milliseconds: 250));
      }
    }

    try {
      return await exchange().timeout(limit);
    } on TimeoutException {
      throw const GatewayException(
          'Hết thời gian chờ ghép nối. Hãy quét lại hoặc thử lại để kiểm tra trạng thái.');
    }
  }

  @override
  Future<({String host, int port})> getProvisioningTarget() async {
    final status = await _gatewayStatus();
    final host = status['mqtt_host'];
    final port = status['mqtt_port'];
    if (host is! String ||
        host.isEmpty ||
        host.contains('/') ||
        host.contains(RegExp(r'\s')) ||
        host.endsWith('.firebasedatabase.app') ||
        port is! int ||
        port < 1 ||
        port > 65535) {
      throw const GatewayException(
          'Bộ trung tâm chưa có địa chỉ kết nối SubBox hợp lệ.');
    }
    return (host: host, port: port);
  }

  // REST avoids Firebase SDK's offline write queue replaying a relay command later.
  Future<void> _writeCloud(String path, Object? value,
      {bool patch = false}) async {
    await _cloudRest(path, method: patch ? 'PATCH' : 'PUT', value: value);
  }

  Future<Object?> _cloudRest(String path,
      {String method = 'PUT', Object? value, DateTime? deadline}) async {
    final account = auth.currentUser;
    final session = _session;
    if (_closed || account == null || !connected)
      throw const GatewayException('Firebase đang ngoại tuyến.');
    final token = await account.getIdToken();
    if (token == null ||
        session != _session ||
        auth.currentUser?.uid != account.uid ||
        !connected ||
        (deadline != null && !DateTime.now().isBefore(deadline)))
      throw const GatewayException('Phiên đăng nhập đã thay đổi.');
    final base = Uri.parse(serverUrl);
    if (base.scheme != 'https' ||
        !base.host.endsWith('.firebasedatabase.app')) {
      throw const GatewayException('Địa chỉ Firebase không hợp lệ.');
    }
    final url =
        base.replace(path: '/$path.json', queryParameters: {'auth': token});
    final headers = {'Content-Type': 'application/json'};
    http.Response response;
    try {
      response = await (method == 'GET'
              ? _cloudHttp.get(url)
              : method == 'PATCH'
                  ? _cloudHttp.patch(url,
                      headers: headers, body: jsonEncode(value))
                  : _cloudHttp.put(url,
                      headers: headers, body: jsonEncode(value)))
          .timeout(const Duration(seconds: 10));
    } on TimeoutException {
      throw const GatewayException(
          'Chưa xác định được lệnh đã lưu hay chưa. Hãy kiểm tra trạng thái mới.');
    } catch (_) {
      throw const GatewayException(
          'Mất kết nối khi gửi lệnh. Hãy kiểm tra trạng thái mới.');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw GatewayException(
          response.statusCode == 401 || response.statusCode == 403
              ? 'Firebase từ chối quyền ghi của tài khoản.'
              : 'Không lưu được dữ liệu Firebase.',
          response.statusCode);
    }
    if (_closed || session != _session || auth.currentUser?.uid != account.uid)
      throw const GatewayException('Phiên đăng nhập đã thay đổi.');
    try {
      return jsonDecode(response.body);
    } on FormatException {
      throw const GatewayException('Dữ liệu Firebase không hợp lệ.');
    }
  }

  @override
  Future<void> uploadFirmware(String filename, List<int> bytes) async =>
      throw const GatewayException(
          'Chưa có dịch vụ cập nhật firmware qua Firebase.');

  static void _key(String value) {
    if (value.isEmpty || RegExp(r'[.#$\[\]/\x00-\x1f\x7f]').hasMatch(value)) {
      throw const GatewayException('Mã thiết bị không hợp lệ.');
    }
  }

  @override
  void dispose() {
    if (_closed) return;
    _closed = true;
    ++_session;
    _authSub?.cancel();
    _devicesSub?.cancel();
    _connectionSub?.cancel();
    _expiry?.cancel();
    _cloudHttp.close();
    super.dispose();
  }
}

Map<String, dynamic> firebaseNodes(Map<String, dynamic> devices,
    {required DateTime now, Map<String, DateTime> observed = const {}}) {
  final nodes = <String, dynamic>{};
  for (final entry in devices.entries) {
    if (entry.value is! Map) continue;
    final raw = asMap(entry.value);
    final stamp = readNumber(raw['last_updated']);
    // Older simulator sends uptime, not Unix time: require a subsequent update.
    final seconds = stamp == null
        ? null
        : stamp > 100000000000
            ? stamp / 1000
            : stamp;
    DateTime? time =
        seconds != null && seconds >= 1577836800 && seconds < 4102444800
            ? DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round())
            : null;
    final activity = observed[entry.key];
    if (activity != null && (time == null || activity.isAfter(time)))
      time = activity;
    final age = time == null ? null : now.difference(time).inMilliseconds;
    final fresh = age != null && age >= -5000 && age <= 15000;
    final channels = <String, dynamic>{};
    for (final key in ['ch1', 'ch2', 'ch3']) {
      final ch = asMap(asMap(raw['channels'])[key]);
      if (ch.isEmpty) continue;
      double? measure(String field) {
        final value = readNumber(ch[field]);
        return value != null && value >= 0 ? value : null;
      }

      channels[key] = {
        ...ch,
        'device_type': ch['device_type'] ?? 'custom',
        'energy_kwh': measure('energy_kwh'),
        'telemetry': {
          'valid': fresh,
          'received_at':
              time == null ? null : time.millisecondsSinceEpoch / 1000,
          'voltage_v': measure('voltage'),
          'current_ma':
              measure('current') == null ? null : measure('current')! * 1000,
          'power_w': measure('power'),
        },
      };
    }
    nodes[entry.key] = {
      ...raw,
      'firebase': true,
      'device_id': entry.key,
      'name': raw['name']?.toString() ?? entry.key,
      'ip': raw['ip']?.toString() ?? '',
      'subbox_id': raw['subbox_id']?.toString(),
      'parent_subbox': raw['parent_subbox']?.toString(),
      'capabilities': raw['capabilities'] is List
          ? (raw['capabilities'] as List).map((v) => v.toString()).toList()
          : <String>[],
      'status': raw['online'] == true && fresh ? 'online' : 'offline',
      'channels': channels,
      'relay_state': [
        for (final key in ['ch1', 'ch2', 'ch3'])
          if (channels.containsKey(key) || key != 'ch3')
            asMap(channels[key])['state']
      ],
      'pzem': {
        'power': readNumber(raw['total_power']),
        'energy': readNumber(raw['total_energy_kwh'])
      },
      'fw': raw['firmware_version']?.toString() ?? 'Chưa có thông tin',
      'board_model': raw['board_model']?.toString() ?? 'Chưa có thông tin',
      'board_revision':
          raw['board_revision']?.toString() ?? 'Chưa có thông tin',
      'room': raw['room']?.toString() ?? 'Chưa phân phòng',
    };
  }
  return nodes;
}
