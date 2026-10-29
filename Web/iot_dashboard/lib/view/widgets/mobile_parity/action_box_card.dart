import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/model/action_box_model.dart';

class ParityActionBoxCard extends StatelessWidget {
  final ActionBoxModel actionBox;
  final VoidCallback onTap;
  final Function(String channelKey, bool newState)? onToggleChannel;

  const ParityActionBoxCard({
    super.key,
    required this.actionBox,
    required this.onTap,
    this.onToggleChannel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return Container(
      decoration: BoxDecoration(
        color: colors.cardSurface,
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        border: Border.all(color: colors.cardBorder),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.03),
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
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Top Row: Board Icon, Title, Room & Online badge
                  Row(
                    children: [
                      Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(
                          color: isDark
                              ? const Color(0xFF1E2532)
                              : const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(
                          actionBox.isSubBox
                              ? Icons.record_voice_over_rounded
                              : Icons.developer_board_rounded,
                          size: 22,
                          color: theme.colorScheme.primary,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              actionBox.name,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                                letterSpacing: -0.2,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              actionBox.isSubBox
                                  ? '${actionBox.room} · SubBox KWS Voice'
                                  : '${actionBox.room} · ${actionBox.channels.length} kênh rơ-le (BL0942)',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: actionBox.online
                              ? colors.online.withValues(alpha: 0.12)
                              : colors.offline.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: actionBox.online
                                    ? colors.online
                                    : colors.offline,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              actionBox.online ? 'Trực tuyến' : 'Ngoại tuyến',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: actionBox.online
                                    ? colors.online
                                    : colors.offline,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 16),

                  // Middle Row: Hardware Specs & BL0942 Power Metering
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: isDark
                          ? const Color(0xFF141923)
                          : const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: colors.cardBorder),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _buildMetricCol(
                          context,
                          label: 'Công suất',
                          value: '${actionBox.totalPower.toStringAsFixed(1)} W',
                          color: colors.lightAccent,
                        ),
                        _buildMetricCol(
                          context,
                          label: 'Điện năng',
                          value:
                              '${actionBox.totalEnergyKwh.toStringAsFixed(2)} kWh',
                          color: colors.fanAccent,
                        ),
                        _buildMetricCol(
                          context,
                          label: 'Tín hiệu',
                          value: '${actionBox.signalStrength} dBm',
                          color: colors.online,
                        ),
                        _buildMetricCol(
                          context,
                          label: 'Firmware',
                          value: actionBox.boardModel,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ],
                    ),
                  ),

                  if (actionBox.channels.isNotEmpty) ...[
                    const SizedBox(height: 14),
                    Text(
                      'Kênh điều khiển Relay & BL0942:',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 8),
                    // Channel Relay Chips
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: actionBox.channels.map((ch) {
                        final isChActive = ch.state && actionBox.online;
                        return InkWell(
                          onTap: (actionBox.online && onToggleChannel != null)
                              ? () => onToggleChannel!(ch.channelKey, !ch.state)
                              : null,
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
                            decoration: BoxDecoration(
                              color: isChActive
                                  ? ch.accentColor.withValues(
                                      alpha: isDark ? 0.2 : 0.12)
                                  : (isDark
                                      ? const Color(0xFF1A212D)
                                      : const Color(0xFFF1F5F9)),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: isChActive
                                    ? ch.accentColor.withValues(alpha: 0.5)
                                    : colors.cardBorder,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  ch.iconData,
                                  size: 16,
                                  color: isChActive
                                      ? ch.accentColor
                                      : (isDark
                                          ? const Color(0xFF94A3B8)
                                          : const Color(0xFF64748B)),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  '${ch.name} (${ch.channelKey.toUpperCase()})',
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: isChActive
                                        ? FontWeight.w700
                                        : FontWeight.w500,
                                    color: isChActive
                                        ? ch.accentColor
                                        : theme.colorScheme.onSurface,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Container(
                                  width: 6,
                                  height: 6,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: isChActive
                                        ? ch.accentColor
                                        : Colors.grey,
                                  ),
                                ),
                              ],
                            ),
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

  Widget _buildMetricCol(
    BuildContext context, {
    required String label,
    required String value,
    required Color color,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 11,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
      ],
    );
  }
}
