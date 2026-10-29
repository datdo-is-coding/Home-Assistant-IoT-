import 'dart:async';
import 'package:flutter/material.dart';
import 'package:firebase_database/firebase_database.dart';
import '../model/action_box_model.dart';
import '../model/device_model.dart';
import '../model/room_model.dart';
import '../model/scene_model.dart';
import '../model/voice_alias_model.dart';

class FirebaseRealtimeService {
  // Singleton Pattern
  static final FirebaseRealtimeService _instance =
      FirebaseRealtimeService._internal();
  factory FirebaseRealtimeService() => _instance;
  FirebaseRealtimeService._internal();

  FirebaseDatabase? _database;
  StreamSubscription<DatabaseEvent>? _devicesSubscription;
  StreamSubscription<DatabaseEvent>? _connectedSubscription;
  Timer? _freshnessTimer;

  // Notifiers phục vụ Reactive UI trên Web
  final ValueNotifier<bool> isConnectedNotifier = ValueNotifier<bool>(false);
  final ValueNotifier<bool> isSyncingNotifier = ValueNotifier<bool>(false);
  final ValueNotifier<String?> errorNotifier = ValueNotifier<String?>(null);

  final ValueNotifier<List<ActionBoxModel>> actionBoxesNotifier =
      ValueNotifier<List<ActionBoxModel>>([]);
  final ValueNotifier<List<RoomModel>> roomsNotifier =
      ValueNotifier<List<RoomModel>>([]);
  final ValueNotifier<double> totalPowerNotifier = ValueNotifier<double>(0.0);
  final ValueNotifier<double> totalEnergyNotifier = ValueNotifier<double>(0.0);
  final ValueNotifier<int> onlineCountNotifier = ValueNotifier<int>(0);
  final ValueNotifier<int> totalDeviceCountNotifier = ValueNotifier<int>(0);

  final ValueNotifier<List<SceneModel>> scenesNotifier =
      ValueNotifier<List<SceneModel>>([]);
  final ValueNotifier<List<VoiceAliasModel>> voiceAliasesNotifier =
      ValueNotifier<List<VoiceAliasModel>>([]);

  final Map<String, DateTime> _lastObservedTime = {};
  bool _initialized = false;

  void init() {
    if (_initialized) return;
    _initialized = true;

    _setupDefaultScenes();
    _setupDefaultVoiceAliases();
    _setupInitialFallbackData();

    try {
      _database = FirebaseDatabase.instance;
      // 1. Lắng nghe trạng thái kết nối Cloud
      _connectedSubscription =
          _database!.ref('.info/connected').onValue.listen((event) {
        final connected = event.snapshot.value == true;
        isConnectedNotifier.value = connected;
        if (!connected) {
          errorNotifier.value = 'Đang chờ kết nối Firebase RTDB...';
        } else {
          errorNotifier.value = null;
        }
      }, onError: (e) {
        isConnectedNotifier.value = false;
        errorNotifier.value = 'Lỗi kết nối Firebase: $e';
      });

      // 2. Lắng nghe cây "devices"
      isSyncingNotifier.value = true;
      _devicesSubscription =
          _database!.ref('devices').onValue.listen((event) {
        isSyncingNotifier.value = false;
        errorNotifier.value = null;
        final data = event.snapshot.value;
        if (data is Map) {
          _processDevicesSnapshot(Map<String, dynamic>.from(data));
        }
      }, onError: (e) {
        isSyncingNotifier.value = false;
        errorNotifier.value = 'Không tải được danh sách thiết bị: $e';
      });

      // 3. Timer kiểm tra độ tươi (Freshness Guard: 15s)
      _freshnessTimer = Timer.periodic(const Duration(seconds: 5), (_) {
        _checkFreshness();
      });
    } catch (e) {
      debugPrint('FirebaseRealtimeService init notice: $e');
      errorNotifier.value = 'Khởi tạo Firebase thất bại: $e';
    }
  }

  /// Bật / Tắt trạng thái kênh Relay thật trên Firebase RTDB
  Future<void> toggleChannel(
      String boxId, String channelKey, bool newState) async {
    // Cập nhật Optimistic UI ngay lập tức
    _applyOptimisticToggle(boxId, channelKey, newState);

    try {
      if (_database != null) {
        await _database!
            .ref('devices/$boxId/channels/$channelKey/state')
            .set(newState);
      }
    } catch (e) {
      debugPrint('Lỗi ghi lệnh toggleChannel lên Firebase: $e');
      errorNotifier.value = 'Gửi lệnh thất bại: $e';
    }
  }

