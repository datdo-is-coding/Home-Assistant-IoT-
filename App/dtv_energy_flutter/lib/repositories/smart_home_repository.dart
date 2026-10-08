import 'dart:async';
import 'package:flutter/material.dart';
import '../models/device.dart';
import '../models/room.dart';
import '../models/action_box.dart';
import '../models/scene.dart';
import '../models/automation.dart';
import '../models/voice_alias.dart';

import '../services/gateway_client.dart';

abstract class DeviceRepository {
  Future<List<Device>> getDevices();
  Stream<List<Device>> watchDevices();
  Future<void> toggleDevice(String id, bool on);
  Future<void> setDeviceValue(String id, double value);
  Future<void> toggleFavorite(String id);
  Future<void> addDevice(Device device);
  Future<void> updateDevice(Device device);
}

abstract class RoomRepository {
  Future<List<Room>> getRooms();
  Stream<List<Room>> watchRooms();
}

abstract class ActionBoxRepository {
  Future<List<ActionBox>> getActionBoxes();
  Stream<List<ActionBox>> watchActionBoxes();
  Future<void> addActionBox(ActionBox actionBox);
  Future<void> updateChannel({
    required String actionBoxId,
    required int channelIndex,
    required String name,
    required DeviceType type,
    required String roomId,
    List<String>? voiceAliases,
  });
}

abstract class AutomationRepository {
  Future<List<Automation>> getAutomations();
  Stream<List<Automation>> watchAutomations();
  Future<void> toggleAutomation(String id, bool enabled);
  Future<void> addAutomation(Automation automation);
  Future<void> deleteAutomation(String id);
}

abstract class SceneRepository {
  Future<List<Scene>> getScenes();
  Stream<List<Scene>> watchScenes();
  Future<void> activateScene(String id);
}

abstract class VoiceRepository {
  Future<List<VoiceVocabularyItem>> getVocabulary();
  Stream<List<VoiceVocabularyItem>> watchVocabulary();
  Future<void> addAlias(String deviceId, String alias);
  Future<void> removeAlias(String deviceId, String alias);
}

abstract class SmartHomeRepository
    implements
        DeviceRepository,
        RoomRepository,
        ActionBoxRepository,
        AutomationRepository,
        SceneRepository,
        VoiceRepository {
  void dispose();
}

/// Authoritative Gateway-backed SmartHomeRepository.
/// Strictly drives application state from real Gateway nodes, relays, and PZEM telemetry.
class GatewaySmartHomeRepository implements SmartHomeRepository {
  final GatewayClient gateway;

  final _deviceStreamCtrl = StreamController<List<Device>>.broadcast();
  final _roomStreamCtrl = StreamController<List<Room>>.broadcast();
  final _actionBoxStreamCtrl = StreamController<List<ActionBox>>.broadcast();
  final _automationStreamCtrl = StreamController<List<Automation>>.broadcast();
  final _sceneStreamCtrl = StreamController<List<Scene>>.broadcast();
  final _voiceStreamCtrl = StreamController<List<VoiceVocabularyItem>>.broadcast();

  final Set<String> _favoriteIds = {};
  List<Device> _devices = [];
  List<Room> _rooms = [];
  List<ActionBox> _actionBoxes = [];
  final List<Automation> _automations = [];

  GatewaySmartHomeRepository(this.gateway) {
    gateway.addListener(_syncFromGateway);
    _syncFromGateway();
  }

