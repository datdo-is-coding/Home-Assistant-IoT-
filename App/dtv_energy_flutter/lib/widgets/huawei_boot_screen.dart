import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Flagship optical boot animation inspired by Huawei's iconic celestial light ring.
///
/// Features pure visual optics:
/// - Pitch-black canvas (`#000000`)
/// - Concentric breathing celestial light rings with soft Gaussian falloff
/// - 360° rotating optical refraction arc (lens flare caustic)
/// - Whispering orbital light particles with dynamic depth
/// - Specular light sweep across architectural typography `S I C   H O M E`
/// - Seamless iris bloom exit transition
class HuaweiBootScreen extends StatefulWidget {
  const HuaweiBootScreen({
    super.key,
    required this.onComplete,
    this.duration = const Duration(milliseconds: 2400),
    this.allowSkip = true,
  });

  final VoidCallback onComplete;
  final Duration duration;
  final bool allowSkip;

  @override
  State<HuaweiBootScreen> createState() => _HuaweiBootScreenState();
}

class _HuaweiBootScreenState extends State<HuaweiBootScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _bloomAnimation;
  late final Animation<double> _ringAnimation;
  late final Animation<double> _textFadeAnimation;
  late final Animation<double> _shimmerAnimation;
  late final Animation<double> _exitFadeAnimation;
  late final Animation<double> _exitScaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.duration,
    );

    // Initial central light inception & bloom (0.0 -> 0.45)
    _bloomAnimation = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.0, 0.45, curve: Curves.easeOutCubic),
    );

    // Ring expansion and optical breathing (0.1 -> 0.85)
    _ringAnimation = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.1, 0.85, curve: Curves.easeInOutCubic),
    );

    // Subtle typography reveal (0.35 -> 0.70)
    _textFadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.35, 0.70, curve: Curves.easeOut),
    );

    // Specular light sweep across text (0.45 -> 0.85)
    _shimmerAnimation = Tween<double>(begin: -1.0, end: 2.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.45, 0.85, curve: Curves.easeInOut),
      ),
    );

    // Iris bloom & exit fade (0.85 -> 1.0)
    _exitFadeAnimation = Tween<double>(begin: 1.0, end: 0.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.85, 1.0, curve: Curves.easeInOut),
      ),
    );

    _exitScaleAnimation = Tween<double>(begin: 1.0, end: 1.12).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.82, 1.0, curve: Curves.easeInCubic),
      ),
    );

    _controller.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        widget.onComplete();
      }
    });

    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _skip() {
    if (widget.allowSkip && !_controller.isCompleted) {
      _controller.stop();
      widget.onComplete();
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _skip,
      behavior: HitTestBehavior.opaque,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          final progress = _controller.value;
          final exitFade = _exitFadeAnimation.value;
          final exitScale = _exitScaleAnimation.value;

          return Scaffold(
            backgroundColor: const Color(0xFF000000),
            body: Opacity(
              opacity: exitFade.clamp(0.0, 1.0),
              child: Transform.scale(
                scale: exitScale,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // Dynamic celestial ring, optical arc and particle canvas
                    CustomPaint(
                      painter: _OpticalBootPainter(
                        bloomProgress: _bloomAnimation.value,
                        ringProgress: _ringAnimation.value,
                        overallProgress: progress,
                      ),
                    ),

                    // Central Architectural Wordmark & Emblem
                    Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Central minimal optical node
                          _buildCoreNode(progress),
                          const SizedBox(height: 36),

                          // Typography with specular light sweep
                          Opacity(
                            opacity: _textFadeAnimation.value,
                            child: Transform.translate(
                              offset: Offset(
                                  0, 14 * (1.0 - _textFadeAnimation.value)),
                              child: _buildShimmerText(
                                text: 'S I C   H O M E',
                                fontSize: 22,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 8,
                                shimmerPos: _shimmerAnimation.value,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),

                    // Top-right subtle glass skip pill
                    if (widget.allowSkip && progress < 0.85)
                      Positioned(
                        top: 50,
                        right: 24,
                        child: Opacity(
                          opacity: (progress * 2).clamp(0.0, 0.5),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 14, vertical: 6),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.07),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.12),
                                width: 0.8,
                              ),
                            ),
                            child: const Text(
                              'Bỏ qua',
                              style: TextStyle(
                                color: Color(0xFFD0D4DC),
                                fontSize: 11,
                                letterSpacing: 1.2,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildCoreNode(double progress) {
    final scale = (_bloomAnimation.value * 0.35 + 0.65).clamp(0.0, 1.0);
    final glow = _bloomAnimation.value.clamp(0.0, 1.0);

    return Transform.scale(
      scale: scale,
      child: Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [
              Colors.white.withValues(alpha: 0.22 * glow),
              Colors.white.withValues(alpha: 0.05 * glow),
              Colors.transparent,
            ],
            stops: const [0.0, 0.5, 1.0],
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.white.withValues(alpha: 0.18 * glow),
              blurRadius: 28,
              spreadRadius: 2,
            ),
          ],
        ),
        child: Center(
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF07080A),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.25 + 0.35 * glow),
                width: 1.2,
              ),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Inner rotating fine diamond
                Transform.rotate(
                  angle: progress * math.pi * 1.2,
                  child: Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(5),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.3),
                        width: 1,
                      ),
                    ),
                  ),
                ),
                // Central luminous photon point
                Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.white.withValues(alpha: 0.95),
                        blurRadius: 10,
                        spreadRadius: 1.5,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildShimmerText({
    required String text,
    required double fontSize,
    required FontWeight fontWeight,
    required double letterSpacing,
    required double shimmerPos,
  }) {
    return ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: (bounds) {
        return LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: const [
            Color(0xFF7A818C),
            Color(0xFFFFFFFF),
            Color(0xFF7A818C),
          ],
          stops: [
            (shimmerPos - 0.25).clamp(0.0, 1.0),
            shimmerPos.clamp(0.0, 1.0),
            (shimmerPos + 0.25).clamp(0.0, 1.0),
          ],
        ).createShader(bounds);
      },
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: fontSize,
          fontWeight: fontWeight,
          letterSpacing: letterSpacing,
          color: Colors.white,
        ),
      ),
    );
  }
}