  /// Kích hoạt kịch bản (Scene)
  Future<void> triggerScene(SceneModel scene) async {
    // Đánh dấu active cho scene được chọn
    final currentScenes = scenesNotifier.value;
    scenesNotifier.value = [
      for (final s in currentScenes)
        s.copyWith(isActive: s.id == scene.id),
    ];

    for (final action in scene.actions) {
      await toggleChannel(action.boxId, action.channelKey, action.targetState);
    }
  }

  /// Cập nhật từ đồng nghĩa giọng nói (Voice Alias)
  Future<void> updateVoiceAliases(
      String boxId, String channelKey, List<String> newAliases) async {
    final list = voiceAliasesNotifier.value;
    final index = list.indexWhere(
        (v) => v.boxId == boxId && v.channelKey == channelKey);
    if (index >= 0) {
      final updated = List<VoiceAliasModel>.from(list);
      updated[index] = updated[index].copyWith(aliases: newAliases);
      voiceAliasesNotifier.value = updated;
    }

    try {
      if (_database != null) {
        await _database!
            .ref('devices/$boxId/channels/$channelKey/voice_aliases')
            .set(newAliases);
      }
    } catch (e) {
      debugPrint('Lỗi lưu voice aliases: $e');
    }
  }

  void _applyOptimisticToggle(String boxId, String channelKey, bool newState) {
    // Cập nhật trong ActionBoxes
    final boxes = List<ActionBoxModel>.from(actionBoxesNotifier.value);
    final bIndex = boxes.indexWhere((b) => b.id == boxId);
    if (bIndex >= 0) {
      final box = boxes[bIndex];
      final channels = List<ActionBoxChannelModel>.from(box.channels);
      final cIndex = channels.indexWhere((c) => c.channelKey == channelKey);
      if (cIndex >= 0) {
        channels[cIndex] = channels[cIndex].copyWith(state: newState);
        boxes[bIndex] = box.copyWith(channels: channels);
        actionBoxesNotifier.value = boxes;
      }
    }

    // Cập nhật trong Rooms
    final rooms = List<RoomModel>.from(roomsNotifier.value);
    for (int r = 0; r < rooms.length; r++) {
      final room = rooms[r];
      final devices = List<DeviceModel>.from(room.devices);
      for (int d = 0; d < devices.length; d++) {
        final dev = devices[d];
        if (dev.boxId == boxId && dev.channelKey == channelKey) {
          devices[d] = dev.copyWith(isOn: newState);
        }
      }
      rooms[r] = RoomModel(id: room.id, name: room.name, devices: devices);
    }
    roomsNotifier.value = rooms;
  }

