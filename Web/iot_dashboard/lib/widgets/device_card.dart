import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/theme/app_theme.dart';
import '../models/device.dart';
import 'connectivity_dot.dart';
import 'soft_3d_decorations.dart';

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
    final colors = theme.extension<AppColors>() ?? AppColors.light;
    final accent = switch (device.type) {
      DeviceType.light => colors.lightAccent,
      DeviceType.fan => colors.fanAccent,
      DeviceType.airConditioner => colors.climateAccent,
      _ => colors.socketAccent,
    };
    final active = device.isOn && device.online;
    final pending = device.metadata['command_pending'] == true;
    final syncing = pending || device.metadata['cloud_state'] == true;
    final power = device.powerWatts;
    final caption = !device.online
        ? ''
        : syncing
            ? device.stateText
            : active && power != null && power.isFinite && power > 0
                ? '${power.toStringAsFixed(1)} W'
                : '';

    return SoftBounce(
      onTap: onTap,
      onLongPress: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        decoration: Soft3DDecorations.card(
          isDark: isDark,
          isActive: active,
          accentColor: accent,
          radius: AppTheme.cardRadius,
        ),
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(children: [
              IconButton(
                tooltip:
                    device.isOn ? 'Tắt ${device.name}' : 'Bật ${device.name}',
                onPressed: device.online
                    ? () {
                        HapticFeedback.lightImpact();
                        onToggle(!device.isOn);
                      }
                    : null,
                icon: Container(
                  width: 34,
                  height: 34,
                  decoration: Soft3DDecorations.iconWell(
                    isDark: isDark,
                    isActive: active,
                    accentColor: accent,
                  ),
                  child: Icon(device.iconData,
                      size: 20,
                      color:
                          active ? accent : theme.colorScheme.onSurfaceVariant),
                ),
                padding: EdgeInsets.zero,
              ),
              const Spacer(),
              if (onFavoriteToggle != null)
                IconButton(
                  tooltip: device.isFavorite ? 'Bỏ yêu thích' : 'Yêu thích',
                  onPressed: onFavoriteToggle,
                  icon: Icon(
                      device.isFavorite
                          ? Icons.star_rounded
                          : Icons.star_outline_rounded,
                      size: 18,
                      color: device.isFavorite
                          ? colors.lightAccent
                          : theme.colorScheme.onSurfaceVariant),
                ),
              ConnectivityDot(online: device.online),
            ]),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(device.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600, height: 1.2)),
              const SizedBox(height: 4),
              Text(device.roomId,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 11, color: theme.colorScheme.onSurfaceVariant)),
            ]),
            Row(children: [
              Expanded(
                  child: Text(caption,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 11,
                          color: theme.colorScheme.onSurfaceVariant))),
              Semantics(
                label: '${device.name}, ${device.stateText}',
                child: Switch.adaptive(
                  value: device.isOn,
                  activeTrackColor: accent,
                  onChanged: device.online ? onToggle : null,
                ),
              ),
            ]),
          ],
        ),
      ),
    );
  }
}
