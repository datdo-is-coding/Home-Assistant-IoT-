import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';
import 'package:dtv_energy_flutter/screens/home_screen.dart';

void main() {
  test('Gateway address validation rejects credential and URL ambiguity', () {
    expect(GatewayClient.normalizeServerUrl('192.168.1.10:8000/').toString(),
        'http://192.168.1.10:8000');
    expect(GatewayClient.normalizeServerUrl('https://home.example').scheme,
        'https');
    for (final value in [
      '',
      'ftp://host',
      'https://name:secret@host',
      'http://host/?key=1',
      'http://host/#x',
      'http://host/admin',
      'http://bad host'
    ]) {
      expect(() => GatewayClient.normalizeServerUrl(value),
          throwsA(isA<GatewayException>()));
    }
  });

  test(
      'relay state uses channel number, not map insertion order; unknown stays unknown',
      () {
    final node = {
      'channels': {'ch2': {}, 'ch1': {}},
      'relay_state': [1, 0]
    };
    expect(relayState(node, 'ch1'), true);
    expect(relayState(node, 'ch2'), false);
    expect(relayState({}, 'ch1'), isNull);
    expect(readNumber('NaN'), isNull);
    expect(readNumber('Infinity'), isNull);
    expect(readNumber('12.5'), 12.5);
    expect(metric(null, 'W'), '— W');
  });

  test('login, explicit relay command, offline retention and expired session',
      () async {
    var snapshotCode = 200;
    var offline = false;
    final sent = <http.Request>[];
    final service = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          sent.add(req);
          if (req.url.path == '/api/auth/login') {
            expect(jsonDecode(req.body),
                {'username': 'tuan', 'password': 'secret'});
            expect(req.headers.containsKey('Authorization'), false);
            return http.Response(
                jsonEncode({'success': true, 'token': 'session'}), 200);
          }
          expect(req.headers['Authorization'], 'Bearer session');
          expect(req.followRedirects, false);
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                jsonEncode({
                  'authenticated': true,
                  'user': {'id': 1, 'role': 'admin', 'fullname': 'Tuấn'}
                }),
                200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          }
          if (req.url.path == '/api/relay') {
            return http.Response('{"success":true,"verify":"ack_only"}', 200);
          }
          if (offline) throw http.ClientException('offline');
          return http.Response(
              '{"nodes":{"AB1":{"status":"online"}},"pending":{}}',
              snapshotCode);
        }));
    addTearDown(service.dispose);
    await service.login(
        url: 'http://home:8000', username: ' tuan ', password: 'secret');
    expect(service.authenticated && service.connected && service.isAdmin, true);
    expect(service.user['fullname'], 'Tuấn');
    final result = await service.relay('AB1', 'ch2', false);
    expect(result['verify'], 'ack_only');
    expect(jsonDecode(sent.firstWhere((r) => r.url.path == '/api/relay').body),
        {'node_id': 'AB1', 'channel': 'ch2', 'action': 'turn_off'});
    offline = true;
    await service.refresh();
    expect(service.connected, false);
    expect(service.nodes.containsKey('AB1'), true);
    expect(service.authenticated, true);
    offline = false;
    snapshotCode = 401;
    await service.refresh();
    expect(service.authenticated, false);
    expect(service.nodes, isEmpty);
  });

  test('invalid API key cannot replace a valid server session', () async {
    final service = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.headers['Authorization'] == 'Bearer bad') {
            return http.Response('{}', 401);
          }
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"user"}}', 200);
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }));
    addTearDown(service.dispose);
    await service.loginWithKey(url: 'http://first:8000', key: 'good');
    await expectLater(
        service.loginWithKey(url: 'http://second:8000', key: 'bad'),
        throwsA(isA<GatewayException>()));
    expect(service.serverUrl, 'http://first:8000');
    expect(service.authenticated, true);
    expect(service.isAdmin, false);
  });

  test('updateDevice and deleteDevice send expected payloads and update state',
      () async {
    final sent = <http.Request>[];
    final nodesMap = <String, dynamic>{
      'AB1': {'name': 'Box 1', 'room': 'living_room', 'status': 'online'}
    };
    final service = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          sent.add(req);
          if (req.url.path == '/api/auth/login') {
            return http.Response('{"success":true,"token":"session"}', 200);
          }
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"id":1,"role":"admin","fullname":"Tuan"}}',
                200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          }
          if (req.url.path == '/api/device/update') {
            final body = jsonDecode(req.body);
            expect(body['device_id'], 'AB1');
            expect(body['name'], 'Loa Phong Khach');
            expect(body['room'], 'phong_khach');
            nodesMap['AB1'] = {
              'name': 'Loa Phong Khach',
              'room': 'phong_khach',
              'status': 'online'
            };
            return http.Response(
                '{"success":true,"device":{"name":"Loa Phong Khach"}}', 200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          }
          if (req.url.path == '/api/device/delete') {
            final body = jsonDecode(req.body);
            expect(body['device_id'], 'AB1');
            nodesMap.remove('AB1');
            return http.Response('{"success":true,"device_id":"AB1"}', 200,
                headers: {'content-type': 'application/json; charset=utf-8'});
          }
          return http.Response(
              jsonEncode({'nodes': nodesMap, 'pending': {}}), 200,
              headers: {'content-type': 'application/json; charset=utf-8'});
        }));
    addTearDown(service.dispose);
    await service.login(
        url: 'http://home:8000', username: 'tuan', password: 'secret');
    expect(service.nodes.containsKey('AB1'), true);

    // Test updateDevice
    final updateRes = await service.updateDevice(
        deviceId: 'AB1',
        name: 'Loa Phong Khach',
        room: 'phong_khach',
        ch1Name: 'Den chum',
        ch1Type: 'light');
    expect(updateRes['success'], true);
    expect(service.nodes['AB1']?['name'], 'Loa Phong Khach');

    // Test deleteDevice
    await service.deleteDevice('AB1');
    expect(service.nodes.containsKey('AB1'), false);
  });
}
