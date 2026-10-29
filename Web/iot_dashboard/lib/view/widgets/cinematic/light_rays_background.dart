import 'dart:math' as math;
import 'package:flutter/material.dart';

class LightRaysBackground extends StatefulWidget {
  final Widget child;

  const LightRaysBackground({super.key, required this.child});

  @override
  State<LightRaysBackground> createState() => _LightRaysBackgroundState();
}

class _LightRaysBackgroundState extends State<LightRaysBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 12),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (!isDark) {
      return Container(
        color: const Color(0xFFF6FBF8),
        child: widget.child,
      );
    }

    return Stack(
      children: [
        // 1. Deep Obsidian Green Base Background with Radial Depth
        Positioned.fill(
          child: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0xFF070D0A), // Obsidian Emerald
                  Color(0xFF040806), // Ultra Dark Noir
                  Color(0xFF020403), // Deepest Void
                ],
                stops: [0.0, 0.45, 1.0],
              ),
            ),
          ),
        ),

        // 2. Animated Volumetric Light Rays (Isolated RepaintBoundary)
        Positioned.fill(
          child: RepaintBoundary(
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, _) {
                return CustomPaint(
                  painter: _CinematicLightRaysPainter(progress: _controller.value),
                );
              },
            ),
          ),
        ),

        // 3. Ethereal Ambient Emitter Orbs (Top Left & Top Right)
        Positioned(
          top: -140,
          left: 100,
          child: IgnorePointer(
            child: Container(
              width: 600,
              height: 600,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFF10B981).withValues(alpha: 0.18),
                    const Color(0xFF059669).withValues(alpha: 0.09),
                    const Color(0xFF047857).withValues(alpha: 0.03),
                    Colors.transparent,
                  ],
                  stops: const [0.0, 0.32, 0.62, 1.0],
                ),
              ),
            ),
          ),
        ),

        Positioned(
          top: -90,
          right: 60,
          child: IgnorePointer(
            child: Container(
              width: 520,
              height: 520,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFF34D399).withValues(alpha: 0.15),
                    const Color(0xFF065F46).withValues(alpha: 0.07),
                    Colors.transparent,
                  ],
                  stops: const [0.0, 0.40, 1.0],
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
                    const Color(0xFF020403).withValues(alpha: 0.35),
                    const Color(0xFF020403).withValues(alpha: 0.85),
                  ],
                  stops: const [0.0, 0.55, 0.85, 1.0],
                ),
              ),
            ),
          ),
        ),

        // 5. Main Application Tree
        Positioned.fill(
          child: widget.child,
        ),
      ],
    );
  }
}

class _CinematicLightRaysPainter extends CustomPainter {
  final double progress; // 0.0 -> 1.0

  _CinematicLightRaysPainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    // Subtle sine-wave oscillation to simulate breathing ethereal light drift
    final driftX1 = math.sin(progress * 2 * math.pi) * 32.0;
    final driftX2 = math.cos(progress * 2 * math.pi) * 28.0;
    final breatheAlpha = 0.88 + 0.24 * math.sin(progress * 2 * math.pi);

    final rayOrigin1 = Offset(size.width * 0.20 + driftX1 * 0.4, -60);
    final rayOrigin2 = Offset(size.width * 0.74 + driftX2 * 0.4, -80);

    // Emitter 1 - Emerald & Mint Beams (Trái sang)
    _drawRayShaft(
      canvas,
      origin: rayOrigin1,
      targetLeft: size.width * -0.18 + driftX1,
      targetRight: size.width * 0.16 + driftX1,
      length: size.height * 1.15,
      color: const Color(0xFF10B981).withValues(alpha: (0.12 * breatheAlpha).clamp(0.0, 1.0)),
      blurRadius: 32,
    );

    _drawRayShaft(
      canvas,
      origin: rayOrigin1,
      targetLeft: size.width * 0.04 + driftX1 * 0.8,
      targetRight: size.width * 0.40 + driftX1 * 0.8,
      length: size.height * 1.20,
      color: const Color(0xFF34D399).withValues(alpha: (0.14 * breatheAlpha).clamp(0.0, 1.0)),
      blurRadius: 36,
    );

