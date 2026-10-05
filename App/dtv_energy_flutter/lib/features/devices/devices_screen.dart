import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../models/room.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/device_card.dart';
import '../../widgets/quick_control_sheet.dart';

class FeatureDevicesScreen extends ConsumerWidget {
  const FeatureDevicesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final roomsAsync = ref.watch(roomsStreamProvider);
    final selectedCategory = ref.watch(deviceFilterCategoryProvider);
    final grouped = ref.watch(groupedFilteredDevicesProvider);

    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            // App Bar Title
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Thiết bị trong nhà',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Quản lý tất cả thiết bị và cảm biến',
                      style: TextStyle(
                        fontSize: 13,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Search Bar
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              sliver: SliverToBoxAdapter(
                child: TextField(
                  onChanged: (val) => ref.read(searchQueryProvider.notifier).state = val,
                  decoration: InputDecoration(
                    hintText: 'Tìm thiết bị, phòng...',
                    prefixIcon: const Icon(Icons.search_rounded, size: 20),
                    filled: true,
                    fillColor: isDark ? const Color(0xFF161B26) : Colors.white,
                    contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 16),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: BorderSide(
                        color: isDark ? const Color(0xFF232B3B) : const Color(0xFFE5E7EB),
                      ),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: BorderSide(
                        color: isDark ? const Color(0xFF232B3B) : const Color(0xFFE5E7EB),
                      ),
                    ),
                  ),
                ),
              ),
            ),

            // Filter Chips: All, Lights, Fans, Sockets, Sensors
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 16),
              sliver: SliverToBoxAdapter(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  physics: const BouncingScrollPhysics(),
                  child: Row(
                    children: [
                      _CategoryChip(
                        label: 'Tất cả',
                        isSelected: selectedCategory == 'all',
                        onTap: () => ref.read(deviceFilterCategoryProvider.notifier).state = 'all',
                      ),
                      _CategoryChip(
                        label: '💡 Đèn',
                        isSelected: selectedCategory == 'light',
                        onTap: () => ref.read(deviceFilterCategoryProvider.notifier).state = 'light',
                      ),
                      _CategoryChip(
                        label: '💨 Quạt',
                        isSelected: selectedCategory == 'fan',
                        onTap: () => ref.read(deviceFilterCategoryProvider.notifier).state = 'fan',
                      ),
                      _CategoryChip(
                        label: '⚡ Ổ cắm',
                        isSelected: selectedCategory == 'socket',
                        onTap: () => ref.read(deviceFilterCategoryProvider.notifier).state = 'socket',
                      ),
                      _CategoryChip(
                        label: '❄️ Điều hòa',
                        isSelected: selectedCategory == 'airConditioner',
                        onTap: () => ref.read(deviceFilterCategoryProvider.notifier).state = 'airConditioner',
                      ),
                    ],
                  ),
                ),
              ),
            ),

            // Devices grouped by room (Optimized via memoized provider)
            if (grouped.isEmpty)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                    child: Text('Không tìm thấy thiết bị phù hợp', style: TextStyle(color: Colors.grey)),
                  ),
                ),
              )
            else
              SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, roomIdx) {
                    final roomId = grouped.keys.elementAt(roomIdx);
                    final roomDevices = grouped[roomId]!;

                    final roomName = roomsAsync.when(
                      data: (rooms) => rooms.firstWhere((r) => r.id == roomId, orElse: () => Room(id: roomId, name: roomId)).name,
                      loading: () => roomId,
                      error: (_, __) => roomId,
                    );

                    return Padding(
                      padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                roomName,
                                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                              ),
                              Text(
                                '${roomDevices.length} thiết bị',
                                style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          GridView.builder(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              mainAxisSpacing: 12,
                              crossAxisSpacing: 12,
                              mainAxisExtent: 156,
                            ),
                            itemCount: roomDevices.length,
                            itemBuilder: (context, idx) {
                              final dev = roomDevices[idx];
                              return DeviceCard(
                                device: dev,
                                onToggle: (isOn) async {
                                  try {
                                    await ref.read(deviceRepositoryProvider).toggleDevice(dev.id, isOn);
                                  } catch (e) {
                                    if (context.mounted) {
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(content: Text('Lỗi điều khiển thiết bị: $e')),
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
                                            SnackBar(content: Text('Lỗi điều khiển thiết bị: $e')),
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
                            },
                          ),
                        ],
                      ),
                    );
                  },
                  childCount: grouped.keys.length,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _CategoryChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: GestureDetector(
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: isSelected
                ? (isDark ? Colors.white : const Color(0xFF0F172A))
                : (isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9)),
            borderRadius: BorderRadius.circular(100),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
              color: isSelected
                  ? (isDark ? const Color(0xFF0F172A) : Colors.white)
                  : theme.colorScheme.onSurface,
            ),
          ),
        ),
      ),
    );
  }
}
