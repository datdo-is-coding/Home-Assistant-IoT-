import 'package:flutter/material.dart';
import 'package:iot_dashboard/view/widgets/charts/device_hourly_consumption_chart.dart';
import 'package:iot_dashboard/view/widgets/charts/monthly_tariff_card.dart';
import 'package:iot_dashboard/view/widgets/charts/quarterly_consumption_chart.dart';
import 'package:iot_dashboard/view/widgets/charts/weekly_consumption_chart.dart';

class ReportPage extends StatefulWidget {
  const ReportPage({super.key});

  @override
  State<ReportPage> createState() => _ReportPageState();
}

class _ReportPageState extends State<ReportPage> {
  // Dữ liệu mẫu (Mock data)
  final List<double> weeklyData = [12.4, 15.0, 11.2, 14.8, 19.5, 22.1, 16.0]; // Tuần này
  final List<double> lastWeekData = [10.5, 13.2, 12.8, 12.0, 17.4, 20.1, 14.2]; // Tuần trước
  final List<String> quarterMonths = ['Tháng 6', 'Tháng 7', 'Tháng 8'];
  final List<double> quarterKwh = [310.0, 395.0, 345.0];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 1. BIỂU ĐỒ TIÊU THỤ THIẾT BỊ THEO GIỜ HÔM NAY
            const DeviceHourlyConsumptionChart(),

            const SizedBox(height: 20),

            // 2. CHART TÍNH TIỀN ĐIỆN VÀ CẢNH BÁO TỰ ĐỘNG
            MonthlyTariffCard(
              currentKwh: 345.0,
              dayOfMonth: 18,
              totalDaysInMonth: 31,
            ),

            const SizedBox(height: 20),

            // 3. HAI BIỂU ĐỒ SONG SONG (TUẦN & 3 THÁNG)
            SizedBox(
              height: 320,
              child: Row(
                children: [
                  // Biểu đồ Tuần (Chiếm 50% width)
                  Expanded(
                    child: WeeklyConsumptionChart(
                      weeklyKwh: weeklyData,
                      lastWeekKwh: lastWeekData,
                    ),
                  ),
                  const SizedBox(width: 20),
                  // Biểu đồ 3 Tháng (Chiếm 50% width)
                  Expanded(
                    child: QuarterlyConsumptionChart(
                      monthNames: quarterMonths,
                      monthlyKwh: quarterKwh,
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
