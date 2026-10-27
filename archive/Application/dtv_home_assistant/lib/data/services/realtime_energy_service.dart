import 'dart:async';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/foundation.dart';

class ChannelData {
  final String key;
  final String id;
  final String name;
  final bool state;
  final double voltage;
  final double current;
  final double power;
  final double energyKwh;

  ChannelData({
    required this.key,
    required this.id,
    required this.name,
    required this.state,
    required this.voltage,
    required this.current,
    required this.power,
    required this.energyKwh,
  });

  factory ChannelData.fromMap(String key, Map<dynamic, dynamic> map) {
    return ChannelData(
      key: key,
      id: map['id']?.toString() ?? key,
      name: map['name']?.toString() ?? 'Thiết bị',
      state: map['state'] == true,
      voltage: (map['voltage'] as num?)?.toDouble() ?? 0.0,
      current: (map['current'] as num?)?.toDouble() ?? 0.0,
      power: (map['power'] as num?)?.toDouble() ?? 0.0,
      energyKwh: (map['energy_kwh'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class ActionBoxData {
  final String deviceId;
  final String name;
  final bool online;
  final double voltage;
  final double totalCurrent;
  final double totalPower;
  final double totalEnergyKwh;
  final DateTime? lastUpdated;
  final Map<String, ChannelData> channels;

  ActionBoxData({
    required this.deviceId,
    required this.name,
    required this.online,
    required this.voltage,
    required this.totalCurrent,
    required this.totalPower,
    required this.totalEnergyKwh,
    this.lastUpdated,
    required this.channels,
  });

  factory ActionBoxData.fromMap(Map<dynamic, dynamic> map) {
    final channelsMap = <String, ChannelData>{};
    if (map['channels'] is Map) {
      final chs = map['channels'] as Map<dynamic, dynamic>;
      chs.forEach((key, val) {
        if (val is Map) {
          channelsMap[key.toString()] = ChannelData.fromMap(key.toString(), val);
        }
      });
    }

    DateTime? updated;
    if (map['last_updated'] != null) {
      final raw = map['last_updated'];
      if (raw is num) {
        // can be seconds or milliseconds
        if (raw > 10000000000) {
          updated = DateTime.fromMillisecondsSinceEpoch(raw.toInt());
        } else {
          updated = DateTime.fromMillisecondsSinceEpoch((raw * 1000).toInt());
        }
      }
    }

    return ActionBoxData(
      deviceId: map['device_id']?.toString() ?? 'action_box_01',
      name: map['name']?.toString() ?? 'Action Box',
      online: map['online'] == true,
      voltage: (map['voltage'] as num?)?.toDouble() ?? 0.0,
      totalCurrent: (map['total_current'] as num?)?.toDouble() ?? 0.0,
      totalPower: (map['total_power'] as num?)?.toDouble() ?? 0.0,
      totalEnergyKwh: (map['total_energy_kwh'] as num?)?.toDouble() ?? 0.0,
      lastUpdated: updated,
      channels: channelsMap,
    );
  }
}

class RealtimeEnergyService {
  static final RealtimeEnergyService instance = RealtimeEnergyService._internal();

  RealtimeEnergyService._internal();

  static const String databaseUrl =
      'https://home-companion-fed2e-default-rtdb.asia-southeast1.firebasedatabase.app';

  late final DatabaseReference _dbRef = FirebaseDatabase.instanceFor(
    app: Firebase.app(),
    databaseURL: databaseUrl,
  ).ref('devices/action_box_01');

  StreamSubscription<DatabaseEvent>? _subscription;

  final ValueNotifier<ActionBoxData?> deviceDataNotifier = ValueNotifier<ActionBoxData?>(null);
  final ValueNotifier<bool> isConnectedNotifier = ValueNotifier<bool>(false);

  void init() {
    if (_subscription != null) return;

    debugPrint('⚡ [RealtimeEnergyService] Initializing Firebase listener on devices/action_box_01...');

    _subscription = _dbRef.onValue.listen(
      (event) {
        final data = event.snapshot.value;
        if (data != null && data is Map) {
          final parsed = ActionBoxData.fromMap(data);
          deviceDataNotifier.value = parsed;
          isConnectedNotifier.value = true;
          debugPrint('⚡ [RealtimeEnergyService] Received update: ${parsed.totalPower}W, ${parsed.totalCurrent}A, ${parsed.voltage}V');
        } else {
          isConnectedNotifier.value = false;
        }
      },
      onError: (error) {
        debugPrint('❌ [RealtimeEnergyService] Error listening to Firebase: $error');
        isConnectedNotifier.value = false;
      },
    );
  }

  Future<void> setChannelState(String channelKey, bool newState) async {
    try {
      await _dbRef.child('channels/$channelKey/state').set(newState);
      debugPrint('⚡ [RealtimeEnergyService] Set $channelKey state to $newState in Firebase');
    } catch (e) {
      debugPrint('❌ [RealtimeEnergyService] Failed to set $channelKey state: $e');
    }
  }

  void dispose() {
    _subscription?.cancel();
    _subscription = null;
  }
}
