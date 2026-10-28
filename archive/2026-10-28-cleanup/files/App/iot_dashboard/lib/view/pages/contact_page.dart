import 'package:flutter/material.dart';
import 'package:iot_dashboard/view/widgets/contact/contact_about_tab.dart';
import 'package:iot_dashboard/view/widgets/contact/contact_emergency_tab.dart';
import 'package:iot_dashboard/view/widgets/contact/contact_upgrade_tab.dart';

class ContactPage extends StatefulWidget {
  const ContactPage({super.key});

  @override
  State<ContactPage> createState() => _ContactPageState();
}

class _ContactPageState extends State<ContactPage>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  void _showEmergencyCallDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Row(
          children: [
            Icon(Icons.phone_in_talk_rounded, color: Colors.red, size: 28),
            SizedBox(width: 10),
            Text("Tổng Đài Gọi Khẩn Cấp 24/7"),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              "Đang kết nối tới đường dây nóng cứu hộ sự cố điện & thiết bị IoT...",
              style: TextStyle(fontSize: 14),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.red.shade200),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.support_agent_rounded, color: Colors.red, size: 30),
                  SizedBox(width: 12),
                  Text(
                    "HOTLINE: 1900 8888",
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: Colors.red,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text("Hủy"),
          ),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text("Đang thực hiện cuộc gọi tới 1900 8888..."),
                  backgroundColor: Colors.redAccent,
                ),
              );
            },
            icon: const Icon(Icons.call),
            label: const Text("Gọi ngay"),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 📌 HEADER CHUẨN DASHBOARD WEB
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'TRUNG TÂM HỖ TRỢ & LIÊN HỆ',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Colors.grey,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Thông Tin, Báo Lỗi & Đăng Ký Thêm Thiết Bị',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: isDark ? Colors.white : const Color(0xFF0F172A),
                      ),
                    ),
                  ],
                ),
                FilledButton.icon(
                  onPressed: _showEmergencyCallDialog,
                  icon: const Icon(Icons.sos_rounded, color: Colors.white),
                  label: const Text("GỌI SOS KHẨN CẤP"),
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.red.shade600,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 12,
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 20),

            // 📌 THANH TAB CHỌN PHÂN HỆ
            Container(
              height: 46,
              padding: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E293B) : Colors.grey.shade200,
                borderRadius: BorderRadius.circular(12),
              ),
              child: TabBar(
                controller: _tabController,
                dividerColor: Colors.transparent,
                indicatorSize: TabBarIndicatorSize.tab,
                indicator: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  color: isDark ? const Color(0xFF3B82F6) : Colors.white,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.08),
                      blurRadius: 4,
                      offset: const Offset(0, 1),
                    ),
                  ],
                ),
                labelColor: isDark ? Colors.white : const Color(0xFF1E293B),
                unselectedLabelColor: Colors.grey.shade600,
                labelStyle: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
                tabs: const [
                  Tab(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.info_outline_rounded, size: 18),
                        SizedBox(width: 8),
                        Text('Giới thiệu About Us'),
                      ],
                    ),
                  ),
                  Tab(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.emergency_rounded, size: 18),
                        SizedBox(width: 8),
                        Text('Báo lỗi khẩn cấp 24/7'),
                      ],
                    ),
                  ),
                  Tab(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.space_dashboard_rounded, size: 18),
                        SizedBox(width: 8),
                        Text('Đăng ký nâng cấp thiết bị'),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // 📌 KHUNG VIEW CHÍNH CHO 3 TAB
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  const ContactAboutTab(),
                  ContactEmergencyTab(
                    onEmergencyCallRequested: _showEmergencyCallDialog,
                  ),
                  const ContactUpgradeTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
