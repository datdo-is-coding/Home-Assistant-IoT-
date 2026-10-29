import 'dart:ui';
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

class ParityStatusBanner extends StatelessWidget {
  final List<String> statuses;

  const ParityStatusBanner({super.key, required this.statuses});

  @override
  Widget build(BuildContext context) {
    if (statuses.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      child: Row(
        children: statuses.map((status) {
          final isWarning = status.contains('ngoại tuyến') ||
              status.contains('mất kết nối') ||
              status.contains('Cảnh báo');
          final isBolt = status.contains('W') || status.contains('kWh');

          final bg = isWarning
              ? colors.offline.withValues(alpha: isDark ? 0.18 : 0.10)
              : isBolt
                  ? colors.fanWash
                  : colors.lightWash;

          final fg = isWarning
              ? colors.offline
              : isBolt
                  ? colors.fanAccent
                  : colors.lightAccent;

          final IconData icon = isWarning
              ? Icons.info_outline_rounded
              : isBolt
                  ? Icons.bolt_rounded
                  : Icons.lightbulb_rounded;

          return Container(
            margin: const EdgeInsets.only(right: 8),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(100),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.circular(100),
                    border: Border.all(
                      color: fg.withValues(alpha: isDark ? 0.4 : 0.3),
                      width: 1,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        icon,
                        size: 15,
                        color: fg,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        status,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: fg,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}
