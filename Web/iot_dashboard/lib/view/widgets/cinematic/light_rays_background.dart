import 'dart:math' as math;
import 'package:flutter/material.dart';

class LightRaysBackground extends StatelessWidget {
  final Widget child;

  const LightRaysBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (!isDark) {
      return Container(
        color: const Color(0xFFF6FBF8),
        child: child,
      );
    }

    return Stack(
      children: [
        // 1. Deep Obsidian Green Base Background
        Positioned.fill(
          child: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0xFF060A08), // Obsidian Emerald
                  Color(0xFF040705), // Ultra Dark Noir
                  Color(0xFF020403), // Deepest Void
                ],
              ),
            ),
          ),
        ),

        // 2. Volumetric Light Rays (Custom Painter)
        Positioned.fill(
          child: RepaintBoundary(
            child: CustomPaint(
              painter: _VolumetricLightRaysPainter(),
            ),
          ),
        ),

        // 3. Ambient Emerald Light Ray Orbs (Soft Radial Glows)
        Positioned(
          top: -120,
          left: 120,
          child: IgnorePointer(
            child: Container(
              width: 550,
              height: 550,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFF10B981).withValues(alpha: 0.16),
                    const Color(0xFF059669).withValues(alpha: 0.08),
                    const Color(0xFF047857).withValues(alpha: 0.02),
                    Colors.transparent,
                  ],
                  stops: const [0.0, 0.35, 0.65, 1.0],
                ),
              ),
            ),
          ),
        ),

        Positioned(
          top: -80,
          right: 80,
          child: IgnorePointer(
            child: Container(
              width: 480,
              height: 480,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFF34D399).withValues(alpha: 0.13),
                    const Color(0xFF065F46).withValues(alpha: 0.06),
                    Colors.transparent,
                  ],
                  stops: const [0.0, 0.45, 1.0],
                ),
              ),
            ),
          ),
        ),

        // 4. Subtle Progressive Mist Vignette (Bottom Depth)
        Positioned.fill(
          child: IgnorePointer(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Colors.transparent,
                    const Color(0xFF020403).withValues(alpha: 0.45),
                    const Color(0xFF020403).withValues(alpha: 0.85),
                  ],
                  stops: const [0.0, 0.6, 0.85, 1.0],
                ),
              ),
            ),
          ),
        ),

        // 5. Main Application Tree
        Positioned.fill(
          child: child,
        ),
      ],
    );
  }
}

class _VolumetricLightRaysPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final rayOrigin1 = Offset(size.width * 0.22, -60);
    final rayOrigin2 = Offset(size.width * 0.72, -80);

    // Vẽ chùm tia sáng phát từ emitter 1 (Bên trái)
    _drawRayShaft(
      canvas,
      origin: rayOrigin1,
      targetLeft: size.width * -0.15,
      targetRight: size.width * 0.18,
      length: size.height * 1.1,
      color: const Color(0xFF10B981).withValues(alpha: 0.11),
    );

    _drawRayShaft(
      canvas,
      origin: rayOrigin1,
      targetLeft: size.width * 0.05,
      targetRight: size.width * 0.42,
      length: size.height * 1.15,
      color: const Color(0xFF34D399).withValues(alpha: 0.13),
    );

    _drawRayShaft(
      canvas,
      origin: rayOrigin1,
      targetLeft: size.width * 0.30,
      targetRight: size.width * 0.65,
      length: size.height * 1.05,
      color: const Color(0xFF059669).withValues(alpha: 0.09),
    );

    // Vẽ chùm tia sáng phát từ emitter 2 (Bên phải)
    _drawRayShaft(
      canvas,
      origin: rayOrigin2,
      targetLeft: size.width * 0.45,
      targetRight: size.width * 0.78,
      length: size.height * 1.1,
      color: const Color(0xFF2DD4BF).withValues(alpha: 0.10),
    );

    _drawRayShaft(
      canvas,
      origin: rayOrigin2,
      targetLeft: size.width * 0.68,
      targetRight: size.width * 1.15,
      length: size.height * 1.2,
      color: const Color(0xFF10B981).withValues(alpha: 0.12),
    );
  }

  void _drawRayShaft(
    Canvas canvas, {
    required Offset origin,
    required double targetLeft,
    required double targetRight,
    required double length,
    required Color color,
  }) {
    final path = Path()
      ..moveTo(origin.dx - 15, origin.dy)
      ..lineTo(origin.dx + 15, origin.dy)
      ..lineTo(targetRight, length)
      ..lineTo(targetLeft, length)
      ..close();

    final paint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          color,
          color.withValues(alpha: color.a * 0.65),
          color.withValues(alpha: color.a * 0.25),
          Colors.transparent,
        ],
        stops: const [0.0, 0.25, 0.65, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, math.max(targetRight, 1000), length))
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 28);

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
