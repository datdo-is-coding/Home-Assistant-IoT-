import 'dart:ui' show ImageFilter;
import 'package:flutter/material.dart';

/// Three clipped bands keep the progressively frosted edge off the device grid.
class ProgressiveBlur extends StatelessWidget {
  const ProgressiveBlur({
    super.key,
    required this.tint,
    this.maxSigma = 8,
    this.maxOpacity = 0.94,
  });

  final Color tint;
  final double maxSigma;
  final double maxOpacity;

  @override
  Widget build(BuildContext context) {
    final reduceEffects = MediaQuery.disableAnimationsOf(context) ||
        MediaQuery.highContrastOf(context);
    return IgnorePointer(
      child: ExcludeSemantics(
        child: reduceEffects
            ? ColoredBox(color: tint.withValues(alpha: 0.97))
            : LayoutBuilder(builder: (context, constraints) {
                return Stack(children: [
                  for (var i = 0; i < 3; i++)
                    Positioned(
                      top: constraints.maxHeight * i / 3,
                      left: 0,
                      right: 0,
                      height: constraints.maxHeight / 3 + 0.5,
                      child: ClipRect(
                        child: BackdropFilter(
                          filter: ImageFilter.blur(
                            sigmaX: maxSigma * (i + 1) / 3,
                            sigmaY: maxSigma * (i + 1) / 3,
                          ),
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [
                                  tint.withValues(alpha: maxOpacity * i / 3),
                                  tint.withValues(
                                      alpha: maxOpacity * (i + 1) / 3),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                ]);
              }),
      ),
    );
  }
}
