import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/card/smart_home_card.dart';
import 'package:iot_dashboard/view/widgets/charts/hourly_consumption_chart.dart';
import 'package:iot_dashboard/view/widgets/common/device_power_manager.dart';
import 'package:iot_dashboard/view/widgets/home/room_device_list_card.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // CỘT BÊN TRÁI: Chiếm 45% chiều rộng home page (Biểu đồ tiêu thụ & Smart Home Card)
            Expanded(
              flex: 45,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    flex: 55,
                    child: MouseRegion(
                      cursor: SystemMouseCursors.click,
                      child: GestureDetector(
                        onTap: () {
                          // Chuyển sang Tab Báo Cáo (ReportPage - Index 1)
                          selectedPageNotifier.value = 1;
                        },
                        child: const HourlyConsumptionChart(),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Expanded(flex: 45, child: SmartHomeCard()),
                ],
              ),
            ),

            const SizedBox(width: 16),

            // CỘT BÊN PHẢI: Chiếm 55% chiều rộng (Danh sách phòng & Thiết bị điều khiển)
            Expanded(
              flex: 55,
              child: RoomDeviceListCard(
                rooms: DevicePowerManager().rooms,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
