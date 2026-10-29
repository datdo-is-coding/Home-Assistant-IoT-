import 'package:flutter/material.dart';
import 'package:iot_dashboard/view/widgets/setting/mqtt_config_card.dart';
import 'package:iot_dashboard/view/widgets/setting/notification_alert_card.dart';
import 'package:iot_dashboard/view/widgets/setting/system_info_logout_card.dart';
import 'package:iot_dashboard/view/widgets/setting/ui_experience_card.dart';

class SettingPage extends StatelessWidget {
  const SettingPage({super.key, this.title = 'Cài đặt'});

  final String title;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 📌 1. HEADER CHUẨN DASHBOARD WEB LAYOUT
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'CÀI ĐẶT HỆ THỐNG SMART HOME',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Colors.grey,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Cấu Hình Dashboard & Kết Nối',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w800,
                        color: isDark ? Colors.white : const Color(0xFF0F172A),
                      ),
                    ),
                  ],
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.green.shade50,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: Colors.green.shade200),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: Colors.green,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 6),
                      const Text(
                        'Hệ thống hoạt động ổn định',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Colors.green,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // 📌 2. BỐ CỤC 2 CỘT RESPONSIVE CHO DASHBOARD
            LayoutBuilder(
              builder: (context, constraints) {
                bool isWideScreen = constraints.maxWidth > 900;

                Widget leftColumn = const Column(
                  children: [
                    UiExperienceCard(),
                    SizedBox(height: 20),
                    NotificationAlertCard(),
                  ],
                );

                Widget rightColumn = const Column(
                  children: [
                    MqttConfigCard(),
                    SizedBox(height: 20),
                    SystemInfoLogoutCard(),
                  ],
                );

                if (isWideScreen) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: leftColumn),
                      const SizedBox(width: 20),
                      Expanded(child: rightColumn),
                    ],
                  );
                } else {
                  return Column(
                    children: [
                      leftColumn,
                      const SizedBox(height: 20),
                      rightColumn,
                    ],
                  );
                }
              },
            ),
          ],
        ),
      ),
    );
  }
}