  void _syncFromGateway() {
    _devices = _buildDevices();
    _rooms = _buildRooms(_devices);
    _actionBoxes = _buildActionBoxes();

    if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
    if (!_roomStreamCtrl.isClosed) _roomStreamCtrl.add(List.unmodifiable(_rooms));
    if (!_actionBoxStreamCtrl.isClosed) _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));
    if (!_voiceStreamCtrl.isClosed) _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
    if (!_sceneStreamCtrl.isClosed) _sceneStreamCtrl.add(List.unmodifiable(_buildScenes(_devices)));
    if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
  }

  List<Device> _buildDevices() {
    final list = <Device>[];
    for (final entry in gateway.nodes.entries) {
      final nodeId = entry.key;
      final node = asMap(entry.value);
      final nodeOnline = (node['status'] == 'online') || (node['is_online'] == true);
      final rawRl = node['relay_state'];
      final List<dynamic> rlList = rawRl is List ? rawRl : const [0, 0];
      final nodeRoom = (node['room'] ?? '').toString();
      final channelsMap = asMap(node['channels']);
      final pzem = asMap(node['pzem']).isNotEmpty ? asMap(node['pzem']) : asMap(node['last_telemetry']);
      final double powerWatts = readNumber(pzem['power']) ?? 0.0;

      // Real ESP32-S3 hardware has 2 physical channels: ch1 (GPIO 4), ch2 (GPIO 5)
      final channelKeys = ['ch1', 'ch2'];
      for (int i = 0; i < channelKeys.length; i++) {
        final chKey = channelKeys[i];
        final chInfo = asMap(channelsMap[chKey]);
        final chName = _resolveChannelName(chKey, chInfo);
        final chTypeStr = (chInfo['device_type'] ?? (i == 0 ? 'light' : 'fan')).toString().toLowerCase();
        final devType = switch (chTypeStr) {
          'light' || 'den' || 'lamp' => DeviceType.light,
          'fan' || 'quat' => DeviceType.fan,
          'socket' || 'o_cam' || 'outlet' => DeviceType.socket,
          'ac' || 'air_conditioner' || 'dieu_hoa' => DeviceType.airConditioner,
          _ => DeviceType.custom,
        };

        final isOn = rlList.length > i && (rlList[i] == 1 || rlList[i] == true || rlList[i] == 'ON');
        final rawAliases = chInfo['aliases'];
        final aliases = rawAliases is List ? rawAliases.map((a) => a.toString()).toList() : <String>[];
        final devId = '$nodeId::$chKey';

        list.add(Device(
          id: devId,
          name: chName,
          type: devType,
          roomId: nodeRoom,
          actionBoxId: nodeId,
          channel: chKey,
          online: nodeOnline,
          isOn: isOn,
          value: powerWatts > 0 ? powerWatts : 0.0,
          voiceAliases: aliases,
          isFavorite: _favoriteIds.contains(devId),
          metadata: {
            'node_id': nodeId,
            'channel': chKey,
            'mac': node['mac'] ?? '',
            'ip': node['ip'] ?? '',
            'can_dim': false,
            'can_speed': false,
            'power': powerWatts,
            'voltage': readNumber(pzem['voltage']),
            'current': readNumber(pzem['current']),
            'energy': readNumber(pzem['energy']),
          },
        ));
      }
    }
    return list;
  }

  static List<Room> _buildRooms(List<Device> devices) {
    final roomIds = <String>{};
    for (final dev in devices) {
      if (dev.roomId.trim().isNotEmpty) {
        roomIds.add(dev.roomId.trim());
      }
    }
    return roomIds.map((rId) {
      return Room(
        id: rId,
        name: _resolveRoomName(rId),
        icon: _resolveRoomIcon(rId),
      );
    }).toList();
  }

  List<ActionBox> _buildActionBoxes() {
    final list = <ActionBox>[];
    for (final entry in gateway.nodes.entries) {
      final nodeId = entry.key;
      final node = asMap(entry.value);
      final nodeOnline = (node['status'] == 'online') || (node['is_online'] == true);
      final rawRl = node['relay_state'];
      final List<dynamic> rlList = rawRl is List ? rawRl : const [0, 0];
      final nodeRoom = (node['room'] ?? '').toString();
      final channelsMap = asMap(node['channels']);

      final channels = <ActionBoxChannel>[];
      final channelKeys = ['ch1', 'ch2'];
      for (int i = 0; i < channelKeys.length; i++) {
        final chKey = channelKeys[i];
        final chInfo = asMap(channelsMap[chKey]);
        final chName = _resolveChannelName(chKey, chInfo);
        final chTypeStr = (chInfo['device_type'] ?? (i == 0 ? 'light' : 'fan')).toString().toLowerCase();
        final devType = switch (chTypeStr) {
          'light' || 'den' || 'lamp' => DeviceType.light,
          'fan' || 'quat' => DeviceType.fan,
          'socket' || 'o_cam' => DeviceType.socket,
          _ => DeviceType.custom,
        };
        final isOn = rlList.length > i && (rlList[i] == 1 || rlList[i] == true);
        channels.add(ActionBoxChannel(
          index: i,
          channelKey: chKey,
          deviceId: '$nodeId::$chKey',
          name: chName,
          type: devType,
          configured: true,
          isOn: isOn,
        ));
      }

      list.add(ActionBox(
        id: nodeId,
        name: node['name'] ?? node['display_name'] ?? 'ActionBox $nodeId',
        roomId: nodeRoom,
        online: nodeOnline,
        channels: channels,
        firmwareVersion: node['fw'] ?? node['firmware_version'] ?? 'v1.2.0-esp32s3',
        ipAddress: node['ip'] ?? (gateway.serverUrl.isNotEmpty ? Uri.tryParse(gateway.serverUrl)?.host ?? '192.168.11.181' : '192.168.11.181'),
        signalStrength: readNumber(node['rssi'])?.toInt() ?? -62,
      ));
    }
    return list;
  }

  static List<VoiceVocabularyItem> _buildVocabulary(List<Device> devices) {
    return devices.map((d) => VoiceVocabularyItem(
      deviceId: d.id,
      deviceName: d.name,
      aliases: List.unmodifiable(d.voiceAliases),
    )).toList();
  }

  static List<Scene> _buildScenes(List<Device> devices) {
    if (devices.isEmpty) return const [];
    return [
      Scene(
        id: 'scene_all_off',
        name: 'Tắt toàn bộ thiết bị',
        icon: Icons.power_settings_new_rounded,
        description: 'Ngắt toàn bộ rơ-le đang bật trong nhà',
        deviceCount: devices.where((d) => d.isOn).length,
      ),
      Scene(
        id: 'scene_morning',
        name: 'Chào buổi sáng',
        icon: Icons.wb_sunny_rounded,
        description: 'Bật các đèn chiếu sáng',
        deviceCount: devices.where((d) => d.type == DeviceType.light).length,
      ),
    ];
  }

  static String _resolveChannelName(String channel, dynamic info) {
    final data = asMap(info);
    final raw = data['name'] ?? data['description'];
    if (raw != null && raw.toString().trim().isNotEmpty) {
      final s = raw.toString().trim();
      final lower = s.toLowerCase();
      if (lower == 'light' || lower == 'lamp' || lower == 'den') return 'Đèn';
      if (lower == 'fan' || lower == 'quat') return 'Quạt';
      if (lower == 'pump' || lower == 'may_bom') return 'Máy bơm';
      if (lower == 'ac' || lower == 'air_conditioner' || lower == 'dieu_hoa') return 'Điều hòa';
      if (lower == 'switch' || lower == 'cong_tac') return 'Công tắc';
      return s;
    }
    final devType = '${data['device_type'] ?? info}'.toLowerCase();
    return switch (devType) {
      'light' || 'lamp' || 'den' => 'Đèn',
      'fan' || 'quat' => 'Quạt',
      'pump' || 'may_bom' => 'Máy bơm',
      'ac' || 'air_conditioner' || 'dieu_hoa' => 'Điều hòa',
      'switch' || 'cong_tac' => 'Công tắc',
      _ => channel == 'ch1' ? 'Kênh 1' : 'Kênh 2',
    };
  }

  static String _resolveRoomName(String id) =>
      const {
        'livingroom': 'Phòng khách',
        'living_room': 'Phòng khách',
        'phong_khach': 'Phòng khách',
        'bedroom': 'Phòng ngủ',
        'phong_ngu': 'Phòng ngủ',
        'kitchen': 'Phòng bếp',
        'phong_bep': 'Phòng bếp',
        'bathroom': 'Phòng tắm',
        'office': 'Phòng làm việc',
        'garden': 'Sân vườn',
        '': 'Chưa phân phòng',
      }[id.toLowerCase()] ??
      id.replaceAll('_', ' ');

  static IconData _resolveRoomIcon(String id) => switch (id.toLowerCase()) {
    'livingroom' || 'living_room' || 'phong_khach' => Icons.weekend_rounded,
    'bedroom' || 'phong_ngu' => Icons.bed_rounded,
    'kitchen' || 'phong_bep' => Icons.kitchen_rounded,
    'bathroom' || 'phong_tam' => Icons.bathtub_rounded,
    'office' || 'phong_lam_viec' => Icons.desk_rounded,
    'garden' || 'san_vuon' => Icons.yard_rounded,
    _ => Icons.meeting_room_rounded,
  };

  // DeviceRepository Implementation
  @override
  Future<List<Device>> getDevices() async => List.unmodifiable(_devices);

  @override
  Stream<List<Device>> watchDevices() {
    scheduleMicrotask(() {
      if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
    });
    return _deviceStreamCtrl.stream;
  }

  @override
  Future<void> toggleDevice(String id, bool isOn) async {
    final parts = id.split('::');
    if (parts.length != 2) return;
    final nodeId = parts[0];
    final channel = parts[1];
    await gateway.relay(nodeId, channel, isOn);
  }

  @override
  Future<void> setDeviceValue(String id, double value) async {
    // For relays, toggles On if value > 0, Off if value == 0
    await toggleDevice(id, value > 0);
  }

  @override
  Future<void> toggleFavorite(String id) async {
    if (_favoriteIds.contains(id)) {
      _favoriteIds.remove(id);
    } else {
      _favoriteIds.add(id);
    }
    _syncFromGateway();
  }

  @override
  Future<void> updateDevice(Device device) async {
    final parts = device.id.split('::');
    if (parts.length != 2) return;
    final nodeId = parts[0];
    final chKey = parts[1];
    final typeStr = switch (device.type) {
      DeviceType.light => 'den',
      DeviceType.fan => 'quat',
      DeviceType.socket => 'o_cam',
      DeviceType.airConditioner => 'dieu_hoa',
      _ => 'den',
    };
    await gateway.updateDevice(
      deviceId: nodeId,
      room: device.roomId.isNotEmpty ? device.roomId : null,
      ch1Name: chKey == 'ch1' ? device.name : null,
      ch1Type: chKey == 'ch1' ? typeStr : null,
      ch2Name: chKey == 'ch2' ? device.name : null,
      ch2Type: chKey == 'ch2' ? typeStr : null,
    );
  }

  @override
  Future<void> addDevice(Device device) async {
    // In production, devices are registered via Gateway commissioning
    _syncFromGateway();
  }

  // RoomRepository Implementation
  @override
  Future<List<Room>> getRooms() async => List.unmodifiable(_rooms);

  @override
  Stream<List<Room>> watchRooms() {
    scheduleMicrotask(() {
      if (!_roomStreamCtrl.isClosed) _roomStreamCtrl.add(List.unmodifiable(_rooms));
    });
    return _roomStreamCtrl.stream;
  }

  // ActionBoxRepository Implementation
  @override
  Future<List<ActionBox>> getActionBoxes() async => List.unmodifiable(_actionBoxes);

  @override
  Stream<List<ActionBox>> watchActionBoxes() {
    scheduleMicrotask(() {
      if (!_actionBoxStreamCtrl.isClosed) _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));
    });
    return _actionBoxStreamCtrl.stream;
  }

  @override
  Future<void> addActionBox(ActionBox actionBox) async {
    _syncFromGateway();
  }

  @override
  Future<void> updateChannel({
    required String actionBoxId,
    required int channelIndex,
    required String name,
    required DeviceType type,
    required String roomId,
    List<String>? voiceAliases,
  }) async {
    final chKey = channelIndex == 0 ? 'ch1' : 'ch2';
    final typeStr = switch (type) {
      DeviceType.light => 'den',
      DeviceType.fan => 'quat',
      DeviceType.socket => 'o_cam',
      _ => 'den',
    };
    await gateway.updateDevice(
      deviceId: actionBoxId,
      room: roomId,
      ch1Name: chKey == 'ch1' ? name : null,
      ch1Type: chKey == 'ch1' ? typeStr : null,
      ch2Name: chKey == 'ch2' ? name : null,
      ch2Type: chKey == 'ch2' ? typeStr : null,
    );
  }

  // AutomationRepository Implementation
  @override
  Future<List<Automation>> getAutomations() async => List.unmodifiable(_automations);

  @override
  Stream<List<Automation>> watchAutomations() {
    scheduleMicrotask(() {
      if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
    });
    return _automationStreamCtrl.stream;
  }

  @override
  Future<void> toggleAutomation(String id, bool enabled) async {
    final idx = _automations.indexWhere((a) => a.id == id);
    if (idx != -1) {
      _automations[idx] = _automations[idx].copyWith(enabled: enabled);
      if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
    }
  }

  @override
  Future<void> addAutomation(Automation automation) async {
    _automations.add(automation);
    if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
  }

  @override
  Future<void> deleteAutomation(String id) async {
    _automations.removeWhere((a) => a.id == id);
    if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
  }

  // SceneRepository Implementation
  @override
  Future<List<Scene>> getScenes() async => _buildScenes(_devices);

  @override
  Stream<List<Scene>> watchScenes() {
    scheduleMicrotask(() {
      if (!_sceneStreamCtrl.isClosed) _sceneStreamCtrl.add(List.unmodifiable(_buildScenes(_devices)));
    });
    return _sceneStreamCtrl.stream;
  }

  @override
  Future<void> activateScene(String id) async {
    if (id == 'scene_all_off' || id == 'scene_night' || id == 'scene_away') {
      for (final dev in _devices) {
        if (dev.online && dev.isOn && dev.channel != null && dev.actionBoxId != null) {
          try {
            await gateway.relay(dev.actionBoxId!, dev.channel!, false);
          } catch (_) {}
        }
      }
    } else if (id == 'scene_morning') {
      for (final dev in _devices) {
        if (dev.online && !dev.isOn && dev.type == DeviceType.light && dev.channel != null && dev.actionBoxId != null) {
          try {
            await gateway.relay(dev.actionBoxId!, dev.channel!, true);
          } catch (_) {}
        }
      }
    }
  }

  // VoiceRepository Implementation
  @override
  Future<List<VoiceVocabularyItem>> getVocabulary() async => _buildVocabulary(_devices);

  @override
  Stream<List<VoiceVocabularyItem>> watchVocabulary() {
    scheduleMicrotask(() {
      if (!_voiceStreamCtrl.isClosed) _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
    });
    return _voiceStreamCtrl.stream;
  }

  @override
  Future<void> addAlias(String deviceId, String alias) async {
    final cleanAlias = alias.trim().toLowerCase();
    if (cleanAlias.isEmpty) return;

    final devIdx = _devices.indexWhere((d) => d.id == deviceId);
    if (devIdx == -1) return;
    final dev = _devices[devIdx];
    if (dev.voiceAliases.contains(cleanAlias)) return;

    // Optimistic update
    final previousAliases = List<String>.from(dev.voiceAliases);
    final updatedAliases = List<String>.from(dev.voiceAliases)..add(cleanAlias);
    _devices[devIdx] = dev.copyWith(voiceAliases: updatedAliases);
    if (!_voiceStreamCtrl.isClosed) _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));

    try {
      final channel = dev.channel ?? (deviceId.contains('::') ? deviceId.split('::')[1] : 'ch1');
      final nodeId = dev.actionBoxId ?? (deviceId.contains('::') ? deviceId.split('::')[0] : deviceId);
      await gateway.addDeviceAlias(
        deviceId: nodeId,
        channel: channel,
        alias: cleanAlias,
      );
    } catch (e) {
      // Rollback on network failure
      final rollbackIdx = _devices.indexWhere((d) => d.id == deviceId);
      if (rollbackIdx != -1) {
        _devices[rollbackIdx] = _devices[rollbackIdx].copyWith(voiceAliases: previousAliases);
        if (!_voiceStreamCtrl.isClosed) {
          _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
        }
      }
      rethrow;
    }
  }

  @override
  Future<void> removeAlias(String deviceId, String alias) async {
    final cleanAlias = alias.trim().toLowerCase();
    if (cleanAlias.isEmpty) return;

    final devIdx = _devices.indexWhere((d) => d.id == deviceId);
    if (devIdx == -1) return;
    final dev = _devices[devIdx];

    // Optimistic update
    final previousAliases = List<String>.from(dev.voiceAliases);
    final updatedAliases = List<String>.from(dev.voiceAliases)..remove(cleanAlias);
    _devices[devIdx] = dev.copyWith(voiceAliases: updatedAliases);
    if (!_voiceStreamCtrl.isClosed) _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));

    try {
      final channel = dev.channel ?? (deviceId.contains('::') ? deviceId.split('::')[1] : 'ch1');
      final nodeId = dev.actionBoxId ?? (deviceId.contains('::') ? deviceId.split('::')[0] : deviceId);
      await gateway.removeDeviceAlias(
        deviceId: nodeId,
        channel: channel,
        alias: cleanAlias,
      );
    } catch (e) {
      // Rollback on network failure
      final rollbackIdx = _devices.indexWhere((d) => d.id == deviceId);
      if (rollbackIdx != -1) {
        _devices[rollbackIdx] = _devices[rollbackIdx].copyWith(voiceAliases: previousAliases);
        if (!_voiceStreamCtrl.isClosed) {
          _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
        }
      }
      rethrow;
    }
  }

  @override
  void dispose() {
    gateway.removeListener(_syncFromGateway);
    _deviceStreamCtrl.close();
    _roomStreamCtrl.close();
    _actionBoxStreamCtrl.close();
    _automationStreamCtrl.close();
    _sceneStreamCtrl.close();
    _voiceStreamCtrl.close();
  }
}

