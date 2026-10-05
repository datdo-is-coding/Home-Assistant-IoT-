import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../models/room.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/device_card.dart';
import '../../widgets/quick_control_sheet.dart';
import '../../widgets/room_chip.dart';
import '../../widgets/room_card.dart';
import '../../widgets/action_box_card.dart';
import '../../widgets/status_banner.dart';

class FeatureHomeScreen extends ConsumerWidget {
  const FeatureHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final deviceIds = ref.watch(filteredDeviceIdsProvider);
    final roomsAsync = ref.watch(roomsStreamProvider);
    final actionBoxesAsync = ref.watch(actionBoxesStreamProvider);
    final selectedRoomId = ref.watch(selectedRoomIdProvider);
    final favoritesOnly = ref.watch(favoritesOnlyProvider);
    final statusList = ref.watch(contextualHomeStatusProvider);

    final totalCount = ref.watch(devicesStreamProvider).when(
          data: (list) => list.length,
          loading: () => 0,
          error: (_, __) => 0,
        );
    final onlineCount = ref.watch(onlineDevicesCountProvider);

    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            // Top App Bar / Header
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'My Home',
                            style: TextStyle(
                              fontSize: 26,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -0.5,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '$totalCount thiết bị · $onlineCount trực tuyến',
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Row(
                      children: [
                        _CircularButton(
                          icon: Icons.add_rounded,
                          tooltip: 'Thêm thiết bị',
                          onPressed: () => context.push('/actionbox/add-device'),
                        ),
                        const SizedBox(width: 8),
                        _CircularButton(
                          icon: Icons.notifications_none_rounded,
                          tooltip: 'Thông báo',
                          onPressed: () => _showNotificationSheet(context, ref),
                        ),
                        const SizedBox(width: 8),
                        _CircularButton(
                          icon: Icons.mic_none_rounded,
                          tooltip: 'Giọng nói',
                          onPressed: () => context.push('/voice'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            // Contextual Status Banner
            if (statusList.isNotEmpty)
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 12),
                sliver: SliverToBoxAdapter(
                  child: StatusBanner(statuses: statusList),
                ),
              ),

            // Horizontal Room Selector Chips (Optimized to eliminate nested watch calls)
            SliverPadding(
              padding: const EdgeInsets.only(left: 20, right: 20, bottom: 16),
              sliver: SliverToBoxAdapter(
                child: roomsAsync.when(
                  data: (rooms) {
                    return SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      physics: const BouncingScrollPhysics(),
                      child: Row(
                        children: [
                          RoomChip(
                            label: 'Tất cả',
                            count: totalCount,
                            isSelected: selectedRoomId == 'all',
                            onSelected: () => ref.read(selectedRoomIdProvider.notifier).state = 'all',
                          ),
                          const SizedBox(width: 8),
                          ...rooms.map((r) {
                            return Padding(
                              padding: const EdgeInsets.only(right: 8),
                              child: _RoomChipItem(
                                room: r,
                                isSelected: selectedRoomId == r.id,
                                onSelected: () => ref.read(selectedRoomIdProvider.notifier).state = r.id,
                              ),
                            );
                          }),
                        ],
                      ),
                    );
                  },
                  loading: () => const SizedBox.shrink(),
                  error: (_, __) => const SizedBox.shrink(),
                ),
              ),
            ),

            // Favorites / Quick Control Header
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      favoritesOnly ? 'Yêu thích' : 'Điều khiển nhanh',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.3,
                      ),
                    ),
                    IconButton(
                      tooltip: favoritesOnly ? 'Hiện tất cả' : 'Chỉ yêu thích',
                      onPressed: () {
                        HapticFeedback.selectionClick();
                        ref.read(favoritesOnlyProvider.notifier).state = !favoritesOnly;
                      },
                      icon: Icon(
                        favoritesOnly ? Icons.star_rounded : Icons.star_outline_rounded,
                        color: favoritesOnly
                            ? const Color(0xFFF59E0B)
                            : (isDark ? const Color(0xFF64748B) : const Color(0xFF94A3B8)),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Adaptive Device Grid (2 columns on mobile, 3-4 on tablet)
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              sliver: SliverLayoutBuilder(
                builder: (context, constraints) {
                  final crossAxisCount = constraints.crossAxisExtent >= 720
                      ? 3
                      : constraints.crossAxisExtent >= 480
                          ? 3
                          : 2;

                  if (deviceIds.isEmpty) {
                    final gw = ref.watch(gatewayClientProvider);
                    return SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 20),
                        child: Center(
                          child: Column(
                            children: [
                              Icon(
                                gw.connected ? Icons.devices_other_rounded : Icons.cloud_off_rounded,
                                size: 48,
                                color: isDark ? const Color(0xFF475569) : const Color(0xFF94A3B8),
                              ),
                              const SizedBox(height: 12),
                              Text(
                                gw.connected
                                    ? 'Chưa có thiết bị nào trong khu vực này'
                                    : 'Chưa kết nối Gateway IoT',
                                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                gw.connected
                                    ? 'Nhấn nút Thêm thiết bị để ghép nối bộ điều khiển'
                                    : 'Kiểm tra mạng Wi-Fi nội bộ hoặc nhấn kết nối lại',
                                style: TextStyle(color: theme.colorScheme.onSurfaceVariant, fontSize: 13),
                                textAlign: TextAlign.center,
                              ),
                              const SizedBox(height: 16),
                              FilledButton.icon(
                                onPressed: () {
                                  if (gw.connected) {
                                    context.push('/actionbox/add-device');
                                  } else {
                                    gw.refresh();
                                  }
                                },
                                icon: Icon(gw.connected ? Icons.add_rounded : Icons.refresh_rounded, size: 18),
                                label: Text(gw.connected ? 'Thêm thiết bị' : 'Thử kết nối lại'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }

                  return SliverGrid(
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: crossAxisCount,
                      mainAxisSpacing: 12,
                      crossAxisSpacing: 12,
                      mainAxisExtent: 156,
                    ),
                    delegate: SliverChildBuilderDelegate(
                      (context, index) {
                        return _DeviceCardItem(deviceId: deviceIds[index]);
                      },
                      childCount: deviceIds.length,
                    ),
                  );
                },
              ),
            ),

            // Rooms Section Header
            const SliverPadding(
              padding: EdgeInsets.fromLTRB(20, 28, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Text(
                  'Khu vực trong nhà',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.3,
                  ),
                ),
              ),
            ),

            // Room Cards List (Optimized with _RoomCardItem)
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              sliver: SliverToBoxAdapter(
                child: roomsAsync.when(
                  data: (rooms) {
                    if (rooms.isEmpty) {
                      return const Padding(
                        padding: EdgeInsets.symmetric(vertical: 16),
                        child: Center(
                          child: Text(
                            'Chưa có phòng nào được phân bổ',
                            style: TextStyle(color: Colors.grey, fontSize: 13),
                          ),
                        ),
                      );
                    }
                    return Column(
                      children: rooms.map((r) {
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _RoomCardItem(room: r),
                        );
                      }).toList(),
                    );
                  },
                  loading: () => const Center(child: CircularProgressIndicator()),
                  error: (e, _) => Text('Lỗi: $e'),
                ),
              ),
            ),

            // ActionBox Controllers Header
            const SliverPadding(
              padding: EdgeInsets.fromLTRB(20, 20, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Text(
                  'Bộ điều khiển ActionBox',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.3,
                  ),
                ),
              ),
            ),

