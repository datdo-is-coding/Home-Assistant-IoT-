import 'package:flutter/material.dart';

class ContactAboutTab extends StatelessWidget {
  const ContactAboutTab({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: IntrinsicHeight(
              child: Column(
                children: [
                  // Banner Giới Thiệu Công Ty & Hệ Thống IoT
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: isDark
                            ? [const Color(0xFF0F172A), const Color(0xFF1E3A8A)]
                            : [const Color(0xFF2563EB), const Color(0xFF1D4ED8)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.blue.withValues(alpha: 0.3),
                          blurRadius: 15,
                          offset: const Offset(0, 6),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: Colors.white.withValues(alpha: 0.2),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: const Text(
                                  "SMART HOME IOT PLATFORM v2.4",
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                    letterSpacing: 1,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 12),
                              const Text(
                                "Giải Pháp Quản Lý Năng Lượng & Tự Động Hóa Toàn Diện",
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold,
                                  height: 1.3,
                                ),
                              ),
                              const SizedBox(height: 10),
                              const Text(
                                "Chúng tôi cung cấp hệ thống IoT thông minh giúp bạn theo dõi công suất tiêu thụ thời gian thực, tự động ngắt điện khi phát hiện quá tải và tối ưu hóa chi phí điện năng cho ngôi nhà của bạn.",
                                style: TextStyle(
                                  color: Colors.white70,
                                  fontSize: 14,
                                  height: 1.5,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 24),
                        Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.15),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.home_max_rounded,
                            size: 80,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 24),

                  // Thống kê thành tựu (Key Metrics Grid)
                  Row(
                    children: [
                      _buildMetricCard(
                        context,
                        "10,000+",
                        "Thiết bị kết nối",
                        Icons.memory_rounded,
                        Colors.blue,
                      ),
                      const SizedBox(width: 16),
                      _buildMetricCard(
                        context,
                        "99.9%",
                        "Độ ổn định Gateway",
                        Icons.verified_user_rounded,
                        Colors.green,
                      ),
                      const SizedBox(width: 16),
                      _buildMetricCard(
                        context,
                        "24/7",
                        "Trực cứu hộ sự cố",
                        Icons.headset_mic_rounded,
                        Colors.orange,
                      ),
                      const SizedBox(width: 16),
                      _buildMetricCard(
                        context,
                        "35%",
                        "Tiết kiệm điện trung bình",
                        Icons.eco_rounded,
                        Colors.teal,
                      ),
                    ],
                  ),

                  const SizedBox(height: 24),

                  // Giá Trị Cốt Lõi & Thông Tin Liên Hệ (Tăng chiều dài full trang)
                  Expanded(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Cột trái: Giá trị cốt lõi
                        Expanded(
                          flex: 3,
                          child: _buildCardContainer(
                            context: context,
                            title: "Sứ Mệnh & Giá Trị Cốt Lõi",
                            icon: Icons.star_rounded,
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                              children: [
                                _buildFeatureTile(
                                  icon: Icons.shield_rounded,
                                  color: Colors.redAccent,
                                  title: "An Toàn Điện Tuyệt Đối",
                                  description:
                                      "Tự động phát hiện chập mạch, rò rỉ dòng điện và ngắt Aptomat tức thì trong vòng 0.05 giây.",
                                ),
                                const Divider(height: 20),
                                _buildFeatureTile(
                                  icon: Icons.analytics_rounded,
                                  color: Colors.blueAccent,
                                  title: "Giám Sát Năng Lượng Thời Gian Thực",
                                  description:
                                      "Đo lường chính xác dòng điện, điện áp và công suất tiêu thụ theo từng phòng và từng thiết bị.",
                                ),
                                const Divider(height: 20),
                                _buildFeatureTile(
                                  icon: Icons.hub_rounded,
                                  color: Colors.purple,
                                  title: "Dễ Dàng Mở Rộng & Tích Hợp",
                                  description:
                                      "Hỗ trợ chuẩn MQTT, Zigbee, Wi-Fi. Dễ dàng đăng ký lắp đặt thêm thiết bị mới bất kỳ lúc nào.",
                                ),
                              ],
                            ),
                          ),
                        ),

                        const SizedBox(width: 20),

                        // Cột phải: Thông tin liên hệ văn phòng
                        Expanded(
                          flex: 2,
                          child: _buildCardContainer(
                            context: context,
                            title: "Văn Phòng & Tổng Đài",
                            icon: Icons.location_on_rounded,
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                _buildContactInfoItem(
                                  icon: Icons.business_rounded,
                                  title: "Trụ Sở Chính",
                                  value:
                                      "Tòa nhà IoT Tower, 123 Đường Công Nghệ, Q. Bình Thạnh, TP. Hồ Chí Minh",
                                ),
                                const SizedBox(height: 12),
                                _buildContactInfoItem(
                                  icon: Icons.phone_rounded,
                                  title: "Tổng Đài Hỗ Trợ Khách Hàng",
                                  value: "1900 8888 (08:00 - 20:00 hàng ngày)",
                                ),
                                const SizedBox(height: 12),
                                _buildContactInfoItem(
                                  icon: Icons.sos_rounded,
                                  title: "Hotline Gọi Khẩn Cấp Báo Lỗi",
                                  value: "0901 234 567 (Túc trực 24/7/365)",
                                ),
                                const SizedBox(height: 12),
                                _buildContactInfoItem(
                                  icon: Icons.email_rounded,
                                  title: "Email Tiếp Nhận",
                                  value: "support@smarthome.vn",
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
            ),
          ),
        );
      },
    );
  }

  Widget _buildCardContainer({
    required BuildContext context,
    required String title,
    required IconData icon,
    required Widget child,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;

    return Container(
      padding: const EdgeInsets.all(20.0),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 15,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.blue.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: Colors.blue, size: 20),
              ),
              const SizedBox(width: 12),
              Text(
                title,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.white : const Color(0xFF1E293B),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Divider(height: 1),
          const SizedBox(height: 16),
          Expanded(child: child),
        ],
      ),
    );
  }

  Widget _buildMetricCard(
    BuildContext context,
    String value,
    String label,
    IconData icon,
    Color color,
  ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(18),
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
                color: color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: color, size: 24),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    value,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.white : Colors.black87,
                    ),
                  ),
                  Text(
                    label,
                    style: const TextStyle(
                      fontSize: 11,
                      color: Colors.grey,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFeatureTile({
    required IconData icon,
    required Color color,
    required String title,
    required String description,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.12),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, color: color, size: 20),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                description,
                style: const TextStyle(
                  fontSize: 12,
                  color: Colors.grey,
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildContactInfoItem({
    required IconData icon,
    required String title,
    required String value,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: Colors.blue),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: Colors.grey,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                value,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
