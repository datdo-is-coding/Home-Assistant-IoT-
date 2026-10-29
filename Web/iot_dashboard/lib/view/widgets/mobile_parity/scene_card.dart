import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/model/scene_model.dart';
import '../cinematic/progressive_blur_card.dart';

class ParitySceneCard extends StatelessWidget {
  final SceneModel scene;
  final VoidCallback onActivate;

  const ParitySceneCard({
    super.key,
    required this.scene,
    required this.onActivate,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return ProgressiveBlurCard(
      blurAmount: 16,
      accentColor: scene.isActive ? scene.color : null,
      hasLightRay: scene.isActive,
      hasGlow: scene.isActive,
      padding: EdgeInsets.zero,
      onTap: onActivate,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: scene.color.withValues(alpha: isDark ? 0.22 : 0.12),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: scene.color.withValues(alpha: 0.35),
                      width: 1,
                    ),
                  ),
                  child: Icon(scene.icon, color: scene.color, size: 22),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0x990A140F)
                        : const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: isDark ? colors.cardBorder : const Color(0xFFE2E8F0),
                    ),
                  ),
                  child: Text(
                    '${scene.actions.length} hành động',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: isDark ? const Color(0xFF94A3B8) : theme.colorScheme.onSurfaceVariant,
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
                letterSpacing: -0.2,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              scene.description,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 12,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