  void _processDevicesSnapshot(Map<String, dynamic> raw) {
    final now = DateTime.now();
    final List<ActionBoxModel> parsedBoxes = [];
    final Map<String, List<DeviceModel>> roomsMap = {};

    double sumPower = 0.0;
    double sumEnergy = 0.0;
    int onlineCount = 0;
    int totalDevices = 0;

    raw.forEach((boxId, boxVal) {
      if (boxVal is! Map) return;
      final boxData = Map<String, dynamic>.from(boxVal);

      // Tính toán độ tươi (15s)
      final num? rawStamp = boxData['last_updated'] is num
          ? boxData['last_updated']
          : num.tryParse(boxData['last_updated']?.toString() ?? '');

      DateTime? lastSeen;
      if (rawStamp != null) {
        final ms = rawStamp > 100000000000 ? rawStamp.toDouble() : rawStamp * 1000.0;
        lastSeen = DateTime.fromMillisecondsSinceEpoch(ms.round());
      }
      if (lastSeen != null) {
        _lastObservedTime[boxId] = lastSeen;
      } else {
        lastSeen = _lastObservedTime[boxId] ?? now;
      }

      final diffMs = now.difference(lastSeen).inMilliseconds;
      final bool isFresh = diffMs >= -5000 && diffMs <= 15000;
      final bool isOnline = boxData['online'] == true && isFresh;

      if (isOnline) onlineCount++;

      final String roomName = boxData['room']?.toString() ?? 'Chưa phân phòng';
      final String boxName = boxData['name']?.toString() ?? boxId;

      final List<ActionBoxChannelModel> channels = [];
      final rawChannels = boxData['channels'];

      if (rawChannels is Map) {
        final chMap = Map<String, dynamic>.from(rawChannels);
        for (final key in ['ch1', 'ch2', 'ch3']) {
          if (!chMap.containsKey(key) || chMap[key] is! Map) continue;
          final chData = Map<String, dynamic>.from(chMap[key]);

          final int index = int.tryParse(key.replaceAll('ch', '')) ?? 1;
          final String chName = chData['name']?.toString() ?? 'Thiết bị $key';
          final String dType = chData['device_type']?.toString() ?? 'light';
          final bool state = chData['state'] == true;
          final double voltage = (chData['voltage'] as num?)?.toDouble() ?? 220.0;
          final double current = (chData['current'] as num?)?.toDouble() ?? 0.0;
          final double power = (chData['power'] as num?)?.toDouble() ?? 0.0;
          final double energy = (chData['energy_kwh'] as num?)?.toDouble() ?? 0.0;

          if (state && isOnline) {
            sumPower += power;
          }
          sumEnergy += energy;
          totalDevices++;

          final channelModel = ActionBoxChannelModel(
            index: index,
            channelKey: key,
            name: chName,
            deviceType: dType,
            state: state,
            voltage: voltage,
            current: current,
            power: power,
            energyKwh: energy,
          );
          channels.add(channelModel);

          // Chuyển đổi thành DeviceModel cho danh sách phòng
          final deviceModel = DeviceModel(
            id: '${boxId}_$key',
            name: chName,
            icon: _getIconName(dType),
            isOn: state,
            powerWatts: power,
            boxId: boxId,
            channelKey: key,
            deviceType: dType,
            voltage: voltage,
            current: current,
            energyKwh: energy,
            online: isOnline,
            roomName: roomName,
            color: channelModel.accentColor,
            hourlyKwh: _generateHourlyEstimate(power, state),
          );

          roomsMap.putIfAbsent(roomName, () => []).add(deviceModel);
        }
      }

      parsedBoxes.add(ActionBoxModel(
        id: boxId,
        name: boxName,
        room: roomName,
        online: isOnline,
        ip: boxData['ip']?.toString() ?? '192.168.1.102',
        firmwareVersion: boxData['firmware_version']?.toString() ?? 'v2.1.0-esp32s3',
        boardModel: boxData['board_model']?.toString() ?? (boxId.startsWith('SB') ? 'SubBox' : 'ActionBox_V2'),
        totalPower: (boxData['total_power'] as num?)?.toDouble() ?? sumPower,
        totalEnergyKwh: (boxData['total_energy_kwh'] as num?)?.toDouble() ?? sumEnergy,
        lastUpdated: lastSeen,
        channels: channels,
      ));
    });

    if (parsedBoxes.isNotEmpty) {
      actionBoxesNotifier.value = parsedBoxes;
      totalPowerNotifier.value = sumPower;
      totalEnergyNotifier.value = sumEnergy;
      onlineCountNotifier.value = onlineCount;
      totalDeviceCountNotifier.value = totalDevices;

      // Xây dựng List<RoomModel>
      int rIdx = 1;
      final List<RoomModel> roomsList = [];
      roomsMap.forEach((rName, devs) {
        roomsList.add(RoomModel(id: 'r$rIdx', name: rName, devices: devs));
        rIdx++;
      });
      roomsNotifier.value = roomsList;
    }
  }

  void _checkFreshness() {
    if (actionBoxesNotifier.value.isEmpty) return;
    final now = DateTime.now();
    bool changed = false;
    final updatedBoxes = <ActionBoxModel>[];

    for (final box in actionBoxesNotifier.value) {
      final last = box.lastUpdated ?? _lastObservedTime[box.id];
      final diff = last == null ? 999999 : now.difference(last).inMilliseconds;
      final isFresh = diff >= -5000 && diff <= 15000;
      if (box.online != isFresh) {
        changed = true;
        updatedBoxes.add(box.copyWith(online: isFresh));
      } else {
        updatedBoxes.add(box);
      }
    }

    if (changed) {
      actionBoxesNotifier.value = updatedBoxes;
      onlineCountNotifier.value = updatedBoxes.where((b) => b.online).length;
    }
  }

  String _getIconName(String type) {
    switch (type.toLowerCase()) {
      case 'light':
      case 'lamp':
        return 'lightbulb';
      case 'fan':
        return 'mode_fan_off';
      case 'socket':
      case 'outlet':
        return 'power';
      case 'airconditioner':
      case 'ac':
        return 'ac_unit';
      default:
        return 'devices_other';
    }
  }

