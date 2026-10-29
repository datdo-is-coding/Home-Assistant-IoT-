import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../models/room.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/device_card.dart';
import '../../widgets/action_box_card.dart';
import '../../widgets/quick_control_sheet.dart';
import '../../widgets/soft_3d_decorations.dart';
import '../../widgets/home_connection_name.dart';

class FeatureDevicesScreen extends ConsumerWidget {
  const FeatureDevicesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    final roomsAsync = ref.watch(roomsStreamProvider);
    final selectedCategory = ref.watch(deviceFilterCategoryProvider);
    final grouped = ref.watch(groupedFilteredDevicesProvider);

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Expanded(
                          child: Text('Thiết bị',
                              style: TextStyle(
                                  fontSize: 30,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: -0.9))),
                      IconButton(
                          tooltip: 'Remote hồng ngoại',
                          onPressed: () => context.push('/infrared'),
                          icon: const Icon(Icons.settings_remote_rounded)),
                    ]),
                    const HomeConnectionName(),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              sliver: SliverToBoxAdapter(
                child: Container(
                  decoration: Soft3DDecorations.card(
                    isDark: theme.brightness == Brightness.dark,
                    radius: 18,
                  ),
                  child: TextField(
                    onChanged: (val) =>
                        ref.read(searchQueryProvider.notifier).state = val,
                    style: TextStyle(
                      fontSize: 14,
                      color: theme.colorScheme.onSurface,
                    ),
                    decoration: InputDecoration(
                      hintText: 'Tìm thiết bị',
                      hintStyle: TextStyle(
                        fontSize: 14,
                        color: theme.colorScheme.onSurfaceVariant
                            .withValues(alpha: 0.8),
                      ),
                      prefixIcon: Icon(
                        Icons.search_rounded,
                        size: 20,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      filled: false,
                      contentPadding: const EdgeInsets.symmetric(
                          vertical: 14, horizontal: 16),
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                    ),
                  ),
                ),
              ),
            ),
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
                        onTap: () => ref
                            .read(deviceFilterCategoryProvider.notifier)
                            .state = 'all',
                      ),
                      _CategoryChip(
                        label: 'Đèn',
                        isSelected: selectedCategory == 'light',
                        onTap: () => ref
                            .read(deviceFilterCategoryProvider.notifier)
                            .state = 'light',
                      ),
                      _CategoryChip(
                        label: 'Quạt',
                        isSelected: selectedCategory == 'fan',
                        onTap: () => ref
                            .read(deviceFilterCategoryProvider.notifier)
                            .state = 'fan',
                      ),
                      _CategoryChip(
                        label: 'Ổ cắm',
                        isSelected: selectedCategory == 'socket',
                        onTap: () => ref
                            .read(deviceFilterCategoryProvider.notifier)
                            .state = 'socket',
                      ),
                      _CategoryChip(
                        label: 'Điều hòa',
                        isSelected: selectedCategory == 'airConditioner',
                        onTap: () => ref
                            .read(deviceFilterCategoryProvider.notifier)
                            .state = 'airConditioner',
                      ),
                      _CategoryChip(
                        label: 'Khác',
                        isSelected: selectedCategory == 'custom',
                        onTap: () => ref
                            .read(deviceFilterCategoryProvider.notifier)
                            .state = 'custom',
                      ),
                    ],
                  ),
                ),
              ),
            ),
            if (grouped.isEmpty)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                    child: Text('Không tìm thấy thiết bị phù hợp',
                        style: TextStyle(color: Colors.grey)),
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
                      data: (rooms) => rooms
                          .firstWhere((r) => r.id == roomId,
                              orElse: () => Room(id: roomId, name: roomId))
                          .name,
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
                                style: const TextStyle(
                                    fontSize: 16, fontWeight: FontWeight.w700),
                              ),
                              Text(
                                '${roomDevices.length} thiết bị',
                                style: TextStyle(
                                    fontSize: 12,
                                    color: theme.colorScheme.onSurfaceVariant),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          GridView.builder(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            gridDelegate:
                                SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              mainAxisSpacing: 12,
                              crossAxisSpacing: 12,
                              mainAxisExtent:
                                  MediaQuery.textScalerOf(context).scale(14) >
                                          17
                                      ? 220
                                      : 180,
                            ),
                            itemCount: roomDevices.length,
                            itemBuilder: (context, idx) {
                              final dev = roomDevices[idx];
                              return DeviceCard(
                                device: dev,
                                onToggle: (isOn) async {
                                  try {
                                    await ref
                                        .read(deviceRepositoryProvider)
                                        .toggleDevice(dev.id, isOn);
                                  } catch (e) {
                                    if (context.mounted) {
                                      ScaffoldMessenger.of(context)
                                          .showSnackBar(
                                        SnackBar(
                                            content: Text(
                                                'Lỗi điều khiển thiết bị: $e')),
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
                                        await ref
                                            .read(deviceRepositoryProvider)
                                            .toggleDevice(dev.id, isOn);
                                      } catch (e) {
                                        if (context.mounted) {
                                          ScaffoldMessenger.of(context)
                                              .showSnackBar(
                                            SnackBar(
                                                content: Text(
                                                    'Lỗi điều khiển thiết bị: $e')),
                                          );
                                        }
                                      }
                                    },
                                    onValueChanged: (val) {
                                      ref
                                          .read(deviceRepositoryProvider)
                                          .setDeviceValue(dev.id, val);
                                    },
                                    onMoreSettings: () {
                                      Navigator.of(context, rootNavigator: true).pop();
                                      context.push('/devices/${dev.id}');
                                    },
                                  );
                                },
                                onFavoriteToggle: () {
                                  ref
                                      .read(deviceRepositoryProvider)
                                      .toggleFavorite(dev.id);
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
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
              sliver: SliverToBoxAdapter(
                  child: ref.watch(actionBoxesStreamProvider).when(
                        data: (boxes) => boxes.isEmpty
                            ? const SizedBox.shrink()
                            : ExpansionTile(
                                tilePadding: EdgeInsets.zero,
                                title: const Text('Bộ điều khiển',
                                    style: TextStyle(
                                        fontSize: 15,
                                        fontWeight: FontWeight.w600)),
                                children: boxes
                                    .map((box) => Padding(
                                          padding:
                                              const EdgeInsets.only(bottom: 10),
                                          child: ActionBoxCard(
                                              actionBox: box,
                                              onTap: () => context.push(
                                                  '/actionbox/${box.id}')),
                                        ))
                                    .toList(),
                              ),
                        loading: () => const SizedBox.shrink(),
                        error: (_, __) => const SizedBox.shrink(),
                      )),
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
      child: SoftBounce(
        onTap: onTap,
        pressedScale: 0.93,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: Soft3DDecorations.pill(
            isDark: isDark,
            isSelected: isSelected,
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
