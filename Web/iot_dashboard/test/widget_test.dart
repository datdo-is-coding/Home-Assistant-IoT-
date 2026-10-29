import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:iot_dashboard/data/model/action_box_model.dart';
import 'package:iot_dashboard/data/model/device_model.dart';
import 'package:iot_dashboard/data/model/scene_model.dart';

void main() {
  group('ActionBoxModel Tests', () {
    test('Correctly constructs ActionBox and calculates channels and power', () {
      final channels = [
        const ActionBoxChannelModel(
          index: 1,
          channelKey: 'ch1',
          name: 'Đèn trần',
          deviceType: 'light',
          state: true,
          voltage: 220.5,
          current: 0.12,
          power: 26.46,
          energyKwh: 1.25,
        ),
        const ActionBoxChannelModel(
          index: 2,
          channelKey: 'ch2',
          name: 'Bình nóng lạnh',
          deviceType: 'waterHeater',
          state: false,
          voltage: 220.0,
          current: 0.0,
          power: 0.0,
          energyKwh: 14.8,
        ),
      ];

      final box = ActionBoxModel(
        id: 'action_box_01',
        name: 'ActionBox Phòng Khách',
        room: 'Phòng khách',
        online: true,
        totalPower: 26.46,
        totalEnergyKwh: 16.05,
        channels: channels,
      );

      expect(box.id, 'action_box_01');
      expect(box.online, true);
      expect(box.channels.length, 2);
      expect(box.channels[0].state, true);
      expect(box.channels[0].power, 26.46);
      expect(box.totalPower, 26.46);
      expect(box.channels[1].state, false);
      expect(box.isSubBox, false);
    });

    test('Correctly identifies SubBox', () {
      const subBox = ActionBoxModel(
        id: 'SB_01',
        name: 'SubBox KWS Phòng Khách',
        room: 'Phòng khách',
        boardModel: 'SubBox_V1',
      );
      expect(subBox.isSubBox, true);
    });
  });

  group('DeviceModel Tests', () {
    test('Calculates power display correctly', () {
      final device = DeviceModel(
        id: 'dev_1',
        name: 'Quạt hút',
        icon: 'air',
        isOn: true,
        powerWatts: 45.0,
        voltage: 220.0,
        current: 0.2,
      );

      expect(device.isOn, true);
      expect(device.powerWatts, 45.0);
    });
  });

  group('SceneModel Tests', () {
    test('Scene execution toggle and actions count', () {
      const scene = SceneModel(
        id: 'scene_goodnight',
        name: 'Đi ngủ',
        icon: Icons.bedtime_rounded,
        color: Color(0xFF6366F1),
        description: 'Tắt toàn bộ đèn và bật điều hòa 26 độ',
        actions: [
          SceneAction(boxId: 'action_box_01', channelKey: 'ch1', targetState: false),
          SceneAction(boxId: 'action_box_01', channelKey: 'ch2', targetState: false),
        ],
      );

      expect(scene.actions.length, 2);
      expect(scene.actions[0].targetState, false);
      expect(scene.color, const Color(0xFF6366F1));
    });
  });
}
