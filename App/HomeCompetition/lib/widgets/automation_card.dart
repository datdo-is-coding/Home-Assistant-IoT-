import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/theme/app_theme.dart';
import '../models/automation.dart';
import 'soft_3d_decorations.dart';

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
    final colors = theme.extension<AppColors>() ??
        (isDark ? AppColors.dark : AppColors.light);

    return SoftBounce(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOutCubic,
        decoration: Soft3DDecorations.card(
          isDark: isDark,
          isActive: automation.enabled,
          accentColor: colors.fanAccent,
          radius: AppTheme.cardRadius,
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              // 3D Soft Glowing Icon Well
              Container(
                width: 44,
                height: 44,
                decoration: Soft3DDecorations.iconWell(
                  isDark: isDark,
                  isActive: automation.enabled,
                  accentColor: colors.fanAccent,
                  radius: 14,
                ),
                child: Icon(
                  automation.icon,
                  color: automation.enabled
                      ? colors.fanAccent
                      : (isDark
                          ? const Color(0xFF94A3B8)
                          : const Color(0xFF64748B)),
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
                      style: const TextStyle(
                        fontSize: 15.5,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -0.3,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${automation.triggerText} · ${automation.deviceCount} thiết bị',
                      style: TextStyle(
                        fontSize: 12,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              Transform.scale(
                scale: 0.85,
                child: Switch(
                  value: automation.enabled,
                  activeTrackColor: colors.fanAccent,
                  activeThumbColor: Colors.white,
                  inactiveThumbColor: isDark
                      ? const Color(0xFF64748B)
                      : const Color(0xFF94A3B8),
                  inactiveTrackColor: isDark
                      ? const Color(0xFF1E2430)
                      : const Color(0xFFE2E8F0),
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
    );
  }
}
