import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:home_competition/features/actionbox/add_device_flow.dart';
import 'package:home_competition/models/device_lifecycle.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final validCandidateJson = {
    'device_uid': 'AB_V2_001',
    'board_model': 'actionbox_v2',
    'board_revision': 'v2.1',
    'protocol_version': 2,
    'capabilities': ['relay', 'energy_meter', 'voice'],
    'channel_count': 3,
    'subbox_id': 'subbox_master',
    'rssi': -65,
    'first_seen': 1000.0,
    'last_seen': 1020.0,
    'setup_window_expires_at': 9999999999.0,
    'ttl_expires_at': 9999999999.0,
    'state': 'unclaimed',
  };

  final expiredCandidateJson = {
    'device_uid': 'AB_V2_EXP',
    'board_model': 'actionbox_v2',
    'board_revision': 'v2.0',
    'protocol_version': 2,
    'capabilities': ['relay', 'energy_meter'],
    'channel_count': 3,
    'subbox_id': 'subbox_master',
    'rssi': -80,
    'first_seen': 1000.0,
    'last_seen': 1010.0,
    'setup_window_expires_at': 10.0,
    'ttl_expires_at': 10.0,
    'state': 'expired',
  };

  Widget createTestWidget(GatewayClient client) {
    return ProviderScope(
      overrides: [
        gatewayClientProvider.overrideWith((ref) => client),
      ],
      child: const MaterialApp(
        home: AddDeviceFlowScreen(),
      ),
    );
  }

  group('Commissioning Candidate Model Tests', () {
    test('isExpired calculates expiration correctly based on timestamps and state', () {
      final valid = CommissioningCandidate.fromJson(validCandidateJson);
      expect(valid.isExpired(1050.0), isFalse);

      final exp = CommissioningCandidate.fromJson(expiredCandidateJson);
      expect(exp.isExpired(1050.0), isTrue);

      final stateExpired = CommissioningCandidate.fromJson({
        ...validCandidateJson,
        'state': 'expired',
      });
      expect(stateExpired.isExpired(), isTrue);
    });

    test('DeviceOperation handles claim kind, metadata and error message', () {
      const op = DeviceOperation(
        kind: DeviceOperationKind.claim,
        operationId: 'op_123',
        deviceUid: 'AB_V2_001',
        state: DeviceOperationState.accepted,
        errorCode: 'SUBBOX_FULL',
        errorMessage: 'SubBox has reached maximum limit of 4 ActionBoxes',
        metadata: {'test_key': 'test_val'},
      );

      final json = op.toJson();
      expect(json['kind'], 'claim');
      expect(json['error_code'], 'SUBBOX_FULL');
      expect(json['error_message'], contains('maximum limit'));
      expect(json['metadata']['test_key'], 'test_val');

      final deserialized = DeviceOperation.fromJson(json);
      expect(deserialized.kind, DeviceOperationKind.claim);
      expect(deserialized.errorCode, 'SUBBOX_FULL');
      expect(deserialized.errorMessage, contains('maximum limit'));
    });
  });

  group('AddDeviceFlowScreen 4-Step Wizard Widget Tests', () {
    testWidgets('discovery failure is shown with retry and cannot reuse a stale selection', (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var fail = false;
      final client = GatewayClient(persistSession: false, client: MockClient((req) async {
        if (req.url.path == '/api/auth/me') return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
        if (req.url.path == '/api/commissioning/candidates') {
          if (fail) return http.Response('{"error":"Gateway is offline. Reconnect and retry."}', 503);
          return http.Response(jsonEncode({'success': true, 'candidates': [validCandidateJson]}), 200);
        }
        return http.Response('{"nodes":{},"pending":{}}', 200);
      }));
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();
      final next = find.byKey(const Key('step1_next_button'));
      await tester.ensureVisible(next);
      await tester.tap(next);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();
      fail = true;
      final refresh = find.byKey(const Key('refresh_candidates_button'));
      await tester.ensureVisible(refresh);
      await tester.tap(refresh);
      await tester.pumpAndSettle();
      expect(find.text('Gateway is offline. Reconnect and retry.'), findsOneWidget);
      expect(find.text('Quét lại'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.byKey(const Key('step2_next_button'))).onPressed, isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      client.dispose();
    });

    testWidgets('removed discovery candidate clears selection before claim', (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var visible = true;
      final client = GatewayClient(persistSession: false, client: MockClient((req) async {
        if (req.url.path == '/api/auth/me') return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
        if (req.url.path == '/api/commissioning/candidates') return http.Response(jsonEncode({
          'success': true, 'candidates': visible ? [validCandidateJson] : [],
        }), 200);
        return http.Response('{"nodes":{},"pending":{}}', 200);
      }));
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {'subbox_01': {'model': 'subbox_v1', 'online': true, 'name': 'SubBox'}};
      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();
      final next = find.byKey(const Key('step1_next_button'));
      await tester.ensureVisible(next); await tester.tap(next); await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001'))); await tester.pumpAndSettle();
      visible = false;
      final refresh = find.byKey(const Key('refresh_candidates_button'));
      await tester.ensureVisible(refresh); await tester.tap(refresh); await tester.pumpAndSettle();
      expect(tester.widget<FilledButton>(find.byKey(const Key('step2_next_button'))).onPressed, isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      client.dispose();
    });

    testWidgets(
        'Test F1 Regression: Next button in Step 2 is disabled when no candidate is selected',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson, expiredCandidateJson],
              }),
              200,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true, 'name': 'SubBox PK'}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Step 1: Click next to go to Step 2
      final step1Next = find.byKey(const Key('step1_next_button'));
      expect(step1Next, findsOneWidget);
      await tester.ensureVisible(step1Next);
      await tester.pumpAndSettle();
      await tester.tap(step1Next);
      await tester.pumpAndSettle();

      // Step 2: Candidates should be listed
      expect(find.byKey(const Key('candidate_card_AB_V2_001')), findsOneWidget);
      expect(find.byKey(const Key('candidate_card_AB_V2_EXP')), findsOneWidget);

      // F1 Guard: Next button MUST be disabled because no candidate is selected yet
      final step2Next = find.byKey(const Key('step2_next_button'));
      expect(step2Next, findsOneWidget);
      final buttonWidget = tester.widget<FilledButton>(step2Next);
      expect(buttonWidget.onPressed, isNull);
    });

    testWidgets(
        'Test F1 Regression: Next button in Step 2 is disabled when expired candidate is selected',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson, expiredCandidateJson],
              }),
              200,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Go to Step 2
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();

      // Select the EXPIRED candidate
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_EXP')));
      await tester.pumpAndSettle();

      // F1 Guard: Next button MUST remain disabled for expired candidate
      final step2Next = find.byKey(const Key('step2_next_button'));
      final buttonWidget = tester.widget<FilledButton>(step2Next);
      expect(buttonWidget.onPressed, isNull);

      // Now tap the VALID candidate
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();

      // Next button MUST now be enabled!
      final buttonWidgetValid = tester.widget<FilledButton>(step2Next);
      expect(buttonWidgetValid.onPressed, isNotNull);
    });

    testWidgets(
        'Test Identify: Identify button calls identify endpoint for 15s without toggling relay',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final requests = <http.Request>[];

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          requests.add(req);
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson],
              }),
              200,
            );
          }
          if (req.url.path == '/api/devices/AB_V2_001/operations') {
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'identify',
                  'operation_id': 'op_ident_001',
                  'device_uid': 'AB_V2_001',
                  'state': 'running',
                }
              }),
              202,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Go to Step 2
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();

      // Select candidate
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();

      // Tap Identify Button
      final identifyBtn = find.byKey(const Key('identify_button'));
      expect(identifyBtn, findsOneWidget);
      await tester.tap(identifyBtn);
      await tester.pump();

      // Verify HTTP call was made to operations endpoint with kind=identify
      final identifyReq = requests.firstWhere(
        (r) => r.url.path == '/api/devices/AB_V2_001/operations',
      );
      final body = jsonDecode(identifyReq.body);
      expect(body['kind'], 'identify');

      // Verify NO relay command was sent
      final relayReqs = requests.where((r) => r.url.path.contains('relay'));
      expect(relayReqs, isEmpty);

      // Verify UI shows countdown
      expect(find.textContaining('nháy đèn LED'), findsWidgets);
    });

    testWidgets(
        'Test Server Confirmation: Success screen never shown before server returns succeeded state',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      int pollCount = 0;

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson],
              }),
              200,
            );
          }
          if (req.url.path == '/api/commissioning/claims') {
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'claim',
                  'operation_id': 'op_claim_456',
                  'device_uid': 'AB_V2_001',
                  'state': 'accepted',
                }
              }),
              202,
            );
          }
          if (req.url.path == '/api/operations/op_claim_456') {
            pollCount++;
            final state = pollCount < 2 ? 'running' : 'succeeded';
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'claim',
                  'operation_id': 'op_claim_456',
                  'device_uid': 'AB_V2_001',
                  'state': state,
                }
              }),
              200,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Step 1 -> Step 2
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();

      // Select candidate -> Step 3
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step2_next_button')));
      await tester.pumpAndSettle();

      // Step 3 -> Step 4
      await tester.ensureVisible(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();

      // Verify we are at confirmation step and NOT yet success
      await tester.ensureVisible(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('confirm_claim_button')), findsOneWidget);
      expect(find.byKey(const Key('claim_success_view')), findsNothing);

      // Tap confirm button
      await tester.tap(find.byKey(const Key('confirm_claim_button')));
      await tester.pump(const Duration(milliseconds: 100));

      // Before server confirms 'succeeded', success screen MUST NOT appear
      expect(find.byKey(const Key('claim_success_view')), findsNothing);
      expect(find.textContaining('Đang gửi cấu hình'), findsOneWidget);

      // Now pump until poll finishes and returns 'succeeded'
      await tester.pump(const Duration(milliseconds: 700));
      await tester.pumpAndSettle();

      // NOW success view must appear
      expect(find.byKey(const Key('claim_success_view')), findsOneWidget);
      expect(find.text('Đã thêm thành công!'), findsOneWidget);
    });

    testWidgets(
        'Test Retry & Form Retention: When claim fails with SUBBOX_FULL, error is displayed and form data is retained',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson],
              }),
              200,
            );
          }
          if (req.url.path == '/api/commissioning/claims') {
            return http.Response.bytes(
              utf8.encode(jsonEncode({
                'success': false,
                'error': 'SUBBOX_FULL',
                'error_code': 'SUBBOX_FULL',
                'message': 'SubBox đã đủ 4 ActionBoxes',
              })),
              409,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Step 1 -> 2
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();

      // Select candidate -> 3
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step2_next_button')));
      await tester.pumpAndSettle();

      // In Step 3: Enter custom user values
      await tester.enterText(
          find.byKey(const Key('box_name_input')), 'ActionBox Tầng 2');
      await tester.enterText(
          find.byKey(const Key('ch1_name_input')), 'Đèn chùm phòng ngủ');
      await tester.enterText(
          find.byKey(const Key('ch2_name_input')), 'Quạt hút gió');
      await tester.enterText(
          find.byKey(const Key('ch3_name_input')), 'Bình nóng lạnh Ariston');

      // Add a custom alias to ch1
      await tester.ensureVisible(find.byKey(const Key('ch1_new_alias_input')));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.byKey(const Key('ch1_new_alias_input')), 'đèn ngủ ấm');
      await tester.tap(find.byKey(const Key('ch1_add_alias_button')));
      await tester.pumpAndSettle();

      // Step 3 -> 4
      await tester.ensureVisible(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();

      // Confirm claim (fails with 409 SUBBOX_FULL)
      await tester.ensureVisible(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();

      // Verify error banner is shown
      expect(find.byKey(const Key('claim_error_banner')), findsOneWidget);
      expect(find.textContaining('SUBBOX_FULL'), findsWidgets);
      expect(find.byKey(const Key('claim_success_view')), findsNothing);

      // Press "Quay lại chỉnh sửa"
      await tester.ensureVisible(find.byKey(const Key('step4_back_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step4_back_button')));
      await tester.pumpAndSettle();

      // Verify Form Retention: all values must be completely preserved!
      expect(find.text('ActionBox Tầng 2'), findsOneWidget);
      expect(find.text('Đèn chùm phòng ngủ'), findsOneWidget);
      expect(find.text('Quạt hút gió'), findsOneWidget);
      expect(find.text('Bình nóng lạnh Ariston'), findsOneWidget);
      expect(find.text('đèn ngủ ấm'), findsOneWidget);
    });

    testWidgets(
        'Test Vietnamese names & aliases: Vietnamese names and aliases are packaged accurately in claim payload',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      Map<String, dynamic>? capturedPayload;

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson],
              }),
              200,
            );
          }
          if (req.url.path == '/api/commissioning/claims') {
            capturedPayload = jsonDecode(utf8.decode(req.bodyBytes));
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'claim',
                  'operation_id': 'op_vn_123',
                  'device_uid': 'AB_V2_001',
                  'state': 'succeeded',
                }
              }),
              202,
            );
          }
          if (req.url.path == '/api/operations/op_vn_123') {
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'claim',
                  'operation_id': 'op_vn_123',
                  'device_uid': 'AB_V2_001',
                  'state': 'succeeded',
                }
              }),
              200,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Step 1 -> 2 -> select candidate -> 3
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step2_next_button')));
      await tester.pumpAndSettle();

      // Enter rich Vietnamese names
      await tester.enterText(find.byKey(const Key('box_name_input')),
          'Bộ Điều Khiển Phòng Khách');
      await tester.enterText(find.byKey(const Key('ch1_name_input')),
          'Đèn chùm pha lê');
      await tester.ensureVisible(find.byKey(const Key('ch1_new_alias_input')));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.byKey(const Key('ch1_new_alias_input')), 'đèn lớn giữa nhà');
      await tester.tap(find.byKey(const Key('ch1_add_alias_button')));
      await tester.pumpAndSettle();

      // Step 3 -> 4
      await tester.ensureVisible(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();

      // Confirm claim
      await tester.ensureVisible(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();

      // Assert payload contains exact Vietnamese names and aliases
      expect(capturedPayload, isNotNull);
      expect(capturedPayload!['name'], 'Bộ Điều Khiển Phòng Khách');
      final channels = capturedPayload!['channels'] as Map<String, dynamic>;
      expect(channels['ch1']['name'], 'Đèn chùm pha lê');
      expect((channels['ch1']['aliases'] as List), contains('đèn lớn giữa nhà'));
      expect(channels['ch3']['name'], 'Bình nóng lạnh');
      expect((channels['ch3']['aliases'] as List), contains('bình nước nóng'));
    });

    testWidgets(
        'Test SubBox guidance: When no SubBox is online, step 1 shows warning and button to switch to SubBox',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      // No SubBoxes online!
      client.nodes = {};

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Verify warning card is present
      expect(find.byKey(const Key('subbox_warning_card')), findsOneWidget);
      expect(find.text('Chưa có SubBox trực tuyến'), findsOneWidget);

      // Verify button to switch to SubBox
      final switchBtn = find.byKey(const Key('switch_to_subbox_button'));
      expect(switchBtn, findsOneWidget);

      // Tap button to switch
      await tester.tap(switchBtn);
      await tester.pumpAndSettle();

      // Verify we switched to SubBox guidance
      expect(find.text('Hướng dẫn cấp nguồn SubBox:'), findsOneWidget);
    });

    testWidgets(
        'Test Duplicate Tap: Multiple consecutive taps do not send duplicate claim requests',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      int claimRequestCount = 0;

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson],
              }),
              200,
            );
          }
          if (req.url.path == '/api/commissioning/claims') {
            claimRequestCount++;
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'claim',
                  'operation_id': 'op_dup_123',
                  'device_uid': 'AB_V2_001',
                  'state': 'succeeded',
                }
              }),
              202,
            );
          }
          if (req.url.path == '/api/operations/op_dup_123') {
            return http.Response(
              jsonEncode({
                'success': true,
                'operation': {
                  'kind': 'claim',
                  'operation_id': 'op_dup_123',
                  'device_uid': 'AB_V2_001',
                  'state': 'succeeded',
                }
              }),
              200,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Step 1 -> 2 -> 3 -> 4
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step2_next_button')));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step3_next_button')));
      await tester.pumpAndSettle();

      // Tap confirm button twice rapidly without awaiting settle
      await tester.ensureVisible(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('confirm_claim_button')));
      await tester.tap(find.byKey(const Key('confirm_claim_button')));
      await tester.pumpAndSettle();

      // Must only send exactly 1 claim request
      expect(claimRequestCount, 1);
    });
    testWidgets(
        'Test Channel 3 Latching Relay: Step 3 renders 3 channels, Channel 3 has latching badge',
        (tester) async {
      tester.view.physicalSize = const Size(400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/commissioning/candidates') {
            return http.Response(
              jsonEncode({
                'success': true,
                'candidates': [validCandidateJson],
              }),
              200,
            );
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }),
      );
      await client.loginWithKey(url: 'http://gateway:8000', key: 'test_key');
      client.nodes = {
        'subbox_01': {'model': 'subbox_v1', 'online': true}
      };

      await tester.pumpWidget(createTestWidget(client));
      await tester.pumpAndSettle();

      // Step 1 -> 2
      await tester.ensureVisible(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step1_next_button')));
      await tester.pumpAndSettle();

      // Select candidate -> 3
      await tester.tap(find.byKey(const Key('candidate_card_AB_V2_001')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('step2_next_button')));
      await tester.pumpAndSettle();

      // Step 3: verify all 3 channels exist
      expect(find.byKey(const Key('ch1_name_input')), findsOneWidget);
      expect(find.byKey(const Key('ch2_name_input')), findsOneWidget);
      expect(find.byKey(const Key('ch3_name_input')), findsOneWidget);

      // Verify Channel 3 has latching relay badge
      expect(find.byKey(const Key('ch3_latching_badge')), findsOneWidget);
      expect(
        find.text('Kênh 3 - Rơ-le chốt (Latching), giữ trạng thái khi mất điện'),
        findsOneWidget,
      );
    });
  });
}
