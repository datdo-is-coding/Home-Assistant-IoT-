import 'package:flutter/material.dart';

class MiniSmartFan extends StatefulWidget {
  final bool isOn;
  final ValueChanged<bool> onToggle;

  const MiniSmartFan({super.key, required this.isOn, required this.onToggle});

  @override
  State<MiniSmartFan> createState() => _MiniSmartFanState();
}

class _MiniSmartFanState extends State<MiniSmartFan> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        widget.onToggle(!widget.isOn);
      },
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: Tooltip(
          message: widget.isOn ? 'Tắt hệ thống gió' : 'Bật hệ thống gió',
          child: Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // 1. Cột chữ bên trái (Căn lề TRÁI để lề đầu chữ thẳng tắp với chữ Đèn)
              SizedBox(
                width: 75,
                child: Text(
                  widget.isOn ? 'Gió: Bật' : 'Gió: Tắt',
                  textAlign: TextAlign.start, // 👈 Căn lề trái thẳng chữ
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.bold,
                    color: widget.isOn
                        ? Colors.cyan.shade700
                        : Colors.grey.shade600,
                  ),
                ),
              ),
              const SizedBox(width: 8),

              // 2. Cột Biểu Tượng bên phải (Cố định width 60px)
              SizedBox(
                width: 60,
                child: Center(
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    padding: const EdgeInsets.all(9),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: widget.isOn
                          ? Colors.cyan.shade400
                          : Colors.grey.shade100,
                      border: Border.all(
                        color: widget.isOn
                            ? Colors.cyan.shade200
                            : Colors.grey.shade300,
                        width: 1.5,
                      ),
                      boxShadow: widget.isOn
                          ? [
                              BoxShadow(
                                color: Colors.cyan.shade400
                                    .withValues(alpha: 0.6),
                                blurRadius: 15,
                                spreadRadius: 2,
                              ),
                            ]
                          : [],
                    ),
                    child: Icon(
                      Icons.air_rounded,
                      size: 24,
                      color: widget.isOn ? Colors.white : Colors.grey.shade600,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
