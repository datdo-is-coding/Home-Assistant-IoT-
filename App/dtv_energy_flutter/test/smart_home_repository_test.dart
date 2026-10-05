import 'package:flutter_test/flutter_test.dart';
import 'package:dtv_energy_flutter/models/device.dart';
import 'package:dtv_energy_flutter/repositories/smart_home_repository.dart';

void main() {
  group('Smart Home Repository & Reactive Propagation Tests', () {
    late InMemorySmartHomeRepository repo;

    setUp(() {
      repo = InMemorySmartHomeRepository();
    });

    tearDown(() {
      repo.dispose();
    });

    test('Initial seeded data loads correctly', () async {
      final devices = await repo.getDevices();
      final rooms = await repo.getRooms();
      final actionBoxes = await repo.getActionBoxes();
      final automations = await repo.getAutomations();
      final scenes = await repo.getScenes();
      final vocab = await repo.getVocabulary();

      expect(devices.isNotEmpty, true);
      expect(rooms.length, 4);
      expect(actionBoxes.length, 2);
      expect(automations.isNotEmpty, true);
      expect(scenes.length, 4);
      expect(vocab.isNotEmpty, true);
    });

    test('Toggling device updates device state and syncs to ActionBox channel', () async {
      final initialDevices = await repo.getDevices();
      final dev = initialDevices.firstWhere((d) => d.id == 'dev_light_living');

      expect(dev.isOn, true);

      // Toggle OFF
      await repo.toggleDevice(dev.id, false);

      final updatedDevices = await repo.getDevices();
      final updatedDev = updatedDevices.firstWhere((d) => d.id == 'dev_light_living');
      expect(updatedDev.isOn, false);

      // Verify synced ActionBox channel state
      final actionBoxes = await repo.getActionBoxes();
      final ab = actionBoxes.firstWhere((b) => b.id == 'ab_01');
      final ch1 = ab.channels.firstWhere((c) => c.channelKey == 'ch1');
      expect(ch1.isOn, false);
    });

    test('ActionBox channel reconfiguration propagates across entire app (Device, Voice, Rooms)', () async {
      // Reconfigure Channel 1 of ab_01 from "Đèn trần" to "Quạt làm mát phòng khách" (DeviceType.fan)
      await repo.updateChannel(
        actionBoxId: 'ab_01',
        channelIndex: 0,
        name: 'Quạt làm mát phòng khách',
        type: DeviceType.fan,
        roomId: 'living_room',
        voiceAliases: ['quạt phòng khách', 'quạt trần gió'],
      );

      // 1. Verify ActionBox channel is updated
      final actionBoxes = await repo.getActionBoxes();
      final ab = actionBoxes.firstWhere((b) => b.id == 'ab_01');
      final ch1 = ab.channels.first;
      expect(ch1.name, 'Quạt làm mát phòng khách');
      expect(ch1.type, DeviceType.fan);

      // 2. Verify corresponding Device is updated in DeviceRepository
      final devices = await repo.getDevices();
      final dev = devices.firstWhere((d) => d.actionBoxId == 'ab_01' && d.channel == 'ch1');
      expect(dev.name, 'Quạt làm mát phòng khách');
      expect(dev.type, DeviceType.fan);
      expect(dev.voiceAliases, contains('quạt phòng khách'));

      // 3. Verify Voice Recognition vocabulary updated automatically
      final vocab = await repo.getVocabulary();
      final vocabItem = vocab.firstWhere((v) => v.deviceId == dev.id);
      expect(vocabItem.deviceName, 'Quạt làm mát phòng khách');
      expect(vocabItem.aliases, contains('quạt phòng khách'));
    });

    test('Adding and removing voice aliases updates vocabulary dynamically', () async {
      const devId = 'dev_light_living';

      await repo.addAlias(devId, 'đèn góc sofa');
      var vocab = await repo.getVocabulary();
      var item = vocab.firstWhere((v) => v.deviceId == devId);
      expect(item.aliases, contains('đèn góc sofa'));

      await repo.removeAlias(devId, 'đèn góc sofa');
      vocab = await repo.getVocabulary();
      item = vocab.firstWhere((v) => v.deviceId == devId);
      expect(item.aliases.contains('đèn góc sofa'), false);
    });

    test('Automations and Scenes activation triggers device actions', () async {
      final automations = await repo.getAutomations();
      final auto = automations.first;

      await repo.toggleAutomation(auto.id, false);
      final updatedAutos = await repo.getAutomations();
      expect(updatedAutos.firstWhere((a) => a.id == auto.id).enabled, false);

      // Activating Good Morning Scene turns on lights
      await repo.activateScene('scene_morning');
      final devices = await repo.getDevices();
      final livingLight = devices.firstWhere((d) => d.id == 'dev_light_living');
      expect(livingLight.isOn, true);
    });
  });
}
