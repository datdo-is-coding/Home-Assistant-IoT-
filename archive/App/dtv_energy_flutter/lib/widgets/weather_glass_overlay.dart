import 'dart:math';
import 'package:flutter/material.dart';
import '../services/weather_state.dart';

class WeatherGlassOverlay extends StatefulWidget {
  final Widget child;
  const WeatherGlassOverlay({super.key, required this.child});

  @override
  State<WeatherGlassOverlay> createState() => _WeatherGlassOverlayState();
}

class _WeatherGlassOverlayState extends State<WeatherGlassOverlay> with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  final List<_RainDrop> _rainDrops = [];
  final Random _rnd = Random();

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat();

    // Generate random raindrops
    for (int i = 0; i < 45; i++) {
      _rainDrops.add(_RainDrop(
        x: _rnd.nextDouble(),
        y: _rnd.nextDouble(),
        speed: 0.15 + _rnd.nextDouble() * 0.3,
        length: 12 + _rnd.nextDouble() * 20,
        thickness: 1.0 + _rnd.nextDouble() * 1.5,
        opacity: 0.2 + _rnd.nextDouble() * 0.4,
      ));
    }
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<String>(
      valueListenable: WeatherState().activeCondition,
      builder: (context, condition, _) {
        return Stack(
          children: [
            widget.child,

            // Background Weather Painter
            Positioned.fill(
              child: IgnorePointer(
                child: AnimatedBuilder(
                  animation: _animController,
                  builder: (context, child) {
                    return CustomPaint(
                      painter: _WeatherAmbientPainter(
                        condition: condition,
                        progress: _animController.value,
                        rainDrops: _rainDrops,
                      ),
                    );
                  },
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _RainDrop {
  double x;
  double y;
  double speed;
  double length;
  double thickness;
  double opacity;

  _RainDrop({
    required this.x,
    required this.y,
    required this.speed,
    required this.length,
    required this.thickness,
    required this.opacity,
  });
}

class _WeatherAmbientPainter extends CustomPainter {
  final String condition;
  final double progress;
  final List<_RainDrop> rainDrops;

  _WeatherAmbientPainter({
    required this.condition,
    required this.progress,
    required this.rainDrops,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (condition == 'sunny') {
      _paintSunnySunburst(canvas, size);
    } else if (condition == 'rainy' || condition == 'stormy') {
      _paintRainEffect(canvas, size);
    } else if (condition == 'cloudy') {
      _paintCloudyFog(canvas, size);
    }
  }

  void _paintSunnySunburst(Canvas canvas, Size size) {
    final sunCenter = Offset(size.width * 0.88, 70);

    // 1. Sun Core Glow
    final corePaint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFFFDE047).withOpacity(0.45),
          const Color(0xFFF97316).withOpacity(0.20),
          const Color(0xFFF59E0B).withOpacity(0.05),
          Colors.transparent,
        ],
        stops: const [0.0, 0.35, 0.70, 1.0],
      ).createShader(Rect.fromCircle(center: sunCenter, radius: 180));

    canvas.drawCircle(sunCenter, 180, corePaint);

    // 2. 3D Sun Lens Flares / Light Rays
    final rayPaint = Paint()
      ..color = const Color(0xFFFEF08A).withOpacity(0.08)
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke;

    double sweepAngle = progress * 2 * pi;
    for (int i = 0; i < 8; i++) {
      double angle = sweepAngle + (i * pi / 4);
      Offset end = sunCenter + Offset(cos(angle) * 320, sin(angle) * 320);
      canvas.drawLine(sunCenter, end, rayPaint);
    }

    // 3. Sweeping Light Flare Bar over Glass
    final lightBarPaint = Paint()
      ..shader = LinearGradient(
        colors: [
          Colors.transparent,
          const Color(0xFFFEF08A).withOpacity(0.08),
          Colors.transparent,
        ],
        begin: Alignment(-1.5 + (progress * 3.0), -1.0),
        end: Alignment(-0.5 + (progress * 3.0), 1.0),
      ).createShader(Offset.zero & size);

    canvas.drawRect(Offset.zero & size, lightBarPaint);
  }

  void _paintRainEffect(Canvas canvas, Size size) {
    final paint = Paint()..style = PaintingStyle.stroke;

    for (var drop in rainDrops) {
      double currentY = (drop.y + progress * drop.speed * 4) % 1.2 - 0.1;
      double startX = drop.x * size.width;
      double startY = currentY * size.height;

      paint
        ..color = const Color(0xFF38BDF8).withOpacity(drop.opacity)
        ..strokeWidth = drop.thickness
        ..strokeCap = StrokeCap.round;

      // Draw slanted rain streak
      canvas.drawLine(
        Offset(startX, startY),
        Offset(startX - 4, startY + drop.length),
        paint,
      );
    }

    // Dynamic Lightning flash if stormy
    if (condition == 'stormy' && (progress * 10).floor() % 7 == 0 && progress % 0.08 < 0.02) {
      final flashPaint = Paint()..color = Colors.white.withOpacity(0.12);
      canvas.drawRect(Offset.zero & size, flashPaint);
    }
  }

  void _paintCloudyFog(Canvas canvas, Size size) {
    final fogPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFF64748B).withOpacity(0.15),
          Colors.transparent,
        ],
        radius: 0.8,
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height * 0.5));

    canvas.drawRect(Offset.zero & size, fogPaint);
  }

  @override
  bool shouldRepaint(covariant _WeatherAmbientPainter oldDelegate) => true;
}
