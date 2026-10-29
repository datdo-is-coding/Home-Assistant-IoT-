import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Tactile interactive spring scale wrapper providing soft bounce feedback on tap/press.
class SoftBounce extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final double pressedScale;
  final Duration duration;
  final HitTestBehavior behavior;

  const SoftBounce({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.pressedScale = 0.965,
    this.duration = const Duration(milliseconds: 120),
    this.behavior = HitTestBehavior.opaque,
  });

  @override
  State<SoftBounce> createState() => _SoftBounceState();
}

class _SoftBounceState extends State<SoftBounce>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.duration,
      reverseDuration: const Duration(milliseconds: 160),
    );
    _scaleAnimation = Tween<double>(
      begin: 1.0,
      end: widget.pressedScale,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
      reverseCurve: Curves.easeOutBack,
    ));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _handleTapDown(TapDownDetails _) {
    if (!MediaQuery.disableAnimationsOf(context) &&
        (widget.onTap != null || widget.onLongPress != null)) {
      _controller.forward();
    }
  }

  void _handleTapUp(TapUpDetails _) {
    if (widget.onTap != null || widget.onLongPress != null) {
      _controller.reverse();
    }
  }

  void _handleTapCancel() {
    if (widget.onTap != null || widget.onLongPress != null) {
      _controller.reverse();
    }
  }

  @override
  Widget build(BuildContext context) {
    final isInteractive = widget.onTap != null || widget.onLongPress != null;
    if (!isInteractive) {
      return widget.child;
    }

    return GestureDetector(
      behavior: widget.behavior,
      onTapDown: _handleTapDown,
      onTapUp: _handleTapUp,
      onTapCancel: _handleTapCancel,
      onTap: () {
        HapticFeedback.lightImpact();
        widget.onTap?.call();
      },
      onLongPress: () {
        HapticFeedback.mediumImpact();
        widget.onLongPress?.call();
      },
      child: AnimatedBuilder(
        animation: _controller,
        child: RepaintBoundary(child: widget.child),
        builder: (context, child) => Transform(
          alignment: Alignment.center,
          transform: Matrix4.identity()
            ..setEntry(3, 2, 0.001)
            ..rotateX(_controller.value * 0.012)
            ..rotateY(-_controller.value * 0.016)
            ..scale(_scaleAnimation.value),
          child: child,
        ),
      ),
    );
  }
}

/// Translucent surfaces share one light direction; blur stays outside the grids.
class Soft3DDecorations {
  Soft3DDecorations._();

  static BoxDecoration card({
    required bool isDark,
    bool isActive = false,
    Color? accentColor,
    double radius = 24,
    Border? customBorder,
  }) {
    final accent = accentColor ?? const Color(0xFF759C84);
    final surface = isDark ? const Color(0xFF24372E) : Colors.white;
    return BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color.alphaBlend(accent.withValues(alpha: isActive ? 0.12 : 0),
              surface.withValues(alpha: isDark ? 0.76 : 0.86)),
          surface.withValues(alpha: isDark ? 0.40 : 0.54),
        ],
      ),
      borderRadius: BorderRadius.circular(radius),
      border: customBorder ??
          Border.all(
            color: isActive
                ? accent.withValues(alpha: 0.40)
                : Colors.white.withValues(alpha: isDark ? 0.10 : 0.70),
            width: 0.8,
          ),
      boxShadow: [
        BoxShadow(
          color:
              const Color(0xFF0E3020).withValues(alpha: isDark ? 0.10 : 0.045),
          blurRadius: 24,
          offset: const Offset(0, 8),
          spreadRadius: -8,
        ),
      ],
    );
  }

  static BoxDecoration iconWell({
    required bool isDark,
    bool isActive = false,
    Color? accentColor,
    double radius = 12,
  }) =>
      BoxDecoration(
        color: isActive && accentColor != null
            ? accentColor.withValues(alpha: isDark ? 0.16 : 0.13)
            : (isDark ? Colors.white : const Color(0xFF51755F))
                .withValues(alpha: 0.055),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
          color: Colors.white.withValues(alpha: isDark ? 0.06 : 0.40),
          width: 0.6,
        ),
      );

  static BoxDecoration pill({
    required bool isDark,
    bool isSelected = false,
    Color? accentColor,
    double radius = 100,
  }) =>
      BoxDecoration(
        color: isSelected
            ? (accentColor ??
                (isDark ? const Color(0xFFD1E5D5) : const Color(0xFF315E4B)))
            : Colors.white.withValues(alpha: isDark ? 0.045 : 0.50),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(
          color: isSelected
              ? Colors.transparent
              : Colors.white.withValues(alpha: isDark ? 0.08 : 0.65),
          width: 0.8,
        ),
      );
}
