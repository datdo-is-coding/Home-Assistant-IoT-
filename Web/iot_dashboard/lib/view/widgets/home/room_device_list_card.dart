import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';
import 'package:iot_dashboard/data/model/room_model.dart';
import 'package:iot_dashboard/data/model/user_model.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/data/services/firebase_realtime_service.dart';
import 'package:iot_dashboard/view/widgets/common/device_power_manager.dart';

class RoomDeviceListCard extends StatefulWidget {
  final List<RoomModel>? rooms;
  final String initialRoomId;

  const RoomDeviceListCard({
    super.key,
    this.rooms,
    this.initialRoomId = 'e1',
  });

  @override
  State<RoomDeviceListCard> createState() => _RoomDeviceListCardState();
}

class _RoomDeviceListCardState extends State<RoomDeviceListCard> {
  late String selectedRoomId;

  List<RoomModel> get _effectiveRooms =>
      widget.rooms ?? DevicePowerManager().rooms;

  @override
  void initState() {
    super.initState();
    selectedRoomId = widget.initialRoomId;
  }

  void _syncWithUserNotifier(String roomName, String deviceName, bool isOn) {
    final user = currentUserNotifier.value;
    final details = user.package.roomDevicesDetails;
    if (details.containsKey(roomName)) {
      final devList = details[roomName]!;
      final index = devList.indexWhere((d) => d.deviceName == deviceName);
      if (index != -1) {
        final oldDev = devList[index];
        devList[index] = RoomDeviceInfo(
          deviceName: oldDev.deviceName,
          powerWatts: oldDev.powerWatts,
          isOn: isOn,
        );
        // Trigger notification for profile page & package listeners
        currentUserNotifier.value = UserModel(
          id: user.id,
          name: user.name,
          email: user.email,
          phone: user.phone,
          address: user.address,
          password: user.password,
          avatarUrl: user.avatarUrl,
          package: user.package,
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);
    final rooms = _effectiveRooms;

    final currentRoom = rooms.firstWhere(
      (room) => room.id == selectedRoomId,
      orElse: () => rooms.isNotEmpty
          ? rooms.first
          : RoomModel(id: 'r_empty', name: 'Đang kết nối...', devices: []),
    );

    return Container(
      padding: const EdgeInsets.all(AppSizes.xl),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSizes.radiusXl),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 20,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 📌 1. BỘ CHỌN PHÒNG VÀ THỐNG KÊ TỔNG QUAN
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: AppColors.inputBg(context),
                  borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                  border: Border.all(color: borderColor),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: selectedRoomId,
                    dropdownColor: cardBg,
                    icon: Icon(
                      Icons.keyboard_arrow_down_rounded,
                      color: isDark ? Colors.white70 : const Color(0xFF475569),
                    ),
                    style: TextStyle(
                      fontSize: AppFontSizes.bodyLarge,
                      fontWeight: FontWeight.bold,
                      color: AppColors.titleColor(context),
                    ),
                    items: rooms.map((room) {
                      return DropdownMenuItem<String>(
                        value: room.id,
                        child: Row(
                          children: [
                            Icon(
                              _getRoomIcon(room.name),
                              size: 20,
                              color: AppColors.primaryLight,
                            ),
                            const SizedBox(width: 10),
                            Text(
                              room.name,
                              style: TextStyle(
                                color: AppColors.titleColor(context),
                              ),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                    onChanged: (String? newValue) {
                      if (newValue != null) {
                        setState(() {
                          selectedRoomId = newValue;
                        });
                      }
                    },
                  ),
                ),
              ),

              // Thống kê nhanh tổng công suất tiêu thụ trong phòng
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E1B4B)
                      : const Color(0xFFEEF2FF),
                  borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                  border: Border.all(
                    color: isDark
                        ? const Color(0xFF3730A3)
                        : const Color(0xFFC7D2FE),
                  ),
                ),
                child: Row(
                  children: [
                    const Icon(
                      Icons.electric_bolt_rounded,
                      size: 16,
                      color: Color(0xFF818CF8),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '${_calculateTotalWatts(currentRoom)} W',
                      style: TextStyle(
                        fontSize: AppFontSizes.bodySmall,
                        fontWeight: FontWeight.bold,
                        color: isDark ? const Color(0xFFA5B4FC) : const Color(0xFF4338CA),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSizes.xl),

          // 📌 2. TIÊU ĐỀ & SỐ LƯỢNG THIẾT BỊ
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Danh sách thiết bị (${currentRoom.devices.length})',
                style: TextStyle(
                  fontSize: AppFontSizes.bodyMedium,
                  fontWeight: FontWeight.bold,
                  color: AppColors.subtleColor(context),
                ),
              ),
              Text(
                '${currentRoom.devices.where((d) => d.isOn).length} đang hoạt động',
                style: TextStyle(
                  fontSize: AppFontSizes.bodySmall,
                  fontWeight: FontWeight.w600,
                  color: isDark ? const Color(0xFF34D399) : const Color(0xFF047857),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.md),

          // 📌 3. DANH SÁCH THIẾT BỊ
          Expanded(
            child: ListView.builder(
              itemCount: currentRoom.devices.length,
              itemBuilder: (context, index) {
                final device = currentRoom.devices[index];
                final iconData = _getDeviceIcon(device.icon);
                final colorScheme = _getDeviceColor(device.icon);

                final itemBg = device.isOn
                    ? (isDark ? const Color(0xFF0F172A) : Colors.white)
                    : (isDark
                        ? const Color(0xFF0F172A).withValues(alpha: 0.5)
                        : const Color(0xFFF8FAFC));

                return AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    color: itemBg,
                    borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                    border: Border.all(
                      color: device.isOn
                          ? colorScheme.withValues(alpha: 0.4)
                          : borderColor,
                      width: 1.2,
                    ),
                    boxShadow: device.isOn
                        ? [
                            BoxShadow(
                              color: colorScheme.withValues(alpha: 0.08),
                              blurRadius: 10,
                              offset: const Offset(0, 4),
                            ),
                          ]
                        : [],
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: device.isOn
                              ? colorScheme.withValues(alpha: 0.15)
                              : (isDark ? const Color(0xFF1E293B) : Colors.grey.shade200),
                          borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                        ),
                        child: Icon(
                          iconData,
                          color: device.isOn
                              ? colorScheme
                              : (isDark ? Colors.grey.shade400 : Colors.grey.shade500),
                          size: 22,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              device.name,
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: AppFontSizes.bodyMedium,
                                color: device.isOn
                                    ? AppColors.titleColor(context)
                                    : AppColors.subtleColor(context),
                              ),
                            ),
                            const SizedBox(height: 3),
                            Row(
                              children: [
                                Container(
                                  width: 6,
                                  height: 6,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: device.isOn
                                        ? const Color(0xFF10B981)
                                        : (isDark ? Colors.grey.shade600 : Colors.grey.shade400),
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  device.isOn
                                      ? '${device.powerWatts.toStringAsFixed(1)} W${device.voltage > 0 ? " · ${device.voltage.toStringAsFixed(0)}V" : ""} • Đang bật'
                                      : 'Đã tắt',
                                  style: TextStyle(
                                    fontSize: AppFontSizes.caption,
                                    fontWeight: FontWeight.w500,
                                    color: device.isOn
                                        ? AppColors.bodyColor(context)
                                        : AppColors.subtleColor(context),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      Switch(
                        value: device.isOn,
                        activeThumbColor: colorScheme,
                        onChanged: (bool value) {
                          setState(() {
                            device.isOn = value;
                            _syncWithUserNotifier(
                              currentRoom.name,
                              device.name,
                              value,
                            );
                            if (device.boxId != null &&
                                device.channelKey != null) {
                              FirebaseRealtimeService().toggleChannel(
                                device.boxId!,
                                device.channelKey!,
                                value,
                              );
                            }
                          });
                        },
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  int _calculateTotalWatts(RoomModel room) {
    return room.devices
        .where((d) => d.isOn)
        .fold<double>(0.0, (sum, device) => sum + device.powerWatts)
        .round();
  }

  IconData _getRoomIcon(String roomName) {
    if (roomName.contains('ngủ')) return Icons.bed_rounded;
    if (roomName.contains('khách')) return Icons.weekend_rounded;
    if (roomName.contains('bếp')) return Icons.soup_kitchen_rounded;
    return Icons.meeting_room_rounded;
  }

  IconData _getDeviceIcon(String iconName) {
    switch (iconName) {
      case 'lightbulb':
      case 'light':
        return Icons.lightbulb_rounded;
      case 'ac_unit':
        return Icons.ac_unit_rounded;
      case 'fan':
        return Icons.mode_fan_off_rounded;
      case 'tv':
        return Icons.tv_rounded;
      case 'soup_kitchen':
      case 'kitchen':
        return Icons.kitchen_rounded;
      default:
        return Icons.power_rounded;
    }
  }

  Color _getDeviceColor(String iconName) {
    switch (iconName) {
      case 'lightbulb':
      case 'light':
        return const Color(0xFFF59E0B);
      case 'ac_unit':
        return const Color(0xFF06B6D4);
      case 'fan':
        return const Color(0xFF10B981);
      case 'tv':
        return const Color(0xFF6366F1);
      case 'soup_kitchen':
      case 'kitchen':
        return const Color(0xFFEC4899);
      default:
        return const Color(0xFF3B82F6);
    }
  }
}
