import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../models/action_box.dart';
import 'connectivity_dot.dart';
import 'soft_3d_decorations.dart';

class ActionBoxCard extends StatelessWidget {
  final ActionBox actionBox;
  final VoidCallback onTap;

  const ActionBoxCard(
      {super.key, required this.actionBox, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? AppColors.light;
    return SoftBounce(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration:
            Soft3DDecorations.card(isDark: isDark, radius: AppTheme.cardRadius),
        child: Column(children: [
          Row(children: [
            Icon(
                actionBox.isSubBox
                    ? Icons.hub_rounded
                    : Icons.developer_board_rounded,
                size: 22,
                color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: 12),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(actionBox.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 3),
                  Text(actionBox.roomId,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant)),
                ])),
            const SizedBox(width: 12),
            ConnectivityDot(online: actionBox.online),
            const SizedBox(width: 8),
            Icon(Icons.chevron_right_rounded,
                size: 18, color: theme.colorScheme.onSurfaceVariant),
          ]),
          if (actionBox.channels.isNotEmpty) ...[
            const SizedBox(height: 14),
            Row(
                children: actionBox.channels.map((channel) {
              final active = actionBox.online && channel.isOn;
              return Expanded(
                  child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 3),
                child: Row(children: [
                  Icon(Icons.power_settings_new_rounded,
                      size: 13,
                      color: active
                          ? colors.lightAccent
                          : theme.colorScheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Expanded(
                      child: Text(channel.configured ? channel.name : 'Trống',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontSize: 11,
                              color: theme.colorScheme.onSurfaceVariant))),
                ]),
              ));
            }).toList()),
          ],
        ]),
      ),
    );
  }
}
