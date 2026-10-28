import 'package:flutter/material.dart';

import 'package:iot_dashboard/view/pages/alerts_page.dart';
import 'package:iot_dashboard/view/pages/contact_page.dart';
import 'package:iot_dashboard/view/pages/home_page.dart';
import 'package:iot_dashboard/view/pages/profile_page.dart';
import 'package:iot_dashboard/view/pages/report_page.dart';
import 'package:iot_dashboard/view/pages/setting_page.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/navigation/sidebar_widget.dart';
import 'package:iot_dashboard/view/widgets/navigation/topbar_widget.dart';

List<Widget> pages = [
  HomePage(), // Index 0: Dashboard (Trang chủ)
  ReportPage(), // Index 1: Report (Báo cáo)
  ProfilePage(), // Index 2: Profile (Hồ sơ)
  AlertsPage(), // Index 3: About (Giới thiệu)
  ContactPage(), // Index 4: Contact (Liên hệ)
  SettingPage(), // Index 5: Setting (Cài đặt)
];

class WidgetsTree extends StatelessWidget {
  const WidgetsTree({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          // 1. Sidebar bên trái (Luôn hiển thị và co giãn mượt theo isSidebarOpenNotifier)
          const SidebarWidget(),

          // 2. Khu vực chính bên phải (Topbar + Nội dung trang)
          Expanded(
            child: Column(
              children: [
                // TopBar nằm cố định phía trên
                const TopbarWidget(),

                // Màn hình trang được chọn bên dưới
                Expanded(
                  child: ValueListenableBuilder<int>(
                    valueListenable: selectedPageNotifier,
                    builder: (context, selectedPage, child) {
                      return pages[selectedPage];
                    },
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
