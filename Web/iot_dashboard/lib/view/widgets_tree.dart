import 'package:flutter/material.dart';
import 'package:iot_dashboard/view/widgets/cinematic/light_rays_background.dart';

import 'package:iot_dashboard/view/pages/alerts_page.dart';
import 'package:iot_dashboard/view/pages/contact_page.dart';
import 'package:iot_dashboard/view/pages/home_page.dart';
import 'package:iot_dashboard/view/pages/profile_page.dart';
import 'package:iot_dashboard/view/pages/report_page.dart';
import 'package:iot_dashboard/view/pages/setting_page.dart';
import 'package:iot_dashboard/view/pages/devices_page.dart';
import 'package:iot_dashboard/view/pages/scenes_page.dart';
import 'package:iot_dashboard/view/pages/voice_page.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/navigation/sidebar_widget.dart';
import 'package:iot_dashboard/view/widgets/navigation/topbar_widget.dart';

List<Widget> pages = const [
  HomePage(),    // Index 0: Dashboard (Trang chủ)
  DevicesPage(), // Index 1: Thiết bị & Bo Mạch (ActionBox & SubBox)
  ReportPage(),  // Index 2: Thống Kê & Điện Năng
  ScenesPage(),  // Index 3: Kịch Bản & Tự Động Hóa
  VoicePage(),   // Index 4: Giọng Nói & KWS
  AlertsPage(),  // Index 5: Cảnh Báo
  ProfilePage(), // Index 6: Hồ Sơ
  ContactPage(), // Index 7: Hỗ Trợ & Liên Hệ
  SettingPage(), // Index 8: Cài Đặt
];

class WidgetsTree extends StatelessWidget {
  const WidgetsTree({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: LightRaysBackground(
        child: Row(
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
                        final validIndex = selectedPage.clamp(0, pages.length - 1);
                        return pages[validIndex];
                      },
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