            // ActionBox Cards
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 36),
              sliver: SliverToBoxAdapter(
                child: actionBoxesAsync.when(
                  data: (boxes) {
                    return Column(
                      children: boxes.map((ab) {
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: ActionBoxCard(
                            actionBox: ab,
                            onTap: () => context.push('/actionbox/${ab.id}'),
                          ),
                        );
                      }).toList(),
                    );
                  },
                  loading: () => const SizedBox.shrink(),
                  error: (e, _) => Text('Lỗi: $e'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DeviceCardItem extends ConsumerWidget {
  final String deviceId;
  const _DeviceCardItem({required this.deviceId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dev = ref.watch(deviceProvider(deviceId));
    if (dev == null) return const SizedBox.shrink();

    return DeviceCard(
      device: dev,
      onToggle: (isOn) async {
        try {
          await ref.read(deviceRepositoryProvider).toggleDevice(dev.id, isOn);
        } catch (e) {
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('Không thể điều khiển thiết bị: $e')),
            );
          }
        }
      },
      onTap: () {
        QuickControlSheet.show(
          context,
          device: dev,
          onToggle: (isOn) async {
            try {
              await ref.read(deviceRepositoryProvider).toggleDevice(dev.id, isOn);
            } catch (e) {
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Lỗi: $e')),
                );
              }
            }
          },
          onValueChanged: (val) {
            ref.read(deviceRepositoryProvider).setDeviceValue(dev.id, val);
          },
          onMoreSettings: () {
            Navigator.pop(context);
            context.push('/devices/${dev.id}');
          },
        );
      },
      onFavoriteToggle: () {
        ref.read(deviceRepositoryProvider).toggleFavorite(dev.id);
      },
    );
  }
}

