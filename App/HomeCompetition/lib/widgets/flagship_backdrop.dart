import 'dart:ui' as ui;
import 'package:flutter/material.dart';

class FlagshipBackdrop extends StatelessWidget {
  const FlagshipBackdrop({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Stack(children: [
      Positioned.fill(
        child: IgnorePointer(
          child: RepaintBoundary(
            child: CustomPaint(
              painter: _LightRays(dark),
              isComplex: true,
              willChange: false,
            ),
          ),
        ),
      ),
      child,
      Positioned(
        top: 0,
        left: 0,
        right: 0,
        height: MediaQuery.paddingOf(context).top + 4,
        child: IgnorePointer(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  (dark ? const Color(0xFF101C1B) : const Color(0xFFF1F5F1))
                      .withValues(alpha: 0.6),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ),
      ),
    ]);
  }
}

class _LightRays extends CustomPainter {
  const _LightRays(this.dark);
  final bool dark;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final base = dark ? const Color(0xFF10191A) : const Color(0xFFF1F5F1);
    final light = dark ? const Color(0xFFC7E8D5) : Colors.white;
    canvas.drawRect(rect, Paint()..color = base);
    canvas.drawRect(
      rect,
      Paint()
        ..shader = ui.Gradient.radial(
          Offset(size.width * 0.06, size.height * 0.04),
          size.height * 0.75,
          [
            dark ? const Color(0xFF2D4941) : const Color(0xFFD7E8DB),
            base,
          ],
        ),
    );
    // A fixed light source, no frame ticker or full-screen backdrop filtering.
    canvas.save();
    canvas.translate(-size.width * 0.12, -size.height * 0.12);
    canvas.rotate(-0.46);
    final length = size.height * 1.3;
    for (final ray in const [
      (-0.09, 0.13, 0.10),
      (0.12, 0.23, 0.14),
      (0.44, 0.10, 0.18),
      (0.65, 0.28, 0.08),
    ]) {
      final x = size.width * ray.$1;
      final width = size.width * ray.$2;
      final path = Path()
        ..moveTo(x, 0)
        ..lineTo(x + width * 0.38, 0)
        ..lineTo(x + width * 2.4, length)
        ..lineTo(x - width * 0.5, length)
        ..close();
      canvas.drawPath(
        path,
        Paint()
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12)
          ..shader = ui.Gradient.linear(
            Offset(x - width * 0.5, 0),
            Offset(x + width * 2.4, 0),
            [
              light.withValues(alpha: 0),
              light.withValues(alpha: dark ? ray.$3 : ray.$3 * 2.4),
              light.withValues(alpha: 0),
            ],
            [0, 0.52, 1],
          ),
      );
    }
    canvas.restore();
    canvas.drawRect(
      rect,
      Paint()
        ..shader = ui.Gradient.linear(
          Offset(0, size.height * 0.14),
          Offset(0, size.height * 0.88),
          [base.withValues(alpha: 0), base],
        ),
    );
  }

  @override
  bool shouldRepaint(covariant _LightRays oldDelegate) =>
      oldDelegate.dark != dark;
}
