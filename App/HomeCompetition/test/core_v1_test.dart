import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:home_competition/features/core_v1/core_client.dart';

void main() {
  test('uses bearer token and never invents channels', () async {
    final client = CoreClient('http://127.0.0.1:8081', 'secret',
        httpClient: MockClient((r) async {
      expect(r.headers['Authorization'], 'Bearer secret');
      return http.Response(
          jsonEncode({
            'home_id': 'home',
            'rooms': [],
            'nodes': [],
            'channels': [],
            'devices': [],
            'cursor': 0
          }),
          200);
    }));
    await client.refresh('home');
    expect(client.snapshot!.channels, isEmpty);
    client.dispose();
  });
  test('command acceptance never mutates reported state', () async {
    final client = CoreClient('http://127.0.0.1:8081', 'secret',
        httpClient: MockClient((r) async {
      if (r.method == 'POST')
        return http.Response('{"command_id":"c","status":"ACCEPTED"}', 202);
      return http.Response(
          '{"home_id":"h","rooms":[],"nodes":[],"channels":[{"channel_id":"f:CH1","node_id":1,"number":1,"relay_state":0,"ct_valid":0,"availability":"ONLINE"}],"devices":[],"cursor":1}',
          200);
    }));
    await client.refresh('h');
    await client.command('d', true);
    expect(client.snapshot!.channels.first.on, false);
    expect(client.pending['d'], 'c');
    client.dispose();
  });
  test('typed errors preserve conflict reason', () async {
    final client = CoreClient('http://localhost:8081', 'secret',
        httpClient: MockClient((r) async => http.Response(
            '{"error":{"code":"offline","message":"offline"}}', 409)));
    await expectLater(client.command('d', true),
        throwsA(isA<CoreException>().having((e) => e.code, 'code', 'offline')));
    client.dispose();
  });
  test('invalid CT remains unknown', () {
    final channel = CoreChannel.fromJson({
      'channel_id': 'x',
      'node_id': 1,
      'number': 1,
      'relay_state': null,
      'ct_valid': 0,
      'current_rms_a': 0,
      'availability': 'STALE'
    });
    expect(channel.current, null);
    expect(channel.on, null);
    expect(channel.online, false);
  });
  test('malformed command acceptance can retry with the same idempotency key',
      () async {
    final requests = <Map<String, dynamic>>[];
    final client = CoreClient('http://127.0.0.1:8081', 'secret',
        httpClient: MockClient((r) async {
      requests.add(jsonDecode(r.body) as Map<String, dynamic>);
      return http.Response(
          requests.length == 1
              ? '{}'
              : '{"command_id":"c","status":"ACCEPTED"}',
          202);
    }));
    addTearDown(client.dispose);
    await expectLater(
        client.command('d', true),
        throwsA(isA<CoreException>()
            .having((e) => e.code, 'code', 'invalid_response')));
    expect(client.pending, isEmpty);
    expect(client.commandStatus['d'], 'UNKNOWN');
    expect(client.hasUncertainCommand('d'), isTrue);
    await expectLater(
        client.command('d', false),
        throwsA(
            isA<CoreException>().having((e) => e.code, 'code', 'uncertain')));
    await client.retryUncertain('d');
    expect(requests, hasLength(2));
    expect(requests[1]['idempotency_key'], requests[0]['idempotency_key']);
    expect(client.pending['d'], 'c');
  });
  test('malformed or unrelated polling response cannot complete a command',
      () async {
    var result = <String, dynamic>{};
    final client = CoreClient('http://127.0.0.1:8081', 'secret',
        httpClient: MockClient((r) async => http.Response(
            r.method == 'POST'
                ? '{"command_id":"c","status":"ACCEPTED"}'
                : jsonEncode(result),
            200)));
    addTearDown(client.dispose);
    await client.command('d', true);
    for (final malformed in [
      <String, dynamic>{},
      {'command_id': 'other', 'status': 'APPLIED'},
      {'command_id': 'c', 'status': 'unknown'},
      {'command_id': 'c', 'status': 'APPLIED', 'reason': 123},
    ]) {
      result = malformed;
      await client.checkCommands();
      expect(client.pending['d'], 'c');
      expect(client.commandStatus['d'], 'ACCEPTED');
    }
    result = {'command_id': 'c', 'status': 'APPLIED'};
    await client.checkCommands();
    expect(client.pending, isEmpty);
    expect(client.commandStatus['d'], 'APPLIED');
  });
}
