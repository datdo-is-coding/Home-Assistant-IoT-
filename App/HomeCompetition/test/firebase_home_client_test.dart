import 'dart:async';
import 'dart:convert';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:home_competition/services/firebase_home_client.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/repositories/smart_home_repository.dart';
import 'package:home_competition/screens/firebase_login_screen.dart';

class _User extends Fake implements User {
  @override
  String get uid => 'alice';
  @override
  String? get email => 'alice@example.test';
  @override
  Future<String?> getIdToken([bool forceRefresh = false]) async => 'test-token';
  @override
  Future<IdTokenResult> getIdTokenResult([bool forceRefresh = false]) async =>
      _Token();
}

class _Token extends Fake implements IdTokenResult {
  @override
  Map<String, dynamic>? get claims => {'role': 'user'};
}

class _Auth extends Fake implements FirebaseAuth {
  User? account = _User();
  final changes = StreamController<User?>.broadcast(sync: true);
  @override
  User? get currentUser => account;
  @override
  Stream<User?> authStateChanges() => changes.stream;
  @override
  Future<void> signOut() async {
    account = null;
    changes.add(null);
  }
}

class _Database extends Fake implements FirebaseDatabase {
  final devices = _Reference();
  final connection = _Reference();
  @override
  String? get databaseURL =>
      'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app';
  @override
  DatabaseReference ref([String? path]) {
    if (path == 'devices') return devices;
    if (path == '.info/connected') return connection;
    throw StateError('Unexpected Firebase path: $path');
  }
}

class _Reference extends Fake implements DatabaseReference {
  final events = StreamController<DatabaseEvent>.broadcast(sync: true);
  @override
  Stream<DatabaseEvent> get onValue => events.stream;
  void send(Object? value) => events.add(_Event(value));
}

class _Event extends Fake implements DatabaseEvent {
  _Event(this.value);
  final Object? value;
  @override
  DataSnapshot get snapshot => _Snapshot(value);
}

class _Snapshot extends Fake implements DataSnapshot {
  _Snapshot(this.value);
  @override
  final Object? value;
}

