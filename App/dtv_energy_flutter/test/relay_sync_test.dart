import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';

void main() {
  test('stale poll cannot undo a relay command and failed ACK rolls back', () async {
    final oldSnapshot = Completer<http.Response>();
    final pollStarted = Completer<void>();
    final command = Completer<http.Response>();
    final commandStarted = Completer<void>();
    var snapshotCount = 0;
    var applied = false;
    var reject = false;
    http.Response snapshot(bool on) => http.Response(jsonEncode({
      'nodes': {'AB1': {'relay_state': [on ? 1 : 0, 1]}}, 'pending': {},
    }), 200);
    final client = GatewayClient(persistSession: false, client: MockClient((req) async {
      if (req.url.path == '/api/auth/me') {
        return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
      }
      if (req.url.path == '/api/relay') {
        if (reject) throw const GatewayException('Network error');
        commandStarted.complete();
        return command.future;
      }
      snapshotCount++;
      if (snapshotCount == 2) {
        pollStarted.complete();
        return oldSnapshot.future;
      }
      return snapshot(applied);
    }));
    addTearDown(client.dispose);
    await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
    final poll = client.refresh();
    await pollStarted.future;
    final sending = client.relay('AB1', 'ch1', true);
    await commandStarted.future;
    expect(client.nodes['AB1']['relay_state'], [1, 1]);
    oldSnapshot.complete(snapshot(false));
    await poll;

    expect(client.nodes['AB1']['relay_state'], [1, 1]);
    applied = true;
    command.complete(http.Response('{"success":true,"verify":"ack_only"}', 200));
    await sending;
    expect(client.nodes['AB1']['relay_state'], [1, 1]);

    reject = true;
    await expectLater(client.relay('AB1', 'ch1', false), throwsA(isA<GatewayException>()));
    expect(client.nodes['AB1']['relay_state'], [1, 1]);
  });

  test('gateway returning success=false rolls back optimistic state and throws GatewayException', () async {
    final client = GatewayClient(persistSession: false, client: MockClient((req) async {
      if (req.url.path == '/api/auth/me') {
        return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
      }
      if (req.url.path == '/api/nodes') {
        return http.Response(jsonEncode({
          'nodes': {
            'AB1': {'relay_state': [0, 0, 0], 'capabilities': ['relay_3ch']}
          },
          'pending': {},
        }), 200);
      }
      if (req.url.path == '/api/relay') {
        return http.Response(jsonEncode({
          'success': false,
          'verify': 'timeout',
          'error': 'Relay command failed on gateway (timeout)',
        }), 200);
      }
      return http.Response('{}', 404);
    }));
    addTearDown(client.dispose);

    await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
    await client.refresh();
    expect(client.nodes['AB1']['relay_state'], [0, 0, 0]);

    // Try to turn on channel 3, gateway returns success: false
    await expectLater(
      client.relay('AB1', 'ch3', true),
      throwsA(isA<GatewayException>().having(
        (e) => e.message,
        'message',
        contains('Relay command failed'),
      )),
    );

    // Ensure state rolled back to original 0 and did NOT overwrite to 1
    expect(client.nodes['AB1']['relay_state'], [0, 0, 0]);
  });
}