/// Custom painter crafting ethereal Huawei-like concentric light rings,
/// subtle particle dust, and radial halation.
class _OpticalBootPainter extends CustomPainter {
  _OpticalBootPainter({
    required this.bloomProgress,
    required this.ringProgress,
    required this.overallProgress,
  });

  final double bloomProgress;
  final double ringProgress;
  final double overallProgress;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);

    // 1. Ambient central radial halation / aurora glow
    final bgGlowRadius = size.width * 0.7;
    final bgGlowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.white.withValues(alpha: 0.08 * bloomProgress),
          const Color(0xFF141924).withValues(alpha: 0.06 * bloomProgress),
          Colors.transparent,
        ],
        stops: const [0.0, 0.45, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: bgGlowRadius));
    canvas.drawCircle(center, bgGlowRadius, bgGlowPaint);

    // 2. Concentric harmonic light rings (expanding outwards)
    final ringPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;

    final baseRadius = 78.0 + (ringProgress * 44.0);

    // Ring 1: Primary fine ring
    ringPaint.color =
        Colors.white.withValues(alpha: 0.22 * (1.0 - ringProgress * 0.4));
    canvas.drawCircle(center, baseRadius, ringPaint);

    // Ring 2: Secondary outer faint ring
    final outerRadius = baseRadius + 32.0 + (ringProgress * 24.0);
    ringPaint.color =
        Colors.white.withValues(alpha: 0.10 * (1.0 - ringProgress * 0.3));
    canvas.drawCircle(center, outerRadius, ringPaint);

    // Ring 3: Subtle inner harmonic ring
    final innerRadius = baseRadius - 24.0;
    if (innerRadius > 0) {
      ringPaint.color = Colors.white.withValues(alpha: 0.15 * bloomProgress);
      canvas.drawCircle(center, innerRadius, ringPaint);
    }

    // 3. Ethereal rotating arcs (like Huawei celestial lens flare with spectral dispersion)
    final arcRect = Rect.fromCircle(center: center, radius: baseRadius + 12.0);
    final arcPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2.0
      ..shader = SweepGradient(
        colors: [
          Colors.transparent,
          const Color(0xFF00E5FF).withValues(alpha: 0.70 * bloomProgress),
          const Color(0xFFFBBF24).withValues(alpha: 0.85 * bloomProgress),
          const Color(0xFFA855F7).withValues(alpha: 0.75 * bloomProgress),
          Colors.transparent,
        ],
        stops: const [0.0, 0.25, 0.5, 0.75, 1.0],
        transform: GradientRotation(overallProgress * math.pi * 2.5),
      ).createShader(arcRect);

    canvas.drawArc(
      arcRect,
      overallProgress * math.pi * 2.5,
      math.pi * 0.75,
      false,
      arcPaint,
    );

    // 4. Subtle orbital particle dust with prismatic hues
    const particleCount = 12;
    const particlePalette = [
      Color(0xFF38BDF8),
      Color(0xFFFBBF24),
      Color(0xFF34D399),
      Color(0xFFA78BFA),
      Color(0xFFF472B6),
      Color(0xFF67E8F9),
    ];
    for (int i = 0; i < particleCount; i++) {
      final angle = (i * (2 * math.pi / particleCount)) +
          (overallProgress * (i % 2 == 0 ? 0.7 : -0.5));
      final dist = baseRadius +
          math.sin(overallProgress * 3 + i) * 20.0 +
          (i * 3.5);
      final px = center.dx + math.cos(angle) * dist;
      final py = center.dy + math.sin(angle) * dist;

      final pAlpha =
          (0.20 + 0.60 * math.sin(overallProgress * math.pi + i)).clamp(0.0, 1.0);
      final pColor = particlePalette[i % particlePalette.length];
      final pPaint = Paint()
        ..color = pColor.withValues(alpha: pAlpha * bloomProgress)
        ..style = PaintingStyle.fill;

      canvas.drawCircle(Offset(px, py), (i % 2 == 0) ? 1.6 : 1.1, pPaint);
    }

  }

  @override
  bool shouldRepaint(covariant _OpticalBootPainter oldDelegate) {
    return oldDelegate.bloomProgress != bloomProgress ||
        oldDelegate.ringProgress != ringProgress ||
        oldDelegate.overallProgress != overallProgress;
  }
}
