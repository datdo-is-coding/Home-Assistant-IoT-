import 'package:flutter/material.dart';
import '../../data/model/scene_model.dart';
import '../../data/services/firebase_realtime_service.dart';
import '../widgets/mobile_parity/scene_card.dart';

class ScenesPage extends StatelessWidget {
  const ScenesPage({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final fb = FirebaseRealtimeService();

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. TIÊU ĐỀ
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Kịch Bản & Tự Động Hóa',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        color: theme.colorScheme.onSurface,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Kích hoạt ngữ cảnh 1-chạm đồng loạt trên các ActionBox và thiết lập lịch tự động',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                ElevatedButton.icon(
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Tính năng tạo kịch bản mới đang sẵn sàng.')),
                    );
                  },
                  icon: const Icon(Icons.add_rounded, size: 18),
                  label: const Text('Thêm Kịch Bản'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: theme.colorScheme.onPrimary,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // 2. LƯỚI KỊCH BẢN THÔNG MINH
            Text(
              'KỊCH BẢN NGỮ CẢNH (SCENES)',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 14),

            ValueListenableBuilder<List<SceneModel>>(
              valueListenable: fb.scenesNotifier,
              builder: (context, scenes, child) {
                return LayoutBuilder(
                  builder: (context, constraints) {
                    final crossAxisCount = constraints.maxWidth > 900 ? 4 : (constraints.maxWidth > 600 ? 2 : 1);
                    return GridView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: crossAxisCount,
                        crossAxisSpacing: 16,
                        mainAxisSpacing: 16,
                        childAspectRatio: 1.35,
                      ),
                      itemCount: scenes.length,
                      itemBuilder: (context, index) {
                        final scene = scenes[index];
                        return ParitySceneCard(
                          scene: scene,
                          onActivate: () {
                            fb.triggerScene(scene);
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('Đã kích hoạt kịch bản: "${scene.name}"'),
                                duration: const Duration(seconds: 2),
                                behavior: SnackBarBehavior.floating,
                              ),
                            );
                          },
                        );
                      },
                    );
                  },
                );
              },
            ),

            const SizedBox(height: 32),

            // 3. TỰ ĐỘNG HÓA THEO LỊCH (AUTOMATIONS)
            Text(
              'LỊCH TRÌNH TỰ ĐỘNG (SCHEDULED AUTOMATIONS)',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
              ),
            ),
            const SizedBox(height: 14),

            _buildAutomationItem(
              context,
              title: 'Hẹn giờ tắt đèn ban đêm',
              timeRange: '23:00 mỗi ngày',
              description: 'Tự động tắt đèn chùm phòng khách và kiểm tra relay ActionBox',
              isEnabled: true,
              isDark: isDark,
            ),
            const SizedBox(height: 12),
            _buildAutomationItem(
              context,
              title: 'Chế độ an toàn tiết kiệm điện',
              timeRange: 'Khi không phát hiện chuyển động sau 30 phút',
              description: 'Tắt quạt và chuyển điều hòa sang chế độ Eco',
              isEnabled: false,
              isDark: isDark,
            ),
            const SizedBox(height: 12),
            _buildAutomationItem(
              context,
              title: 'Đánh thức buổi sáng',
              timeRange: '06:30 từ Thứ Hai - Thứ Sáu',
              description: 'Mở đèn ngủ, bật quạt và gửi thông báo sẵn sàng',
              isEnabled: true,
              isDark: isDark,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAutomationItem(
    BuildContext context, {
    required String title,
    required String timeRange,
    required String description,
    required bool isEnabled,
    required bool isDark,
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
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFF3B82F6).withValues(alpha: isDark ? 0.2 : 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.alarm_rounded, color: Color(0xFF3B82F6), size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: isDark ? Colors.white : const Color(0xFF1E293B),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: isDark ? const Color(0xFF334155) : Colors.grey.shade100,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        timeRange,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: TextStyle(
                    fontSize: 12,
                    color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value: isEnabled,
            activeThumbColor: const Color(0xFF3B82F6),
            onChanged: (val) {},
          ),
        ],
      ),
    );
  }
}