Map<String, dynamic> fixture(DateTime time,
        {Object? state = false, String channel = 'ch1'}) =>
    {
      'box': {
        'online': true,
        'last_updated': time.millisecondsSinceEpoch,
        'total_power': 12.5,
        'total_energy_kwh': 1.2,
        'channels': {
          channel: {
            'state': state,
            'name': 'Đèn',
            'current': 0.25,
            'voltage': 220,
            'power': 12.5,
            'energy_kwh': 1.2
          }
        },
      },
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  final time = DateTime.utc(2026, 10, 27);
  test(
      'maps cloud schema, per-channel units, and null measurements without invented channels',
      () async {
    final live = DateTime.now();
    final mapped = firebaseNodes(fixture(live, channel: 'ch2'), now: live);
    expect(mapped['box']['channels']['ch2']['telemetry']['current_ma'], 250);
    final client = GatewayClient(persistSession: false)..connected = true;
    final repo = GatewaySmartHomeRepository(client);
    repo.applySnapshot(mapped);
    final devices = await repo.getDevices();
    expect(devices, hasLength(1));
    expect(devices.single.channel, 'ch2');
    expect((await repo.getActionBoxes()).single.channels.single.index, 1);
    expect(devices.single.currentAmps, 0.25);
    expect(devices.single.metadata['energy'], 1.2);
    expect(devices.single.stateText, contains('chưa xác nhận tải'));
    repo.dispose();
    client.dispose();
  });
  test('malformed optional cloud metadata does not crash the reused repository',
      () async {
    final raw = fixture(DateTime.now());
    raw['box'].addAll({
      'name': 123,
      'room': 1,
      'board_model': 2,
      'capabilities': 'not-a-list'
    });
    final client = GatewayClient(persistSession: false)..connected = true;
    final repo = GatewaySmartHomeRepository(client);
    repo.applySnapshot(firebaseNodes(raw, now: DateTime.now()));
    expect((await repo.getActionBoxes()).single.name, '123');
    repo.dispose();
    client.dispose();
  });
  test('stale, future and uptime snapshots do not claim online', () {
    expect(
        firebaseNodes(fixture(time.subtract(const Duration(seconds: 16))),
            now: time)['box']['status'],
        'offline');
    expect(
        firebaseNodes(fixture(time.add(const Duration(minutes: 1))),
            now: time)['box']['status'],
        'offline');
    final raw = fixture(time);
    raw['box']['last_updated'] = 123456;
    expect(firebaseNodes(raw, now: time)['box']['status'], 'offline');
    expect(
        firebaseNodes(raw, now: time, observed: {'box': time})['box']['status'],
        'online');
  });
  test('missing/invalid numbers stay missing; no data is an empty list', () {
    expect(firebaseNodes({}, now: time), isEmpty);
    final raw = fixture(time);
    raw['box']['channels']['ch1'].remove('current');
    raw['box']['channels']['ch1']['power'] = 'NaN';
    final ch =
        firebaseNodes(raw, now: time)['box']['channels']['ch1']['telemetry'];
    expect(ch['current_ma'], isNull);
    expect(ch['power_w'], isNull);
  });

  late _Auth auth;
  late _Database db;
  late FirebaseHomeClient client;
  late List<http.Request> requests;
  int responseStatus = 200;
  Future<http.Response> Function(http.Request)? cloudHandler;
  setUp(() {
    auth = _Auth();
    db = _Database();
    requests = [];
    responseStatus = 200;
    cloudHandler = null;
    client = FirebaseHomeClient(
        auth: auth,
        database: db,
        cloudHttp: MockClient((request) async {
          requests.add(request);
          if (cloudHandler != null) return cloudHandler!(request);
          return http.Response('true', responseStatus);
        }));
  });
  tearDown(() async {
    client.dispose();
    await auth.changes.close();
    await db.devices.events.close();
    await db.connection.events.close();
  });
  Future<void> ready() async {
    await client.restoreLocalSession();
    db.connection.send(true);
    db.devices.send(fixture(DateTime.now()));
  }

  void mailbox({
    Map<String, dynamic>? access,
    Map<String, dynamic>? status,
    int resultStatus = 200,
    Map<String, dynamic>? result,
    bool wrongRequestId = false,
    bool pending = false,
  }) {
    cloudHandler = (request) async {
      final path = request.url.path;
      if (path == '/gateway_access/alice.json') {
        return http.Response(jsonEncode(access ?? {'gw_home': true}), 200);
      }
      if (path == '/gateways/gw_home/status.json') {
        return http.Response(
            jsonEncode(status ??
                {
                  'online': true,
                  'last_seen': DateTime.now().millisecondsSinceEpoch,
                  'mqtt_host': '192.168.11.29',
                  'mqtt_port': 8883,
                }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'});
      }
      if (request.method == 'PUT') return http.Response('null', 200);
      if (path.startsWith('/gateway_rpc/gw_home/responses/alice/')) {
        final id = path.split('/').last.replaceFirst('.json', '');
        return http.Response(
            pending
                ? 'null'
                : jsonEncode({
                    'request_id': wrongRequestId ? 'some-other-request' : id,
                    'status_code': resultStatus,
                    'body': result ?? {'success': true, 'candidates': []},
                  }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'});
      }
      throw StateError('Unexpected cloud request: ${request.method} $path');
    };
  }

  test(
      'existing commissioning calls use an owner-scoped authenticated cloud mailbox',
      () async {
    await ready();
    mailbox(result: {
      'success': true,
      'operation': {
        'operation_id': 'op_cloud',
        'device_uid': 'AB_1',
        'kind': 'claim',
        'state': 'accepted'
      },
    });
    final claim = await client.startClaim(
        candidateId: 'AB_1',
        subboxId: 'SB_1',
        roomId: 'livingroom',
        idempotencyKey: 'claim_retry_key');
    expect(claim.operationId, 'op_cloud');
    await client.getCandidates();
    await client.identifyDevice('AB_1');
    await client.getOperation('op_cloud');
    final writes =
        requests.where((request) => request.method == 'PUT').toList();
    expect(writes, hasLength(4));
    final envelopes =
        writes.map((request) => jsonDecode(request.body) as Map).toList();
    expect(envelopes.map((value) => value['path']), [
      '/api/commissioning/claims',
      '/api/commissioning/candidates',
      '/api/devices/AB_1/operations',
      '/api/operations/op_cloud',
    ]);
    expect(envelopes.map((value) => value['method']),
        ['POST', 'GET', 'POST', 'GET']);
    expect(envelopes.first['body']['idempotency_key'], 'claim_retry_key');
    expect(envelopes[2]['body'], {'kind': 'identify'});
    expect(envelopes.map((value) => value['request_id']).toSet(), hasLength(4));
    for (final request in requests) {
      expect(request.url.scheme, 'https');
      expect(request.url.host, endsWith('.firebasedatabase.app'));
      expect(request.url.queryParameters['auth'], 'test-token');
    }
    for (final request in writes) {
      expect(
          request.url.path, startsWith('/gateway_rpc/gw_home/requests/alice/'));
      final envelope = jsonDecode(request.body);
      expect(envelope['expires_at'], greaterThan(envelope['created_at']));
      expect(envelope.containsKey('token'), isFalse);
    }
  });

  test('unassigned or stale gateway fails without enqueueing a pairing command',
      () async {
    await ready();
    mailbox(access: {});
    await expectLater(client.getCandidates(), throwsA(isA<GatewayException>()));
    mailbox(status: {'online': true, 'last_seen': 1});
    await expectLater(client.getCandidates(), throwsA(isA<GatewayException>()));
    mailbox(access: {'gw_home': true, 'gw_other': true});
    await expectLater(client.getCandidates(), throwsA(isA<GatewayException>()));
    expect(requests.where((request) => request.method == 'PUT'), isEmpty);
  });

  test(
      'cloud mailbox preserves gateway failures and rejects mismatched responses',
      () async {
    await ready();
    mailbox(resultStatus: 409, result: {
      'error': 'SUBBOX_FULL',
      'message': 'SubBox đã đủ 4 ActionBoxes'
    });
    await expectLater(
        client.getCandidates(),
        throwsA(isA<GatewayException>()
            .having((failure) => failure.statusCode, 'status', 409)
            .having(
                (failure) => failure.message, 'message', contains('đủ 4'))));
    mailbox(wrongRequestId: true);
    await expectLater(client.getCandidates(), throwsA(isA<GatewayException>()));
  });

  test('pairing timeout sends once and never replays after reconnection',
      () async {
    await ready();
    mailbox(pending: true);
    await expectLater(
        client.request('/api/commissioning/claims',
            body: {'candidate_id': 'AB_1'},
            timeout: const Duration(milliseconds: 30)),
        throwsA(isA<GatewayException>()));
    expect(requests.where((request) => request.method == 'PUT'), hasLength(1));
    db.connection.send(false);
    db.connection.send(true);
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(requests.where((request) => request.method == 'PUT'), hasLength(1));
  });

  test('logout discards in-flight cloud response from the previous account',
      () async {
    await ready();
    mailbox();
    final respond = Completer<http.Response>();
    final waiting = Completer<void>();
    final handler = cloudHandler!;
    cloudHandler = (request) async {
      if (request.url.path.contains('/responses/')) {
        waiting.complete();
        return respond.future;
      }
      return handler(request);
    };
    final pending = client.getCandidates();
    final assertion = expectLater(pending, throwsA(isA<GatewayException>()));
    await waiting.future;
    await client.logout();
    respond.complete(http.Response('null', 200));
    await assertion;
    expect(client.nodes, isEmpty);
  });

  test(
      'SubBox setup uses its assigned broker metadata and never the Firebase hostname',
      () async {
    await ready();
    mailbox();
    final target = await client.getProvisioningTarget();
    expect(target.host, '192.168.11.29');
    expect(target.port, 8883);
    mailbox(status: {
      'online': true,
      'last_seen': DateTime.now().millisecondsSinceEpoch
    });
    await expectLater(
        client.getProvisioningTarget(), throwsA(isA<GatewayException>()));
    expect(requests.where((request) => request.method == 'PUT'), isEmpty);
  });

  test('auth-scoped realtime data, disconnect, and deletion clear UI correctly',
      () async {
    await ready();
    expect(client.connected, isTrue);
    expect(client.nodes, hasLength(1));
    db.connection.send(false);
    expect(client.connected, isFalse);
    db.devices.send(null);
    expect(client.nodes, isEmpty);
    await client.logout();
    expect(client.authenticated, isFalse);
    expect(client.nodes, isEmpty);
    db.devices.send(fixture(DateTime.now()));
    expect(client.nodes, isEmpty);
  });
  test('permission denied removes data and offers retry without local fallback',
      () async {
    await ready();
    db.devices.events.addError(FirebaseException(
        plugin: 'firebase_database', code: 'permission-denied'));
    expect(client.connected, isFalse);
    expect(client.nodes, isEmpty);
    expect(client.error, contains('chưa được cấp quyền'));
    expect(requests, isEmpty);
  });
  test('relay writes only authenticated HTTPS Firebase, not fake physical ACK',
      () async {
    await ready();
    final result = await client.relay('box', 'ch1', true);
    expect(requests.single.url.host, endsWith('.firebasedatabase.app'));
    expect(requests.single.url.scheme, 'https');
    expect(requests.single.url.path, '/devices/box/channels/ch1/state.json');
    expect(requests.single.url.queryParameters['auth'], 'test-token');
    expect(jsonDecode(requests.single.body), true);
    expect(result['status'], 'cloud_written');
    expect(result['load_confirmed'], false);
    expect(client.nodes['box']['channels']['ch1']['state'], false);
  });
  test(
      'denied writes, offline controls, unknown states and path injection fail',
      () async {
    await ready();
    responseStatus = 403;
    await expectLater(
        client.relay('box', 'ch1', true), throwsA(isA<GatewayException>()));
    await expectLater(
        client.relay('../box', 'ch1', true), throwsA(isA<GatewayException>()));
    db.devices.send(fixture(DateTime.now(), state: null));
    await expectLater(
        client.relay('box', 'ch1', true), throwsA(isA<GatewayException>()));
    db.connection.send(false);
    await expectLater(
        client.relay('box', 'ch1', true), throwsA(isA<GatewayException>()));
    expect(requests, hasLength(1));
  });
  test(
      'uptime becomes fresh only after a changed sample; identical state edits do not refresh it',
      () async {
    await client.restoreLocalSession();
    db.connection.send(true);
    final raw = fixture(DateTime.now());
    raw['box']['last_updated'] = 1200;
    db.devices.send(raw);
    expect(client.nodes['box']['status'], 'offline');
    raw['box']['channels']['ch1']['state'] = true;
    db.devices.send(raw);
    expect(client.nodes['box']['status'], 'offline');
    raw['box']['last_updated'] = 2400;
    db.devices.send(raw);
    expect(client.nodes['box']['status'], 'online');
  });
  testWidgets('revoked read permission stays cleared across expiry refresh',
      (tester) async {
    await ready();
    db.devices.events.addError(FirebaseException(
        plugin: 'firebase_database', code: 'permission-denied'));
    await tester.pump(const Duration(seconds: 6));
    expect(client.nodes, isEmpty);
    expect(client.connected, false);
    client.dispose();
  });
  test('unsupported Gateway operations never fall back to port 8000', () async {
    await ready();
    await expectLater(
        client.request('/api/kws/config'), throwsA(isA<GatewayException>()));
    await expectLater(
        client.request('/api/devices/AB_1/operations',
            body: {'kind': 'factory_reset'}),
        throwsA(isA<GatewayException>()));
    await expectLater(
        client
            .request('/api/devices/../operations', body: {'kind': 'identify'}),
        throwsA(isA<GatewayException>()));
    await expectLater(
        client.request('/api/commissioning/claims', method: 'DELETE', body: {}),
        throwsA(isA<GatewayException>()));
    await expectLater(
        client.uploadFirmware('x.bin', [1]), throwsA(isA<GatewayException>()));
    expect(requests, isEmpty);
  });
  testWidgets(
      'unified login has Firebase email/signup/Google and no Gateway URL',
      (tester) async {
    await tester
        .pumpWidget(MaterialApp(home: FirebaseLoginScreen(client: client)));
    expect(find.text('HomeCompetition'), findsOneWidget);
    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Tiếp tục với Google'), findsOneWidget);
    expect(find.textContaining('Gateway'), findsNothing);
    expect(find.textContaining('8000'), findsNothing);
    await tester.tap(find.text('Chưa có tài khoản? Đăng ký'));
    await tester.pump();
    expect(find.text('Tạo tài khoản Firebase'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
