import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:iot_dashboard/data/constants.dart';
import 'package:iot_dashboard/data/model/device_model.dart';
import 'package:iot_dashboard/view/widgets/common/device_power_manager.dart';

class DeviceHourlyConsumptionChart extends StatefulWidget {
  final List<DeviceModel>? devices;

  const DeviceHourlyConsumptionChart({super.key, this.devices});

  @override
  State<DeviceHourlyConsumptionChart> createState() =>
      _DeviceHourlyConsumptionChartState();
}

class _DeviceHourlyConsumptionChartState
    extends State<DeviceHourlyConsumptionChart> {
  int? touchedIndex;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);

    final int currentHour = DateTime.now().hour;

    // Đồng bộ danh sách thiết bị từ DevicePowerManager nếu không truyền ngoài vào
    final List<DeviceModel> activeDevices =
        widget.devices ?? DevicePowerManager().getAllDevices();

    // Chuẩn hóa danh sách thiết bị cho biểu đồ, cấp dữ liệu mặc định nếu chưa có hourlyKwh
    final List<DeviceModel> chartDevices = activeDevices.map((dev) {
      if (dev.hourlyKwh != null && dev.hourlyKwh!.isNotEmpty) {
        return dev;
      }
      // Tạo dữ liệu mặc định theo công suất thiết bị nếu hourlyKwh bị trống
      final double baseKwhPerHour = (dev.powerWatts * 0.0008).clamp(0.02, 1.5);
      final fallbackList = List.generate(
        24,
        (i) => double.parse((baseKwhPerHour * (0.8 + (i % 5) * 0.1)).toStringAsFixed(2)),
      );
      return DeviceModel(
        id: dev.id,
        name: dev.name,
        icon: dev.icon,
        isOn: dev.isOn,
        powerWatts: dev.powerWatts,
        color: dev.color,
        hourlyKwh: fallbackList,
      );
    }).toList();

    // Tính tổng kWh toàn hệ thống hôm nay
    final double grandTotalToday = chartDevices.fold(
      0.0,
      (sum, dev) => sum + dev.getTotalUntilCurrentHour(currentHour),
    );

    // Tìm giá trị kWh lớn nhất của 1 thiết bị để làm max Y
    final double maxDeviceKwh = chartDevices.fold(
      0.0,
      (maxVal, dev) {
        final total = dev.getTotalUntilCurrentHour(currentHour);
        return total > maxVal ? total : maxVal;
      },
    );

    final double maxY = (maxDeviceKwh * 1.25).clamp(1.0, 100.0);

    return Container(
      padding: const EdgeInsets.all(AppSizes.lg),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSizes.radiusLg),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 15,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. Header: Tiêu đề & Cập nhật giờ hiện tại
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Tiêu Thụ Theo Thiết Bị Trong Ngày',
                    style: TextStyle(
                      fontSize: AppFontSizes.titleMedium,
                      fontWeight: FontWeight.bold,
                      color: AppColors.titleColor(context),
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Cột tích lũy theo từng tiếng (Đến ${currentHour.toString().padLeft(2, '0')}:00 hiện tại)',
                    style: TextStyle(
                      fontSize: AppFontSizes.caption,
                      color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade700,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E3A8A).withValues(alpha: 0.5)
                      : Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(AppSizes.radiusFull),
                  border: Border.all(
                    color: isDark ? const Color(0xFF3B82F6) : Colors.blue.shade200,
                  ),
                ),
                child: Text(
                  'Tổng: ${grandTotalToday.toStringAsFixed(2)} kWh',
                  style: TextStyle(
                    fontSize: AppFontSizes.bodySmall,
                    fontWeight: FontWeight.bold,
                    color: isDark ? const Color(0xFF93C5FD) : Colors.blue.shade800,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSizes.xl),

          // 2. BIỂU ĐỒ CỘT DỌC SYNCHRONIZED
          SizedBox(
            height: 250,
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: maxY,
                barTouchData: BarTouchData(
                  touchCallback: (FlTouchEvent event, barTouchResponse) {
                    setState(() {
                      if (!event.isInterestedForInteractions ||
                          barTouchResponse == null ||
                          barTouchResponse.spot == null) {
                        touchedIndex = -1;
                        return;
                      }
                      touchedIndex =
                          barTouchResponse.spot!.touchedBarGroupIndex;
                    });
                  },
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipItem: (group, groupIndex, rod, rodIndex) {
                      final dev = chartDevices[groupIndex];
                      final devKwh = dev.getTotalUntilCurrentHour(currentHour);
                      final percent = grandTotalToday > 0
                          ? (devKwh / grandTotalToday * 100).toStringAsFixed(1)
                          : '0.0';
                      return BarTooltipItem(
                        '${dev.name}\n⚡ ${devKwh.toStringAsFixed(2)} kWh ($percent%)\nCông suất: ${dev.powerWatts}W',
                        const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      );
                    },
                  ),
                ),
                titlesData: FlTitlesData(
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 44,
                      getTitlesWidget: (value, meta) {
                        final index = value.toInt();
                        if (index < 0 || index >= chartDevices.length) {
                          return const SizedBox.shrink();
                        }
                        final dev = chartDevices[index];
                        final isTouched = index == touchedIndex;
                        final devColor = dev.color ?? AppColors.info;

                        return Padding(
                          padding: const EdgeInsets.only(top: 8.0),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                dev.name,
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                  color: isTouched
                                      ? devColor
                                      : AppColors.titleColor(context),
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '${dev.getTotalUntilCurrentHour(currentHour).toStringAsFixed(1)} kWh',
                                style: TextStyle(
                                  fontSize: 9.5,
                                  color: isTouched
                                      ? devColor.withValues(alpha: 0.9)
                                      : AppColors.subtleColor(context),
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 40,
                      getTitlesWidget: (value, meta) {
                        final formattedVal = value >= 1000
                            ? '${(value / 1000).toStringAsFixed(1)}k'
                            : value.toStringAsFixed(1);
                        return Text(
                          formattedVal,
                          style: TextStyle(
                            fontSize: 11,
                            color: AppColors.subtleColor(context),
                            fontWeight: FontWeight.w500,
                          ),
                        );
                      },
                    ),
                  ),
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                ),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: maxY > 10 ? 5.0 : 1.0,
                  getDrawingHorizontalLine: (value) => FlLine(
                    color: borderColor,
                    strokeWidth: 1,
                  ),
                ),
                borderData: FlBorderData(show: false),
                barGroups: List.generate(chartDevices.length, (index) {
                  final dev = chartDevices[index];
                  final isTouched = index == touchedIndex;
                  final double devTotalKwh =
                      dev.getTotalUntilCurrentHour(currentHour);
                  final devColor = dev.color ?? AppColors.info;

                  return BarChartGroupData(
                    x: index,
                    barRods: [
                      BarChartRodData(
                        toY: devTotalKwh == 0 ? 0.05 : devTotalKwh,
                        gradient: LinearGradient(
                          begin: Alignment.bottomCenter,
                          end: Alignment.topCenter,
                          colors: [
                            devColor.withValues(alpha: touchedIndex != null && touchedIndex! >= 0 ? (isTouched ? 0.9 : 0.4) : 0.7),
                            devColor.withValues(alpha: touchedIndex != null && touchedIndex! >= 0 ? (isTouched ? 1.0 : 0.5) : 1.0),
                          ],
                        ),
                        width: 16, // Kích thước cố định để không bị xô lệch layout khi chạm
                        borderRadius: const BorderRadius.only(
                          topLeft: Radius.circular(6),
                          topRight: Radius.circular(6),
                        ),
                        backDrawRodData: BackgroundBarChartRodData(
                          show: true,
                          toY: maxY,
                          color: AppColors.inputBg(context),
                        ),
                      ),
                    ],
                  );
                }),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