/// Unified In-Memory Reactive Repository implementation.
/// Used for mock/test mode only via --dart-define=USE_MOCK_DATA=true.
class InMemorySmartHomeRepository implements SmartHomeRepository {
  final _deviceStreamCtrl = StreamController<List<Device>>.broadcast();
  final _roomStreamCtrl = StreamController<List<Room>>.broadcast();
  final _actionBoxStreamCtrl = StreamController<List<ActionBox>>.broadcast();
  final _automationStreamCtrl = StreamController<List<Automation>>.broadcast();
  final _sceneStreamCtrl = StreamController<List<Scene>>.broadcast();
  final _voiceStreamCtrl = StreamController<List<VoiceVocabularyItem>>.broadcast();

  List<Room> _rooms = [
    const Room(id: 'living_room', name: 'Phòng khách', icon: Icons.weekend_rounded, temperature: 27.5, humidity: 65),
    const Room(id: 'bedroom', name: 'Phòng ngủ', icon: Icons.bed_rounded, temperature: 26.0, humidity: 60),
    const Room(id: 'kitchen', name: 'Nhà bếp', icon: Icons.kitchen_rounded, temperature: 28.2, humidity: 70),
    const Room(id: 'office', name: 'Phòng làm việc', icon: Icons.desk_rounded, temperature: 25.5, humidity: 55),
  ];

