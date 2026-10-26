import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/common/fan_animation.dart';
import 'package:iot_dashboard/view/widgets/common/lamp_animation.dart';

class SmartHomeCard extends StatefulWidget {
  const SmartHomeCard({super.key});

  @override
  State<SmartHomeCard> createState() => _SmartHomeCardState();
}

class _SmartHomeCardState extends State<SmartHomeCard> {
  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 20,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. HEADER: CHẾ ĐỘ NHANH & BADGE TRẠNG THÁI
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: Colors.amber.shade50.withValues(alpha: isDark ? 0.2 : 1.0),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      Icons.bolt_rounded,
                      size: 20,
                      color: Colors.amber.shade700,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    'Chế độ nhanh',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.white : const Color(0xFF1E293B),
                    ),
                  ),
                ],
              ),
              ValueListenableBuilder<bool>(
                valueListenable: isAwayModeNotifier,
                builder: (context, isAway, child) {
                  return Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: isAway
                          ? Colors.orange.shade50.withValues(alpha: isDark ? 0.2 : 1.0)
                          : const Color(0xFFECFDF5).withValues(alpha: isDark ? 0.2 : 1.0),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: isAway ? Colors.orange.shade200 : const Color(0xFFA7F3D0),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isAway ? Colors.orange : const Color(0xFF10B981),
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          isAway ? 'Ra khỏi nhà' : 'Đang ở nhà',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: isAway ? Colors.orange.shade800 : const Color(0xFF10B981),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ],
          ),

          const SizedBox(height: 16),

          // 2. KHU VỰC ĐIỀU KHIỂN: THẺ Ở NHÀ/RA KHỎI NHÀ + ĐÈN & GIÓ
          Expanded(
            child: Row(
              children: [
                // Thẻ Trái: Nút chuyển nhanh Ở nhà / Ra khỏi nhà
                Expanded(
                  flex: 5,
                  child: ValueListenableBuilder<bool>(
                    valueListenable: isAwayModeNotifier,
                    builder: (context, isAway, child) {
                      return InkWell(
                        onTap: () {
                          final currentAway = isAwayModeNotifier.value;
                          isAwayModeNotifier.value = !currentAway;
                          if (!currentAway) {
                            isLampOnNotifier.value = false;
                            isFanOnNotifier.value = false;
                          }
                        },
                        borderRadius: BorderRadius.circular(16),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            gradient: isAway
                                ? const LinearGradient(
                                    colors: [
                                      Color(0xFF334155),
                                      Color(0xFF0F172A),
                                    ],
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                  )
                                : const LinearGradient(
                                    colors: [
                                      Color(0xFF3B82F6),
                                      Color(0xFF1D4ED8),
                                    ],
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                  ),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: (isAway ? const Color(0xFF334155) : Colors.blue)
                                    .withValues(alpha: 0.3),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      color: Colors.white.withValues(alpha: 0.2),
                                      shape: BoxShape.circle,
                                    ),
                                    child: Icon(
                                      isAway
                                          ? Icons.sensor_door_rounded
                                          : Icons.home_rounded,
                                      color: Colors.white,
                                      size: 24,
                                    ),
                                  ),
                                  const Icon(
                                    Icons.touch_app_rounded,
                                    color: Colors.white70,
                                    size: 18,
                                  ),
                                ],
                              ),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    isAway ? 'CHẾ ĐỘ VẮNG MẶT' : 'CHẾ ĐỘ Ở NHÀ',
                                    style: const TextStyle(
                                      color: Colors.white70,
                                      fontSize: 10,
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 0.8,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    isAway ? 'Ra khỏi nhà' : 'Đang ở nhà',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),

                const SizedBox(width: 12),

                // Thẻ Phải: Điều khiển nhanh Đèn & Gió
                Expanded(
                  flex: 6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 12,
                    ),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: isDark ? const Color(0xFF334155) : Colors.grey.shade200,
                      ),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: [
                        ValueListenableBuilder<bool>(
                          valueListenable: isLampOnNotifier,
                          builder: (context, isLampOn, child) {
                            return MiniSmartLamp(
                              isOn: isLampOn,
                              onToggle: (newState) {
                                isLampOnNotifier.value = newState;
                              },
                            );
                          },
                        ),
                        Divider(
                          height: 1,
                          color: isDark ? const Color(0xFF334155) : Colors.grey.shade200,
                        ),
                        ValueListenableBuilder<bool>(
                          valueListenable: isFanOnNotifier,
                          builder: (context, isFanOn, child) {
                            return MiniSmartFan(
                              isOn: isFanOn,
                              onToggle: (newState) {
                                isFanOnNotifier.value = newState;
                              },
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
