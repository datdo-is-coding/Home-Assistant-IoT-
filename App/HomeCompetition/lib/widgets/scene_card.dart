import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/theme/app_theme.dart';
import '../models/scene.dart';
import 'soft_3d_decorations.dart';

class SceneCard extends StatelessWidget {
  final Scene scene;
  final VoidCallback onActivate;

  const SceneCard({
    super.key,
    required this.scene,
    required this.onActivate,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ??
        (isDark ? AppColors.dark : AppColors.light);

    return SoftBounce(
      onTap: () {
        HapticFeedback.mediumImpact();
        onActivate();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        decoration: Soft3DDecorations.card(
          isDark: isDark,
          radius: AppTheme.cardRadius,
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // 3D Soft Glowing Icon Well
                  Container(
                    width: 42,
                    height: 42,
                    decoration: Soft3DDecorations.iconWell(
                      isDark: isDark,
                      isActive: true,
                      accentColor: colors.lightAccent,
                      radius: 14,
                    ),
                    child: Icon(
                      scene.icon,
                      color: colors.lightAccent,
                      size: 21,
                    ),
                  ),
                  Flexible(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      child: Text(
                        '${scene.deviceCount} thiết bị',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                scene.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.3,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
