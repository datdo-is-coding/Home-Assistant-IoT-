import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/device.dart';
import '../models/room.dart';
import '../models/action_box.dart';
import '../models/scene.dart';
import '../models/automation.dart';
import '../models/voice_alias.dart';

import '../services/app_preferences_service.dart';
import '../services/gateway_client.dart';
import '../services/gateway_event_stream.dart';

class ChangedResources {
  final bool devicesChanged;
  final bool roomsChanged;
  final bool actionBoxesChanged;
  final bool vocabularyChanged;
  final bool scenesChanged;
  const ChangedResources({
    this.devicesChanged = false,
    this.roomsChanged = false,
    this.actionBoxesChanged = false,
    this.vocabularyChanged = false,
    this.scenesChanged = false,
  });
  bool get hasChanges =>
      devicesChanged ||
      roomsChanged ||
      actionBoxesChanged ||
      vocabularyChanged ||
      scenesChanged;
}

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
  Map<String, Device> get deviceMap;
  void dispose();
}

class GatewaySmartHomeRepository implements SmartHomeRepository {
  final GatewayClient gateway;
  final AppPreferencesService preferencesService;
  String _currentLoadedScopeKey = '';
  Future<void>? _currentFavoritesLoad;

  final _deviceStreamCtrl = StreamController<List<Device>>.broadcast();
  final _roomStreamCtrl = StreamController<List<Room>>.broadcast();
  final _actionBoxStreamCtrl = StreamController<List<ActionBox>>.broadcast();
  final _automationStreamCtrl = StreamController<List<Automation>>.broadcast();
  final _sceneStreamCtrl = StreamController<List<Scene>>.broadcast();
  final _voiceStreamCtrl = StreamController<List<VoiceVocabularyItem>>.broadcast();

  final Set<String> _favoriteIds = {};
  final Map<String, Device> _deviceMap = {};
  final Map<String, ActionBox> _actionBoxMap = {};
  List<Device> _devices = [];
  List<Room> _rooms = [];
  List<ActionBox> _actionBoxes = [];
  List<Scene> _scenes = [];
  final List<Automation> _automations = [];
  static const String _kAutomationsPrefKey = 'aetheria_saved_automations';

  StreamSubscription<GatewayEvent>? _eventSub;
  Timer? _meterExpiryTimer;

  GatewaySmartHomeRepository(
    this.gateway, {
    AppPreferencesService? preferencesService,
  }) : preferencesService = preferencesService ?? AppPreferencesService() {
    gateway.addListener(_syncFromGateway);
    _eventSub = gateway.eventStreamBroadcast.listen((evt) {
      applyEvent(evt.name, evt.data);
    });
    _loadPersistedAutomations();
    _syncFromGateway();
  }