  List<Device> _devices = [
    const Device(
      id: 'dev_light_living',
      name: 'Đèn trần phòng khách',
      type: DeviceType.light,
      roomId: 'living_room',
      actionBoxId: 'ab_01',
      channel: 'ch1',
      online: true,
      isOn: true,
      value: 80.0,
      isFavorite: true,
      voiceAliases: ['đèn phòng khách', 'đèn trần', 'đèn chính'],
    ),
    const Device(
      id: 'dev_fan_living',
      name: 'Quạt trần phòng khách',
      type: DeviceType.fan,
      roomId: 'living_room',
      actionBoxId: 'ab_01',
      channel: 'ch2',
      online: true,
      isOn: true,
      value: 2.0,
      isFavorite: true,
      voiceAliases: ['quạt phòng khách', 'quạt trần', 'bật quạt'],
    ),
    const Device(
      id: 'dev_socket_office',
      name: 'Ổ cắm bàn làm việc',
      type: DeviceType.socket,
      roomId: 'office',
      actionBoxId: 'ab_01',
      channel: 'ch3',
      online: true,
      isOn: true,
      value: 120.5, // 120.5W
      isFavorite: true,
      voiceAliases: ['ổ cắm máy tính', 'ổ cắm bàn'],
    ),
    const Device(
      id: 'dev_ac_bedroom',
      name: 'Điều hòa nhiệt độ',
      type: DeviceType.airConditioner,
      roomId: 'bedroom',
      online: true,
      isOn: false,
      value: 24.0, // 24°C
      isFavorite: true,
      voiceAliases: ['điều hòa phòng ngủ', 'máy lạnh'],
    ),
    const Device(
      id: 'dev_light_bed',
      name: 'Đèn ngủ đầu giường',
      type: DeviceType.light,
      roomId: 'bedroom',
      actionBoxId: 'ab_02',
      channel: 'ch1',
      online: false, // Offline demo
      isOn: false,
      value: 50.0,
      isFavorite: true,
      voiceAliases: ['đèn ngủ', 'đèn đầu giường'],
    ),
    const Device(
      id: 'dev_fan_bed',
      name: 'Quạt phòng ngủ',
      type: DeviceType.fan,
      roomId: 'bedroom',
      actionBoxId: 'ab_02',
      channel: 'ch2',
      online: false, // Offline demo
      isOn: false,
      value: 1.0,
      isFavorite: false,
      voiceAliases: ['quạt phòng ngủ'],
    ),
    const Device(
      id: 'dev_kitchen_light',
      name: 'Đèn bếp nấu',
      type: DeviceType.light,
      roomId: 'kitchen',
      online: true,
      isOn: false,
      value: 100.0,
      isFavorite: false,
      voiceAliases: ['đèn bếp', 'đèn nấu ăn'],
    ),
    const Device(
      id: 'dev_kitchen_socket',
      name: 'Ổ cắm lò vi sóng',
      type: DeviceType.socket,
      roomId: 'kitchen',
      online: true,
      isOn: true,
      value: 850.0,
      isFavorite: false,
      voiceAliases: ['ổ cắm lò', 'ổ cắm bếp'],
    ),
  ];

