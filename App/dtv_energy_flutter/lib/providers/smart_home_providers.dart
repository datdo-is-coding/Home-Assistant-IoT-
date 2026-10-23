import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import '../models/device.dart';
import '../models/room.dart';
import '../models/action_box.dart';
import '../models/scene.dart';
import '../models/automation.dart';
import '../models/voice_alias.dart';
import '../repositories/smart_home_repository.dart';
import '../services/app_preferences_service.dart';

import '../main.dart' show gateway;
import '../services/gateway_client.dart';

final appPreferencesServiceProvider = Provider<AppPreferencesService>((ref) {
  return AppPreferencesService();
});

final gatewayClientProvider = ChangeNotifierProvider<GatewayClient>((ref) => gateway);

final smartHomeRepositoryProvider = Provider<SmartHomeRepository>((ref) {
  const useMock = bool.fromEnvironment('USE_MOCK_DATA', defaultValue: false);
  if (useMock) {
    final repo = InMemorySmartHomeRepository();
    ref.onDispose(() => repo.dispose());
    return repo;
  }
  final client = ref.read(gatewayClientProvider);
  final prefs = ref.read(appPreferencesServiceProvider);
  final repo = GatewaySmartHomeRepository(client, preferencesService: prefs);
  ref.onDispose(() => repo.dispose());
  return repo;
});

final deviceRepositoryProvider = Provider<DeviceRepository>((ref) {
  return ref.watch(smartHomeRepositoryProvider);
});

final roomRepositoryProvider = Provider<RoomRepository>((ref) {
  return ref.watch(smartHomeRepositoryProvider);
});

final actionBoxRepositoryProvider = Provider<ActionBoxRepository>((ref) {
  return ref.watch(smartHomeRepositoryProvider);
});

final automationRepositoryProvider = Provider<AutomationRepository>((ref) {
  return ref.watch(smartHomeRepositoryProvider);
});

final sceneRepositoryProvider = Provider<SceneRepository>((ref) {
  return ref.watch(smartHomeRepositoryProvider);
});

final voiceRepositoryProvider = Provider<VoiceRepository>((ref) {
  return ref.watch(smartHomeRepositoryProvider);
});

final devicesStreamProvider = StreamProvider<List<Device>>((ref) {
  return ref.watch(deviceRepositoryProvider).watchDevices();
});

final roomsStreamProvider = StreamProvider<List<Room>>((ref) {
  return ref.watch(roomRepositoryProvider).watchRooms();
});

final actionBoxesStreamProvider = StreamProvider<List<ActionBox>>((ref) {
  return ref.watch(actionBoxRepositoryProvider).watchActionBoxes();
});

final automationsStreamProvider = StreamProvider<List<Automation>>((ref) {
  return ref.watch(automationRepositoryProvider).watchAutomations();
});

final scenesStreamProvider = StreamProvider<List<Scene>>((ref) {
  return ref.watch(sceneRepositoryProvider).watchScenes();
});

final voiceVocabularyStreamProvider = StreamProvider<List<VoiceVocabularyItem>>((ref) {
  return ref.watch(voiceRepositoryProvider).watchVocabulary();
});

class SelectedRoomIdNotifier extends Notifier<String> {
  @override
  String build() => 'all';
  @override
  set state(String value) => super.state = value;
  void set(String value) => super.state = value;
}
final selectedRoomIdProvider = NotifierProvider<SelectedRoomIdNotifier, String>(SelectedRoomIdNotifier.new);

class FavoritesOnlyNotifier extends Notifier<bool> {
  @override
  bool build() => false;
  @override
  set state(bool value) => super.state = value;
  void toggle() => super.state = !super.state;
}
final favoritesOnlyProvider = NotifierProvider<FavoritesOnlyNotifier, bool>(FavoritesOnlyNotifier.new);

class SearchQueryNotifier extends Notifier<String> {
  @override
  String build() => '';
  @override
  set state(String value) => super.state = value;
}
final searchQueryProvider = NotifierProvider<SearchQueryNotifier, String>(SearchQueryNotifier.new);

class DeviceFilterCategoryNotifier extends Notifier<String> {
  @override
  String build() => 'all';
  @override
  set state(String value) => super.state = value;
}
final deviceFilterCategoryProvider = NotifierProvider<DeviceFilterCategoryNotifier, String>(DeviceFilterCategoryNotifier.new);

class ThemeModeNotifier extends Notifier<ThemeMode> {
  AppPreferencesService get _prefs => ref.read(appPreferencesServiceProvider);

  @override
  ThemeMode build() {
    ref.watch(appPreferencesServiceProvider);
    _loadTheme();
    return ThemeMode.light;
  }

  Future<void> _loadTheme() async {
    final mode = await _prefs.loadThemeMode();
    if (state != mode) {
      state = mode;
    }
  }

  @override
  set state(ThemeMode value) {
    super.state = value;
    _prefs.saveThemeMode(value);
  }
}
final themeModeProvider = NotifierProvider<ThemeModeNotifier, ThemeMode>(ThemeModeNotifier.new);

class HomeNameNotifier extends Notifier<String> {
  AppPreferencesService get _prefs => ref.read(appPreferencesServiceProvider);