class _RoomChipItem extends ConsumerWidget {
  final Room room;
  final bool isSelected;
  final VoidCallback onSelected;

  const _RoomChipItem({
    required this.room,
    required this.isSelected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(roomDeviceCountProvider(room.id));
    return RoomChip(
      label: room.name,
      count: count,
      isSelected: isSelected,
      onSelected: onSelected,
    );
  }
}

class _RoomCardItem extends ConsumerWidget {
  final Room room;
  const _RoomCardItem({required this.room});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devices = ref.watch(devicesStreamProvider).value ?? const [];
    final roomDevs = devices.where((d) => d.roomId == room.id).toList();

    return RoomCard(
      room: room,
      devices: roomDevs,
      onTap: () => context.push('/rooms/${room.id}'),
    );
  }
}

void _showNotificationSheet(BuildContext context, WidgetRef ref) {
  final gw = ref.read(gatewayClientProvider);
  final abs = ref.read(actionBoxesStreamProvider).value ?? [];
  final offlineBoxes = abs.where((b) => !b.online).toList();

  showModalBottomSheet(
    context: context,
    useSafeArea: true,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (ctx) {
      return Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Thông báo hệ thống', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                IconButton(onPressed: () => Navigator.pop(ctx), icon: const Icon(Icons.close)),
              ],
            ),
            const SizedBox(height: 16),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                gw.connected ? Icons.cloud_done_rounded : Icons.cloud_off_rounded,
                color: gw.connected ? const Color(0xFF10B981) : const Color(0xFFEF4444),
                size: 28,
              ),
              title: Text(
                gw.connected ? 'Máy chủ Gateway đang kết nối' : 'Mất kết nối máy chủ Gateway',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Text(gw.serverUrl.isNotEmpty ? gw.serverUrl : 'http://192.168.11.29:8000'),
            ),
            if (offlineBoxes.isNotEmpty) ...[
              const Divider(height: 24),
              const Text('Cảnh báo phần cứng', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
              const SizedBox(height: 8),
              ...offlineBoxes.map((b) => ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.warning_amber_rounded, color: Color(0xFFF59E0B)),
                title: Text('${b.name} đang ngoại tuyến'),
                subtitle: Text('IP: ${b.ipAddress} · Kiểm tra nguồn điện phần cứng'),
              )),
            ] else if (gw.connected) ...[
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('Tất cả rơ-le và cảm biến đang hoạt động bình thường.', style: TextStyle(color: Colors.grey)),
              ),
            ],
            const SizedBox(height: 12),
          ],
        ),
      );
    },
  );
}

class _CircularButton extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  const _CircularButton({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return IconButton(
      tooltip: tooltip,
      onPressed: () {
        HapticFeedback.lightImpact();
        onPressed();
      },
      icon: Icon(icon, size: 20),
      style: IconButton.styleFrom(
        backgroundColor: isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(100)),
        padding: const EdgeInsets.all(10),
      ),
    );
  }
}
