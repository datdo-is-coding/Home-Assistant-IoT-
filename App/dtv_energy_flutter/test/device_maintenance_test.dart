import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:dtv_energy_flutter/features/actionbox/action_box_detail_screen.dart';
import 'package:dtv_energy_flutter/models/action_box.dart';
import 'package:dtv_energy_flutter/models/device.dart';
import 'package:dtv_energy_flutter/providers/smart_home_providers.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final sampleChannels = [
    const ActionBoxChannel(index: 0, channelKey: 'ch1', name: 'Đèn chính phòng khách', type: DeviceType.light, isOn: true),
    const ActionBoxChannel(index: 1, channelKey: 'ch2', name: 'Quạt trần phòng khách', type: DeviceType.fan, isOn: false),
    const ActionBoxChannel(index: 2, channelKey: 'ch3', name: 'Bình nóng lạnh', type: DeviceType.socket, isOn: false),
  ];

  final sampleActionBoxV2 = ActionBox(
    id: 'ab_v2_living',
    name: 'ActionBox Phòng Khách',
    roomId: 'living_room',
    online: true,
    channels: sampleChannels,
    firmwareVersion: 'v2.1.0-esp32s3',
    boardModel: 'actionbox_v2',
    boardRevision: 'v2.1',
    subboxId: 'subbox_01',
    signalStrength: -62,
    ownerEpoch: 2,
    capabilities: const ['relay', 'energy_meter', 'voice'],
    protocolVersion: 2,
  );

  const sampleSubBox = ActionBox(
    id: 'subbox_01',
    name: 'SubBox Trung Tâm',
    roomId: 'living_room',
    online: true,
    channels: [],
    firmwareVersion: 'v2.1.0-subbox',
    boardModel: 'subbox_v1',
    boardRevision: 'v1.2',
    signalStrength: -50,
    ownerEpoch: 1,
    capabilities: ['mesh_router', 'audio_bridge'],
    protocolVersion: 2,
  );

  Widget createTestWidget({
    required GatewayClient client,
    required ActionBox actionBox,
  }) {
    return ProviderScope(
      overrides: [
        gatewayClientProvider.overrideWith((ref) => client),
        actionBoxesStreamProvider.overrideWith((ref) => Stream.value([actionBox])),
      ],
      child: MaterialApp(
        home: FeatureActionBoxDetailScreen(actionBoxId: actionBox.id),
      ),
    );
  }

  Future<GatewayClient> createTestClient({
    String role = 'admin',
    Future<http.Response> Function(http.Request req)? handler,
  }) async {
    final client = GatewayClient(
      persistSession: false,
      client: MockClient((req) async {
        if (req.url.path == '/api/auth/me') {
          return http.Response(
            jsonEncode({
              'authenticated': true,
              'user': {'id': role == 'admin' ? 1 : 2, 'username': role, 'role': role},
            }),
            200,
          );
        }
        if (handler != null) {
          return await handler(req);
        }
        return http.Response('{"success": true}', 200);
      }),
    );
    await client.loginWithKey(url: 'http://gateway:8000', key: 'test_token');
    return client;
  }

  group('ActionBox & SubBox Maintenance Tests (Task T11)', () {
    testWidgets('Test Role Guard: Member sees admin banner and is blocked from reboot', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'member');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      // Check admin required banner is displayed
      expect(find.byKey(const Key('admin_required_banner')), findsOneWidget);

      // Attempt to tap reboot tile
      final rebootTile = find.byKey(const Key('reboot_tile'));
      expect(rebootTile, findsOneWidget);
      await tester.tap(rebootTile);
      await tester.pumpAndSettle();

      // Shows admin required dialog, NOT reboot confirm dialog
      expect(find.text('Yêu cầu quyền Quản trị'), findsOneWidget);
      expect(find.byKey(const Key('reboot_confirm_dialog')), findsNothing);
    });

    testWidgets('Test Admin User: Reboot dialog contains board name, model and affected channels', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      // Admin banner is NOT displayed
      expect(find.byKey(const Key('admin_required_banner')), findsNothing);

      // Tap reboot tile
      await tester.tap(find.byKey(const Key('reboot_tile')));
      await tester.pumpAndSettle();

      // Verify dialog details
      expect(find.byKey(const Key('reboot_confirm_dialog')), findsOneWidget);
      expect(find.textContaining('ActionBox Phòng Khách'), findsWidgets);
      expect(find.textContaining('ACTIONBOX_V2'), findsOneWidget);
      expect(find.textContaining('3 kênh rơ-le phụ tải'), findsOneWidget);
      expect(find.textContaining('Đèn chính phòng khách, Quạt trần phòng khách, Bình nóng lạnh'), findsOneWidget);
    });

    testWidgets('Test Identify: Triggers 15s countdown and does NOT send relay command', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      bool identifyCalled = false;
      bool relayCalled = false;

      final client = await createTestClient(
        role: 'admin',
        handler: (request) async {
          if (request.url.path.contains('/operations') && request.method == 'POST') {
            final body = json.decode(request.body);
            if (body['kind'] == 'identify') {
              identifyCalled = true;
              return http.Response(json.encode({
                'success': true,
                'operation': {
                  'operation_id': 'op_ident_123',
                  'kind': 'identify',
                  'device_uid': 'ab_v2_living',
                  'state': 'running',
                }
              }), 202);
            }
          }
          if (request.url.path.contains('/relay') || request.url.path.contains('/control')) {
            relayCalled = true;
          }
          return http.Response('{"success": true}', 200);
        },
      );

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      final identifyBtn = find.byKey(const Key('identify_button'));
      expect(identifyBtn, findsOneWidget);
      await tester.tap(identifyBtn);
      await tester.pump();

      expect(identifyCalled, isTrue);
      expect(relayCalled, isFalse);
      expect(find.textContaining('Đang nhấp nháy đèn LED'), findsOneWidget);
    });

    testWidgets('Test Reboot Execution: Dispatches reboot and polls operation until succeeded', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      int pollCount = 0;
      final client = await createTestClient(
        role: 'admin',
        handler: (request) async {
          if (request.url.path.endsWith('/operations') && request.method == 'POST') {
            return http.Response(json.encode({
              'success': true,
              'operation': {
                'operation_id': 'op_reboot_999',
                'kind': 'reboot',
                'device_uid': 'ab_v2_living',
                'state': 'running',
              }
            }), 202);
          }
          if (request.url.path.contains('/operations/op_reboot_999')) {
            pollCount++;
            final state = pollCount >= 2 ? 'succeeded' : 'awaiting_reconnect';
            return http.Response(json.encode({
              'success': true,
              'operation': {
                'operation_id': 'op_reboot_999',
                'kind': 'reboot',
                'device_uid': 'ab_v2_living',
                'state': state,
              }
            }), 200);
          }
          if (request.url.path == '/api/nodes') {
            return http.Response('{"success": true, "nodes": {}}', 200);
          }
          return http.Response('{"success": true}', 200);
        },
      );

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      // Open reboot dialog
      await tester.tap(find.byKey(const Key('reboot_tile')));
      await tester.pumpAndSettle();

      // Confirm reboot
      await tester.tap(find.byKey(const Key('confirm_reboot_button')));
      await tester.pump();

      // Progress overlay should be shown
      expect(find.byKey(const Key('operation_progress_card')), findsOneWidget);

      // Fast-forward polling
      await tester.pump(const Duration(milliseconds: 800));
      await tester.pump(const Duration(milliseconds: 800));
      await tester.pumpAndSettle();

      expect(find.text('Thao tác hoàn tất thành công!'), findsOneWidget);
      expect(find.byKey(const Key('operation_dismiss_button')), findsOneWidget);
    });

    testWidgets('Test Network Reset Dialog: Shows data preserved vs data erased', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('network_reset_tile')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('network_reset_confirm_dialog')), findsOneWidget);
      expect(find.textContaining('DỮ LIỆU ĐƯỢC BẢO LƯU'), findsOneWidget);
      expect(find.textContaining('calibration'), findsOneWidget);
      expect(find.textContaining('DỮ LIỆU BỊ ĐẶT LẠI'), findsOneWidget);
      expect(find.byKey(const Key('confirm_network_reset_button')), findsOneWidget);
    });

    testWidgets('Test Factory Reset Dialog: High danger warning, lists erased data vs preserved calibration', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('factory_reset_tile')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('factory_reset_confirm_dialog')), findsOneWidget);
      expect(find.textContaining('CẢNH BÁO'), findsOneWidget);
      expect(find.textContaining('trạng thái an toàn (OFF)'), findsOneWidget);
      expect(find.textContaining('SẼ XÓA HOÀN TOÀN'), findsOneWidget);
      expect(find.textContaining('BẢO TỒN NGUYÊN VẸN'), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(const Key('factory_reset_confirm_dialog')),
          matching: find.textContaining('BL0942'),
        ),
        findsOneWidget,
      );
      expect(find.byKey(const Key('confirm_factory_reset_button')), findsOneWidget);
    });

    testWidgets('Test SubBox Removal: Dialog shows child ActionBoxes protection notice', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleSubBox));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('remove_device_tile')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('remove_device_confirm_dialog')), findsOneWidget);
      expect(find.textContaining('LƯU Ý SUBBOX'), findsOneWidget);
      expect(find.textContaining('Chờ khôi phục tuyến (Route Recovery)'), findsOneWidget);
      expect(find.textContaining('tuyệt đối không bị xóa ngầm'), findsOneWidget);
    });

    testWidgets('Test Offline Removal: Dialog explains tombstone record', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final offlineBox = sampleActionBoxV2.copyWith(online: false);
      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: offlineBox));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('remove_device_tile')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('remove_device_confirm_dialog')), findsOneWidget);
      expect(find.textContaining('Tombstone'), findsOneWidget);
      expect(find.textContaining('chặn kết nối lại trái phép'), findsOneWidget);
    });

    testWidgets('Test Export Diagnostics: Exports sanitized JSON excluding secrets and passwords', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('export_diagnostics_button')));
      await tester.pumpAndSettle();

      expect(find.text('Dữ liệu chẩn đoán bo mạch'), findsOneWidget);

      final selectableTextFinder = find.byType(SelectableText);
      expect(selectableTextFinder, findsOneWidget);
      final jsonText = (tester.widget(selectableTextFinder) as SelectableText).data!;

      expect(jsonText.contains('ab_v2_living'), isTrue);
      expect(jsonText.contains('actionbox_v2'), isTrue);
      expect(jsonText.contains('owner_epoch'), isTrue);

      // Verify no sensitive credentials in the JSON text
      expect(jsonText.contains('"password"'), isFalse);
      expect(jsonText.contains('"secret"'), isFalse);
      expect(jsonText.contains('"token"'), isFalse);
      expect(jsonText.contains('"audio_pcm"'), isFalse);
    });

    testWidgets('Test Safety Isolation: Single channel config modal contains only channel fields', (tester) async {
      tester.view.physicalSize = const Size(500, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final client = await createTestClient(role: 'admin');

      await tester.pumpWidget(createTestWidget(client: client, actionBox: sampleActionBoxV2));
      await tester.pumpAndSettle();

      // Check Channel 3 latching badge
      expect(find.text('Rơ-le chốt'), findsOneWidget);

      // Find "Cấu hình" button on channel 1
      final configButtons = find.text('Cấu hình');
      expect(configButtons, findsWidgets);
      await tester.tap(configButtons.first);
      await tester.pumpAndSettle();

      // Modal bottom sheet should only have channel settings
      final bottomSheet = find.byType(BottomSheet);
      expect(bottomSheet, findsOneWidget);
      expect(find.descendant(of: bottomSheet, matching: find.text('Cấu hình CH1')), findsOneWidget);
      expect(find.descendant(of: bottomSheet, matching: find.text('Tên thiết bị (ví dụ: Quạt trần, Đèn chính)')), findsOneWidget);
      expect(find.descendant(of: bottomSheet, matching: find.text('Lưu thay đổi & Đồng bộ')), findsOneWidget);

      // Board-level dangerous buttons must NOT be inside channel modal
      expect(find.descendant(of: bottomSheet, matching: find.text('Khởi động lại bo mạch')), findsNothing);
      expect(find.descendant(of: bottomSheet, matching: find.text('Khôi phục cài đặt gốc (Factory Reset)')), findsNothing);
      expect(find.descendant(of: bottomSheet, matching: find.text('Gỡ thiết bị khỏi Nhà')), findsNothing);
    });
  });
}
