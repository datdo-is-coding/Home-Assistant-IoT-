import 'package:flutter/material.dart';

// ================= WIDGET ĐÈN TREO MINI DÀNH CHO CARD HOME =================
class MiniSmartLamp extends StatefulWidget {
  final bool isOn;
  final ValueChanged<bool> onToggle;

  const MiniSmartLamp({super.key, required this.isOn, required this.onToggle});

  @override
  State<MiniSmartLamp> createState() => _MiniSmartLampState();
}

class _MiniSmartLampState extends State<MiniSmartLamp>
    with SingleTickerProviderStateMixin {
  late AnimationController _pullController;
  late Animation<double> _pullAnimation;

  @override
  void initState() {
    super.initState();
    // Hiệu ứng giật dây công tắc mượt mà
    _pullController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 180),
    );
    _pullAnimation = Tween<double>(begin: 0, end: 12).animate(
      CurvedAnimation(parent: _pullController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pullController.dispose();
    super.dispose();
  }

  void _handlePull() async {
    await _pullController.forward();
    widget.onToggle(!widget.isOn);
    await _pullController.reverse();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // 1. Cột chữ bên trái (Căn lề TRÁI để lề đầu chữ thẳng tắp với chữ Gió)
        SizedBox(
          width: 75,
          child: Text(
            widget.isOn ? 'Đèn: Bật' : 'Đèn: Tắt',
            textAlign: TextAlign.start, // 👈 Căn lề trái thẳng chữ
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.bold,
              color: widget.isOn ? Colors.amber.shade800 : Colors.grey.shade600,
            ),
          ),
        ),
        const SizedBox(width: 8),

        // 2. Cột chứa cây đèn bên phải (Cố định width 60px)
        SizedBox(
          width: 60,
          height: 85,
          child: Stack(
            alignment: Alignment.topCenter,
            clipBehavior: Clip.none,
            children: [
              // Quầng sáng vàng tỏa ra khi bật đèn
              Positioned(
                top: 5,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 350),
                  width: widget.isOn ? 70 : 0,
                  height: widget.isOn ? 70 : 0,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        const Color(0xFFFDE047).withValues(alpha: 0.45),
                        const Color(0xFFFACC15).withValues(alpha: 0.15),
                        Colors.transparent,
                      ],
                      stops: const [0.0, 0.5, 1.0],
                    ),
                  ),
                ),
              ),

              // Dây kéo công tắc giật nảy
              AnimatedBuilder(
                animation: _pullAnimation,
                builder: (context, child) {
                  return Positioned(
                    top: 32 + _pullAnimation.value,
                    right: 6,
                    child: GestureDetector(
                      onTap: _handlePull,
                      child: MouseRegion(
                        cursor: SystemMouseCursors.click,
                        child: Column(
                          children: [
                            Container(
                              width: 1.5,
                              height: 28,
                              color: Colors.grey.shade400,
                            ),
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 250),
                              width: 9,
                              height: 9,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: widget.isOn
                                    ? const Color(0xFFFBBF24)
                                    : Colors.grey.shade400,
                                boxShadow: [
                                  if (widget.isOn)
                                    BoxShadow(
                                      color: const Color(
                                        0xFFFBBF24,
                                      ).withValues(alpha: 0.6),
                                      blurRadius: 6,
                                      spreadRadius: 1,
                                    ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),

              // Chụp đèn & Khung đèn Mini
              GestureDetector(
                onTap: _handlePull,
                child: MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: Column(
                    children: [
                      Container(
                        width: 2,
                        height: 8,
                        color: Colors.grey.shade400,
                      ),
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        width: 50,
                        height: 24,
                        decoration: BoxDecoration(
                          color: widget.isOn
                              ? Colors.amber.shade100
                              : Colors.grey.shade200,
                          borderRadius: const BorderRadius.only(
                            topLeft: Radius.circular(40),
                            topRight: Radius.circular(40),
                          ),
                          boxShadow: [
                            if (widget.isOn)
                              BoxShadow(
                                color: const Color(
                                  0xFFFDE047,
                                ).withValues(alpha: 0.7),
                                blurRadius: 15,
                                spreadRadius: 2,
                              ),
                          ],
                        ),
                      ),
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        width: 34,
                        height: 6,
                        decoration: BoxDecoration(
                          color: widget.isOn
                              ? const Color(0xFFFEF08A)
                              : Colors.grey.shade400,
                          borderRadius: const BorderRadius.vertical(
                            bottom: Radius.circular(20),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
