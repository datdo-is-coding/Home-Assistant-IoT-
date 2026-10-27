import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../models/room.dart';
import '../models/device.dart';

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
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    final activeCount = devices.where((d) => d.isOn && d.online).length;

    return Container(
      decoration: BoxDecoration(
        color: colors.cardSurface,
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        border: Border.all(color: colors.cardBorder, width: 1.0),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.25 : 0.03),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          color: isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(room.icon, size: 20, color: theme.colorScheme.primary),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              room.name,
                              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              '${devices.length} thiết bị · $activeCount đang hoạt động',
                              style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      if (room.temperature != null) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: colors.climateWash,
                            borderRadius: BorderRadius.circular(12),
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
                      Icon(Icons.chevron_right_rounded, size: 20, color: theme.colorScheme.onSurfaceVariant),
                    ],
                  ),
                  if (devices.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      children: devices.take(4).map((d) {
                        final isDevOn = d.isOn && d.online;
                        return Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: isDevOn
                                ? (isDark ? const Color(0xFF261E14) : const Color(0xFFFEF3C7))
                                : (isDark ? const Color(0xFF1F2532) : const Color(0xFFF1F5F9)),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                d.iconData,
                                size: 14,
                                color: isDevOn
                                    ? colors.lightAccent
                                    : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B)),
                              ),
                              const SizedBox(width: 4),
                              Text(
                                d.name,
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: isDevOn
                                      ? colors.lightAccent
                                      : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B)),
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
        ),
      ),
    );
  }
}