  List<ActionBox> _actionBoxes = [
    const ActionBox(
      id: 'ab_01',
      name: 'ActionBox 1 (Phòng khách)',
      roomId: 'living_room',
      online: true,
      firmwareVersion: 'v1.4.2-esp32s3',
      ipAddress: '192.168.1.105',
      signalStrength: -58,
      channels: [
        ActionBoxChannel(index: 0, channelKey: 'ch1', deviceId: 'dev_light_living', name: 'Đèn trần', type: DeviceType.light, configured: true, isOn: true),
        ActionBoxChannel(index: 1, channelKey: 'ch2', deviceId: 'dev_fan_living', name: 'Quạt trần', type: DeviceType.fan, configured: true, isOn: true),
        ActionBoxChannel(index: 2, channelKey: 'ch3', deviceId: 'dev_socket_office', name: 'Ổ cắm bàn', type: DeviceType.socket, configured: true, isOn: true),
        ActionBoxChannel(index: 3, channelKey: 'ch4', deviceId: null, name: 'Chưa gán', type: DeviceType.light, configured: false, isOn: false),
      ],
    ),
    const ActionBox(
      id: 'ab_02',
      name: 'ActionBox 2 (Phòng ngủ)',
      roomId: 'bedroom',
      online: false,
      firmwareVersion: 'v1.4.0-esp32s3',
      ipAddress: '192.168.1.108',
      signalStrength: -82,
      channels: [
        ActionBoxChannel(index: 0, channelKey: 'ch1', deviceId: 'dev_light_bed', name: 'Đèn ngủ đầu giường', type: DeviceType.light, configured: true, isOn: false),
        ActionBoxChannel(index: 1, channelKey: 'ch2', deviceId: 'dev_fan_bed', name: 'Quạt phòng ngủ', type: DeviceType.fan, configured: true, isOn: false),
        ActionBoxChannel(index: 2, channelKey: 'ch3', deviceId: null, name: 'Chưa gán', type: DeviceType.socket, configured: false, isOn: false),
        ActionBoxChannel(index: 3, channelKey: 'ch4', deviceId: null, name: 'Chưa gán', type: DeviceType.light, configured: false, isOn: false),
      ],
    ),
  ];

