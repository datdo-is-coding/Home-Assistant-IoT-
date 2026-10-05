import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../models/device.dart';
import '../../models/room.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/device_card.dart';
import '../../widgets/quick_control_sheet.dart';

class RoomDetailScreen extends ConsumerWidget {
  final String roomId;

  const RoomDetailScreen({
    super.key,
    required this.roomId,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final roomsAsync = ref.watch(roomsStreamProvider);
    final allDevices = ref.watch(devicesStreamProvider).value ?? [];

    final room = roomsAsync.value?.firstWhere(
      (r) => r.id == roomId,
      orElse: () => Room(id: roomId, name: 'Phòng $roomId'),
    );

    final roomDevices = allDevices.where((d) => d.roomId == roomId).toList();
    final activeCount = roomDevices.where((d) => d.isOn).length;

    // Grouping
    final lights = roomDevices.where((d) => d.type == DeviceType.light).toList();
    final climate = roomDevices.where((d) => d.type == DeviceType.fan || d.type == DeviceType.airConditioner).toList();
    final sockets = roomDevices.where((d) => d.type == DeviceType.socket).toList();
    final sensors = roomDevices.where((d) => d.type == DeviceType.sensor).toList();
    final others = roomDevices.where((d) =>
        d.type != DeviceType.light &&
        d.type != DeviceType.fan &&
        d.type != DeviceType.airConditioner &&
        d.type != DeviceType.socket &&
        d.type != DeviceType.sensor).toList();

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: Padding(
          padding: const EdgeInsets.only(left: 12),
          child: IconButton(
            icon: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E242B) : Colors.white,
                shape: BoxShape.circle,
                border: Border.all(
                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                ),
              ),
              child: Icon(
                Icons.arrow_back_ios_new_rounded,
                size: 16,
                color: theme.colorScheme.onSurface,
              ),
            ),
            onPressed: () => context.pop(),
          ),
        ),
        actions: [
          IconButton(
            tooltip: 'Tắt toàn bộ thiết bị trong phòng',
            icon: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E242B) : Colors.white,
                shape: BoxShape.circle,
                border: Border.all(
                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                ),
              ),
              child: Icon(
                Icons.power_settings_new_rounded,
                size: 18,
                color: activeCount > 0 ? const Color(0xFFE53935) : theme.colorScheme.onSurfaceVariant,
              ),
            ),
            onPressed: activeCount == 0
                ? null
                : () {
                    HapticFeedback.mediumImpact();
                    for (final dev in roomDevices) {
                      if (dev.isOn) {
                        ref.read(deviceRepositoryProvider).toggleDevice(dev.id, false);
                      }
                    }
                  },
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: room == null
          ? const Center(child: CircularProgressIndicator())
          : CustomScrollView(
              physics: const BouncingScrollPhysics(),
              slivers: [
                // Header section
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: isDark ? const Color(0xFF1E242B) : Colors.white,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                                ),
                              ),
                              child: Icon(
                                room.icon,
                                size: 24,
                                color: theme.colorScheme.primary,
                              ),
                            ),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    room.name,
                                    style: TextStyle(
                                      fontSize: 26,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: -0.5,
                                      color: theme.colorScheme.onSurface,
                                    ),
                                  ),
                                  Text(
                                    '${roomDevices.length} thiết bị · $activeCount đang hoạt động',
                                    style: TextStyle(
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500,
                                      color: theme.colorScheme.onSurfaceVariant,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),

                        // Room Environmental Telemetry Bar (if available)
                        if (room.temperature != null || room.humidity != null) ...[
                          const SizedBox(height: 16),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            decoration: BoxDecoration(
                              color: isDark ? const Color(0xFF161A22) : Colors.white,
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: isDark ? Colors.white.withOpacity(0.06) : Colors.black.withOpacity(0.05),
                              ),
                            ),
                            child: Row(
                              children: [
                                if (room.temperature != null) ...[
                                  const Icon(Icons.thermostat_rounded, size: 20, color: Color(0xFFFF9800)),
                                  const SizedBox(width: 6),
                                  Text(
                                    '${room.temperature!.toStringAsFixed(1)}°C',
                                    style: TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w700,
                                      color: theme.colorScheme.onSurface,
                                    ),
                                  ),
                                  const SizedBox(width: 4),
                                  Text(
                                    'Nhiệt độ',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: theme.colorScheme.onSurfaceVariant,
                                    ),
                                  ),
                                ],
                                if (room.temperature != null && room.humidity != null)
                                  Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 16),
                                    child: Container(
                                      width: 1,
                                      height: 16,
                                      color: isDark ? Colors.white12 : Colors.black12,
                                    ),
                                  ),
                                if (room.humidity != null) ...[
                                  const Icon(Icons.water_drop_rounded, size: 18, color: Color(0xFF29B6F6)),
                                  const SizedBox(width: 6),
                                  Text(
                                    '${room.humidity!.toStringAsFixed(0)}%',
                                    style: TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w700,
                                      color: theme.colorScheme.onSurface,
                                    ),
                                  ),
                                  const SizedBox(width: 4),
                                  Text(
                                    'Độ ẩm',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: theme.colorScheme.onSurfaceVariant,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),

                if (roomDevices.isEmpty)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.all(40),
                      child: Center(
                        child: Column(
                          children: [
                            Icon(
                              Icons.devices_other_rounded,
                              size: 48,
                              color: theme.colorScheme.onSurfaceVariant.withOpacity(0.5),
                            ),
                            const SizedBox(height: 12),
                            Text(
                              'Chưa có thiết bị nào trong phòng này',
                              style: TextStyle(
                                fontSize: 14,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),

                // Device Categories
                if (lights.isNotEmpty) ...[
                  _buildCategoryHeader('Chiếu sáng · Lights (${lights.length})'),
                  _buildDeviceGrid(context, ref, lights),
                ],

                if (climate.isNotEmpty) ...[
                  _buildCategoryHeader('Khí hậu · Climate (${climate.length})'),
                  _buildDeviceGrid(context, ref, climate),
                ],

                if (sockets.isNotEmpty) ...[
                  _buildCategoryHeader('Ổ cắm · Sockets (${sockets.length})'),
                  _buildDeviceGrid(context, ref, sockets),
                ],

                if (sensors.isNotEmpty) ...[
                  _buildCategoryHeader('Cảm biến · Sensors (${sensors.length})'),
                  _buildDeviceGrid(context, ref, sensors),
                ],

                if (others.isNotEmpty) ...[
                  _buildCategoryHeader('Thiết bị khác (${others.length})'),
                  _buildDeviceGrid(context, ref, others),
                ],

                const SliverToBoxAdapter(
                  child: SizedBox(height: 48),
                ),
              ],
            ),
    );
  }

  Widget _buildCategoryHeader(String title) {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
      sliver: SliverToBoxAdapter(
        child: Text(
          title,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.2,
          ),
        ),
      ),
    );
  }

  Widget _buildDeviceGrid(BuildContext context, WidgetRef ref, List<Device> devices) {
    return SliverPadding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      sliver: SliverGrid(
        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
          maxCrossAxisExtent: 220,
          mainAxisExtent: 156,
          crossAxisSpacing: 10,
          mainAxisSpacing: 10,
        ),
        delegate: SliverChildBuilderDelegate(
          (context, index) {
            final device = devices[index];
            return DeviceCard(
              device: device,
              onToggle: (isOn) {
                ref.read(deviceRepositoryProvider).toggleDevice(device.id, isOn);
              },
              onTap: () {
                QuickControlSheet.show(
                  context,
                  device: device,
                  onToggle: (isOn) {
                    ref.read(deviceRepositoryProvider).toggleDevice(device.id, isOn);
                  },
                  onValueChanged: (val) {
                    ref.read(deviceRepositoryProvider).setDeviceValue(device.id, val);
                  },
                  onMoreSettings: () {
                    Navigator.pop(context);
                    context.push('/devices/${device.id}');
                  },
                );
              },
            );
          },
          childCount: devices.length,
        ),
      ),
    );
  }
}
