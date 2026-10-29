import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'gateway_client.dart';

class _RelayView {
  _RelayView(this.on, this.logicalId, this.configRevision, this.bootId);
  final bool on;
  final Object? logicalId, configRevision, bootId;
  bool pending = true;
  int? stateSeq;
  DateTime expires = DateTime.now().add(const Duration(seconds: 20));
}

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
  final Map<String, _RelayView> _relayViews = {};
  final Map<String, Future<Map<String, dynamic>>> _relayQueues = {};

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
  bool get isAdmin =>
      user['gateway_manage'] == true ||
      (super.isAdmin && user['gateway_role'] == null);
  @override
  bool get canConfigure => isAdmin || user['gateway_configure'] == true;

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
    _relayViews.clear();
    _relayQueues.clear();
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
    _relayViews.clear();
    notifyListeners();
  }

  void applyDevices(Object? value, {DateTime? now}) {
    final time = now ?? DateTime.now();
    final incoming = asMap(value);
    for (final entry in incoming.entries) {
      final previous = asMap(_raw[entry.key]);
      final next = asMap(entry.value);
      if (next['core_node_id'] == previous['core_node_id'] &&
          next['home_id'] == previous['home_id'] &&
          next['boot_id'] == previous['boot_id'] &&
          (readNumber(next['config_rev']) ?? 0) <
              (readNumber(previous['config_rev']) ?? 0)) {
        final channels = {...asMap(next['channels'])};
        for (final ch in asMap(previous['channels']).entries) {
          final old = asMap(ch.value);
          channels[ch.key] = {
            ...asMap(channels[ch.key]),
            for (final key in [
              'name',
              'device_type',
              'aliases',
              'logical_device_id'
            ])
              if (old.containsKey(key)) key: old[key]
          };
        }
        incoming[entry.key] = {
          ...next,
          'config_rev': previous['config_rev'],
          'channels': channels
        };
      }
    }
    _raw = incoming;
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
    for (final entry in _relayViews.entries.toList()) {
      final parts = entry.key.split('::');
      final node = asMap(nodes[parts[0]]);
      final channel = asMap(asMap(node['channels'])[parts[1]]);
      final view = entry.value;
      final seq = readNumber(channel['state_seq'])?.toInt();
      if (node['status'] != 'online' ||
          channel['logical_device_id'] != view.logicalId ||
          node['config_rev'] != view.configRevision ||
          node['boot_id'] != view.bootId ||
          DateTime.now().isAfter(view.expires) ||
          (!view.pending &&
              seq != null &&
              view.stateSeq != null &&
              (seq > view.stateSeq! ||
                  (seq == view.stateSeq && channel['state'] == view.on)))) {
        _relayViews.remove(entry.key);
        continue;
      }
      channel['state'] = view.on;
      channel['command_pending'] = view.pending;
      // firebaseNodes owns these maps; replace explicitly rather than mutate _raw.
      node['channels'] = {...asMap(node['channels']), parts[1]: channel};
      final relays = List<dynamic>.from(node['relay_state'] as List);
      relays[int.parse(parts[1].substring(2)) - 1] = view.on;
      node['relay_state'] = relays;
      nodes[parts[0]] = node;
    }
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
    if (!authenticated || !connected)
      throw const GatewayException('Firebase đang ngoại tuyến.');
    final node = asMap(nodes[nodeId]);
    final ch = asMap(asMap(node['channels'])[channel]);
    if (!RegExp(r'^ch[123]$').hasMatch(channel) ||
        node['status'] != 'online' ||
        ch['state'] is! bool) {
      throw const GatewayException(
          'Chưa có trạng thái thiết bị mới để điều khiển.');
    }
    final key = '$nodeId::$channel';
    final session = _session;
    final view = _RelayView(
        on, ch['logical_device_id'], node['config_rev'], node['boot_id']);
    _relayViews[key] = view;
    _publish();
    final previous = _relayQueues[key];
    final operation = () async {
      if (previous != null) {
        try {
          await previous;
        } catch (_) {}
      }
      if (_closed || _session != session)
        throw const GatewayException('Phiên đăng nhập đã thay đổi.');
      final current = asMap(nodes[nodeId]);
      if (asMap(asMap(current['channels'])[channel])['logical_device_id'] !=
              view.logicalId ||
          current['config_rev'] != view.configRevision ||
          current['boot_id'] != view.bootId) {
        throw const GatewayException(
            'Cấu hình thiết bị đã thay đổi. Hãy thử lại.');
      }
      return _relayRequest(nodeId, channel, on);
    }();
    _relayQueues[key] = operation;
    try {
      final result = await operation;
      if (_session == session && identical(_relayViews[key], view)) {
        if (result['status'] == 'cloud_written') {
          _relayViews.remove(key);
        } else {
          view.pending = false;
          view.stateSeq = readNumber(result['state_seq'])?.toInt();
          view.expires = DateTime.now().add(const Duration(seconds: 15));
        }
      }
      return result;
    } finally {
      if (identical(_relayQueues[key], operation)) _relayQueues.remove(key);
      if (_session == session &&
          identical(_relayViews[key], view) &&
          view.pending) _relayViews.remove(key);
      if (_session == session) _publish();
    }
  }

  Future<Map<String, dynamic>> _relayRequest(
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
        'load_confirmed': false,
        'state_seq': command['state_seq'],
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
    final infraredRequest =
        RegExp(r'^/api/v1/ir/(bootstrap|test|receivers/[1-9][0-9]*|remotes(?:/REMOTE-[0-9a-f]{24}(?:/(send|learn|configure))?)?)$')
                .hasMatch(path) &&
            const {'GET', 'POST', 'DELETE'}.contains(verb);
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
    final managementWrite = verb == 'POST' &&
        body != null &&
        RegExp(r'^/api/devices/(AB|SB)[0-9A-F]{12}/(operations|remove)$')
            .hasMatch(path) &&
        const {'reboot', 'factory_reset', 'remove_from_home'}
            .contains(body['kind']);
    if (commissioningRead ||
        commissioningWrite ||
        coreRequest ||
        infraredRequest ||
        managementWrite) {
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
                const {
                      'offline':
                          'ActionBox đang mất kết nối. Hãy kiểm tra nguồn và thử lại.',
                      'config_pending':
                          'Thiết bị đang đồng bộ cấu hình. Hãy thử lại sau giây lát.',
                      'ir_subbox_offline':
                          'SubBox đang ngoại tuyến. Hãy kiểm tra nguồn và mạng.',
                      'ir_receiver_unavailable':
                          'SubBox này chưa lắp mắt thu hồng ngoại.',
                      'ir_expired':
                          'Lệnh đã hết hạn trước khi phát. Hãy kiểm tra kết nối rồi thử lại.',
                      'ir_firmware_required':
                          'SubBox cần bản firmware hỗ trợ hồng ngoại.',
                      'ir_ack_unknown':
                          'Chưa nhận được xác nhận phát. Kiểm tra thiết bị trước khi thử lại.',
                      'ir_previous_unknown':
                          'Lượt trước chưa rõ kết quả. Kiểm tra thiết bị rồi bấm lại.',
                      'ir_busy': 'SubBox đang xử lý remote. Vui lòng chờ.',
                      'ir_learn_timeout':
                          'Chưa thu được tín hiệu. Hướng remote vào mắt thu và thử lại.',
                      'ir_invalid_capture':
                          'Tín hiệu chưa đầy đủ. Đưa remote gần mắt thu và thử lại.',
                      'ir_hardware':
                          'Chưa khởi tạo được phần thu hồng ngoại trên SubBox.',
                      'ir_no_memory':
                          'SubBox đang thiếu bộ nhớ. Hãy thử lại khi không phát loa.',
                      'ir_transmit_failed':
                          'SubBox chưa phát được lệnh hồng ngoại.',
                      'ir_test_required':
                          'Hãy thử bộ mã và xác nhận thiết bị có phản ứng trước khi lưu.',
                      'ir_climate_unsupported':
                          'Bộ mã này cần học từng lệnh từ remote gốc.',
                      'ir_temperature_not_learned':
                          'Chưa học mã cho mức nhiệt độ này.',
                      'ir_power_not_learned':
                          'Chưa học mã bật/tắt riêng từ remote.',
                      'ir_relative_code':
                          'Đây là mã nhấn nút tương đối. Không thể dùng làm mã bật/tắt riêng hoặc đặt nhiệt độ tuyệt đối.',
                      'ir_receiver_firmware_required':
                          'Cần nạp firmware mới hỗ trợ cấu hình mắt thu IR.',
                      'maintenance_firmware_required':
                          'Bo cần firmware mới để nhận lệnh quản trị. Các thiết bị khác vẫn dùng bình thường.',
                      'maintenance_busy':
                          'Bo đang xử lý một thao tác khác. Vui lòng chờ.',
                      'maintenance_ack_unknown':
                          'Chưa xác nhận được kết quả trên bo. Hãy kiểm tra thiết bị trước khi thử lại.',
                      'maintenance_kind_unsupported':
                          'Thao tác này chưa được hỗ trợ trên bo Core. Hãy dùng Khôi phục cài đặt gốc để xóa cấu hình ghép nối.',
                      'children_attached':
                          'SubBox còn ActionBox đang ghép. Hãy gỡ các ActionBox trước.',
                      'confirmation_required':
                          'Cần xác nhận trước khi xóa hoặc reset thiết bị.',
                      'forbidden':
                          'Tài khoản chưa có quyền quản trị nhà cho thao tác này.',
                      'invalid_device_type':
                          'Loại thiết bị chưa hợp lệ. Hãy chọn lại loại và lưu.',
                      'invalid_voice_aliases':
                          'Mỗi kênh có tối đa 8 tên gọi giọng nói, mỗi tên tối đa 120 ký tự.',
                      'room_belongs_to_subbox':
                          'Phòng được gán theo SubBox. Hãy giữ phòng hiện tại của ActionBox.',
                      'ota_in_progress':
                          'Thiết bị đang cập nhật. Hãy thử lại khi cập nhật xong.',
                    }[result['error_code'] ?? result['error']] ??
                    '${result['message'] ?? result['error'] ?? 'Không xử lý được yêu cầu. Hãy thử lại.'}',
                code);
          }
          if (result['profile'] == 'core-v1' &&
              path == '/api/commissioning/context') {
            user['gateway_role'] = result['role'];
            user['gateway_manage'] =
                asMap(result['capabilities'])['manage_devices'] == true;
            user['gateway_configure'] =
                asMap(result['capabilities'])['configure'] == true;
            user['role'] = user['gateway_manage'] == true
                ? 'admin'
                : result['role'] == 'Installer'
                    ? 'installer'
                    : 'member';
            notifyListeners();
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
          if (path == '/api/device/update' && result['configuration'] is Map) {
            final configuration = asMap(result['configuration']);
            final id = configuration['device_id']?.toString();
            if (id != null && _raw.containsKey(id)) {
              final raw = asMap(_raw[id]);
              final channels = {...asMap(raw['channels'])};
              for (final entry in asMap(configuration['channels']).entries) {
                channels[entry.key] = {
                  ...asMap(channels[entry.key]),
                  ...asMap(entry.value)
                };
              }
              _raw[id] = {
                ...raw,
                'config_rev': configuration['config_rev'],
                'channels': channels
              };
              _publish();
            }
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