  final List<Scene> _scenes = [
    const Scene(id: 'scene_morning', name: 'Chào buổi sáng', icon: Icons.wb_sunny_rounded, description: 'Bật đèn 40%, mở rèm và khởi động ngày mới', deviceCount: 4),
    const Scene(id: 'scene_night', name: 'Đi ngủ', icon: Icons.bedtime_rounded, description: 'Tắt toàn bộ đèn và ổ cắm phụ', deviceCount: 6),
    const Scene(id: 'scene_movie', name: 'Xem phim', icon: Icons.movie_filter_rounded, description: 'Giảm ánh sáng 15%, quạt êm cấp 1', deviceCount: 3),
    const Scene(id: 'scene_away', name: 'Rời khỏi nhà', icon: Icons.door_front_door_rounded, description: 'Khóa cửa, tắt điều hòa và các tải công suất', deviceCount: 8),
  ];

  final List<Automation> _automations = [
    const Automation(id: 'auto_night_off', name: 'Hẹn giờ tắt đèn đêm', icon: Icons.nights_stay_rounded, triggerText: '23:00 mỗi ngày', deviceCount: 3, enabled: true),
    const Automation(id: 'auto_temp_fan', name: 'Tự động bật quạt khi nóng', icon: Icons.thermostat_rounded, triggerText: 'Nhiệt độ phòng > 29°C', deviceCount: 1, enabled: true),
    const Automation(id: 'auto_leave_home', name: 'Tự tắt điện khi rời nhà', icon: Icons.directions_walk_rounded, triggerText: 'Khi điện thoại ra khỏi bán kính 200m', deviceCount: 5, enabled: false),
  ];

