import 'package:flutter/material.dart';
import 'package:iot_dashboard/core/theme/app_theme.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/data/services/firebase_realtime_service.dart';
import 'package:iot_dashboard/view/widgets/common/custom_searchbar.dart';
import 'package:iot_dashboard/view/widgets/common/user_avatar_menu.dart';

class TopbarWidget extends StatelessWidget {
  const TopbarWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 18),
      decoration: BoxDecoration(
        color: colors.cardSurface,
        border: Border(
          bottom: BorderSide(color: colors.cardBorder, width: 1),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 1. Bên trái: Search Bar
          const Expanded(
            child: Row(
              children: [
                SizedBox(width: 8),
                CustomSearchAutocomplete(),
              ],
            ),
          ),

          const SizedBox(width: 16),

          // 2. Bên phải: Status pills + Dark mode toggle + Notifications + Avatar
          Row(
            children: [
              // Pill 1: Trạng thái Firebase Cloud RTDB
              ValueListenableBuilder<bool>(
                valueListenable: FirebaseRealtimeService().isConnectedNotifier,
                builder: (context, isConnected, child) {
                  return Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: isConnected
                          ? colors.online.withValues(alpha: isDark ? 0.16 : 0.10)
                          : colors.offline.withValues(alpha: isDark ? 0.16 : 0.10),
                      borderRadius: BorderRadius.circular(100),
                      border: Border.all(
                        color: (isConnected ? colors.online : colors.offline)
                            .withValues(alpha: 0.35),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isConnected ? colors.online : colors.offline,
                            boxShadow: isConnected
                                ? [
                                    BoxShadow(
                                      color: colors.online.withValues(alpha: 0.7),
                                      blurRadius: 5,
                                      spreadRadius: 1,
                                    )
                                  ]
                                : null,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          isConnected ? 'Cloud RTDB: Trực tuyến' : 'Cloud RTDB: Ngoại tuyến',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: isConnected ? colors.online : colors.offline,
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),

              const SizedBox(width: 10),

              // Pill 2: Công suất tiêu thụ tức thời
              ValueListenableBuilder<double>(
                valueListenable: FirebaseRealtimeService().totalPowerNotifier,
                builder: (context, totalPower, child) {
                  return Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: colors.fanWash,
                      borderRadius: BorderRadius.circular(100),
                      border: Border.all(
                        color: colors.fanAccent.withValues(alpha: 0.35),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.bolt_rounded,
                          size: 15,
                          color: colors.fanAccent,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${totalPower.toStringAsFixed(1)} W',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: colors.fanAccent,
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),

              const SizedBox(width: 10),

              // Dark / Light Mode Toggle
              IconButton(
                tooltip: isDark ? 'Chế độ Sáng' : 'Chế độ Tối',
                icon: Icon(
                  isDark ? Icons.light_mode_rounded : Icons.dark_mode_rounded,
                  size: 20,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                onPressed: () {
                  isDarkModeNotifier.value = !isDarkModeNotifier.value;
                },
              ),

              // Notifications
              Stack(
                children: [
                  IconButton(
                    icon: const Icon(Icons.notifications_none_rounded),
                    color: theme.colorScheme.onSurfaceVariant,
                    iconSize: 21,
                    onPressed: () {
                      selectedPageNotifier.value = 5;
                    },
                  ),
                  Positioned(
                    right: 10,
                    top: 10,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: colors.lightAccent,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(width: 6),

              const UserAvatarMenu(),
            ],
          ),
        ],
      ),
    );
  }
}
