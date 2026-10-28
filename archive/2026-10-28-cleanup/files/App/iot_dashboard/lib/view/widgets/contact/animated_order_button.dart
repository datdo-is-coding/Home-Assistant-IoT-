import 'dart:math' as math;
import 'package:flutter/material.dart';

enum OrderButtonState { idle, animating, completed }

class AnimatedOrderButton extends StatefulWidget {
  final Future<bool> Function()? onPressed;
  final VoidCallback? onCompleted;
  final String defaultText;
  final String successText;

  const AnimatedOrderButton({
    super.key,
    required this.onPressed,
    this.onCompleted,
    this.defaultText = "GỬI ĐƠN ĐĂNG KÝ NÂNG CẤP HỆ THỐNG",
    this.successText = "Đã Gửi Đơn Đăng Ký ✓",
  });

  @override
  State<AnimatedOrderButton> createState() => _AnimatedOrderButtonState();
}

class _AnimatedOrderButtonState extends State<AnimatedOrderButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  OrderButtonState _buttonState = OrderButtonState.idle;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    );

    _controller.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        setState(() {
          _buttonState = OrderButtonState.completed;
        });
        if (widget.onCompleted != null) {
          widget.onCompleted!();
        }
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _handleTap() async {
    if (_buttonState != OrderButtonState.idle) return;

    if (widget.onPressed != null) {
      final isValid = await widget.onPressed!();
      if (!isValid) return;
    }

    setState(() {
      _buttonState = OrderButtonState.animating;
    });

    _controller.forward(from: 0.0);
  }

  /// Reset nút về trạng thái ban đầu
  void reset() {
    _controller.reset();
    setState(() {
      _buttonState = OrderButtonState.idle;
    });
  }

  @override
  Widget build(BuildContext context) {
    final isCompleted = _buttonState == OrderButtonState.completed;
    final isAnimating = _buttonState == OrderButtonState.animating;

    final borderColor = isCompleted ? const Color(0xFF22C55E) : const Color(0xFF334155);
    final bgColor = isCompleted ? const Color(0xFF064E3B) : const Color(0xFF1E293B);

    return LayoutBuilder(
      builder: (context, constraints) {
        final buttonWidth = constraints.maxWidth;
        const buttonHeight = 56.0;

        return Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 400),
            width: buttonWidth,
            height: buttonHeight,
            decoration: BoxDecoration(
              color: bgColor,
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: borderColor, width: 2),
              boxShadow: [
                BoxShadow(
                  color: isCompleted
                      ? const Color(0xFF22C55E).withValues(alpha: 0.3)
                      : Colors.black.withValues(alpha: 0.4),
                  blurRadius: 15,
                  offset: const Offset(0, 5),
                ),
              ],
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: _handleTap,
                borderRadius: BorderRadius.circular(28),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(28),
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      // 1. DEFAULT TEXT (Slide up & fade out when animating)
                      AnimatedPositioned(
                        duration: const Duration(milliseconds: 300),
                        top: isAnimating || isCompleted ? -30 : 16,
                        child: AnimatedOpacity(
                          duration: const Duration(milliseconds: 300),
                          opacity: _buttonState == OrderButtonState.idle ? 1.0 : 0.0,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.send_rounded,
                                color: Color(0xFFF8FAFC),
                                size: 18,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                widget.defaultText,
                                style: const TextStyle(
                                  color: Color(0xFFF8FAFC),
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 0.5,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),

                      // 2. ROAD LINE (Vạch kẻ đường cuộn liên tục)
                      if (isAnimating)
                        AnimatedBuilder(
                          animation: _controller,
                          builder: (context, child) {
                            return CustomPaint(
                              size: Size(buttonWidth, 2),
                              painter: _RoadLinePainter(
                                progress: _controller.value * 10,
                              ),
                            );
                          },
                        ),

                      // 3. TRUCK ANIMATION 🚚
                      if (isAnimating)
                        AnimatedBuilder(
                          animation: _controller,
                          builder: (context, child) {
                            final value = _controller.value;
                            double leftPos;

                            // keyframes: 0% -> 40%: -50px to 45%; 40% -> 60%: 45%; 60% -> 100%: 45% to 110%
                            if (value <= 0.4) {
                              final t = value / 0.4;
                              final curveT = Curves.easeOut.transform(t);
                              leftPos = -50 + (buttonWidth * 0.45 + 50) * curveT;
                            } else if (value <= 0.6) {
                              leftPos = buttonWidth * 0.45;
                            } else {
                              final t = (value - 0.6) / 0.4;
                              final curveT = Curves.easeIn.transform(t);
                              leftPos = buttonWidth * 0.45 +
                                  (buttonWidth * 0.65 + 50) * curveT;
                            }

                            return Positioned(
                              left: leftPos,
                              child: Transform.scale(
                                scaleX: -1,
                                child: const Text(
                                  '🚚',
                                  style: TextStyle(fontSize: 26),
                                ),
                              ),
                            );
                          },
                        ),

                      // 4. SUCCESS TEXT (Slide in & fade in when completed)
                      AnimatedPositioned(
                        duration: const Duration(milliseconds: 400),
                        curve: Curves.easeOutBack,
                        top: isCompleted ? 16 : 50,
                        child: AnimatedOpacity(
                          duration: const Duration(milliseconds: 300),
                          opacity: isCompleted ? 1.0 : 0.0,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.check_circle_rounded,
                                color: Color(0xFF22C55E),
                                size: 22,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                widget.successText,
                                style: const TextStyle(
                                  color: Color(0xFF22C55E),
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 0.5,
                                ),
                              ),
                            ],
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
      },
    );
  }
}

/// Painter vẽ vạch kẻ đường dạng đứt nét cuộn liên tục (Road Line Animation)
class _RoadLinePainter extends CustomPainter {
  final double progress;

  _RoadLinePainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF64748B)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;

    const dashWidth = 12.0;
    const dashSpace = 8.0;
    final startX = -(progress % (dashWidth + dashSpace));

    double currentX = startX;
    final y = size.height / 2;

    while (currentX < size.width) {
      canvas.drawLine(
        Offset(math.max(0, currentX), y),
        Offset(math.min(size.width, currentX + dashWidth), y),
        paint,
      );
      currentX += dashWidth + dashSpace;
    }
  }

  @override
  bool shouldRepaint(covariant _RoadLinePainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