  // DeviceRepository Implementation
  @override
  Future<List<Device>> getDevices() async => List.unmodifiable(_devices);

  @override
  Stream<List<Device>> watchDevices() {
    scheduleMicrotask(() => _deviceStreamCtrl.add(List.unmodifiable(_devices)));
    return _deviceStreamCtrl.stream;
  }

  @override
  Future<void> toggleDevice(String id, bool isOn) async {
    final idx = _devices.indexWhere((d) => d.id == id);
    if (idx == -1) return;
    final dev = _devices[idx];
    if (!dev.online) return; // Cannot toggle offline devices
    _devices[idx] = dev.copyWith(isOn: isOn);
    _deviceStreamCtrl.add(List.unmodifiable(_devices));

    // Sync with ActionBox if attached
    if (dev.actionBoxId != null && dev.channel != null) {
      _syncDeviceToActionBox(dev.actionBoxId!, dev.channel!, isOn);
    }
  }

  @override
  Future<void> setDeviceValue(String id, double value) async {
    final idx = _devices.indexWhere((d) => d.id == id);
    if (idx == -1) return;
    final dev = _devices[idx];
    _devices[idx] = dev.copyWith(value: value, isOn: value > 0 ? true : dev.isOn);
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
  }

  @override
  Future<void> toggleFavorite(String id) async {
    final idx = _devices.indexWhere((d) => d.id == id);
    if (idx == -1) return;
    final dev = _devices[idx];
    _devices[idx] = dev.copyWith(isFavorite: !dev.isFavorite);
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
  }

  @override
  Future<void> updateDevice(Device device) async {
    final idx = _devices.indexWhere((d) => d.id == device.id);
    if (idx != -1) {
      _devices[idx] = device;
    } else {
      _devices.add(device);
    }
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
    _emitVocabulary();
  }

  @override
  Future<void> addDevice(Device device) async {
    _devices.add(device);
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
    _emitVocabulary();
  }

  // RoomRepository Implementation
  @override
  Future<List<Room>> getRooms() async => List.unmodifiable(_rooms);

  @override
  Stream<List<Room>> watchRooms() {
    scheduleMicrotask(() => _roomStreamCtrl.add(List.unmodifiable(_rooms)));
    return _roomStreamCtrl.stream;
  }

  // ActionBoxRepository Implementation
  @override
  Future<List<ActionBox>> getActionBoxes() async => List.unmodifiable(_actionBoxes);