  @override
  String build() {
    ref.watch(appPreferencesServiceProvider);
    final gateway = ref.watch(gatewayClientProvider);
    _loadHomeName(gateway.serverUrl, gateway.currentUserId);
    return 'My Home';
  }

  Future<void> _loadHomeName(String url, String userId) async {
    final name = await _prefs.loadHomeName(gatewayUrl: url, userId: userId);
    if (state != name) {
      state = name;
    }
  }

  Future<void> updateHomeName(String newName) async {
    state = newName;
    final gateway = ref.read(gatewayClientProvider);
    await _prefs.saveHomeName(newName, gatewayUrl: gateway.serverUrl, userId: gateway.currentUserId);
  }
}
final homeNameProvider = NotifierProvider<HomeNameNotifier, String>(HomeNameNotifier.new);

final deviceMapProvider = Provider<Map<String, Device>>((ref) {
  final repo = ref.watch(smartHomeRepositoryProvider);
  final devicesAsync = ref.watch(devicesStreamProvider);
  return repo is GatewaySmartHomeRepository
      ? repo.deviceMap
      : {for (final d in devicesAsync.value ?? const <Device>[]) d.id: d};
});

final deviceProvider = Provider.family<Device?, String>((ref, id) {
  return ref.watch(deviceMapProvider.select((m) => m[id]));
});

List<String> _cachedIds = const [];

bool _listEquals(List<String> a, List<String> b) {
  if (identical(a, b)) return true;
  if (a.length != b.length) return false;
  for (int i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

final filteredDeviceIdsProvider = Provider<List<String>>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  final selectedRoomId = ref.watch(selectedRoomIdProvider);
  final favoritesOnly = ref.watch(favoritesOnlyProvider);

  final newIds = devicesAsync.when(
    data: (devices) {
      return devices.where((d) {
        if (selectedRoomId != 'all' && d.roomId != selectedRoomId) return false;
        if (favoritesOnly && !d.isFavorite) return false;
        return true;
      }).map((d) => d.id).toList();
    },
    loading: () => const <String>[],
    error: (_, __) => const <String>[],
  );

  if (_listEquals(_cachedIds, newIds)) {
    return _cachedIds;
  }
  _cachedIds = List.unmodifiable(newIds);
  return _cachedIds;
});

final roomDeviceCountProvider = Provider.family<int, String>((ref, roomId) {
  return ref.watch(deviceMapProvider.select((m) {
    int count = 0;
    for (final d in m.values) {
      if (d.roomId == roomId) count++;
    }
    return count;
  }));
});

final groupedFilteredDevicesProvider = Provider<Map<String, List<Device>>>((ref) {
  final devices = ref.watch(devicesStreamProvider).value ?? const [];
  final query = ref.watch(searchQueryProvider).trim().toLowerCase();
  final category = ref.watch(deviceFilterCategoryProvider);

  final filtered = devices.where((d) {
    if (query.isNotEmpty && !d.name.toLowerCase().contains(query)) return false;
    if (category != 'all' && d.type.name != category) return false;
    return true;
  }).toList();

  final grouped = <String, List<Device>>{};
  for (final d in filtered) {
    grouped.putIfAbsent(d.roomId, () => []).add(d);
  }
  return grouped;
});

final filteredDevicesProvider = Provider<List<Device>>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  final selectedRoomId = ref.watch(selectedRoomIdProvider);
  final favoritesOnly = ref.watch(favoritesOnlyProvider);

  return devicesAsync.when(
    data: (devices) {
      return devices.where((d) {
        if (selectedRoomId != 'all' && d.roomId != selectedRoomId) return false;
        if (favoritesOnly && !d.isFavorite) return false;
        return true;
      }).toList();
    },
    loading: () => const [],
    error: (_, __) => const [],
  );
});

final favoriteDevicesProvider = Provider<List<Device>>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  return devicesAsync.when(
    data: (devices) => devices.where((d) => d.isFavorite).toList(),
    loading: () => const [],
    error: (_, __) => const [],
  );
});

final activeDevicesCountProvider = Provider<int>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  return devicesAsync.when(
    data: (devices) => devices.where((d) => d.isOn && d.online).length,
    loading: () => 0,
    error: (_, __) => 0,
  );
});

final onlineDevicesCountProvider = Provider<int>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  return devicesAsync.when(
    data: (devices) => devices.where((d) => d.online).length,
    loading: () => 0,
    error: (_, __) => 0,
  );
});

final contextualHomeStatusProvider = Provider<List<String>>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  final actionBoxesAsync = ref.watch(actionBoxesStreamProvider);

  final list = <String>[];
  devicesAsync.whenData((devices) {
    final activeLights = devices.where((d) => d.type == DeviceType.light && d.isOn && d.online).length;
    if (activeLights > 0) {
      list.add('$activeLights đèn đang bật');
    }
    final activeWatts = devices.where((d) => d.type == DeviceType.socket && d.isOn && d.online).fold(0.0, (acc, d) => acc + d.value);
    if (activeWatts > 0) {
      list.add('${activeWatts.toStringAsFixed(1)}W đang tiêu thụ');
    }
  });

  actionBoxesAsync.whenData((abs) {
    final offline = abs.where((ab) => !ab.online).toList();
    for (final o in offline) {
      list.add('${o.name} đang ngoại tuyến');
    }
  });

  return list;
});
