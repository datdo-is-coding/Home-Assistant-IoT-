import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
  });

  group('Gateway Session Lifecycle & Generation Guard Tests', () {
    test(
        'F3: Switching gateway while relay request is in-flight cancels old response and does not overwrite new session',
        () async {
      final gatewayARelayCompleter = Completer<http.Response>();
      final gatewayARelayStarted = Completer<void>();

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            final isA = req.url.host.contains('gateway-a');
            return http.Response(
              jsonEncode({
                'authenticated': true,
                'user': {
                  'id': isA ? 'user_a' : 'user_b',
                  'role': 'admin',
                  'fullname': isA ? 'User A' : 'User B',
                }
              }),
              200,
              headers: {'content-type': 'application/json'},
            );
          }

          if (req.url.path == '/api/auth/login') {
            return http.Response(
                jsonEncode({'success': true, 'token': 'tok_${req.url.host}'}),
                200);
          }

          if (req.url.path == '/api/nodes') {
            final isA = req.url.host.contains('gateway-a');
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB1': {
                    'name': isA ? 'Box A' : 'Box B',
                    'status': 'online',
                    'relay_state': [0, 0],
                    'channels': {'ch1': {}, 'ch2': {}}
                  }
                },
                'pending': {},
              }),
              200,
            );
          }

          if (req.url.path == '/api/relay') {
            if (req.url.host.contains('gateway-a')) {
              gatewayARelayStarted.complete();
              return gatewayARelayCompleter.future;
            }
            return http.Response('{"success":true,"verify":"confirmed_load"}', 200);
          }

          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      // 1. Login to Gateway A
      await client.login(
        url: 'http://gateway-a:8000',
        username: 'user_a',
        password: 'pwd',
      );
      expect(client.serverUrl, 'http://gateway-a:8000');
      expect(client.currentUserId, 'user_a');
      expect(client.nodes['AB1']['name'], 'Box A');
      expect(client.nodes['AB1']['relay_state'], [0, 0]);
      final genA = client.generation;

      // 2. Fire relay command on Gateway A (turn ON ch1)
      final relayAFuture = client.relay('AB1', 'ch1', true);
      await gatewayARelayStarted.future;

      // Optimistic update should be active on Gateway A
      expect(client.nodes['AB1']['relay_state'], [1, 0]);

      // 3. While relay A is in-flight, switch to Gateway B!
      await client.login(
        url: 'http://gateway-b:8000',
        username: 'user_b',
        password: 'pwd',
      );
      expect(client.serverUrl, 'http://gateway-b:8000');
      expect(client.currentUserId, 'user_b');
      expect(client.generation, greaterThan(genA));
      expect(client.nodes['AB1']['name'], 'Box B');
      expect(client.nodes['AB1']['relay_state'], [0, 0]);
      // Pending relays from session A must be wiped
      expect(client.pendingRelays.isEmpty, isTrue);

      // 4. Complete the delayed response from Gateway A
      gatewayARelayCompleter.complete(http.Response(
        '{"success":true,"verify":"confirmed_load"}',
        200,
      ));
      final relayAResult = await relayAFuture;

      // Result should be marked cancelled
      expect(relayAResult['cancelled'], isTrue);

      // CRITICAL F3 CHECK: Gateway B's node AB1 MUST STILL BE [0, 0]!
      // Old Gateway A's relay response must NOT overwrite Gateway B!
      expect(client.nodes['AB1']['relay_state'], [0, 0]);
      expect(client.nodes['AB1']['name'], 'Box B');
      expect(client.serverUrl, 'http://gateway-b:8000');
    });

    test('Generation increments on login and logout, clearing pending state',
        () async {
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
              '{"authenticated":true,"user":{"id":"u1","role":"user"}}',
              200,
            );
          }
          if (req.url.path == '/api/auth/logout') {
            return http.Response('{"success":true}', 200);
          }
          if (req.url.path == '/api/nodes') {
            return http.Response('{"nodes":{},"pending":{}}', 200);
          }
          return http.Response('{}', 200);
        }),
      );
      addTearDown(client.dispose);

      final gen0 = client.generation;
      await client.loginWithKey(url: 'http://gateway:8000', key: 'key1');
      final gen1 = client.generation;
      expect(gen1, greaterThan(gen0));
      expect(client.authenticated, isTrue);

      await client.logout();
      final gen2 = client.generation;
      expect(gen2, greaterThan(gen1));
      expect(client.authenticated, isFalse);
      expect(client.nodes.isEmpty, isTrue);
      expect(client.pendingRelays.isEmpty, isTrue);
    });

    test('Per-channel coalescing dispatches sequential commands without race',
        () async {
      final networkCommands = <String>[];
      final cmd1Completer = Completer<http.Response>();
      final cmd1Started = Completer<void>();

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
              '{"authenticated":true,"user":{"id":"u1","role":"admin"}}',
              200,
            );
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB1': {
                    'status': 'online',
                    'relay_state': [0, 0],
                    'channels': {'ch1': {}, 'ch2': {}}
                  }
                },
                'pending': {},
              }),
              200,
            );
          }
          if (req.url.path == '/api/relay') {
            final body = jsonDecode(req.body);
            final action = body['action'];
            networkCommands.add(action);
            if (action == 'turn_on') {
              if (!cmd1Started.isCompleted) cmd1Started.complete();
              return cmd1Completer.future;
            }
            return http.Response(
                '{"success":true,"verify":"confirmed_load"}', 200);
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'k');
      await client.refresh();

      // Trigger ON
      final futureOn = client.relay('AB1', 'ch1', true);
      await cmd1Started.future;

      // While ON is in-flight, immediately trigger OFF
      final futureOff = client.relay('AB1', 'ch1', false);

      // Verify only 1 network command was sent so far
      expect(networkCommands, ['turn_on']);

      // Now complete the first command
      cmd1Completer.complete(
          http.Response('{"success":true,"verify":"confirmed_load"}', 200));

      final resOn = await futureOn;
      expect(resOn['success'], isTrue);

      final resOff = await futureOff;
      expect(resOff['success'], isTrue);

      // Both commands dispatched sequentially in correct order
      expect(networkCommands, ['turn_on', 'turn_off']);
      expect(client.nodes['AB1']['relay_state'], [0, 0]);
    });

    test(
        'Per-channel coalescing: ON -> OFF -> ON while first command in-flight coalesces redundant command',
        () async {
      final networkCommands = <String>[];
      final cmd1Completer = Completer<http.Response>();
      final cmd1Started = Completer<void>();

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
              '{"authenticated":true,"user":{"id":"u1","role":"admin"}}',
              200,
            );
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB1': {
                    'status': 'online',
                    'relay_state': [0, 0],
                    'channels': {'ch1': {}, 'ch2': {}}
                  }
                },
                'pending': {},
              }),
              200,
            );
          }
          if (req.url.path == '/api/relay') {
            final body = jsonDecode(req.body);
            final action = body['action'];
            networkCommands.add(action);
            if (!cmd1Started.isCompleted) cmd1Started.complete();
            return cmd1Completer.future;
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'k');
      await client.refresh();

      final f1 = client.relay('AB1', 'ch1', true);
      await cmd1Started.future;

      // While f1 is in-flight, rapid OFF then ON
      final f2 = client.relay('AB1', 'ch1', false);
      final f3 = client.relay('AB1', 'ch1', true);

      cmd1Completer.complete(
          http.Response('{"success":true,"verify":"confirmed_load"}', 200));

      final r1 = await f1;
      await f2;
      final r3 = await f3;

      expect(r1['success'], isTrue);
      expect(r3['success'], isTrue);
      // Redundant command was coalesced because confirmed state matched target ON
      expect(networkCommands, ['turn_on']);
      expect(client.nodes['AB1']['relay_state'], [1, 0]);
    });

    test('401 response automatically clears session and records expired message',
        () async {
      var return401 = false;
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
              '{"authenticated":true,"user":{"id":"u1","role":"admin"}}',
              200,
            );
          }
          if (req.url.path == '/api/nodes') {
            if (return401) {
              return http.Response('{"error":"unauthorized"}', 401);
            }
            return http.Response('{"nodes":{"AB1":{}},"pending":{}}', 200);
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_token');
      expect(client.authenticated, isTrue);
      expect(client.nodes.containsKey('AB1'), isTrue);

      return401 = true;
      await client.refresh();

      expect(client.authenticated, isFalse);
      expect(client.nodes.isEmpty, isTrue);
      expect(client.error, contains('hết hạn'));
    });

    test(
        '401 during refresh/revalidateSession does not deadlock loading flag, and relogin allows refresh to succeed',
        () async {
      var return401 = false;
      var nodeCount = 1;
      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            if (return401) {
              return http.Response('{"authenticated":false}', 401);
            }
            final isUser2 =
                req.headers['Authorization']?.contains('token2') ?? false;
            return http.Response(
              jsonEncode({
                'authenticated': true,
                'user': {'id': isUser2 ? 'u2' : 'u1', 'role': 'admin'}
              }),
              200,
            );
          }
          if (req.url.path == '/api/nodes') {
            if (return401) {
              return http.Response('{"error":"unauthorized"}', 401);
            }
            return http.Response(
              jsonEncode({
                'nodes': {
                  for (var i = 1; i <= nodeCount; i++)
                    'AB$i': {
                      'status': 'online',
                      'relay_state': [0, 0],
                      'channels': {'ch1': {}, 'ch2': {}}
                    }
                },
                'pending': {},
              }),
              200,
            );
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      // 1. Initial login
      await client.loginWithKey(url: 'http://gateway:8000', key: 'token1');
      expect(client.authenticated, isTrue);
      expect(client.loading, isFalse);
      expect(client.nodes.length, 1);

      // 2. Trigger 401 on refresh()
      return401 = true;
      await client.refresh();

      // Session should be cleared and loading MUST be false (no deadlock!)
      expect(client.authenticated, isFalse);
      expect(client.loading, isFalse);
      expect(client.nodes.isEmpty, isTrue);

      // 3. User logs in with a new account/session
      return401 = false;
      nodeCount = 2;
      await client.loginWithKey(url: 'http://gateway:8000', key: 'token2');

      expect(client.authenticated, isTrue);
      expect(client.currentUserId, 'u2');
      expect(client.loading, isFalse);
      expect(client.nodes.length, 2);

      // 4. refresh() works properly without being blocked by loading deadlock
      nodeCount = 3;
      await client.refresh();
      expect(client.loading, isFalse);
      expect(client.nodes.length, 3);

      // 5. Trigger 401 during revalidateSession() as well
      return401 = true;
      await client.revalidateSession();
      expect(client.authenticated, isFalse);
      expect(client.loading, isFalse);

      // Login again and verify refresh still works
      return401 = false;
      nodeCount = 4;
      await client.loginWithKey(url: 'http://gateway:8000', key: 'token3');
      expect(client.authenticated, isTrue);
      expect(client.loading, isFalse);
      expect(client.nodes.length, 4);
    });

    test(
        'When relay fails due to network error, subsequent retry on the same channel is NOT marked already_in_state and is dispatched to network',
        () async {
      final networkCommands = <Map<String, dynamic>>[];
      var shouldFailRelay = true;

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
              '{"authenticated":true,"user":{"id":"u1","role":"admin"}}',
              200,
            );
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB1': {
                    'status': 'online',
                    'relay_state': [0, 0],
                    'channels': {'ch1': {}, 'ch2': {}}
                  }
                },
                'pending': {},
              }),
              200,
            );
          }
          if (req.url.path == '/api/relay') {
            final body = jsonDecode(req.body) as Map<String, dynamic>;
            networkCommands.add(body);
            if (shouldFailRelay) {
              return http.Response('{"error":"relay hardware failure"}', 500);
            }
            return http.Response(
              '{"success":true,"verify":"confirmed_load"}',
              200,
            );
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'k');
      await client.refresh();

      expect(client.nodes['AB1']['relay_state'], [0, 0]);

      // 1. First relay call fails
      shouldFailRelay = true;
      await expectLater(
        client.relay('AB1', 'ch1', true),
        throwsA(isA<GatewayException>()),
      );

      // Verify node relay state rolled back to [0, 0]
      expect(client.nodes['AB1']['relay_state'], [0, 0]);
      expect(networkCommands.length, 1);
      expect(networkCommands.last['action'], 'turn_on');

      // 2. Immediate retry call on same channel with the same target state (turn_on)
      shouldFailRelay = false;
      final retryResult = await client.relay('AB1', 'ch1', true);

      // CRITICAL CHECK: The retry MUST NOT be swallowed or marked 'already_in_state'
      expect(retryResult['verify'], isNot('already_in_state'));
      expect(retryResult['verify'], 'confirmed_load');
      expect(retryResult['success'], isTrue);

      // The network MUST have received the second command
      expect(networkCommands.length, 2);
      expect(networkCommands[1]['action'], 'turn_on');
      expect(client.nodes['AB1']['relay_state'], [1, 0]);
    });

    test(
        'When relay fails, queued retry in-flight is NOT marked already_in_state and is dispatched to network',
        () async {
      final networkCommands = <String>[];
      final cmd1Completer = Completer<http.Response>();
      final cmd1Started = Completer<void>();

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
              '{"authenticated":true,"user":{"id":"u1","role":"admin"}}',
              200,
            );
          }
          if (req.url.path == '/api/nodes') {
            return http.Response(
              jsonEncode({
                'nodes': {
                  'AB1': {
                    'status': 'online',
                    'relay_state': [0, 0],
                    'channels': {'ch1': {}, 'ch2': {}}
                  }
                },
                'pending': {},
              }),
              200,
            );
          }
          if (req.url.path == '/api/relay') {
            final body = jsonDecode(req.body);
            final action = body['action'] as String;
            networkCommands.add(action);
            if (networkCommands.length == 1) {
              if (!cmd1Started.isCompleted) cmd1Started.complete();
              return cmd1Completer.future;
            }
            return http.Response(
              '{"success":true,"verify":"confirmed_load"}',
              200,
            );
          }
          return http.Response('{}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'k');
      await client.refresh();

      final f1 = client.relay('AB1', 'ch1', true);
      await cmd1Started.future;

      // While f1 is in-flight, queue another ON retry
      final f2 = client.relay('AB1', 'ch1', true);

      // Complete f1 with an error
      cmd1Completer.complete(
          http.Response('{"error":"network drop"}', 500));

      // f1 should fail
      await expectLater(f1, throwsA(isA<GatewayException>()));

      // f2 MUST NOT be swallowed or marked already_in_state, it must execute and succeed
      final res2 = await f2;
      expect(res2['success'], isTrue);
      expect(res2['verify'], isNot('already_in_state'));
      expect(res2['verify'], 'confirmed_load');

      // Both commands were sent to network
      expect(networkCommands, ['turn_on', 'turn_on']);
      expect(client.nodes['AB1']['relay_state'], [1, 0]);
    });
  });
}
