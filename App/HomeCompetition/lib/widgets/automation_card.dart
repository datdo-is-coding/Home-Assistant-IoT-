import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/theme/app_theme.dart';
import '../models/automation.dart';

class AutomationCard extends StatelessWidget {
  final Automation automation;
  final ValueChanged<bool> onToggle;
  final VoidCallback? onTap;

  const AutomationCard({
    super.key,
    required this.automation,
    required this.onToggle,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

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
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: automation.enabled
                          ? colors.fanWash
                          : (isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9)),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      automation.icon,
                      color: automation.enabled
                          ? colors.fanAccent
                          : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B)),
                      size: 22,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          automation.name,
                          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          '${automation.triggerText} · ${automation.deviceCount} thiết bị',
                          style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                  Transform.scale(
                    scale: 0.85,
                    child: Switch(
                      value: automation.enabled,
                      onChanged: (val) {
                        HapticFeedback.lightImpact();
                        onToggle(val);
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
