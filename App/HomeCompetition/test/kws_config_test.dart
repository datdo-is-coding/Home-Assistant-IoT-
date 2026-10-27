import 'dart:convert';

import 'package:home_competition/features/actionbox/action_box_detail_screen.dart';
import 'package:home_competition/models/action_box.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const boxes = [
  ActionBox(id: 'AB1', name: 'Bo một', roomId: 'arbitrary', channels: [
    ActionBoxChannel(index: 0, channelKey: 'ch1', name: 'Tải một'),
    ActionBoxChannel(index: 1, channelKey: 'ch2', name: 'Tải hai'),
    ActionBoxChannel(index: 2, channelKey: 'ch3', name: 'Tải ba'),
  ]),
  ActionBox(id: 'AB2', name: 'Bo hai', roomId: 'other', channels: [
    ActionBoxChannel(index: 1, channelKey: 'ch2', name: 'Tải khác'),
  ]),
  ActionBox(id: 'SB1', name: 'SubBox', roomId: '', channels: []),
];

void main() {
  Future<void> openEditor(WidgetTester tester, GatewayClient client) async {
    tester.view.physicalSize = const Size(600, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(ProviderScope(
      overrides: [
        gatewayClientProvider.overrideWith((ref) => client),
        actionBoxesStreamProvider.overrideWith((ref) => Stream.value(boxes)),
      ],
      child: const MaterialApp(
        home: FeatureActionBoxDetailScreen(actionBoxId: 'AB1'),
      ),
    ));
    await tester.pumpAndSettle();
    final entry = find.byKey(const Key('kws_config_tile'));
    expect(entry, findsOneWidget);
    await tester.ensureVisible(entry);
    await tester.tap(entry);
    await tester.pumpAndSettle();
  }

  Future<void> select(WidgetTester tester, String key, String label) async {
    final field = find.byKey(Key(key));
    await tester.ensureVisible(field);
    await tester.tap(field);
    await tester.pumpAndSettle();
    await tester.tap(find.text(label).last);
    await tester.pumpAndSettle();
  }

  testWidgets(
      'explicit CH3 mapping preserves other bindings, removes cleanly, waits for ACK',
      (tester) async {
    final writes = <Map<String, dynamic>>[];
    var config = <String, dynamic>{
      'revision': 7,
      'bindings': [
        {
          'room': 'KITCHEN',
          'device': 'FAN',
          'node_id': 'AB2',
          'channel': 2,
          'hardware_uid': 'mac2',
          'config_version': 4,
          'subbox_id': 'SB1'
        },
      ],
      'sources': <dynamic>[],
      'sync': {
        'SB1': {'revision': 7, 'status': 'applied'}
      },
    };
    final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/kws/config') {
            expect(req.headers['Authorization'], 'Bearer test');
            if (req.method == 'PUT') {
              final body = jsonDecode(req.body) as Map<String, dynamic>;
              writes.add(body);
              config = {
                ...body,
                'revision': (body['revision'] as int) + 1,
                'sync': {
                  'SB1': {
                    'revision': (body['revision'] as int) + 1,
                    'status': 'pending'
                  }
                }
              };
            } else {
              expect(req.method, 'GET');
            }
            return http.Response(jsonEncode(config), 200);
          }
          return http.Response('{"nodes":{},"pending":{}}', 200);
        }));
    addTearDown(client.dispose);
    await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
    await openEditor(tester, client);
    expect(writes, isEmpty);
    expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('kws_save')))
            .onPressed,
        isNull);
    await select(tester, 'binding_BEDROOM_LIGHT', 'Bo một · CH3 · Tải ba');
    await select(tester, 'source_AB1', 'Phòng ngủ');
    await tester.ensureVisible(find.byKey(const Key('kws_save')));
    await tester.tap(find.byKey(const Key('kws_save')));
    await tester.pumpAndSettle();
    expect(writes.single, {
      'revision': 7,
      'bindings': [
        {'room': 'KITCHEN', 'device': 'FAN', 'node_id': 'AB2', 'channel': 2},
        {'room': 'BEDROOM', 'device': 'LIGHT', 'node_id': 'AB1', 'channel': 3},
      ],
      'sources': [
        {'node_id': 'AB1', 'room': 'BEDROOM'}
      ],
    });
    expect(find.text('SB1: Chờ SubBox xác nhận'), findsOneWidget);
    expect(find.text('SB1: Đã áp dụng'), findsNothing);
    config['sync'] = {
      'SB1': {'revision': 8, 'status': 'applied'}
    };
    await tester.tap(find.byKey(const Key('kws_refresh')));
    await tester.pumpAndSettle();
    expect(find.text('SB1: Đã áp dụng'), findsOneWidget);
    await select(tester, 'binding_BEDROOM_LIGHT', 'Chưa gán');
    await select(tester, 'source_AB1', 'Chưa gán');
    await tester.ensureVisible(find.byKey(const Key('kws_save')));
    await tester.tap(find.byKey(const Key('kws_save')));
    await tester.pumpAndSettle();
    expect(writes.last['revision'], 8);
    expect(writes.last['bindings'], [
      {'room': 'KITCHEN', 'device': 'FAN', 'node_id': 'AB2', 'channel': 2},
    ]);
    expect(writes.last['sources'], isEmpty);
  });

  testWidgets('stale snapshot keeps draft and offers explicit reload',
      (tester) async {
    final client = GatewayClient(
        persistSession: false,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"role":"admin"}}', 200);
          }
          if (req.url.path == '/api/kws/config' && req.method == 'PUT') {
            return http.Response('{"error":"revision_conflict"}', 409);
          }
          return http.Response(
              '{"revision":3,"bindings":[],"sources":[],"sync":{"SB1":{"revision":2,"status":"applied"}}}',
              200);
        }));
    addTearDown(client.dispose);
    await client.loginWithKey(url: 'http://gateway:8000', key: 'test');
    await openEditor(tester, client);
    expect(find.text('SB1: Đã áp dụng'), findsNothing);
    await select(tester, 'binding_LIVING_ROOM_FAN', 'Bo một · CH1 · Tải một');
    await tester.ensureVisible(find.byKey(const Key('kws_save')));
    await tester.tap(find.byKey(const Key('kws_save')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Cấu hình đã thay đổi'), findsOneWidget);
    expect(
        tester
            .widget<DropdownButtonFormField<String>>(
                find.byKey(const Key('binding_LIVING_ROOM_FAN')))
            .initialValue,
        'AB1:1');
    expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('kws_save')))
            .onPressed,
        isNotNull);
  });
}
