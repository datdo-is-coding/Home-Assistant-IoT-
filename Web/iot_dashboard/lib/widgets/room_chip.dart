import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'soft_3d_decorations.dart';

class RoomChip extends StatelessWidget {
  final String label;
  final int count;
  final bool isSelected;
  final VoidCallback onSelected;

  const RoomChip({
    super.key,
    required this.label,
    required this.count,
    required this.isSelected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final Color textColor = isSelected
        ? (isDark ? const Color(0xFF0F172A) : Colors.white)
        : (isDark ? const Color(0xFFE2E8F0) : const Color(0xFF334155));

    final Color countBg = isSelected
        ? (isDark ? const Color(0xFFE2E8F0) : const Color(0xFF334155))
        : (isDark ? const Color(0xFF283142) : const Color(0xFFE2E8F0));

    final Color countText = isSelected
        ? (isDark ? const Color(0xFF0F172A) : Colors.white)
        : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B));

    return SoftBounce(
      onTap: () {
        HapticFeedback.selectionClick();
        onSelected();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: Soft3DDecorations.pill(
          isDark: isDark,
          isSelected: isSelected,
          radius: 100,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                letterSpacing: -0.2,
                color: textColor,
              ),
            ),
            const SizedBox(width: 7),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
              decoration: BoxDecoration(
                color: countBg,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: countText,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
