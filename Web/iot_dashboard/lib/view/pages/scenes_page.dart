import 'package:flutter/material.dart';
import '../../data/model/scene_model.dart';
import '../../data/services/firebase_realtime_service.dart';

class ScenesPage extends StatelessWidget {
  const ScenesPage({super.key});

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
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: isDark ? Colors.white : const Color(0xFF1E293B),
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Kích hoạt ngữ cảnh 1-chạm đồng loạt trên các ActionBox và thiết lập lịch tự động',
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                  ],
                ),
                ElevatedButton.icon(
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Tính năng thêm kịch bản mới đang sẵn sàng.')),
                    );
                  },
                  icon: const Icon(Icons.add_rounded, size: 18),
                  label: const Text('Thêm Kịch Bản'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF3B82F6),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // 2. LƯỚI KỊCH BẢN THÔNG MINH
            Text(
              'KỊCH BẢN NGỮ CẢNH (SCENES)',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
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
                        return _buildSceneCard(context, scene, isDark, fb);
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

  Widget _buildSceneCard(
    BuildContext context,
    SceneModel scene,
    bool isDark,
    FirebaseRealtimeService fb,
  ) {
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = scene.isActive
        ? scene.color
        : (isDark ? const Color(0xFF334155) : Colors.grey.shade200);

    return InkWell(
      onTap: () {
        fb.triggerScene(scene);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã kích hoạt kịch bản: "${scene.name}"'),
            duration: const Duration(seconds: 2),
            behavior: SnackBarBehavior.floating,
          ),
        );
      },
      borderRadius: BorderRadius.circular(20),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: cardBg,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: borderColor, width: scene.isActive ? 2.0 : 1.0),
          boxShadow: [
            BoxShadow(
              color: scene.isActive
                  ? scene.color.withValues(alpha: 0.25)
                  : Colors.black.withValues(alpha: isDark ? 0.2 : 0.03),
              blurRadius: scene.isActive ? 16 : 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: scene.color.withValues(alpha: isDark ? 0.25 : 0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(scene.icon, color: scene.color, size: 24),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: scene.isActive
                        ? scene.color
                        : (isDark ? const Color(0xFF334155) : Colors.grey.shade100),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    scene.isActive ? 'ĐANG CHẠY' : 'KÍCH HOẠT',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w800,
                      color: scene.isActive
                          ? Colors.white
                          : (isDark ? Colors.grey.shade300 : Colors.grey.shade700),
                    ),
                  ),
                ),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  scene.name,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  scene.description,
                  style: TextStyle(
                    fontSize: 11,
                    color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
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
