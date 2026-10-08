import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';
import 'package:dtv_energy_flutter/repositories/smart_home_repository.dart';

void main() {
  group('Voice Alias Gateway Synchronization & Rollback Tests', () {
    test('addAlias transmits to Gateway, persists in canonical state, and rolls back on failure', () async {
      final List<Map<String, dynamic>> aliasRequests = [];
      var shouldFail = false;
      var currentAliases = <String>['den'];

      http.Response makeNodesResponse() => http.Response(
        jsonEncode({
          'nodes': {
            'livingroom-node01': {
              'status': 'online',
              'room': 'phong_khach',
              'channels': {
                'ch1': {
                  'device_type': 'light',
                  'name': 'Đèn',
                  'aliases': currentAliases,
                },
                'ch2': {
                  'device_type': 'fan',
                  'name': 'Quạt',
                  'aliases': ['quat'],
                }
              }
            }
          },
          'pending': {},
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/nodes') {
            return makeNodesResponse();
          }
          if (req.url.path == '/api/device/alias') {
            final body = jsonDecode(req.body) as Map<String, dynamic>;
            aliasRequests.add(body);
            if (shouldFail) {
              return http.Response('{"success":false,"error":"Gateway internal error"}', 500);
            }
            if (body['action'] == 'add') {
              currentAliases.add(body['alias'] as String);
            } else if (body['action'] == 'remove') {
              currentAliases.remove(body['alias'] as String);
            }
            return http.Response('{"success":true}', 200);
          }
          if (req.url.path == '/api/voice/vocabulary') {
            return http.Response(jsonEncode({
              'success': true,
              'total_active_hotwords': 45,
            }), 200);
          }
          return http.Response('{"error":"Not found"}', 404);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
      final repo = GatewaySmartHomeRepository(client);
      addTearDown(repo.dispose);

      // 1. Initial vocabulary contains 'den'
      var vocab = await repo.getVocabulary();
      expect(vocab.length, 2);
      final ch1Item = vocab.firstWhere((v) => v.deviceId == 'livingroom-node01::ch1');
      expect(ch1Item.aliases, contains('den'));
      expect(ch1Item.aliases.contains('o_cam'), false);

      // 2. Add alias 'o_cam' successfully
      await repo.addAlias('livingroom-node01::ch1', 'o_cam');

      // Verify payload sent over the wire
      expect(aliasRequests.length, 1);
      expect(aliasRequests[0]['device_id'], 'livingroom-node01');
      expect(aliasRequests[0]['channel'], 'ch1');
      expect(aliasRequests[0]['alias'], 'o_cam');
      expect(aliasRequests[0]['action'], 'add');

      // Verify canonical state in repo
      vocab = await repo.getVocabulary();
      var updatedItem = vocab.firstWhere((v) => v.deviceId == 'livingroom-node01::ch1');
      expect(updatedItem.aliases, contains('o_cam'));

      // 3. Remove alias 'o_cam'
      await repo.removeAlias('livingroom-node01::ch1', 'o_cam');
      expect(aliasRequests.length, 2);
      expect(aliasRequests[1]['alias'], 'o_cam');
      expect(aliasRequests[1]['action'], 'remove');

      vocab = await repo.getVocabulary();
      updatedItem = vocab.firstWhere((v) => v.deviceId == 'livingroom-node01::ch1');
      expect(updatedItem.aliases.contains('o_cam'), false);

      // 4. Test Gateway Rejection / Network failure rollback
      shouldFail = true;
      await expectLater(
        repo.addAlias('livingroom-node01::ch1', 'o_cam_failed'),
        throwsA(isA<GatewayException>()),
      );

      // Crucial: alias must NOT remain in vocabulary when gateway failed!
      vocab = await repo.getVocabulary();
      final failedItem = vocab.firstWhere((v) => v.deviceId == 'livingroom-node01::ch1');
      expect(failedItem.aliases.contains('o_cam_failed'), false);

      // 5. Test diagnostic endpoint
      final diag = await client.getVoiceVocabularyDiagnostics();
      expect(diag['total_active_hotwords'], 45);
    });
  });
}
