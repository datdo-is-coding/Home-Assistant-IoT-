import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dtv_energy_flutter/models/action_box.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';
import 'package:dtv_energy_flutter/repositories/smart_home_repository.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  test('SubBox with legacy relay metadata stays a hub, not a third ActionBox', () async {
    final client = GatewayClient(persistSession: false);
    client.connected = true;
    client.nodes = {
      'SB288485350B54': {'status': 'online', 'board_model': 'actionbox_v2', 'channels': {
        'ch1': {'name': 'Old light'}, 'ch2': {}, 'ch3': {}}},
      'AB28848533DDF8': {'status': 'online', 'channels': {'ch1': {}, 'ch2': {}, 'ch3': {}}},
      'AB28848533DDE8': {'status': 'offline', 'is_online': true, 'channels': {'ch1': {}, 'ch2': {}, 'ch3': {}}},
    };
    final repo = GatewaySmartHomeRepository(client);
    final boxes = await repo.watchActionBoxes().first;
    final devices = await repo.watchDevices().first;
    expect(boxes.where((b) => !b.isSubBox), hasLength(2));
    final hub = boxes.singleWhere((b) => b.isSubBox);
    expect(hub.name, contains('SubBox'));
    expect(hub.channels, isEmpty);
    expect(devices.where((d) => d.actionBoxId == hub.id), isEmpty);
    expect(boxes.singleWhere((b) => b.id.endsWith('DDE8')).online, isFalse);
    repo.dispose();
    client.dispose();
  });
  test('SubBox stable hardware ID wins over missing legacy model', () {
    expect(const ActionBox(id: 'SB288485350B54', name: 'Hub', roomId: '', channels: []).isSubBox, isTrue);
  });
}
