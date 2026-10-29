import 'dart:ui';
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

    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 22, sigmaY: 22),
        child: Container(
          height: 64,
          padding: const EdgeInsets.symmetric(horizontal: 18),
          decoration: BoxDecoration(
            color: isDark
                ? const Color(0xD90A120E)
                : Colors.white.withValues(alpha: 0.92),
            border: Border(
              bottom: BorderSide(
                color: isDark ? const Color(0xFF18281F) : const Color(0xFFE2E8F0),
                width: 1,
              ),
            ),
          ),
          child: Stack(
            children: [
              // Bottom Specular Ray Edge
              if (isDark)
                Positioned(
                  bottom: 0,
                  left: 60,
                  right: 60,
                  height: 1,
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          Colors.transparent,
                          const Color(0xFF10B981).withValues(alpha: 0.45),
                          const Color(0xFF34D399).withValues(alpha: 0.55),
                          const Color(0xFF10B981).withValues(alpha: 0.45),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),

              // Main Row Content
              Row(
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
                      // Pill 1: Trạng thái Firebase Cloud RTDB với Radar Ping Dot
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
                                  width: 14,
                                  height: 14,
                                  margin: const EdgeInsets.only(right: 6),
                                  child: Stack(
                                    alignment: Alignment.center,
                                    children: [
                                      if (isConnected)
                                        Container(
                                          width: 14,
                                          height: 14,
                                          decoration: BoxDecoration(
                                            shape: BoxShape.circle,
                                            color: colors.online.withValues(alpha: 0.25),
                                          ),
                                        ),
                                      Container(
                                        width: 7,
                                        height: 7,
                                        decoration: BoxDecoration(
                                          shape: BoxShape.circle,
                                          color: isConnected ? colors.online : colors.offline,
                                          boxShadow: isConnected
                                              ? [
                                                  BoxShadow(
                                                    color: colors.online.withValues(alpha: 0.8),
                                                    blurRadius: 6,
                                                  )
                                                ]
                                              : null,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
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
                                const SizedBox(width: 5),
                                Text(
                                  '${totalPower.toStringAsFixed(1)} W',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w800,
                                    color: colors.fanAccent,
                                  ),
                                ),
                              ],
                            ),
                          );
                        },
                      ),

                      const SizedBox(width: 12),

                      // Nút Chuyển đổi Dark/Light mode
                      ValueListenableBuilder<bool>(
                        valueListenable: isDarkModeNotifier,
                        builder: (context, isDarkValue, child) {
                          return Tooltip(
                            message: isDarkValue ? 'Chế độ Sáng' : 'Chế độ Tối',
                            child: IconButton(
                              onPressed: () {
                                isDarkModeNotifier.value = !isDarkValue;
                              },
                              icon: Icon(
                                isDarkValue
                                    ? Icons.light_mode_rounded
                                    : Icons.dark_mode_rounded,
                                size: 20,
                                color: isDark ? const Color(0xFF34D399) : const Color(0xFF64748B),
                              ),
                            ),
                          );
                        },
                      ),

                      const SizedBox(width: 4),

                      // Nút Chuông Thông Báo
                      Tooltip(
                        message: 'Thông báo',
                        child: IconButton(
                          onPressed: () {
                            selectedPageNotifier.value = 5;
                          },
                          icon: Icon(
                            Icons.notifications_none_rounded,
                            size: 21,
                            color: isDark ? const Color(0xFF8BAA97) : const Color(0xFF64748B),
                          ),
                        ),
                      ),

                      const SizedBox(width: 8),

                      // User Profile Menu
                      const UserAvatarMenu(),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
