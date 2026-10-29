import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../cinematic/progressive_blur_card.dart';

class ParityEnergyOverviewCard extends StatelessWidget {
  final double totalPower;
  final double totalEnergy;
  final int measuredCount;
  final int totalCount;
  final VoidCallback? onTap;

  const ParityEnergyOverviewCard({
    super.key,
    required this.totalPower,
    required this.totalEnergy,
    required this.measuredCount,
    required this.totalCount,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return ProgressiveBlurCard(
      blurAmount: 22,
      accentColor: colors.lightAccent,
      hasLightRay: true,
      hasGlow: totalPower > 0,
      padding: EdgeInsets.zero,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: colors.fanWash,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: colors.fanAccent.withValues(alpha: 0.35),
                          width: 1,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: colors.fanAccent.withValues(alpha: isDark ? 0.25 : 0.1),
                            blurRadius: 12,
                          ),
                        ],
                      ),
                      child: Icon(
                        Icons.bolt_rounded,
                        color: colors.fanAccent,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Công suất đang đo',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.2,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'Cảm biến năng lượng BL0942',
                          style: TextStyle(
                            fontSize: 11,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                Icon(
                  Icons.chevron_right_rounded,
                  color: theme.colorScheme.onSurfaceVariant,
                  size: 22,
                ),
              ],
            ),
            const SizedBox(height: 18),

            // Power readout with Holographic Gradient Text
            ShaderMask(
              shaderCallback: (bounds) {
                return LinearGradient(
                  colors: isDark
                      ? [
                          const Color(0xFFFFFFFF),
                          const Color(0xFF6EE7B7),
                          const Color(0xFF34D399),
                        ]
                      : [
                          const Color(0xFF0F172A),
                          const Color(0xFF059669),
                        ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ).createShader(bounds);
              },
              child: Text(
                '${totalPower.toStringAsFixed(1)} W',
                style: const TextStyle(
                  fontSize: 36,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1.0,
                  color: Colors.white,
                ),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '$measuredCount/$totalCount kênh tải đang hoạt động có số đo',
              style: TextStyle(
                fontSize: 12,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            Divider(color: colors.cardBorder, height: 1),
            const SizedBox(height: 14),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Điện năng tích lũy',
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${totalEnergy.toStringAsFixed(3)} kWh',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: colors.fanAccent,
                      ),
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: colors.lightWash,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: colors.lightAccent.withValues(alpha: 0.35),
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
                            Container(
                              width: 14,
                              height: 14,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: colors.lightAccent.withValues(alpha: 0.25),
                              ),
                            ),
                            Container(
                              width: 6,
                              height: 6,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: colors.lightAccent,
                                boxShadow: [
                                  BoxShadow(
                                    color: colors.lightAccent.withValues(alpha: 0.8),
                                    blurRadius: 6,
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        'Thời gian thực',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: colors.lightAccent,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
