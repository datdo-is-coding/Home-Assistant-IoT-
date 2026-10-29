import 'dart:ui';
import 'package:flutter/material.dart';

class ProgressiveBlurCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final bool isActive;
  final bool hasGlow;
  final bool hasLightRay;
  final Color? accentColor;
  final double borderRadius;
  final double blurAmount;

  const ProgressiveBlurCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.onTap,
    this.isActive = false,
    this.hasGlow = false,
    this.hasLightRay = true,
    this.accentColor,
    this.borderRadius = 22.0,
    this.blurAmount = 16.0,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primaryGlow = accentColor ?? const Color(0xFF10B981);
    final isGlowing = isActive || hasGlow;

    // Dark-Tech Obsidian Jade palette
    final glassColor = isDark
        ? (isGlowing
            ? Color.alphaBlend(primaryGlow.withValues(alpha: 0.14), const Color(0xE60D1510))
            : const Color(0xD90D1410)) // ~85% opacity obsidian jade
        : Colors.white.withValues(alpha: 0.90);

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(borderRadius),
        boxShadow: [
          if (isGlowing && isDark) ...[
            BoxShadow(
              color: primaryGlow.withValues(alpha: 0.25),
              blurRadius: 24,
              spreadRadius: 2,
              offset: const Offset(0, 4),
            ),
            BoxShadow(
              color: primaryGlow.withValues(alpha: 0.12),
              blurRadius: 40,
              spreadRadius: 6,
            ),
          ] else if (isDark) ...[
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.45),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
            BoxShadow(
              color: const Color(0xFF10B981).withValues(alpha: 0.04),
              blurRadius: 12,
              offset: const Offset(0, 2),
            ),
          ] else ...[
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 15,
              offset: const Offset(0, 4),
            ),
          ],
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: blurAmount, sigmaY: blurAmount),
          child: Container(
            decoration: BoxDecoration(
              color: glassColor,
              borderRadius: BorderRadius.circular(borderRadius),
              border: Border.all(
                color: isDark
                    ? (isGlowing
                        ? primaryGlow.withValues(alpha: 0.55)
                        : const Color(0xFF1E3527))
                    : const Color(0xFFE2E8F0),
                width: isGlowing ? 1.4 : 1.0,
              ),
            ),
            child: Stack(
              children: [
                // Light Ray Top Glint Reflection (Ray Edge)
                if (hasLightRay && isDark)
                  Positioned(
                    top: 0,
                    left: 20,
                    right: 20,
                    height: 1.5,
                    child: Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.centerLeft,
                          end: Alignment.centerRight,
                          colors: [
                            Colors.transparent,
                            primaryGlow.withValues(alpha: isGlowing ? 0.75 : 0.40),
                            const Color(0xFF6EE7B7).withValues(alpha: isGlowing ? 0.85 : 0.50),
                            primaryGlow.withValues(alpha: isGlowing ? 0.75 : 0.40),
                            Colors.transparent,
                          ],
                        ),
                      ),
                    ),
                  ),

                // Card Content with optional InkWell
                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: onTap,
                    borderRadius: BorderRadius.circular(borderRadius),
                    splashColor: primaryGlow.withValues(alpha: 0.15),
                    highlightColor: primaryGlow.withValues(alpha: 0.08),
                    child: Padding(
                      padding: padding,
                      child: child,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
