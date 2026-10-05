import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

class StatusBanner extends StatelessWidget {
  final List<String> statuses;

  const StatusBanner({super.key, required this.statuses});

  @override
  Widget build(BuildContext context) {
    if (statuses.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: statuses.map((status) {
          final isWarning = status.contains('ngoại tuyến');
          final bg = isWarning
              ? colors.offline.withValues(alpha: isDark ? 0.16 : 0.10)
              : colors.lightWash;
          final fg = isWarning ? colors.offline : colors.lightAccent;

          return Container(
            margin: const EdgeInsets.only(right: 8),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(100),
              border: Border.all(color: fg.withValues(alpha: 0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isWarning ? Icons.info_outline_rounded : Icons.lightbulb_rounded,
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
          );
        }).toList(),
      ),
    );
  }
}