  List<double> _generateHourlyEstimate(double powerWatts, bool isOn) {
    final double kwh = (powerWatts * 0.8) / 1000.0;
    return List.generate(24, (i) {
      if (i >= 7 && i <= 23 && isOn) {
        return (kwh * (0.8 + (i % 5) * 0.1));
      }
      return 0.01;
    });
  }

  void _setupDefaultScenes() {
    scenesNotifier.value = [
      SceneModel(
        id: 'scene_home',
        name: 'Về Nhà',
        description: 'Bật đèn phòng khách, khởi động quạt và máy lạnh làm mát.',
        icon: Icons.home_rounded,
        color: const Color(0xFF3B82F6),
        actions: const [
          SceneAction(boxId: 'action_box_01', channelKey: 'ch1', targetState: true),
          SceneAction(boxId: 'action_box_01', channelKey: 'ch2', targetState: true),
        ],
      ),
      SceneModel(
        id: 'scene_away',
        name: 'Ra Ngoài',
        description: 'Tắt toàn bộ thiết bị và đèn ở tất cả các phòng để tiết kiệm điện.',
        icon: Icons.directions_run_rounded,
        color: const Color(0xFFEF4444),
        actions: const [
          SceneAction(boxId: 'action_box_01', channelKey: 'ch1', targetState: false),
          SceneAction(boxId: 'action_box_01', channelKey: 'ch2', targetState: false),
          SceneAction(boxId: 'action_box_01', channelKey: 'ch3', targetState: false),
        ],
      ),
      SceneModel(
        id: 'scene_sleep',
        name: 'Đi Ngủ',
        description: 'Tắt đèn chiếu sáng phòng khách, bật đèn ngủ dịu nhẹ và điều hòa.',
        icon: Icons.bedtime_rounded,
        color: const Color(0xFF8B5CF6),
        actions: const [
          SceneAction(boxId: 'action_box_01', channelKey: 'ch1', targetState: false),
          SceneAction(boxId: 'action_box_01', channelKey: 'ch2', targetState: true),
        ],
      ),
      SceneModel(
        id: 'scene_morning',
        name: 'Thức Dậy',
        description: 'Tắt điều hòa, bật đèn phòng ngủ và mở quạt đón gió sáng.',
        icon: Icons.wb_sunny_rounded,
        color: const Color(0xFFF59E0B),
        actions: const [
          SceneAction(boxId: 'action_box_01', channelKey: 'ch1', targetState: true),
          SceneAction(boxId: 'action_box_01', channelKey: 'ch2', targetState: false),
        ],
      ),
    ];
  }

  void _setupDefaultVoiceAliases() {
    voiceAliasesNotifier.value = [
      const VoiceAliasModel(
        boxId: 'action_box_01',
        channelKey: 'ch1',
        deviceName: 'Đèn trần',
        roomName: 'Phòng khách',
        aliases: ['bật đèn', 'tắt đèn', 'mở đèn trần', 'đèn phòng khách'],
      ),
      const VoiceAliasModel(
        boxId: 'action_box_01',
        channelKey: 'ch2',
        deviceName: 'Quạt trần',
        roomName: 'Phòng khách',
        aliases: ['bật quạt', 'tắt quạt', 'mở quạt trần', 'quạt số 2'],
      ),
      const VoiceAliasModel(
        boxId: 'action_box_01',
        channelKey: 'ch3',
        deviceName: 'Ổ cắm phụ',
        roomName: 'Phòng khách',
        aliases: ['bật ổ cắm', 'tắt sạc', 'mở nguồn'],
      ),
    ];
  }

