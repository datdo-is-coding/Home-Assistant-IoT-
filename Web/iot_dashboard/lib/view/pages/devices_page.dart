import 'package:flutter/material.dart';
import '../../data/model/action_box_model.dart';
import '../../data/services/firebase_realtime_service.dart';

class DevicesPage extends StatelessWidget {
  const DevicesPage({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fb = FirebaseRealtimeService();

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
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
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: isDark ? Colors.white : const Color(0xFF1E293B),
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Giám sát phần cứng ActionBox 3 Relay + BL0942 và SubBox điều phối KWS',
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
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
                    return _buildActionBoxCard(context, box, isDark, fb);
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
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isDark ? const Color(0xFF334155) : Colors.grey.shade200,
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

  Widget _buildActionBoxCard(
    BuildContext context,
    ActionBoxModel box,
    bool isDark,
    FirebaseRealtimeService fb,
  ) {
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
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.03),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // HEADER BO MẠCH
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: (box.isSubBox ? const Color(0xFF8B5CF6) : const Color(0xFF3B82F6))
                          .withValues(alpha: isDark ? 0.25 : 0.12),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      box.isSubBox ? Icons.record_voice_over_rounded : Icons.developer_board_rounded,
                      color: box.isSubBox ? const Color(0xFF8B5CF6) : const Color(0xFF3B82F6),
                      size: 26,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            box.name,
                            style: TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w800,
                              color: isDark ? Colors.white : const Color(0xFF1E293B),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: isDark ? const Color(0xFF334155) : Colors.grey.shade100,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              box.id,
                              style: TextStyle(
                                fontSize: 11,
                                fontFamily: 'monospace',
                                color: isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Vị trí: ${box.room}  ·  IP: ${box.ip}  ·  FW: ${box.firmwareVersion}',
                        style: TextStyle(
                          fontSize: 12,
                          color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              // TRẠNG THÁI ONLINE / OFFLINE
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: box.online
                      ? const Color(0xFF10B981).withValues(alpha: isDark ? 0.2 : 0.1)
                      : Colors.red.withValues(alpha: isDark ? 0.2 : 0.1),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: box.online ? const Color(0xFF10B981) : Colors.red,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 7,
                      height: 7,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: box.online ? const Color(0xFF10B981) : Colors.red,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      box.online ? 'Trực tuyến' : 'Ngoại tuyến (15s)',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: box.online ? const Color(0xFF10B981) : Colors.red,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          if (box.channels.isNotEmpty) ...[
            const SizedBox(height: 20),
            const Divider(height: 1),
            const SizedBox(height: 16),
            Text(
              'CÁC KÊNH RELAY & ĐO CÔNG SUẤT BL0942',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
              ),
            ),
            const SizedBox(height: 12),
            // LƯỚI KÊNH RELAY
            Row(
              children: box.channels.map((ch) {
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(right: 12),
                    child: _buildChannelCard(context, box.id, ch, isDark, fb),
                  ),
                );
              }).toList(),
            ),
          ] else if (box.isSubBox) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: isDark ? const Color(0xFF334155) : Colors.grey.shade200,
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.mic_rounded, color: Color(0xFF8B5CF6), size: 22),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'SubBox tiếp nhận từ khóa giọng nói đánh thức (KWS offline) và điều phối phát âm thanh phản hồi.',
                      style: TextStyle(
                        fontSize: 12,
                        color: isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildChannelCard(
    BuildContext context,
    String boxId,
    ActionBoxChannelModel ch,
    bool isDark,
    FirebaseRealtimeService fb,
  ) {
    final bgColor = isDark
        ? (ch.state ? ch.accentColor.withValues(alpha: 0.15) : const Color(0xFF0F172A))
        : (ch.state ? ch.accentColor.withValues(alpha: 0.08) : const Color(0xFFF8FAFC));

    final borderColor = ch.state
        ? ch.accentColor.withValues(alpha: 0.5)
        : (isDark ? const Color(0xFF334155) : Colors.grey.shade200);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: borderColor, width: 1.2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(ch.iconData, color: ch.accentColor, size: 20),
                  const SizedBox(width: 8),
                  Text(
                    ch.channelKey.toUpperCase(),
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
              Transform.scale(
                scale: 0.8,
                child: Switch(
                  value: ch.state,
                  activeThumbColor: ch.accentColor,
                  onChanged: (val) {
                    fb.toggleChannel(boxId, ch.channelKey, val);
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            ch.name,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: isDark ? Colors.white : const Color(0xFF1E293B),
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 12),
          // THỐNG SỐ BL0942
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildMetricItem('Công suất', '${ch.power.toStringAsFixed(1)}W', isDark),
              _buildMetricItem('Điện áp', '${ch.voltage.toStringAsFixed(0)}V', isDark),
              _buildMetricItem('Dòng', '${(ch.current * 1000).toStringAsFixed(0)}mA', isDark),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetricItem(String label, String value, bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 9,
            color: isDark ? Colors.grey.shade400 : Colors.grey.shade500,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w800,
            color: isDark ? Colors.white : const Color(0xFF1E293B),
          ),
        ),
      ],
    );
  }
}
