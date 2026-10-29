import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:home_competition/features/infrared/infrared_screen.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';

final remote = <String, dynamic>{
  'remote_id': 'REMOTE-aaaaaaaaaaaaaaaaaaaaaaaa',
  'node_id': 1,
  'name': 'Điều hòa Panasonic',
  'category': 'air_conditioner',
  'brand': 'Panasonic',
  'model': 'CWA75C4179',
  'climate': true,
  'requested_state': {
    'power': false,
    'temperature': 26,
    'mode': 'cool',
    'fan': 0,
    'swing': false
  },
  'buttons': [],
};

class _IrClient extends GatewayClient {
  _IrClient({this.existing = false, this.receiver = true})
      : super(persistSession: false);
  final bool existing;
  final bool receiver;
  final calls = <(String, Map<String, dynamic>?)>[];
  @override
  bool get usesFirebase => true;
  @override
  Future<Map<String, dynamic>> request(String path,
      {Map<String, dynamic>? body, String? method, Duration? timeout}) async {
    calls.add((path, body));
    if (path.endsWith('/bootstrap'))
      return {
        'subboxes': [
          {
            'node_id': 1,
            'name': 'SubBox',
            'room': 'Phòng ngủ',
            'online': true,
            'tx': true,
            'rx': receiver
          }
        ],
        'profiles': [
          {
            'id': 'panasonic-cwa75c4179',
            'category': 'air_conditioner',
            'brand': 'Panasonic',
            'model': 'CWA75C4179',
            'climate': true
          }
        ],
        'remotes': existing ? [remote] : []
      };
    if (path.endsWith('/test'))
      return {'status': 'sent', 'state_confirmed': false};
    if (path.endsWith('/remotes')) return remote;
    if (path.endsWith('/learn'))
      return {
        ...remote,
        'full_climate': false,
        'temperatures': [26],
        'buttons': [
          {'key': body!['key'], 'label': body['label']}
        ]
      };
    if (path.endsWith('/send'))
      return {
        'message': 'Đã phát lệnh hồng ngoại.',
        'status': 'sent',
        'state_confirmed': false
      };
    throw StateError('Unexpected IR request: $path');
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  Future<void> show(WidgetTester tester, _IrClient client) async {
    tester.view.physicalSize = const Size(390, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(client.dispose);
    await tester.pumpWidget(ProviderScope(
        overrides: [gatewayClientProvider.overrideWith((ref) => client)],
        child: const MaterialApp(home: InfraredScreen())));
    await tester.pumpAndSettle();
  }

  testWidgets(
      'profile save requires a transmission and the user confirming a response',
      (tester) async {
    final client = _IrClient();
    await show(tester, client);
    await tester.tap(find.widgetWithText(FilledButton, 'Thêm remote'));
    await tester.pumpAndSettle();
    final save = find.widgetWithText(FilledButton, 'Lưu remote');
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(save).onPressed, isNull);
    final test = find.text('Thử bộ mã');
    await tester.ensureVisible(test);
    await tester.tap(test);
    await tester.pumpAndSettle();
    expect(client.calls.where((c) => c.$1.endsWith('/test')), hasLength(1));
    expect(tester.widget<FilledButton>(save).onPressed, isNull);
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(find.text('Cấu hình sẽ gửi'), findsOneWidget);
    final create = client.calls.firstWhere((c) => c.$1.endsWith('/remotes'));
    expect(create.$2?['confirmed'], isTrue);
    expect(create.$2?['node_id'], 1);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'a transmit-only SubBox cannot offer learning from the original remote',
      (tester) async {
    final client = _IrClient(receiver: false);
    await show(tester, client);
    await tester.tap(find.widgetWithText(FilledButton, 'Thêm remote'));
    await tester.pumpAndSettle();
    final picker = tester.widget<DropdownButton<String>>(find.byWidgetPredicate(
        (w) =>
            w is DropdownButton<String> &&
            w.items!.any((i) => i.value == 'learned')));
    final learned = picker.items!.singleWhere((i) => i.value == 'learned');
    expect(learned.enabled, isFalse);
    expect(client.calls.any((c) => c.$1.endsWith('/learn')), isFalse);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'learning a temperature stores an explicit absolute-temperature key',
      (tester) async {
    final client = _IrClient(existing: true);
    await show(tester, client);
    await tester.tap(find.text('Điều hòa Panasonic'));
    await tester.pumpAndSettle();
    final learn = find.text('Học nút từ remote gốc');
    await tester.ensureVisible(learn);
    await tester.tap(learn);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Đặt nhiệt độ').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Bắt đầu'));
    await tester.pumpAndSettle();
    final request = client.calls.singleWhere((c) => c.$1.endsWith('/learn'));
    expect(request.$2?['key'], 'temp_26');
    expect(request.$2?['label'], 'Đặt 26°C');
    expect(find.text('Nhiệt độ đã học'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
  testWidgets(
      'climate edits are draft only and a send remains explicitly unconfirmed',
      (tester) async {
    final client = _IrClient(existing: true);
    await show(tester, client);
    await tester.tap(find.text('Điều hòa Panasonic'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Tăng nhiệt độ'));
    await tester.pumpAndSettle();
    expect(find.text('27°'), findsOneWidget);
    expect(client.calls.any((c) => c.$1.endsWith('/send')), isFalse);
    final send = find.widgetWithText(FilledButton, 'Phát lệnh');
    await tester.ensureVisible(send);
    await tester.tap(send);
    await tester.pumpAndSettle();
    final call = client.calls.firstWhere((c) => c.$1.endsWith('/send'));
    expect((call.$2?['state'] as Map)['temperature'], 27);
    expect(call.$2?['idempotency_key'], isNotEmpty);
    expect(find.text('Đã phát lệnh hồng ngoại.'), findsOneWidget);
    expect(find.text('Đã bật điều hòa'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