  @override
  Stream<List<ActionBox>> watchActionBoxes() {
    scheduleMicrotask(() => _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes)));
    return _actionBoxStreamCtrl.stream;
  }

  @override
  Future<void> updateChannel({
    required String actionBoxId,
    required int channelIndex,
    required String name,
    required DeviceType type,
    required String roomId,
    List<String>? voiceAliases,
  }) async {
    final abIdx = _actionBoxes.indexWhere((ab) => ab.id == actionBoxId);
    if (abIdx == -1) return;
    final ab = _actionBoxes[abIdx];
    final updatedChannels = List<ActionBoxChannel>.from(ab.channels);
    final curCh = updatedChannels[channelIndex];

    final channelKey = curCh.channelKey;
    final deviceId = curCh.deviceId ?? '${actionBoxId}_$channelKey';

    updatedChannels[channelIndex] = curCh.copyWith(
      name: name,
      type: type,
      configured: true,
      deviceId: deviceId,
    );

    _actionBoxes[abIdx] = ab.copyWith(channels: updatedChannels);
    _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));

    // Propagate automatically to DeviceRepository!
    final devIdx = _devices.indexWhere((d) => d.id == deviceId);
    final newAliases = voiceAliases ?? [name.toLowerCase()];
    if (devIdx != -1) {
      _devices[devIdx] = _devices[devIdx].copyWith(
        name: name,
        type: type,
        roomId: roomId,
        voiceAliases: newAliases,
      );
    } else {
      _devices.add(Device(
        id: deviceId,
        name: name,
        type: type,
        roomId: roomId,
        actionBoxId: actionBoxId,
        channel: channelKey,
        online: ab.online,
        isOn: false,
        value: type == DeviceType.light ? 100 : (type == DeviceType.fan ? 1 : 0),
        voiceAliases: newAliases,
      ));
    }
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
    _emitVocabulary();
  }

  void _syncDeviceToActionBox(String actionBoxId, String channelKey, bool isOn) {
    final abIdx = _actionBoxes.indexWhere((ab) => ab.id == actionBoxId);
    if (abIdx == -1) return;
    final ab = _actionBoxes[abIdx];
    final chIdx = ab.channels.indexWhere((c) => c.channelKey == channelKey);
    if (chIdx == -1) return;
    final updatedChannels = List<ActionBoxChannel>.from(ab.channels);
    updatedChannels[chIdx] = updatedChannels[chIdx].copyWith(isOn: isOn);
    _actionBoxes[abIdx] = ab.copyWith(channels: updatedChannels);
    _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));
  }

  @override
  Future<void> addActionBox(ActionBox actionBox) async {
    _actionBoxes.add(actionBox);
    _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));
  }

  // AutomationRepository Implementation
  @override
  Future<List<Automation>> getAutomations() async => List.unmodifiable(_automations);

  @override
  Stream<List<Automation>> watchAutomations() {
    scheduleMicrotask(() => _automationStreamCtrl.add(List.unmodifiable(_automations)));
    return _automationStreamCtrl.stream;
  }

  @override
  Future<void> toggleAutomation(String id, bool enabled) async {
    final idx = _automations.indexWhere((a) => a.id == id);
    if (idx == -1) return;
    _automations[idx] = _automations[idx].copyWith(enabled: enabled);
    _automationStreamCtrl.add(List.unmodifiable(_automations));
  }

  @override
  Future<void> addAutomation(Automation automation) async {
    _automations.add(automation);
    _automationStreamCtrl.add(List.unmodifiable(_automations));
  }

  @override
  Future<void> deleteAutomation(String id) async {
    _automations.removeWhere((a) => a.id == id);
    _automationStreamCtrl.add(List.unmodifiable(_automations));
  }

  // SceneRepository Implementation
  @override
  Future<List<Scene>> getScenes() async => List.unmodifiable(_scenes);

  @override
  Stream<List<Scene>> watchScenes() {
    scheduleMicrotask(() => _sceneStreamCtrl.add(List.unmodifiable(_scenes)));
    return _sceneStreamCtrl.stream;
  }

  @override
  Future<void> activateScene(String id) async {
    // Executes device actions for the scene
    if (id == 'scene_morning') {
      for (var i = 0; i < _devices.length; i++) {
        if (_devices[i].type == DeviceType.light && _devices[i].online) {
          _devices[i] = _devices[i].copyWith(isOn: true, value: 50.0);
        }
      }
    } else if (id == 'scene_night' || id == 'scene_away') {
      for (var i = 0; i < _devices.length; i++) {
        if (_devices[i].online) {
          _devices[i] = _devices[i].copyWith(isOn: false);
        }
      }
    }
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
  }

  // VoiceRepository Implementation
  @override
  Future<List<VoiceVocabularyItem>> getVocabulary() async {
    return _generateVocabulary();
  }

  @override
  Stream<List<VoiceVocabularyItem>> watchVocabulary() {
    scheduleMicrotask(() => _emitVocabulary());
    return _voiceStreamCtrl.stream;
  }

  @override
  Future<void> addAlias(String deviceId, String alias) async {
    final idx = _devices.indexWhere((d) => d.id == deviceId);
    if (idx == -1) return;
    final curAliases = List<String>.from(_devices[idx].voiceAliases);
    if (!curAliases.contains(alias.trim().toLowerCase())) {
      curAliases.add(alias.trim().toLowerCase());
      _devices[idx] = _devices[idx].copyWith(voiceAliases: curAliases);
      _deviceStreamCtrl.add(List.unmodifiable(_devices));
      _emitVocabulary();
    }
  }

  @override
  Future<void> removeAlias(String deviceId, String alias) async {
    final idx = _devices.indexWhere((d) => d.id == deviceId);
    if (idx == -1) return;
    final curAliases = List<String>.from(_devices[idx].voiceAliases);
    curAliases.remove(alias);
    _devices[idx] = _devices[idx].copyWith(voiceAliases: curAliases);
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
    _emitVocabulary();
  }

  List<VoiceVocabularyItem> _generateVocabulary() {
    return _devices.map((d) => VoiceVocabularyItem(
      deviceId: d.id,
      deviceName: d.name,
      aliases: List.unmodifiable(d.voiceAliases),
    )).toList();
  }

  void _emitVocabulary() {
    _voiceStreamCtrl.add(_generateVocabulary());
  }

  @override
  void dispose() {
    _deviceStreamCtrl.close();
    _roomStreamCtrl.close();
    _actionBoxStreamCtrl.close();
    _automationStreamCtrl.close();
    _sceneStreamCtrl.close();
    _voiceStreamCtrl.close();
  }
}