  Future<void> _loadPersistedAutomations() async {
    final scope = _currentScopeKey;
    try {
      WidgetsFlutterBinding.ensureInitialized();
      final prefs = await SharedPreferences.getInstance();
      if (gateway.usesFirebase && scope != _currentScopeKey) return;
      final key = gateway.usesFirebase ? '${_kAutomationsPrefKey}_$scope' : _kAutomationsPrefKey;
      final raw = prefs.getString(key);
      if (raw != null && raw.isNotEmpty) {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          _automations.clear();
          for (final item in decoded) {
            if (item is Map<String, dynamic>) {
              _automations.add(Automation.fromJson(item));
            } else if (item is Map) {
              _automations.add(Automation.fromJson(Map<String, dynamic>.from(item)));
            }
          }
          if (!_automationStreamCtrl.isClosed) {
            _automationStreamCtrl.add(List.unmodifiable(_automations));
          }
        }
      }
    } catch (e) {
      debugPrint('Failed to load automations: $e');
    }
  }

  Future<void> _savePersistedAutomations() async {
    final scope = _currentScopeKey;
    final list = _automations.map((a) => a.toJson()).toList();
    try {
      WidgetsFlutterBinding.ensureInitialized();
      final prefs = await SharedPreferences.getInstance();
      final key = gateway.usesFirebase ? '${_kAutomationsPrefKey}_$scope' : _kAutomationsPrefKey;
      await prefs.setString(key, jsonEncode(list));
    } catch (e) {
      debugPrint('Failed to save automations: $e');
    }
  }

  String get _currentScopeKey => gateway.authenticated
      ? AppPreferencesService.scopeKey(gateway.serverUrl, gateway.currentUserId)
      : '';

  void _syncFromGateway() {
    final scopeKey = _currentScopeKey;
    if (scopeKey != _currentLoadedScopeKey) {
      _currentLoadedScopeKey = scopeKey;
      if (gateway.usesFirebase) {
        _automations.clear();
        _automationStreamCtrl.add(const []);
        if (gateway.authenticated) _loadPersistedAutomations();
      }
      if (!gateway.authenticated) {
        _favoriteIds.clear();
        _applyFavoritesToDeviceMap();
        _currentFavoritesLoad = null;
      } else {
        _currentFavoritesLoad = _loadFavoritesForCurrentScope();
      }
    }
    applySnapshot(gateway.nodes);
  }

  Future<void> _loadFavoritesForCurrentScope() async {
    if (!gateway.authenticated) {
      _favoriteIds.clear();
      _applyFavoritesToDeviceMap();
      return;
    }
    final targetScope = _currentScopeKey;
    final loaded = await preferencesService.loadFavoriteIds(
      gatewayUrl: gateway.serverUrl,
      userId: gateway.currentUserId,
    );
    if (targetScope != _currentScopeKey) return;
    _favoriteIds.clear();
    _favoriteIds.addAll(loaded);
    _applyFavoritesToDeviceMap();
  }

  void _applyFavoritesToDeviceMap() {
    bool changed = false;
    for (final entry in _deviceMap.entries) {
      final isFav = _favoriteIds.contains(entry.key);
      if (entry.value.isFavorite != isFav) {
        _deviceMap[entry.key] = entry.value.copyWith(isFavorite: isFav);
        changed = true;
      }
    }
    if (changed) {
      _devices = _deviceMap.values.toList();
      if (!_deviceStreamCtrl.isClosed) {
        _deviceStreamCtrl.add(List.unmodifiable(_devices));
      }
    }
  }

  static bool _isDeviceEqual(Device a, Device b) {
    if (identical(a, b)) return true;
    return a.name == b.name &&
        a.isOn == b.isOn &&
        a.online == b.online &&
        a.powerWatts == b.powerWatts &&
        a.channel == b.channel &&
        a.roomId == b.roomId &&
        a.type == b.type &&
        listEquals(a.voiceAliases, b.voiceAliases) &&
        a.isFavorite == b.isFavorite &&
        a.value == b.value &&
        a.actionBoxId == b.actionBoxId &&
        mapEquals(a.metadata, b.metadata);
  }

  static bool _isActionBoxEqual(ActionBox a, ActionBox b) {
    if (identical(a, b)) return true;
    if (a.name != b.name ||
        a.online != b.online ||
        a.subboxId != b.subboxId ||
        a.ownerEpoch != b.ownerEpoch ||
        a.protocolVersion != b.protocolVersion ||
        a.roomId != b.roomId ||
        a.firmwareVersion != b.firmwareVersion ||
        a.boardModel != b.boardModel ||
        a.boardRevision != b.boardRevision ||
        !listEquals(a.capabilities, b.capabilities) ||
        a.channels.length != b.channels.length) {
      return false;
    }
    for (int i = 0; i < a.channels.length; i++) {
      final cA = a.channels[i];
      final cB = b.channels[i];
      if (cA.isOn != cB.isOn ||
          cA.name != cB.name ||
          cA.type != cB.type ||
          cA.channelKey != cB.channelKey ||
          cA.configured != cB.configured) {
        return false;
      }
    }
    return true;
  }

  ChangedResources applySnapshot(Map<String, dynamic> nodes, {int? revision}) {
    final candidateDevices = _buildCandidateDevices(nodes);
    if (candidateDevices.any((d) => d.metadata['metered'] == true)) {
      _meterExpiryTimer ??= Timer.periodic(const Duration(seconds: 5), (_) => applySnapshot(gateway.nodes));
    } else {
      _meterExpiryTimer?.cancel();
      _meterExpiryTimer = null;
    }
    final candidateActionBoxes = _buildCandidateActionBoxes(nodes);

    bool devicesChanged = false;
    bool vocabularyChanged = false;

    final candidateDeviceIds = <String>{};
    for (final candidate in candidateDevices) {
      candidateDeviceIds.add(candidate.id);
      final existing = _deviceMap[candidate.id];
      if (existing != null && _isDeviceEqual(existing, candidate)) {
        // Keep the exact object reference!
      } else {
        if (existing == null ||
            existing.name != candidate.name ||
            !listEquals(existing.voiceAliases, candidate.voiceAliases)) {
          vocabularyChanged = true;
        }
        _deviceMap[candidate.id] = candidate;
        devicesChanged = true;
      }
    }

    final removedDeviceIds = _deviceMap.keys.where((id) => !candidateDeviceIds.contains(id)).toList();
    if (removedDeviceIds.isNotEmpty) {
      for (final id in removedDeviceIds) {
        _deviceMap.remove(id);
      }
      devicesChanged = true;
      vocabularyChanged = true;
    }

    bool actionBoxesChanged = false;
    final candidateBoxIds = <String>{};
    for (final candidate in candidateActionBoxes) {
      candidateBoxIds.add(candidate.id);
      final existing = _actionBoxMap[candidate.id];
      if (existing != null && _isActionBoxEqual(existing, candidate)) {
        // Keep existing object reference!
      } else {
        _actionBoxMap[candidate.id] = candidate;
        actionBoxesChanged = true;
      }
    }

    final removedBoxIds = _actionBoxMap.keys.where((id) => !candidateBoxIds.contains(id)).toList();
    if (removedBoxIds.isNotEmpty) {
      for (final id in removedBoxIds) {
        _actionBoxMap.remove(id);
      }
      actionBoxesChanged = true;
    }

    final currentDevices = _deviceMap.values.toList();
    final candidateRooms = _buildRooms(currentDevices);
    bool roomsChanged = false;
    if (_rooms.length != candidateRooms.length) {
      roomsChanged = true;
    } else {
      for (final cr in candidateRooms) {
        final er = _rooms.where((r) => r.id == cr.id).firstOrNull;
        if (er == null) {
          roomsChanged = true;
          break;
        }
        final oldCount = _devices.where((d) => d.roomId == cr.id).length;
        final newCount = currentDevices.where((d) => d.roomId == cr.id).length;
        if (oldCount != newCount) {
          roomsChanged = true;
          break;
        }
      }
    }

    final candidateScenes = _buildScenes(currentDevices);
    bool scenesChanged = false;
    if (_scenes.length != candidateScenes.length) {
      scenesChanged = true;
    } else {
      for (int i = 0; i < candidateScenes.length; i++) {
        if (_scenes[i].id != candidateScenes[i].id ||
            _scenes[i].deviceCount != candidateScenes[i].deviceCount) {
          scenesChanged = true;
          break;
        }
      }
    }

    _devices = currentDevices;
    _actionBoxes = _actionBoxMap.values.toList();
    if (roomsChanged) _rooms = candidateRooms;
    if (scenesChanged) _scenes = candidateScenes;

    if (devicesChanged && !_deviceStreamCtrl.isClosed) {
      _deviceStreamCtrl.add(List.unmodifiable(_devices));
    }
    if (roomsChanged && !_roomStreamCtrl.isClosed) {
      _roomStreamCtrl.add(List.unmodifiable(_rooms));
    }
    if (actionBoxesChanged && !_actionBoxStreamCtrl.isClosed) {
      _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));
    }
    if (vocabularyChanged && !_voiceStreamCtrl.isClosed) {
      _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
    }
    if (scenesChanged && !_sceneStreamCtrl.isClosed) {
      _sceneStreamCtrl.add(List.unmodifiable(_scenes));
    }

    return ChangedResources(
      devicesChanged: devicesChanged,
      roomsChanged: roomsChanged,
      actionBoxesChanged: actionBoxesChanged,
      vocabularyChanged: vocabularyChanged,
      scenesChanged: scenesChanged,
    );
  }

  ChangedResources applyEvent(String eventName, Map<String, dynamic> data) {
    bool devicesChanged = false;
    bool roomsChanged = false;
    bool actionBoxesChanged = false;
    bool vocabularyChanged = false;
    bool scenesChanged = false;

    final nodeId = (data['node_id'] ?? data['device_id'])?.toString();

    switch (eventName) {
      case 'relay_state':
        if (nodeId != null) {
          final rl = data['relay_state'];
          if (rl is List) {
            for (int i = 0; i < rl.length; i++) {
              final chKey = 'ch${i + 1}';
              final devId = '$nodeId::$chKey';
              final dev = _deviceMap[devId];
              if (dev != null) {
                final val = rl[i];
                final bool targetOn = (val == 1 || val == true || val == 'ON');
                if (dev.isOn != targetOn) {
                  _deviceMap[devId] = dev.copyWith(isOn: targetOn);
                  devicesChanged = true;
                }
              }
            }
          } else if (data.containsKey('channel') && data.containsKey('state')) {
            final chKey = data['channel'].toString();
            final devId = '$nodeId::$chKey';
            final dev = _deviceMap[devId];
            if (dev != null) {
              final state = data['state'];
              final bool targetOn = (state == 1 || state == true || state == 'ON');
              if (dev.isOn != targetOn) {
                _deviceMap[devId] = dev.copyWith(isOn: targetOn);
                devicesChanged = true;
              }
            }
          }

          final ab = _actionBoxMap[nodeId];
          if (ab != null && devicesChanged) {
            final newChannels = ab.channels.map((ch) {
              final dev = _deviceMap[ch.deviceId ?? '$nodeId::${ch.channelKey}'];
              if (dev != null && ch.isOn != dev.isOn) {
                return ch.copyWith(isOn: dev.isOn);
              }
              return ch;
            }).toList();
            _actionBoxMap[nodeId] = ab.copyWith(channels: newChannels);
            actionBoxesChanged = true;
          }
        }
        break;

      case 'node_status':
        if (nodeId != null) {
          if (data.containsKey('online') || data.containsKey('status')) {
            final isOnline = data['online'] == true || data['status'] == 'online';
            for (final dev in _deviceMap.values.where((d) => d.actionBoxId == nodeId).toList()) {
              if (dev.online != isOnline) {
                _deviceMap[dev.id] = dev.copyWith(online: isOnline);
                devicesChanged = true;
              }
            }
            final ab = _actionBoxMap[nodeId];
            if (ab != null && ab.online != isOnline) {
              _actionBoxMap[nodeId] = ab.copyWith(online: isOnline);
              actionBoxesChanged = true;
            }
          }
          if (data.containsKey('relay_state') && data['relay_state'] is List) {
            final rl = data['relay_state'] as List;
            for (int i = 0; i < rl.length; i++) {
              final chKey = 'ch${i + 1}';
              final devId = '$nodeId::$chKey';
              final dev = _deviceMap[devId];
              if (dev != null) {
                final val = rl[i];
                final bool targetOn = (val == 1 || val == true || val == 'ON');
                if (dev.isOn != targetOn) {
                  _deviceMap[devId] = dev.copyWith(isOn: targetOn);
                  devicesChanged = true;
                }
              }
            }
          }
        }
        break;

      case 'node_telemetry':
        if (nodeId != null) {
          final p = readNumber(data['power'] ?? data['power_w'] ?? data['telemetry']?['power'] ?? data['telemetry']?['power_w']);
          if (data['channels'] is Map && asMap(data['channels']).values.any((c) => asMap(c).containsKey('valid'))) {
            final node = gateway.nodes[nodeId];
            if (node is Map) {
              final channels = asMap(node['channels']);
              for (final entry in asMap(data['channels']).entries) {
                if (!channels.containsKey(entry.key)) continue;
                final meter = asMap(entry.value);
                channels[entry.key] = {...asMap(channels[entry.key]), 'telemetry': meter, 'power': meter['power_w']};
              }
              node['channels'] = channels;
              return applySnapshot(gateway.nodes);
            }
          }
          if (data['channels'] is Map) {
            final chMap = asMap(data['channels']);
            for (final entry in chMap.entries) {
              final chKey = entry.key;
              final chData = asMap(entry.value);
              final chPower = readNumber(chData['power'] ?? chData['power_w'] ?? chData['telemetry']?['power']);
              final devId = '$nodeId::$chKey';
              final dev = _deviceMap[devId];
              if (dev != null && chPower != null && dev.powerWatts != chPower) {
                _deviceMap[devId] = dev.copyWith(powerWatts: chPower);
                devicesChanged = true;
              }
            }
          } else if (p != null) {
            final chKey = data['channel']?.toString() ?? 'ch1';
            final devId = '$nodeId::$chKey';
            final dev = _deviceMap[devId];
            if (dev != null && dev.powerWatts != p) {
              _deviceMap[devId] = dev.copyWith(powerWatts: p);
              devicesChanged = true;
            }
          }
        }
        break;

      case 'device_deleted':
        if (nodeId != null) {
          final removedDevIds = _deviceMap.values
              .where((d) => d.id == nodeId || d.actionBoxId == nodeId)
              .map((d) => d.id)
              .toList();
          if (removedDevIds.isNotEmpty) {
            for (final id in removedDevIds) {
              _deviceMap.remove(id);
            }
            devicesChanged = true;
            roomsChanged = true;
            vocabularyChanged = true;
            scenesChanged = true;
          }
          if (_actionBoxMap.containsKey(nodeId)) {
            _actionBoxMap.remove(nodeId);
            actionBoxesChanged = true;
          }
        }
        break;

      case 'device_claimed':
      case 'operation_updated':
      case 'device_rebooted':
        return applySnapshot(gateway.nodes);

      default:
        break;
    }

    if (devicesChanged) {
      _devices = _deviceMap.values.toList();
      _deviceStreamCtrl.add(List.unmodifiable(_devices));

      final newScenes = _buildScenes(_devices);
      bool sChanged = _scenes.length != newScenes.length;
      if (!sChanged) {
        for (int i = 0; i < newScenes.length; i++) {
          if (_scenes[i].id != newScenes[i].id || _scenes[i].deviceCount != newScenes[i].deviceCount) {
            sChanged = true;
            break;
          }
        }
      }
      if (sChanged) {
        _scenes = newScenes;
        scenesChanged = true;
        if (!_sceneStreamCtrl.isClosed) {
          _sceneStreamCtrl.add(List.unmodifiable(_scenes));
        }
      }
    }

    if (actionBoxesChanged) {
      _actionBoxes = _actionBoxMap.values.toList();
      if (!_actionBoxStreamCtrl.isClosed) {
        _actionBoxStreamCtrl.add(List.unmodifiable(_actionBoxes));
      }
    }

    if (roomsChanged) {
      _rooms = _buildRooms(_devices);
      if (!_roomStreamCtrl.isClosed) {
        _roomStreamCtrl.add(List.unmodifiable(_rooms));
      }
    }

    if (vocabularyChanged) {
      if (!_voiceStreamCtrl.isClosed) {
        _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
      }
    }

    return ChangedResources(
      devicesChanged: devicesChanged,
      roomsChanged: roomsChanged,
      actionBoxesChanged: actionBoxesChanged,
      vocabularyChanged: vocabularyChanged,
      scenesChanged: scenesChanged,
    );
  }

  List<Device> _buildCandidateDevices(Map<String, dynamic> nodes) {
    final list = <Device>[];
    for (final entry in nodes.entries) {
      final nodeId = entry.key;
      final node = asMap(entry.value);
      if (isSubBoxNode(nodeId, node)) continue;
      final nodeOnline = gateway.connected &&
          (node['status'] != null ? node['status'] == 'online' : node['is_online'] == true);
      final rawRl = node['relay_state'];
      final List<dynamic> rlList = rawRl is List ? rawRl : const [0, 0];
      final nodeRoom = (node['room'] ?? '').toString();
      final channelsMap = asMap(node['channels']);
      final pzem = asMap(node['pzem']).isNotEmpty ? asMap(node['pzem']) : asMap(node['last_telemetry']);
      final double powerWatts = readNumber(pzem['power']) ?? 0.0;

      final boardModel = (node['board_model'] ?? node['hardware'] ?? '').toString().toLowerCase();
      final has3Ch = channelsMap.containsKey('ch3') ||
          rlList.length >= 3 ||
          boardModel.contains('actionbox_v2') ||
          boardModel.contains('v2') ||
          (node['capabilities'] is List && (node['capabilities'] as List).contains('relay_3ch'));
      final channelKeys = node['firebase'] == true
          ? ['ch1', 'ch2', 'ch3'].where(channelsMap.containsKey).toList()
          : has3Ch ? const ['ch1', 'ch2', 'ch3'] : const ['ch1', 'ch2'];
      for (int i = 0; i < channelKeys.length; i++) {
        final chKey = channelKeys[i];
        final chInfo = asMap(channelsMap[chKey]);
        final chName = _resolveChannelName(chKey, chInfo);
        final chTypeStr = (chInfo['device_type'] ?? (i == 0 ? 'light' : (i == 1 ? 'fan' : 'switch'))).toString().toLowerCase();
        final devType = switch (chTypeStr) {
          'light' || 'den' || 'lamp' => DeviceType.light,
          'fan' || 'quat' => DeviceType.fan,
          'socket' || 'o_cam' || 'outlet' || 'switch' || 'cong_tac' => DeviceType.socket,
          'ac' || 'air_conditioner' || 'dieu_hoa' => DeviceType.airConditioner,
          _ => DeviceType.custom,
        };

        final relayValue = node['firebase'] == true ? chInfo['state'] : (rlList.length > i ? rlList[i] : null);
        final isOn = relayValue == 1 || relayValue == true || relayValue == 'ON';
        final rawAliases = chInfo['aliases'];
        final aliases = rawAliases is List ? rawAliases.map((a) => a.toString()).toList() : <String>[];
        final devId = '$nodeId::$chKey';

        final meter = asMap(chInfo['telemetry']);
        final metered = meter.containsKey('valid');
        final receivedAt = readNumber(meter['received_at']);
        final age = receivedAt == null ? double.infinity : DateTime.now().millisecondsSinceEpoch / 1000 - receivedAt;
        final meterValid = nodeOnline && meter['valid'] == true && age >= -5 && age <= 15;
        final rawCurrent = readNumber(meter['current_ma']);
        final current = metered
            ? (meterValid && rawCurrent != null && rawCurrent.isFinite && rawCurrent >= 0 ? rawCurrent / 1000 : null)
            : (nodeOnline && i == 0 ? readNumber(pzem['current']) : null);
        final voltage = metered
            ? (meterValid ? readNumber(meter['voltage_v']) : null)
            : (nodeOnline && i == 0 ? readNumber(pzem['voltage']) : null);
        final chPowerRaw = readNumber(chInfo['power'] ?? chInfo['power_w'] ?? meter['power_w'] ?? meter['power']);
        final double? channelPower = metered
            ? (meterValid ? readNumber(meter['power_w']) : null)
            : chPowerRaw != null && chPowerRaw > 0 ? chPowerRaw : i == 0 && powerWatts > 0 ? powerWatts : null;

        list.add(Device(
          id: devId,
          name: chName,
          type: devType,
          roomId: nodeRoom,
          actionBoxId: nodeId,
          channel: chKey,
          online: nodeOnline && (node['firebase'] != true || chInfo['state'] is bool),
          isOn: isOn,
          value: 0.0,
          powerWatts: channelPower,
          voiceAliases: aliases,
          isFavorite: _favoriteIds.contains(devId),
          metadata: {
            'cloud_state': node['firebase'] == true,
            'node_id': nodeId,
            'channel': chKey,
            'mac': node['mac'] ?? '',
            'ip': node['ip'] ?? '',
            'can_dim': false,
            'can_speed': false,
            'has_thermostat': false,
            'power': metered ? channelPower : channelPower ?? 0.0,
            'metered': metered,
            'voltage': voltage,
            'current': current,
            'energy': node['firebase'] == true ? readNumber(chInfo['energy_kwh']) : i == 0 ? readNumber(pzem['energy']) : null,
            'board_power': powerWatts,
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

  List<ActionBox> _buildCandidateActionBoxes(Map<String, dynamic> nodes) {
    final list = <ActionBox>[];
    for (final entry in nodes.entries) {
      final nodeId = entry.key;
      final node = asMap(entry.value);
      final isSubbox = isSubBoxNode(nodeId, node);
      final nodeOnline = gateway.connected &&
          (node['status'] != null ? node['status'] == 'online' : node['is_online'] == true);
      final rawRl = node['relay_state'];
      final List<dynamic> rlList = rawRl is List ? rawRl : const [0, 0];
      final nodeRoom = (node['room'] ?? '').toString();
      final channelsMap = asMap(node['channels']);

      final channels = <ActionBoxChannel>[];
      final has3Ch = channelsMap.containsKey('ch3') ||
          rlList.length >= 3 ||
          (node['capabilities'] is List && (node['capabilities'] as List).contains('relay_3ch'));
      final channelKeys = node['firebase'] == true
          ? ['ch1', 'ch2', 'ch3'].where(channelsMap.containsKey).toList()
          : isSubbox ? const <String>[] : has3Ch ? const ['ch1', 'ch2', 'ch3'] : const ['ch1', 'ch2'];
      for (int i = 0; i < channelKeys.length; i++) {
        final chKey = channelKeys[i];
        final chInfo = asMap(channelsMap[chKey]);
        final chName = _resolveChannelName(chKey, chInfo);
        final chTypeStr = (chInfo['device_type'] ?? (i == 0 ? 'light' : (i == 1 ? 'fan' : 'switch'))).toString().toLowerCase();
        final devType = switch (chTypeStr) {
          'light' || 'den' || 'lamp' => DeviceType.light,
          'fan' || 'quat' => DeviceType.fan,
          'socket' || 'o_cam' || 'switch' || 'cong_tac' => DeviceType.socket,
          _ => DeviceType.custom,
        };
        final isOn = node['firebase'] == true ? chInfo['state'] == true : rlList.length > i && (rlList[i] == 1 || rlList[i] == true);
        channels.add(ActionBoxChannel(
          index: channelIndex(chKey) ?? i,
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
        name: node['name'] ?? node['display_name'] ?? '${isSubbox ? 'SubBox' : 'ActionBox'} $nodeId',
        roomId: nodeRoom,
        online: nodeOnline,
        channels: channels,
        firmwareVersion: node['fw'] ?? node['firmware_version'] ?? 'v2.1.0-esp32s3',
        ipAddress: node['ip'] ?? (gateway.serverUrl.isNotEmpty ? Uri.tryParse(gateway.serverUrl)?.host ?? '192.168.11.181' : '192.168.11.181'),
        signalStrength: readNumber(node['rssi'])?.toInt() ?? -62,
        boardModel: isSubbox ? 'subbox_v1' : node['board_model'] ?? node['model'] ?? 'actionbox_v2',
        boardRevision: node['board_revision'] ?? 'v2.1',
        subboxId: node['subbox_id'] ?? node['parent_subbox'],
        ownerEpoch: readNumber(node['owner_epoch'])?.toInt() ?? 1,
        capabilities: isSubbox ? const ['gateway', 'audio'] : (node['capabilities'] as List?)?.map((e) => e.toString()).toList() ?? const ['relay', 'energy_meter'],
        protocolVersion: readNumber(node['protocol_version'])?.toInt() ?? 2,
        metadata: Map<String, dynamic>.from(node),
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
      _ => channel == 'ch1' ? 'Kênh 1' : (channel == 'ch2' ? 'Kênh 2' : (channel == 'ch3' ? 'Kênh 3' : 'Kênh $channel')),
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

  @override
  Future<List<Device>> getDevices() async {
    if (_currentFavoritesLoad != null) {
      await _currentFavoritesLoad;
    }
    return List.unmodifiable(_devices);
  }

  @override
  Stream<List<Device>> watchDevices() {
    scheduleMicrotask(() {
      if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
    });
    return _deviceStreamCtrl.stream;
  }

  @override
  Map<String, Device> get deviceMap => Map.unmodifiable(_deviceMap);

  Map<String, ActionBox> get actionBoxMap => Map.unmodifiable(_actionBoxMap);

  @override
  Future<void> toggleDevice(String id, bool isOn) async {
    if (!gateway.connected) {
      throw const GatewayException('Không thể gửi lệnh khi Gateway đang ngoại tuyến');
    }
    final parts = id.split('::');
    if (parts.length != 2) return;
    final nodeId = parts[0];
    final channel = parts[1];
    try {
      await gateway.relay(nodeId, channel, isOn);
    } catch (e) {
      _syncFromGateway();
      rethrow;
    }
  }

  @override
  Future<void> setDeviceValue(String id, double value) async {

    await toggleDevice(id, value > 0);
  }

  @override
  Future<void> toggleFavorite(String id) async {
    if (_currentFavoritesLoad != null) {
      await _currentFavoritesLoad;
    }
    if (_favoriteIds.contains(id)) {
      _favoriteIds.remove(id);
    } else {
      _favoriteIds.add(id);
    }
    if (gateway.authenticated) {
      await preferencesService.saveFavoriteIds(
        _favoriteIds,
        gatewayUrl: gateway.serverUrl,
        userId: gateway.currentUserId,
      );
    }
    final dev = _deviceMap[id];
    if (dev != null) {
      _deviceMap[id] = dev.copyWith(isFavorite: _favoriteIds.contains(id));
      _devices = _deviceMap.values.toList();
      if (!_deviceStreamCtrl.isClosed) {
        _deviceStreamCtrl.add(List.unmodifiable(_devices));
      }
    }
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
      ch3Name: chKey == 'ch3' ? device.name : null,
      ch3Type: chKey == 'ch3' ? typeStr : null,
    );
  }

  @override
  Future<void> addDevice(Device device) async {

    _syncFromGateway();
  }

  @override
  Future<List<Room>> getRooms() async => List.unmodifiable(_rooms);

  @override
  Stream<List<Room>> watchRooms() {
    scheduleMicrotask(() {
      if (!_roomStreamCtrl.isClosed) _roomStreamCtrl.add(List.unmodifiable(_rooms));
    });
    return _roomStreamCtrl.stream;
  }

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
    final chKey = channelIndex == 0 ? 'ch1' : (channelIndex == 1 ? 'ch2' : 'ch3');
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
      ch3Name: chKey == 'ch3' ? name : null,
      ch3Type: chKey == 'ch3' ? typeStr : null,
    );
  }

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
      await _savePersistedAutomations();
    }
  }

  @override
  Future<void> addAutomation(Automation automation) async {
    _automations.add(automation);
    if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
    await _savePersistedAutomations();
  }

  @override
  Future<void> deleteAutomation(String id) async {
    _automations.removeWhere((a) => a.id == id);
    if (!_automationStreamCtrl.isClosed) _automationStreamCtrl.add(List.unmodifiable(_automations));
    await _savePersistedAutomations();
  }

  @override
  Future<List<Scene>> getScenes() async => List.unmodifiable(_scenes.isNotEmpty ? _scenes : _buildScenes(_devices));

  @override
  Stream<List<Scene>> watchScenes() {
    scheduleMicrotask(() {
      if (!_sceneStreamCtrl.isClosed) {
        _sceneStreamCtrl.add(List.unmodifiable(_scenes.isNotEmpty ? _scenes : _buildScenes(_devices)));
      }
    });
    return _sceneStreamCtrl.stream;
  }

  @override
  Future<void> activateScene(String id) async {
    final targets = <({String nodeId, String channel, bool targetOn})>[];
    if (id == 'scene_all_off' || id == 'scene_night' || id == 'scene_away') {
      for (final dev in _devices) {
        if (dev.online && dev.isOn && dev.channel != null && dev.actionBoxId != null) {
          targets.add((nodeId: dev.actionBoxId!, channel: dev.channel!, targetOn: false));
        }
      }
    } else if (id == 'scene_morning') {
      for (final dev in _devices) {
        if (dev.online && !dev.isOn && dev.type == DeviceType.light && dev.channel != null && dev.actionBoxId != null) {
          targets.add((nodeId: dev.actionBoxId!, channel: dev.channel!, targetOn: true));
        }
      }
    }

    int failCount = 0;
    for (final target in targets) {
      try {
        await gateway.relay(target.nodeId, target.channel, target.targetOn);
      } catch (_) {
        failCount++;
      }
    }

    if (failCount > 0) {
      throw GatewayException('Kích hoạt ngữ cảnh có một số thiết bị không phản hồi ($failCount/${targets.length})');
    }
  }

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

    final dev = _deviceMap[deviceId];
    if (dev == null) return;
    if (dev.voiceAliases.contains(cleanAlias)) return;

    final previousAliases = List<String>.from(dev.voiceAliases);
    final updatedAliases = List<String>.from(dev.voiceAliases)..add(cleanAlias);
    _deviceMap[deviceId] = dev.copyWith(voiceAliases: updatedAliases);
    _devices = _deviceMap.values.toList();
    if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
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
      final currentDev = _deviceMap[deviceId];
      if (currentDev != null) {
        _deviceMap[deviceId] = currentDev.copyWith(voiceAliases: previousAliases);
        _devices = _deviceMap.values.toList();
        if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
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

    final dev = _deviceMap[deviceId];
    if (dev == null) return;

    final previousAliases = List<String>.from(dev.voiceAliases);
    final updatedAliases = List<String>.from(dev.voiceAliases)..remove(cleanAlias);
    _deviceMap[deviceId] = dev.copyWith(voiceAliases: updatedAliases);
    _devices = _deviceMap.values.toList();
    if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
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
      final currentDev = _deviceMap[deviceId];
      if (currentDev != null) {
        _deviceMap[deviceId] = currentDev.copyWith(voiceAliases: previousAliases);
        _devices = _deviceMap.values.toList();
        if (!_deviceStreamCtrl.isClosed) _deviceStreamCtrl.add(List.unmodifiable(_devices));
        if (!_voiceStreamCtrl.isClosed) {
          _voiceStreamCtrl.add(List.unmodifiable(_buildVocabulary(_devices)));
        }
      }
      rethrow;
    }
  }

  @override
  void dispose() {
    _meterExpiryTimer?.cancel();
    _eventSub?.cancel();
    gateway.removeListener(_syncFromGateway);
    _deviceStreamCtrl.close();
    _roomStreamCtrl.close();
    _actionBoxStreamCtrl.close();
    _automationStreamCtrl.close();
    _sceneStreamCtrl.close();
    _voiceStreamCtrl.close();
  }
}

class InMemorySmartHomeRepository implements SmartHomeRepository {
  final _deviceStreamCtrl = StreamController<List<Device>>.broadcast();
  final _roomStreamCtrl = StreamController<List<Room>>.broadcast();
  final _actionBoxStreamCtrl = StreamController<List<ActionBox>>.broadcast();
  final _automationStreamCtrl = StreamController<List<Automation>>.broadcast();
  final _sceneStreamCtrl = StreamController<List<Scene>>.broadcast();
  final _voiceStreamCtrl = StreamController<List<VoiceVocabularyItem>>.broadcast();

  @override
  Map<String, Device> get deviceMap => {for (final d in _devices) d.id: d};

  final List<Room> _rooms = [
    const Room(id: 'living_room', name: 'Phòng khách', icon: Icons.weekend_rounded, temperature: 27.5, humidity: 65),
    const Room(id: 'bedroom', name: 'Phòng ngủ', icon: Icons.bed_rounded, temperature: 26.0, humidity: 60),
    const Room(id: 'kitchen', name: 'Nhà bếp', icon: Icons.kitchen_rounded, temperature: 28.2, humidity: 70),
    const Room(id: 'office', name: 'Phòng làm việc', icon: Icons.desk_rounded, temperature: 25.5, humidity: 55),
  ];

  final List<Device> _devices = [
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
      value: 0.0,
      powerWatts: 120.5,
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
      value: 24.0,
      isFavorite: true,
      voiceAliases: ['điều hòa phòng ngủ', 'máy lạnh'],
      metadata: {'has_thermostat': true},
    ),
    const Device(
      id: 'dev_light_bed',
      name: 'Đèn ngủ đầu giường',
      type: DeviceType.light,
      roomId: 'bedroom',
      actionBoxId: 'ab_02',
      channel: 'ch1',
      online: false,
      isOn: false,
      value: 50.0,
      isFavorite: true,
      voiceAliases: ['đèn ngủ', 'đèn đầu giường'],
      metadata: {'can_dim': true},
    ),
    const Device(
      id: 'dev_fan_bed',
      name: 'Quạt phòng ngủ',
      type: DeviceType.fan,
      roomId: 'bedroom',
      actionBoxId: 'ab_02',
      channel: 'ch2',
      online: false,
      isOn: false,
      value: 1.0,
      isFavorite: false,
      voiceAliases: ['quạt phòng ngủ'],
      metadata: {'can_speed': true},
    ),
    const Device(
      id: 'dev_kitchen_light',
      name: 'Đèn bếp nấu',
      type: DeviceType.light,
      roomId: 'kitchen',
      online: true,
      isOn: false,
      value: 0.0,
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
      value: 0.0,
      powerWatts: 850.0,
      isFavorite: false,
      voiceAliases: ['ổ cắm lò', 'ổ cắm bếp'],
    ),
  ];

  final List<ActionBox> _actionBoxes = [
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
    if (!dev.online) return;
    _devices[idx] = dev.copyWith(isOn: isOn);
    _deviceStreamCtrl.add(List.unmodifiable(_devices));

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

  @override
  Future<List<Room>> getRooms() async => List.unmodifiable(_rooms);

  @override
  Stream<List<Room>> watchRooms() {
    scheduleMicrotask(() => _roomStreamCtrl.add(List.unmodifiable(_rooms)));
    return _roomStreamCtrl.stream;
  }

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

  @override
  Future<List<Scene>> getScenes() async => List.unmodifiable(_scenes);

  @override
  Stream<List<Scene>> watchScenes() {
    scheduleMicrotask(() => _sceneStreamCtrl.add(List.unmodifiable(_scenes)));
    return _sceneStreamCtrl.stream;
  }

  @override
  Future<void> activateScene(String id) async {

    if (id == 'scene_morning') {
      for (var i = 0; i < _devices.length; i++) {
        if (_devices[i].type == DeviceType.light && _devices[i].online) {
          _devices[i] = _devices[i].copyWith(isOn: true, value: 50.0);
        }
      }
    } else if (id == 'scene_night' || id == 'scene_away' || id == 'scene_all_off') {
      for (var i = 0; i < _devices.length; i++) {
        if (_devices[i].online) {
          _devices[i] = _devices[i].copyWith(isOn: false);
        }
      }
    }
    _deviceStreamCtrl.add(List.unmodifiable(_devices));
  }

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
