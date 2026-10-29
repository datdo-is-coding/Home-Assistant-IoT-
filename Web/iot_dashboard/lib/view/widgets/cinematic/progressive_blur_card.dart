import 'dart:ui';
import 'package:flutter/material.dart';

class ProgressiveBlurCard extends StatefulWidget {
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
    this.blurAmount = 18.0,
  });

  @override
  State<ProgressiveBlurCard> createState() => _ProgressiveBlurCardState();
}

class _ProgressiveBlurCardState extends State<ProgressiveBlurCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primaryGlow = widget.accentColor ?? const Color(0xFF10B981);
    final isGlowing = widget.isActive || widget.hasGlow;
    final isElevated = _isHovered && widget.onTap != null;

    // Multi-stop progressive gradient glass background
    final glassColorTop = isDark
        ? (isGlowing
            ? Color.alphaBlend(primaryGlow.withValues(alpha: 0.16), const Color(0xE60F1A14))
            : const Color(0xD90E1812))
        : Colors.white.withValues(alpha: 0.92);

    final glassColorBottom = isDark
        ? (isGlowing
            ? Color.alphaBlend(primaryGlow.withValues(alpha: 0.08), const Color(0xF208100C))
            : const Color(0xF2070E0A))
        : const Color(0xFFF8FAFC).withValues(alpha: 0.88);

    // Dynamic border color
    final borderColor = isDark
        ? (isGlowing
            ? primaryGlow.withValues(alpha: isElevated ? 0.70 : 0.50)
            : (isElevated ? const Color(0xFF2C4A36) : const Color(0xFF192C20)))
        : (isElevated ? const Color(0xFFCBD5E1) : const Color(0xFFE2E8F0));

    return MouseRegion(
      onEnter: (_) {
        if (mounted && widget.onTap != null) setState(() => _isHovered = true);
      },
      onExit: (_) {
        if (mounted && widget.onTap != null) setState(() => _isHovered = false);
      },
      cursor: widget.onTap != null ? SystemMouseCursors.click : MouseCursor.defer,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        transform: Matrix4.translationValues(0, isElevated ? -3.5 : 0.0, 0),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(widget.borderRadius),
          boxShadow: [
            if (isGlowing && isDark) ...[
              BoxShadow(
                color: primaryGlow.withValues(alpha: isElevated ? 0.35 : 0.22),
                blurRadius: isElevated ? 32 : 24,
                spreadRadius: isElevated ? 3 : 1,
                offset: Offset(0, isElevated ? 8 : 4),
              ),
              BoxShadow(
                color: primaryGlow.withValues(alpha: 0.12),
                blurRadius: 48,
                spreadRadius: 8,
              ),
            ] else if (isDark) ...[
              BoxShadow(
                color: Colors.black.withValues(alpha: isElevated ? 0.60 : 0.42),
                blurRadius: isElevated ? 24 : 16,
                offset: Offset(0, isElevated ? 10 : 6),
              ),
              if (isElevated)
                BoxShadow(
                  color: const Color(0xFF10B981).withValues(alpha: 0.08),
                  blurRadius: 16,
                  offset: const Offset(0, 2),
                ),
            ] else ...[
              BoxShadow(
                color: Colors.black.withValues(alpha: isElevated ? 0.09 : 0.04),
                blurRadius: isElevated ? 20 : 12,
                offset: Offset(0, isElevated ? 6 : 3),
              ),
            ],
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(widget.borderRadius),
          child: BackdropFilter(
            filter: ImageFilter.blur(
              sigmaX: widget.blurAmount,
              sigmaY: widget.blurAmount,
            ),
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [glassColorTop, glassColorBottom],
                ),
                borderRadius: BorderRadius.circular(widget.borderRadius),
                border: Border.all(
                  color: borderColor,
                  width: isGlowing ? 1.4 : 1.0,
                ),
              ),
              child: Stack(
                children: [
                  // 1. Ray Specular Edge Highlight (Razor Light Line on Top)
                  if (widget.hasLightRay && isDark)
                    Positioned(
                      top: 0,
                      left: 18,
                      right: 18,
                      height: 1.5,
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                            colors: [
                              Colors.transparent,
                              primaryGlow.withValues(alpha: isGlowing || isElevated ? 0.85 : 0.45),
                              const Color(0xFF6EE7B7).withValues(alpha: isGlowing || isElevated ? 0.95 : 0.60),
                              primaryGlow.withValues(alpha: isGlowing || isElevated ? 0.85 : 0.45),
                              Colors.transparent,
                            ],
                            stops: const [0.0, 0.25, 0.50, 0.75, 1.0],
                          ),
                        ),
                      ),
                    ),

                  // 2. Card Content with InkWell for Ripple
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: widget.onTap,
                      borderRadius: BorderRadius.circular(widget.borderRadius),
                      splashColor: primaryGlow.withValues(alpha: 0.16),
                      highlightColor: primaryGlow.withValues(alpha: 0.08),
                      child: Padding(
                        padding: widget.padding,
                        child: widget.child,
                      ),
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
