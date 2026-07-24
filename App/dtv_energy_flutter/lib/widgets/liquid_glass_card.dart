import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';
import '../services/theme_service.dart';
import '../services/weather_state.dart';

class LiquidGlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final double borderRadius;
  final Color? borderColor;
  final Color? glowColor;
  final double blurSigma;
  final VoidCallback? onTap;

  const LiquidGlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margin,
    this.borderRadius = 20,
    this.borderColor,
    this.glowColor,
    this.blurSigma = 16,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = ThemeService().currentTheme;
    final borderC = borderColor ?? theme.primary.withOpacity(0.3);
    final glowC = glowColor ?? theme.primary.withOpacity(0.1);

    Widget cardContent = Container(
      margin: margin,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(borderRadius),
        boxShadow: [
          BoxShadow(
            color: glowC,
            blurRadius: 24,
            spreadRadius: 1,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
          child: Stack(
            children: [
              Container(
                padding: padding,
                decoration: BoxDecoration(
                  color: theme.surface.withOpacity(0.75),
                  borderRadius: BorderRadius.circular(borderRadius),
                  border: Border.all(color: borderC, width: 1.2),
                ),
                child: child,
              ),

              // 3D Glass Water Droplets Overlay on Borders
              ValueListenableBuilder<String>(
                valueListenable: WeatherState().activeCondition,
                builder: (context, condition, _) {
                  if (condition == 'rainy' || condition == 'stormy') {
                    return Positioned.fill(
                      child: IgnorePointer(
                        child: CustomPaint(
                          painter: _GlassBorderDropletsPainter(borderRadius: borderRadius),
                        ),
                      ),
                    );
                  }
                  return const SizedBox.shrink();
                },
              ),
            ],
          ),
        ),
      ),
    );

    if (onTap != null) {
      return GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: cardContent,
      );
    }
    return cardContent;
  }
}

class _GlassBorderDropletsPainter extends CustomPainter {
  final double borderRadius;
  _GlassBorderDropletsPainter({required this.borderRadius});

  @override
  void paint(Canvas canvas, Size size) {
    final shadowPaint = Paint()..color = Colors.black.withOpacity(0.3);
    final bodyPaint = Paint()..color = const Color(0xFFBAE6FD).withOpacity(0.45);
    final highlightPaint = Paint()..color = Colors.white.withOpacity(0.95);

    // Pre-calculated droplet offsets along the border
    final List<Map<String, double>> droplets = [
      {'x': 18.0, 'y': 6.0, 'r': 3.5, 'trail': 6.0},
      {'x': 45.0, 'y': 3.0, 'r': 2.5, 'trail': 4.0},
      {'x': 85.0, 'y': 8.0, 'r': 4.0, 'trail': 10.0},
      {'x': size.width - 60, 'y': 4.0, 'r': 3.0, 'trail': 5.0},
      {'x': size.width - 25, 'y': 12.0, 'r': 4.5, 'trail': 12.0},
      {'x': size.width - 8, 'y': 40.0, 'r': 3.2, 'trail': 8.0},
      {'x': 6.0, 'y': 35.0, 'r': 3.8, 'trail': 9.0},
      {'x': size.width * 0.45, 'y': 4.0, 'r': 2.8, 'trail': 4.5},
      {'x': size.width * 0.70, 'y': 5.0, 'r': 3.6, 'trail': 7.0},
    ];

    for (var d in droplets) {
      double x = d['x']!;
      double y = d['y']!;
      double r = d['r']!;
      double trail = d['trail']!;

      if (x > size.width || y > size.height) continue;

      // 1. Water trail down glass
      if (trail > 0) {
        final trailPaint = Paint()
          ..color = const Color(0xFF7DD3FC).withOpacity(0.25)
          ..strokeWidth = r * 0.8
          ..strokeCap = StrokeCap.round;
        canvas.drawLine(Offset(x, y - trail), Offset(x, y), trailPaint);
      }

      // 2. 3D Drop Shadow underneath
      canvas.drawOval(
        Rect.fromCenter(center: Offset(x + 0.8, y + 1.2), width: r * 2.2, height: r * 2.4),
        shadowPaint,
      );

      // 3. Drop Body (translucent liquid)
      canvas.drawOval(
        Rect.fromCenter(center: Offset(x, y), width: r * 2.0, height: r * 2.2),
        bodyPaint,
      );

      // 4. Specular White Light Highlight (3D Glass Refraction)
      canvas.drawCircle(
        Offset(x - r * 0.3, y - r * 0.3),
        r * 0.45,
        highlightPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