    _drawRayShaft(
      canvas,
      origin: rayOrigin1,
      targetLeft: size.width * 0.28 + driftX1 * 0.6,
      targetRight: size.width * 0.62 + driftX1 * 0.6,
      length: size.height * 1.10,
      color: const Color(0xFF059669).withValues(alpha: (0.10 * breatheAlpha).clamp(0.0, 1.0)),
      blurRadius: 30,
    );

    // Emitter 2 - Cyan Mint & Neon Emerald Beams (Phải sang)
    _drawRayShaft(
      canvas,
      origin: rayOrigin2,
      targetLeft: size.width * 0.42 + driftX2 * 0.7,
      targetRight: size.width * 0.76 + driftX2 * 0.7,
      length: size.height * 1.15,
      color: const Color(0xFF2DD4BF).withValues(alpha: (0.11 * breatheAlpha).clamp(0.0, 1.0)),
      blurRadius: 34,
    );

    _drawRayShaft(
      canvas,
      origin: rayOrigin2,
      targetLeft: size.width * 0.66 + driftX2,
      targetRight: size.width * 1.16 + driftX2,
      length: size.height * 1.25,
      color: const Color(0xFF10B981).withValues(alpha: (0.13 * breatheAlpha).clamp(0.0, 1.0)),
      blurRadius: 38,
    );

    // Ethereal Dust Motes / Particles drifting through rays
    _drawDustMotes(canvas, size, progress);
  }

  void _drawRayShaft(
    Canvas canvas, {
    required Offset origin,
    required double targetLeft,
    required double targetRight,
    required double length,
    required Color color,
    required double blurRadius,
  }) {
    final path = Path()
      ..moveTo(origin.dx - 18, origin.dy)
      ..lineTo(origin.dx + 18, origin.dy)
      ..lineTo(targetRight, length)
      ..lineTo(targetLeft, length)
      ..close();

    final paint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          color,
          color.withValues(alpha: color.a * 0.75),
          color.withValues(alpha: color.a * 0.25),
          Colors.transparent,
        ],
        stops: const [0.0, 0.22, 0.60, 1.0],
      ).createShader(Rect.fromLTWH(0, 0, math.max(targetRight, 1000), length))
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, blurRadius);

    canvas.drawPath(path, paint);
  }

  void _drawDustMotes(Canvas canvas, Size size, double p) {
    final motePaint = Paint()..style = PaintingStyle.fill;

    // A constellation of 14 deterministic motes that gently float upward
    const motes = [
      [0.18, 0.25, 2.0, 0xFF6EE7B7],
      [0.24, 0.42, 2.8, 0xFF34D399],
      [0.32, 0.18, 1.8, 0xFF10B981],
      [0.38, 0.55, 2.4, 0xFF6EE7B7],
      [0.46, 0.30, 3.2, 0xFF2DD4BF],
      [0.52, 0.68, 2.0, 0xFF34D399],
      [0.60, 0.22, 2.6, 0xFF10B981],
      [0.68, 0.48, 3.0, 0xFF6EE7B7],
      [0.75, 0.35, 2.2, 0xFF2DD4BF],
      [0.82, 0.58, 2.6, 0xFF34D399],
      [0.28, 0.72, 1.8, 0xFF10B981],
      [0.70, 0.80, 2.4, 0xFF6EE7B7],
    ];

    for (final m in motes) {
      final double baseX = m[0].toDouble() * size.width;
      final double baseY = m[1].toDouble() * size.height;
      final double radius = m[2].toDouble();
      final int colorHex = m[3].toInt();

      // Float upward by (p * 40) px and oscillate horizontally
      final yOffset = -((p * 50) % size.height);
      final currentY = (baseY + yOffset) % size.height;
      final currentX = baseX + math.sin((p * 2 * math.pi) + baseX) * 12.0;

      // Pulse opacity
      final alpha = (0.25 + 0.35 * math.sin(p * 2 * math.pi + baseY)).clamp(0.1, 0.6);
      motePaint.color = Color(colorHex).withValues(alpha: alpha);

      canvas.drawCircle(Offset(currentX, currentY), radius, motePaint);
    }
  }

  @override
  bool shouldRepaint(covariant _CinematicLightRaysPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
