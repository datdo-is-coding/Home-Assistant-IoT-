import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
import '../../data/model/device_model.dart';
import '../../data/model/room_model.dart';
import '../../data/model/scene_model.dart';
import '../../data/notifiers.dart';
import '../../data/services/firebase_realtime_service.dart';
import '../widgets/charts/hourly_consumption_chart.dart';
import '../widgets/mobile_parity/device_card.dart';
import '../widgets/mobile_parity/energy_overview_card.dart';
import '../widgets/mobile_parity/room_chip.dart';
import '../widgets/mobile_parity/scene_card.dart';
import '../widgets/mobile_parity/status_banner.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  String _selectedRoomId = 'all';
  bool _favoritesOnly = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final rtdb = FirebaseRealtimeService();

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: ValueListenableBuilder<List<RoomModel>>(
        valueListenable: rtdb.roomsNotifier,
        builder: (context, rooms, _) {
          return ValueListenableBuilder<double>(
            valueListenable: rtdb.totalPowerNotifier,
            builder: (context, totalPower, _) {
              return ValueListenableBuilder<double>(
                valueListenable: rtdb.totalEnergyNotifier,
                builder: (context, totalEnergy, _) {
                  return ValueListenableBuilder<bool>(
                    valueListenable: rtdb.isConnectedNotifier,
                    builder: (context, isConnected, _) {
                      // Tổng hợp danh sách tất cả thiết bị
                      final allDevices = <DeviceModel>[];
                      for (final r in rooms) {
                        for (final d in r.devices) {
                          allDevices.add(d);
                        }
                      }

                      final totalCount = allDevices.length;
                      final onlineCount =
                          allDevices.where((d) => d.online).length;
                      final offlineCount = totalCount - onlineCount;
                      final activeCount =
                          allDevices.where((d) => d.isOn && d.online).length;

                      // Lọc theo phòng
                      List<DeviceModel> filteredDevices = allDevices;
                      if (_selectedRoomId != 'all') {
                        filteredDevices = filteredDevices
                            .where((d) => d.roomName == _selectedRoomId)
                            .toList();
                      }
                      if (_favoritesOnly) {
                        filteredDevices = filteredDevices
                            .where((d) => d.isFavorite)
                            .toList();
                      }

                      // Chuẩn bị danh sách trạng thái cho StatusBanner
                      final statuses = <String>[
                        '${totalPower.toStringAsFixed(1)} W đang đo',
                        '$activeCount thiết bị đang bật',
                        if (offlineCount > 0)
                          '$offlineCount thiết bị ngoại tuyến'
                        else
                          'Tất cả thiết bị trực tuyến',
                        if (!isConnected)
                          'Mất kết nối RTDB'
                        else
                          'Cloud RTDB sẵn sàng',
                      ];

                      return SingleChildScrollView(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 24, vertical: 20),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // 1. HEADER: Tên nhà & Nút hành động nhanh (Đồng bộ Mobile HomeScreen)
                            _buildHeader(context, theme, isDark, totalCount,
                                onlineCount),

                            const SizedBox(height: 16),

                            // 2. STATUS BANNER: Các pill hiển thị trạng thái hệ thống
                            ParityStatusBanner(statuses: statuses),

                            const SizedBox(height: 18),

                            // 3. ROOM CHIPS: Lọc theo từng phòng (Tất cả, Phòng khách, Phòng ngủ, ...)
                            _buildRoomChips(rooms, allDevices.length),

                            const SizedBox(height: 20),

                            // 4. MAIN CONTENT AREA (2 CỘT TỐI ƯU GIAO DIỆN WEB)
                            LayoutBuilder(
                              builder: (context, constraints) {
                                final isWide = constraints.maxWidth >= 960;

                                if (isWide) {
                                  return Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      // Cột Trái (58%): Điều khiển thiết bị nhanh
                                      Expanded(
                                        flex: 58,
                                        child: _buildDevicesGridSection(
                                          context,
                                          theme,
                                          isDark,
                                          filteredDevices,
                                          rtdb,
                                        ),
                                      ),
                                      const SizedBox(width: 20),
                                      // Cột Phải (42%): Thẻ Năng lượng BL0942 + Biểu đồ + Kịch bản
                                      Expanded(
                                        flex: 42,
                                        child: _buildRightSideSection(
                                          context,
                                          totalPower,
                                          totalEnergy,
                                          onlineCount,
                                          totalCount,
                                          rtdb,
                                        ),
                                      ),
                                    ],
                                  );
                                }

                                // Mobile / Tablet screen: Single column stack
                                return Column(
                                  children: [
                                    _buildDevicesGridSection(
                                      context,
                                      theme,
                                      isDark,
                                      filteredDevices,
                                      rtdb,
                                    ),
                                    const SizedBox(height: 20),
                                    _buildRightSideSection(
                                      context,
                                      totalPower,
                                      totalEnergy,
                                      onlineCount,
                                      totalCount,
                                      rtdb,
                                    ),
                                  ],
                                );
                              },
                            ),
                          ],
                        ),
                      );
                    },
                  );
                },
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildHeader(BuildContext context, ThemeData theme, bool isDark,
      int totalCount, int onlineCount) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Home Companion',
              style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.5,
                color: theme.colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              '$totalCount thiết bị · $onlineCount trực tuyến · Tự động đồng bộ Firebase',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        Row(
          children: [
            _buildCircularAction(
              icon: Icons.add_rounded,
              tooltip: 'Thêm bo mạch / Thiết bị',
              onPressed: () => selectedPageNotifier.value = 1,
            ),
            const SizedBox(width: 8),
            _buildCircularAction(
              icon: Icons.notifications_none_rounded,
              tooltip: 'Cảnh báo',
              onPressed: () => selectedPageNotifier.value = 5,
            ),
            const SizedBox(width: 8),
            _buildCircularAction(
              icon: Icons.record_voice_over_rounded,
              tooltip: 'Giọng nói KWS',
              onPressed: () => selectedPageNotifier.value = 4,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildCircularAction({
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
  }) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(100),
        child: Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: isDark ? const Color(0xCC0C1610) : const Color(0xFFF1F5F9),
            border: Border.all(
              color: isDark ? const Color(0xFF18281F) : const Color(0xFFE2E8F0),
            ),
          ),
          child: Icon(icon, size: 19, color: theme.colorScheme.primary),
        ),
      ),
    );
  }

  Widget _buildRoomChips(List<RoomModel> rooms, int totalCount) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      child: Row(
        children: [
          ParityRoomChip(
            label: 'Tất cả',
            count: totalCount,
            isSelected: _selectedRoomId == 'all',
            onSelected: () => setState(() => _selectedRoomId = 'all'),
          ),
          const SizedBox(width: 8),
          ...rooms.map((r) {
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ParityRoomChip(
                label: r.name,
                count: r.devices.length,
                isSelected: _selectedRoomId == r.name,
                onSelected: () => setState(() => _selectedRoomId = r.name),
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildDevicesGridSection(
    BuildContext context,
    ThemeData theme,
    bool isDark,
    List<DeviceModel> devices,
    FirebaseRealtimeService rtdb,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              _favoritesOnly ? 'Thiết bị yêu thích' : 'Điều khiển nhanh',
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.3,
              ),
            ),
            IconButton(
              tooltip: _favoritesOnly ? 'Hiện tất cả' : 'Chỉ yêu thích',
              onPressed: () {
                setState(() => _favoritesOnly = !_favoritesOnly);
              },
              icon: Icon(
                _favoritesOnly
                    ? Icons.star_rounded
                    : Icons.star_outline_rounded,
                color: _favoritesOnly
                    ? const Color(0xFFF59E0B)
                    : (isDark
                        ? const Color(0xFF64748B)
                        : const Color(0xFF94A3B8)),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (devices.isEmpty)
          Container(
            padding: const EdgeInsets.all(32),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: isDark ? const Color(0xCC0D1410) : Colors.white,
              borderRadius: BorderRadius.circular(AppTheme.cardRadius),
              border: Border.all(
                color: isDark ? const Color(0xFF18281F) : const Color(0xFFE5E7EB),
              ),
            ),
            child: Column(
              children: [
                Icon(
                  Icons.devices_other_rounded,
                  size: 44,
                  color: isDark ? const Color(0xFF475569) : const Color(0xFF94A3B8),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Không có thiết bị trong khu vực này',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                ),
                const SizedBox(height: 4),
                Text(
                  'Hãy chọn phòng khác hoặc nhấn nút Thêm bo mạch',
                  style: TextStyle(
                    color: theme.colorScheme.onSurfaceVariant,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          )
        else
          LayoutBuilder(
            builder: (context, constraints) {
              final crossAxisCount = constraints.maxWidth >= 600 ? 3 : 2;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: devices.length,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: crossAxisCount,
                  mainAxisSpacing: 14,
                  crossAxisSpacing: 14,
                  childAspectRatio: 1.25,
                ),
                itemBuilder: (context, index) {
                  final dev = devices[index];
                  return ParityDeviceCard(
                    device: dev,
                    onTap: () {
                      if (dev.boxId != null && dev.channelKey != null) {
                        rtdb.toggleChannel(
                            dev.boxId!, dev.channelKey!, !dev.isOn);
                      }
                    },
                    onToggle: (newVal) {
                      if (dev.boxId != null && dev.channelKey != null) {
                        rtdb.toggleChannel(
                            dev.boxId!, dev.channelKey!, newVal);
                      }
                    },
                    onFavoriteToggle: () {
                      setState(() {
                        dev.isFavorite = !dev.isFavorite;
                      });
                    },
                  );
                },
              );
            },
          ),
      ],
    );
  }

  Widget _buildRightSideSection(
    BuildContext context,
    double totalPower,
    double totalEnergy,
    int onlineCount,
    int totalCount,
    FirebaseRealtimeService rtdb,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Card Năng Lượng Chuẩn Mobile EnergyScreen
        ParityEnergyOverviewCard(
          totalPower: totalPower,
          totalEnergy: totalEnergy,
          measuredCount: onlineCount,
          totalCount: totalCount,
          onTap: () => selectedPageNotifier.value = 2,
        ),

        const SizedBox(height: 18),

        // Biểu đồ tiêu thụ điện năng tương tác (với Progressive Blur & Light Rays)
        const SizedBox(
          height: 290,
          child: HourlyConsumptionChart(),
        ),

        const SizedBox(height: 18),

        // Kịch bản nhanh (Quick Scenes)
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'Kịch bản nhanh',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.2,
              ),
            ),
            TextButton(
              onPressed: () => selectedPageNotifier.value = 3,
              child: const Text('Xem tất cả'),
            ),
          ],
        ),
        const SizedBox(height: 8),

        ValueListenableBuilder<List<SceneModel>>(
          valueListenable: rtdb.scenesNotifier,
          builder: (context, scenes, _) {
            final previewScenes = scenes.take(2).toList();
            return Row(
              children: previewScenes.map((sc) {
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(right: 8.0),
                    child: ParitySceneCard(
                      scene: sc,
                      onActivate: () {
                        rtdb.triggerScene(sc);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text('Đã kích hoạt kịch bản: ${sc.name}'),
                            duration: const Duration(seconds: 2),
                          ),
                        );
                      },
                    ),
                  ),
                );
              }).toList(),
            );
          },
        ),
      ],
    );
  }
}
