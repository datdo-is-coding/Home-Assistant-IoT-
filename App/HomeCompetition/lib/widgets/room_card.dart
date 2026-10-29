import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../models/room.dart';
import '../models/device.dart';
import 'soft_3d_decorations.dart';

class RoomCard extends StatelessWidget {
  final Room room;
  final List<Device> devices;
  final VoidCallback onTap;

  const RoomCard({
    super.key,
    required this.room,
    required this.devices,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ??
        (isDark ? AppColors.dark : AppColors.light);

    final activeCount = devices.where((d) => d.isOn && d.online).length;
    final bool hasActiveDevices = activeCount > 0;

    return SoftBounce(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOutCubic,
        decoration: Soft3DDecorations.card(
          isDark: isDark,
          isActive: false,
          radius: AppTheme.cardRadius,
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  // 3D Soft Icon Well
                  Container(
                    width: 42,
                    height: 42,
                    decoration: Soft3DDecorations.iconWell(
                      isDark: isDark,
                      isActive: hasActiveDevices,
                      accentColor: colors.lightAccent,
                      radius: 14,
                    ),
                    child: Icon(
                      room.icon,
                      size: 21,
                      color: hasActiveDevices
                          ? colors.lightAccent
                          : theme.colorScheme.primary,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          room.name,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.3,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Row(
                          children: [
                            if (hasActiveDevices) ...[
                              Container(
                                width: 6,
                                height: 6,
                                margin: const EdgeInsets.only(right: 5),
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: colors.online,
                                  boxShadow: [
                                    BoxShadow(
                                      color: colors.online.withValues(alpha: 0.8),
                                      blurRadius: 5,
                                      spreadRadius: 1,
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            Expanded(
                              child: Text(
                                '${devices.length} thiết bị · $activeCount đang hoạt động',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  if (room.temperature != null) ...[
                    // Sleek 3D temperature pill
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 9, vertical: 4.5),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: isDark
                              ? [const Color(0xFF132A26), const Color(0xFF0F1E1B)]
                              : [const Color(0xFFE6FFFA), const Color(0xFFCCFBF1)],
                        ),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: colors.climateAccent.withValues(alpha: 0.35),
                          width: 1,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: colors.climateAccent.withValues(alpha: 0.15),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Text(
                        '${room.temperature}°C',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: colors.climateAccent,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                  ],
                  Icon(
                    Icons.chevron_right_rounded,
                    size: 20,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ],
              ),
              if (devices.isNotEmpty) ...[
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: devices.take(4).map((d) {
                    final isDevOn = d.isOn && d.online;
                    return Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 9, vertical: 4.5),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: isDevOn
                              ? (isDark
                                  ? [
                                      const Color(0xFF2E2416),
                                      const Color(0xFF221A0F)
                                    ]
                                  : [
                                      const Color(0xFFFFFBEB),
                                      const Color(0xFFFEF3C7)
                                    ])
                              : (isDark
                                  ? [
                                      const Color(0xFF222B3B),
                                      const Color(0xFF181F2C)
                                    ]
                                  : [
                                      Colors.white,
                                      const Color(0xFFF1F5F9)
                                    ]),
                        ),
                        borderRadius: BorderRadius.circular(9),
                        border: Border.all(
                          color: isDevOn
                              ? colors.lightAccent.withValues(alpha: 0.4)
                              : (isDark
                                  ? const Color(0xFF2D374A)
                                  : const Color(0xFFE2E8F0)),
                          width: 1,
                        ),
                        boxShadow: isDevOn
                            ? [
                                BoxShadow(
                                  color: colors.lightAccent
                                      .withValues(alpha: 0.18),
                                  blurRadius: 6,
                                  offset: const Offset(0, 2),
                                ),
                              ]
                            : null,
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            d.iconData,
                            size: 14,
                            color: isDevOn
                                ? colors.lightAccent
                                : (isDark
                                    ? const Color(0xFF94A3B8)
                                    : const Color(0xFF64748B)),
                          ),
                          const SizedBox(width: 5),
                          Text(
                            d.name,
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: isDevOn
                                  ? colors.lightAccent
                                  : (isDark
                                      ? const Color(0xFF94A3B8)
                                      : const Color(0xFF64748B)),
                            ),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