  void _setupInitialFallbackData() {
    final sampleChannels = [
      const ActionBoxChannelModel(
        index: 1,
        channelKey: 'ch1',
        name: 'Đèn chùm',
        deviceType: 'light',
        state: true,
        voltage: 220.0,
        current: 0.18,
        power: 40.0,
        energyKwh: 1.25,
      ),
      const ActionBoxChannelModel(
        index: 2,
        channelKey: 'ch2',
        name: 'Quạt trần',
        deviceType: 'fan',
        state: true,
        voltage: 220.0,
        current: 0.25,
        power: 55.0,
        energyKwh: 0.85,
      ),
      const ActionBoxChannelModel(
        index: 3,
        channelKey: 'ch3',
        name: 'Ổ cắm sạc',
        deviceType: 'socket',
        state: false,
        voltage: 220.0,
        current: 0.0,
        power: 0.0,
        energyKwh: 0.32,
      ),
    ];

    final defaultBoxes = [
      ActionBoxModel(
        id: 'action_box_01',
        name: 'ActionBox V2 - Trung Tâm',
        room: 'Phòng khách',
        online: true,
        ip: '192.168.1.105',
        firmwareVersion: 'v2.1.0-esp32s3',
        boardModel: 'ActionBox_V2',
        totalPower: 95.0,
        totalEnergyKwh: 2.42,
        channels: sampleChannels,
      ),
      const ActionBoxModel(
        id: 'subbox_01',
        name: 'SubBox S3 - Điều Phối & KWS',
        room: 'Phòng khách',
        online: true,
        ip: '192.168.1.108',
        firmwareVersion: 'v2.0.3-subbox',
        boardModel: 'SubBox',
        totalPower: 3.5,
        totalEnergyKwh: 0.15,
        channels: [],
      ),
    ];

    actionBoxesNotifier.value = defaultBoxes;
    totalPowerNotifier.value = 95.0;
    totalEnergyNotifier.value = 2.57;
    onlineCountNotifier.value = 2;
    totalDeviceCountNotifier.value = 3;

    roomsNotifier.value = [
      RoomModel(
        id: 'r1',
        name: 'Phòng khách',
        devices: [
          DeviceModel(
            id: 'action_box_01_ch1',
            name: 'Đèn chùm',
            icon: 'lightbulb',
            isOn: true,
            powerWatts: 40.0,
            boxId: 'action_box_01',
            channelKey: 'ch1',
            deviceType: 'light',
            voltage: 220.0,
            current: 0.18,
            energyKwh: 1.25,
            online: true,
            roomName: 'Phòng khách',
            color: const Color(0xFFF59E0B),
            hourlyKwh: _generateHourlyEstimate(40.0, true),
          ),
          DeviceModel(
            id: 'action_box_01_ch2',
            name: 'Quạt trần',
            icon: 'mode_fan_off',
            isOn: true,
            powerWatts: 55.0,
            boxId: 'action_box_01',
            channelKey: 'ch2',
            deviceType: 'fan',
            voltage: 220.0,
            current: 0.25,
            energyKwh: 0.85,
            online: true,
            roomName: 'Phòng khách',
            color: const Color(0xFF3B82F6),
            hourlyKwh: _generateHourlyEstimate(55.0, true),
          ),
          DeviceModel(
            id: 'action_box_01_ch3',
            name: 'Ổ cắm sạc',
            icon: 'power',
            isOn: false,
            powerWatts: 0.0,
            boxId: 'action_box_01',
            channelKey: 'ch3',
            deviceType: 'socket',
            voltage: 220.0,
            current: 0.0,
            energyKwh: 0.32,
            online: true,
            roomName: 'Phòng khách',
            color: const Color(0xFF8B5CF6),
            hourlyKwh: _generateHourlyEstimate(0.0, false),
          ),
        ],
      ),
      RoomModel(
        id: 'r2',
        name: 'Phòng ngủ',
        devices: [
          DeviceModel(
            id: 'dev_bedroom_light',
            name: 'Đèn ngủ dịu',
            icon: 'lightbulb',
            isOn: false,
            powerWatts: 15.0,
            boxId: 'action_box_02',
            channelKey: 'ch1',
            deviceType: 'light',
            voltage: 220.0,
            current: 0.07,
            energyKwh: 0.45,
            online: true,
            roomName: 'Phòng ngủ',
            color: const Color(0xFFF59E0B),
            hourlyKwh: _generateHourlyEstimate(15.0, false),
          ),
          DeviceModel(
            id: 'dev_bedroom_ac',
            name: 'Điều hòa Inverter',
            icon: 'ac_unit',
            isOn: false,
            powerWatts: 750.0,
            boxId: 'action_box_02',
            channelKey: 'ch2',
            deviceType: 'airConditioner',
            voltage: 220.0,
            current: 3.4,
            energyKwh: 5.60,
            online: true,
            roomName: 'Phòng ngủ',
            color: const Color(0xFF06B6D4),
            hourlyKwh: _generateHourlyEstimate(750.0, false),
          ),
        ],
      ),
    ];
  }

  void dispose() {
    _devicesSubscription?.cancel();
    _connectedSubscription?.cancel();
    _freshnessTimer?.cancel();
  }
}
