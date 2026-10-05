import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/theme/app_theme.dart';
import '../models/device.dart';

class DeviceCard extends StatelessWidget {
  final Device device;
  final VoidCallback onTap;
  final ValueChanged<bool> onToggle;
  final VoidCallback? onFavoriteToggle;

  const DeviceCard({
    super.key,
    required this.device,
    required this.onTap,
    required this.onToggle,
    this.onFavoriteToggle,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    // Accent color based on device type
    final Color accentColor = switch (device.type) {
      DeviceType.light => colors.lightAccent,
      DeviceType.fan => colors.fanAccent,
      DeviceType.socket => colors.socketAccent,
      DeviceType.airConditioner => colors.climateAccent,
      _ => colors.socketAccent,
    };

    final bool isActive = device.isOn && device.online;

    final Color cardBg = whenActiveColor(
      isActive: isActive,
      online: device.online,
      isDark: isDark,
      accentColor: accentColor,
      surface: colors.cardSurface,
    );

    final Color borderColor = isActive
        ? accentColor.withValues(alpha: isDark ? 0.45 : 0.38)
        : colors.cardBorder;

    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        border: Border.all(color: borderColor, width: isActive ? 1.2 : 1.0),
        boxShadow: [
          BoxShadow(
            color: isActive
                ? accentColor.withValues(alpha: isDark ? 0.14 : 0.07)
                : Colors.black.withValues(alpha: isDark ? 0.25 : 0.03),
            blurRadius: isActive ? 16 : 8,
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
            onLongPress: onTap,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Row 1: Squircle Icon (Direct toggle on tap) + Favorite & Chevron
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      GestureDetector(
                        onTap: device.online
                            ? () {
                                HapticFeedback.lightImpact();
                                onToggle(!device.isOn);
                              }
                            : null,
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 240),
                          curve: Curves.easeOutCubic,
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: isActive
                                ? accentColor.withValues(alpha: isDark ? 0.24 : 0.16)
                                : (isDark ? const Color(0xFF1E2533) : const Color(0xFFF1F5F9)),
                            borderRadius: BorderRadius.circular(AppTheme.iconRadius),
                            border: Border.all(
                              color: isActive
                                  ? accentColor.withValues(alpha: 0.5)
                                  : colors.cardBorder,
                              width: 1,
                            ),
                          ),
                          child: Icon(
                            device.iconData,
                            size: 19,
                            color: isActive
                                ? accentColor
                                : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B)),
                          ),
                        ),
                      ),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (onFavoriteToggle != null)
                            IconButton(
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(minWidth: 26, minHeight: 26),
                              onPressed: () {
                                HapticFeedback.selectionClick();
                                onFavoriteToggle!();
                              },
                              icon: Icon(
                                device.isFavorite ? Icons.star_rounded : Icons.star_outline_rounded,
                                size: 18,
                                color: device.isFavorite
                                    ? const Color(0xFFF59E0B)
                                    : (isDark ? const Color(0xFF475569) : const Color(0xFF94A3B8)),
                              ),
                            ),
                          const SizedBox(width: 2),
                          Icon(
                            Icons.chevron_right_rounded,
                            size: 16,
                            color: isDark ? const Color(0xFF475569) : const Color(0xFF94A3B8),
                          ),
                        ],
                      ),
                    ],
                  ),

                  // Middle Block: Device Name & Subtitle
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        device.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          letterSpacing: -0.2,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        device.channel != null ? '${device.roomId} · ${device.channel!.toUpperCase()}' : device.roomId,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),

                  // Row 4: Status Indicator Dot & Scaled Switch
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Row(
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              margin: const EdgeInsets.only(right: 6),
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: !device.online
                                    ? (isDark ? const Color(0xFF475569) : const Color(0xFF94A3B8))
                                    : (isActive
                                        ? accentColor
                                        : (isDark ? const Color(0xFF475569) : const Color(0xFF94A3B8))),
                                boxShadow: isActive
                                    ? [
                                        BoxShadow(
                                          color: accentColor.withValues(alpha: 0.8),
                                          blurRadius: 5,
                                          spreadRadius: 1,
                                        )
                                      ]
                                    : null,
                              ),
                            ),
                            Expanded(
                              child: Text(
                                device.stateText,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
                                  color: isActive ? accentColor : theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      Semantics(
                        label: '${device.name} switch',
                        child: Transform.scale(
                          scale: 0.82,
                          alignment: Alignment.centerRight,
                          child: Switch(
                            value: isActive,
                            activeThumbColor: Colors.white,
                            activeTrackColor: accentColor,
                            inactiveThumbColor: isDark ? const Color(0xFF64748B) : const Color(0xFF94A3B8),
                            inactiveTrackColor: isDark ? const Color(0xFF1E2430) : const Color(0xFFE2E8F0),
                            onChanged: device.online
                                ? (val) {
                                    HapticFeedback.lightImpact();
                                    onToggle(val);
                                  }
                                : null,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  static Color whenActiveColor({
    required bool isActive,
    required bool online,
    required bool isDark,
    required Color accentColor,
    required Color surface,
  }) {
    if (!online) {
      return isDark ? const Color(0xFF10131A) : const Color(0xFFF3F4F6);
    }
    if (isActive) {
      return isDark
          ? Color.alphaBlend(accentColor.withValues(alpha: 0.12), const Color(0xFF141923))
          : Color.alphaBlend(accentColor.withValues(alpha: 0.08), Colors.white);
    }
    return surface;
  }
}
