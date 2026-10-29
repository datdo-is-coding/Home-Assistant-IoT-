import 'package:flutter/material.dart';
import '../../data/model/action_box_model.dart';
import '../../data/services/firebase_realtime_service.dart';
import '../widgets/mobile_parity/action_box_card.dart';

class DevicesPage extends StatelessWidget {
  const DevicesPage({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final fb = FirebaseRealtimeService();

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. TIÊU ĐỀ & TRẠNG THÁI TỔNG QUAN
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Quản Lý Thiết Bị & Bo Mạch',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: theme.colorScheme.onSurface,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Giám sát phần cứng ActionBox 3 Relay + BL0942 và SubBox điều phối KWS',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                ValueListenableBuilder<bool>(
                  valueListenable: fb.isConnectedNotifier,
                  builder: (context, connected, child) {
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: connected
                            ? const Color(0xFF10B981).withValues(alpha: isDark ? 0.2 : 0.1)
                            : Colors.orange.withValues(alpha: isDark ? 0.2 : 0.1),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: connected ? const Color(0xFF10B981) : Colors.orange,
                          width: 1.2,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: connected ? const Color(0xFF10B981) : Colors.orange,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            connected ? 'Firebase RTDB Đang Kết Nối' : 'Chờ Kết Nối Cloud',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                              color: connected ? const Color(0xFF10B981) : Colors.orange.shade800,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ],
            ),

            const SizedBox(height: 20),

            // 2. THẺ THỐNG KÊ NHANH
            Row(
              children: [
                Expanded(
                  child: _buildSummaryCard(
                    context,
                    title: 'Bo Mạch Trực Tuyến',
                    valueListenable: fb.onlineCountNotifier,
                    suffix: 'trực tuyến',
                    icon: Icons.router_rounded,
                    color: const Color(0xFF3B82F6),
                    isDark: isDark,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _buildSummaryCard(
                    context,
                    title: 'Tổng Công Suất Tải',
                    valueListenable: fb.totalPowerNotifier,
                    suffix: 'Watts',
                    icon: Icons.bolt_rounded,
                    color: const Color(0xFFF59E0B),
                    isDark: isDark,
                    isDouble: true,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _buildSummaryCard(
                    context,
                    title: 'Tổng Điện Năng',
                    valueListenable: fb.totalEnergyNotifier,
                    suffix: 'kWh',
                    icon: Icons.energy_savings_leaf_rounded,
                    color: const Color(0xFF10B981),
                    isDark: isDark,
                    isDouble: true,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _buildSummaryCard(
                    context,
                    title: 'Tổng Thiết Bị Đo',
                    valueListenable: fb.totalDeviceCountNotifier,
                    suffix: 'thiết bị',
                    icon: Icons.devices_rounded,
                    color: const Color(0xFF8B5CF6),
                    isDark: isDark,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // 3. DANH SÁCH CÁC BO MẠCH PHẦN CỨNG
            ValueListenableBuilder<List<ActionBoxModel>>(
              valueListenable: fb.actionBoxesNotifier,
              builder: (context, boxes, child) {
                if (boxes.isEmpty) {
                  return const Center(
                    child: Padding(
                      padding: EdgeInsets.all(40),
                      child: CircularProgressIndicator(),
                    ),
                  );
                }

                return ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: boxes.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 20),
                  itemBuilder: (context, index) {
                    final box = boxes[index];
                    return ParityActionBoxCard(
                      actionBox: box,
                      onTap: () {},
                      onToggleChannel: (chKey, newState) {
                        fb.toggleChannel(box.id, chKey, newState);
                      },
                    );
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryCard(
    BuildContext context, {
    required String title,
    required ValueNotifier valueListenable,
    required String suffix,
    required IconData icon,
    required Color color,
    required bool isDark,
    bool isDouble = false,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF161B26) : Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: isDark ? const Color(0xFF232B3B) : const Color(0xFFE5E7EB),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withValues(alpha: isDark ? 0.2 : 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 24),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 12,
                    color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 4),
                ValueListenableBuilder(
                  valueListenable: valueListenable,
                  builder: (context, val, child) {
                    final displayStr = isDouble
                        ? (val as double).toStringAsFixed(1)
                        : val.toString();
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          displayStr,
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                            color: isDark ? Colors.white : const Color(0xFF1E293B),
                          ),
                        ),
                        const SizedBox(width: 4),
                        Text(
                          suffix,
                          style: TextStyle(
                            fontSize: 11,
                            color: isDark ? Colors.grey.shade400 : Colors.grey.shade500,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
