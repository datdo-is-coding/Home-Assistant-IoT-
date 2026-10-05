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

import '../main.dart' show gateway;
import '../services/gateway_client.dart';

final gatewayClientProvider = ChangeNotifierProvider<GatewayClient>((ref) => gateway);

final smartHomeRepositoryProvider = Provider<SmartHomeRepository>((ref) {
  const useMock = bool.fromEnvironment('USE_MOCK_DATA', defaultValue: false);
  if (useMock) {
    final repo = InMemorySmartHomeRepository();
    ref.onDispose(() => repo.dispose());
    return repo;
  }
  final client = ref.read(gatewayClientProvider);
  final repo = GatewaySmartHomeRepository(client);
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

// Stream Providers
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

// UI State Providers (Riverpod 3 NotifierProvider pattern)
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
  @override
  ThemeMode build() => ThemeMode.light;
  @override
  set state(ThemeMode value) => super.state = value;
}
final themeModeProvider = NotifierProvider<ThemeModeNotifier, ThemeMode>(ThemeModeNotifier.new);

// Granular Family Provider for isolated DeviceCard rebuilds (Prevents Rebuild Storms)
final deviceProvider = Provider.family<Device?, String>((ref, id) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  return devicesAsync.when(
    data: (devices) {
      for (final d in devices) {
        if (d.id == id) return d;
      }
      return null;
    },
    loading: () => null,
    error: (_, __) => null,
  );
});

// Provides only the List of IDs matching filter, preventing CustomScrollView rebuild on power/watt changes
final filteredDeviceIdsProvider = Provider<List<String>>((ref) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  final selectedRoomId = ref.watch(selectedRoomIdProvider);
  final favoritesOnly = ref.watch(favoritesOnlyProvider);

  return devicesAsync.when(
    data: (devices) {
      return devices.where((d) {
        if (selectedRoomId != 'all' && d.roomId != selectedRoomId) return false;
        if (favoritesOnly && !d.isFavorite) return false;
        return true;
      }).map((d) => d.id).toList();
    },
    loading: () => const [],
    error: (_, __) => const [],
  );
});

// Granular room device count family provider
final roomDeviceCountProvider = Provider.family<int, String>((ref, roomId) {
  final devicesAsync = ref.watch(devicesStreamProvider);
  return devicesAsync.when(
    data: (devices) => devices.where((d) => d.roomId == roomId).length,
    loading: () => 0,
    error: (_, __) => 0,
  );
});

// Memoized grouping for DevicesScreen to prevent expensive calculations in build()
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

// Derived Filtered Providers
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

// Contextual Home Status Banners (shown only when relevant)
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
