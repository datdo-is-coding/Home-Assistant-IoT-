import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/model/device_model.dart';
import '../cinematic/progressive_blur_card.dart';

class ParityDeviceCard extends StatelessWidget {
  final DeviceModel device;
  final VoidCallback onTap;
  final ValueChanged<bool> onToggle;
  final VoidCallback? onFavoriteToggle;

  const ParityDeviceCard({
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
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    // Xanh lá / Emerald / Mint accents
    final Color accentColor = switch (device.deviceType?.toLowerCase()) {
      'light' || 'lamp' => colors.lightAccent, // #10B981
      'fan' => colors.fanAccent,             // #2DD4BF
      'socket' || 'outlet' => colors.socketAccent, // #34D399
      'airconditioner' || 'ac' => colors.climateAccent, // #6EE7B7
      _ => const Color(0xFF10B981),
    };

    final bool isActive = device.isOn && device.online;

    return ProgressiveBlurCard(
      isActive: isActive,
      accentColor: accentColor,
      borderRadius: 22,
      blurAmount: 18,
      padding: const EdgeInsets.all(16),
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Top Row: Icon button with wash background & Favorite Star
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              GestureDetector(
                onTap: device.online ? () => onToggle(!device.isOn) : null,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 240),
                  curve: Curves.easeOutCubic,
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: isActive
                        ? accentColor.withValues(alpha: isDark ? 0.28 : 0.16)
                        : (isDark
                            ? const Color(0xFF132219)
                            : const Color(0xFFF1F5F9)),
                    borderRadius: BorderRadius.circular(AppTheme.iconRadius),
                    border: Border.all(
                      color: isActive
                          ? accentColor.withValues(alpha: 0.65)
                          : (isDark ? const Color(0xFF1C3426) : colors.cardBorder),
                      width: 1,
                    ),
                    boxShadow: isActive && isDark
                        ? [
                            BoxShadow(
                              color: accentColor.withValues(alpha: 0.40),
                              blurRadius: 14,
                              spreadRadius: 1,
                              offset: const Offset(0, 2),
                            ),
                          ]
                        : null,
                  ),
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      // Subtile ray glint on top of active icon
                      if (isActive && isDark)
                        Positioned(
                          top: 0,
                          left: 6,
                          right: 6,
                          height: 1.5,
                          child: Container(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  Colors.transparent,
                                  accentColor.withValues(alpha: 0.8),
                                  Colors.transparent,
                                ],
                              ),
                            ),
                          ),
                        ),
                      Icon(
                        device.iconData,
                        size: 21,
                        color: isActive
                            ? accentColor
                            : (isDark
                                ? const Color(0xFF8BAA97)
                                : const Color(0xFF64748B)),
                      ),
                    ],
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
                      constraints: const BoxConstraints(
                          minWidth: 26, minHeight: 26),
                      onPressed: onFavoriteToggle,
                      icon: Icon(
                        device.isFavorite
                            ? Icons.star_rounded
                            : Icons.star_outline_rounded,
                        size: 18,
                        color: device.isFavorite
                            ? const Color(0xFFF59E0B)
                            : (isDark
                                ? const Color(0xFF4A6855)
                                : const Color(0xFF94A3B8)),
                      ),
                    ),
                  const SizedBox(width: 2),
                  Icon(
                    Icons.chevron_right_rounded,
                    size: 16,
                    color: isDark
                        ? const Color(0xFF4A6855)
                        : const Color(0xFF94A3B8),
                  ),
                ],
              ),
            ],
          ),

          const SizedBox(height: 10),

          // Middle: Name, Room/Channel, and Voltage/Current
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                device.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                  color: isDark ? const Color(0xFFF0FDF4) : theme.colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                device.channelKey != null
                    ? '${device.roomName} · ${device.channelKey!.toUpperCase()}'
                    : device.roomName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                  color: isDark ? const Color(0xFF8BAA97) : theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                device.currentText,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? const Color(0xFF6B8B77) : theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),

          const SizedBox(height: 10),

          // Bottom Row: Status Indicator Dot + State Text & Switch
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Row(
                  children: [
                    Container(
                      width: 14,
                      height: 14,
                      margin: const EdgeInsets.only(right: 6),
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          if (isActive)
                            Container(
                              width: 14,
                              height: 14,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: accentColor.withValues(alpha: 0.25),
                              ),
                            ),
                          Container(
                            width: 7,
                            height: 7,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: !device.online
                                  ? (isDark
                                      ? const Color(0xFF4A6855)
                                      : const Color(0xFF94A3B8))
                                  : (isActive
                                      ? accentColor
                                      : (isDark
                                          ? const Color(0xFF4A6855)
                                          : const Color(0xFF94A3B8))),
                              boxShadow: isActive
                                  ? [
                                      BoxShadow(
                                        color: accentColor.withValues(alpha: 0.95),
                                        blurRadius: 8,
                                        spreadRadius: 1.5,
                                      )
                                    ]
                                  : null,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      child: Text(
                        device.stateText,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: isActive
                              ? FontWeight.w700
                              : FontWeight.w500,
                          color: isActive
                              ? accentColor
                              : (isDark ? const Color(0xFF8BAA97) : theme.colorScheme.onSurfaceVariant),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Transform.scale(
                scale: 0.82,
                alignment: Alignment.centerRight,
                child: Switch(
                  value: isActive,
                  activeThumbColor: Colors.white,
                  activeTrackColor: accentColor,
                  inactiveThumbColor: isDark
                      ? const Color(0xFF4A6855)
                      : const Color(0xFF94A3B8),
                  inactiveTrackColor: isDark
                      ? const Color(0xFF0F1C15)
                      : const Color(0xFFE2E8F0),
                  onChanged: device.online ? onToggle : null,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
