import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:iot_dashboard/data/constants.dart';

class WeeklyConsumptionChart extends StatelessWidget {
  final List<double> weeklyKwh; // Dữ liệu tuần này
  final List<double>? lastWeekKwh; // Dữ liệu tuần trước (cột xám bên trái)

  const WeeklyConsumptionChart({
    super.key,
    required this.weeklyKwh,
    this.lastWeekKwh,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);

    final days = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

    // Dữ liệu tuần trước mặc định nếu không được truyền vào
    final List<double> defaultLastWeek = [10.5, 13.2, 12.8, 12.0, 17.4, 20.1, 14.2];
    final List<double> effectiveLastWeek = lastWeekKwh ?? defaultLastWeek;

    // Tìm giá trị cao nhất & trung bình tuần này
    double maxThisWeek = weeklyKwh.isEmpty ? 0 : weeklyKwh.reduce((a, b) => a > b ? a : b);
    double maxLastWeek = effectiveLastWeek.isEmpty ? 0 : effectiveLastWeek.reduce((a, b) => a > b ? a : b);
    double maxKwh = maxThisWeek > maxLastWeek ? maxThisWeek : maxLastWeek;
    if (maxKwh == 0) maxKwh = 10;

    double avgKwh = weeklyKwh.isEmpty ? 0 : weeklyKwh.reduce((a, b) => a + b) / weeklyKwh.length;
    int maxIndex = weeklyKwh.isEmpty ? -1 : weeklyKwh.indexOf(maxThisWeek);

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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Tiêu thụ theo Tuần',
                style: TextStyle(
                  fontSize: AppFontSizes.titleMedium,
                  fontWeight: FontWeight.bold,
                  color: AppColors.titleColor(context),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSizes.sm + 2,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E3A8A).withValues(alpha: 0.5)
                      : Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                  border: Border.all(
                    color: isDark ? const Color(0xFF3B82F6) : Colors.blue.shade200,
                  ),
                ),
                child: Text(
                  'TB: ${avgKwh.toStringAsFixed(1)} kWh/ngày',
                  style: TextStyle(
                    fontSize: AppFontSizes.bodySmall,
                    color: isDark ? const Color(0xFF93C5FD) : Colors.blue.shade800,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.sm),
          // Chú thích (Legend) cho Tuần trước và Tuần này
          Row(
            children: [
              _buildLegendItem(
                context: context,
                color: isDark ? Colors.grey.shade600 : Colors.grey.shade400,
                label: 'Tuần trước',
              ),
              const SizedBox(width: AppSizes.md),
              _buildLegendItem(
                context: context,
                color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade500,
                label: 'Tuần này',
              ),
            ],
          ),
          const SizedBox(height: AppSizes.md),
          Expanded(
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: maxKwh * 1.2,
                barTouchData: BarTouchData(
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipItem: (group, groupIndex, rod, rodIndex) {
                      String weekLabel = rodIndex == 0 ? 'Tuần trước' : 'Tuần này';
                      return BarTooltipItem(
                        '${days[group.x.toInt()]}\n$weekLabel: ${rod.toY.toStringAsFixed(1)} kWh',
                        const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                      );
                    },
                  ),
                ),
                titlesData: FlTitlesData(
                  show: true,
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 30,
                      getTitlesWidget: (value, meta) => Text(
                        '${value.toInt()}',
                        style: TextStyle(
                          fontSize: AppFontSizes.caption,
                          color: AppColors.subtleColor(context),
                        ),
                      ),
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (value, meta) {
                        int index = value.toInt();
                        if (index >= 0 && index < days.length) {
                          bool isMax = index == maxIndex;
                          return Padding(
                            padding: const EdgeInsets.only(top: 8.0),
                            child: Text(
                              days[index],
                              style: TextStyle(
                                fontSize: AppFontSizes.bodySmall,
                                fontWeight: isMax
                                    ? FontWeight.bold
                                    : FontWeight.normal,
                                color: isMax
                                    ? AppColors.warning
                                    : AppColors.titleColor(context),
                              ),
                            ),
                          );
                        }
                        return const Text('');
                      },
                    ),
                  ),
                ),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: 5,
                  getDrawingHorizontalLine: (value) => FlLine(
                    color: borderColor,
                    strokeWidth: 1,
                  ),
                ),
                borderData: FlBorderData(show: false),
                barGroups: List.generate(weeklyKwh.length, (index) {
                  bool isMax = index == maxIndex;
                  double lastWeekVal = index < effectiveLastWeek.length ? effectiveLastWeek[index] : 0.0;
                  double thisWeekVal = weeklyKwh[index];

                  return BarChartGroupData(
                    x: index,
                    barsSpace: 4,
                    barRods: [
                      // Cột 1 (Bên trái): Tuần trước
                      BarChartRodData(
                        toY: lastWeekVal,
                        color: isDark ? Colors.grey.shade600 : Colors.grey.shade400,
                        width: 10,
                        borderRadius: BorderRadius.circular(AppSizes.xs),
                      ),
                      // Cột 2 (Bên phải): Tuần này
                      BarChartRodData(
                        toY: thisWeekVal,
                        color: isMax
                            ? AppColors.warning
                            : (isDark ? const Color(0xFF60A5FA) : Colors.blue.shade500),
                        width: 10,
                        borderRadius: BorderRadius.circular(AppSizes.xs),
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

  Widget _buildLegendItem({
    required BuildContext context,
    required Color color,
    required String label,
  }) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            fontSize: AppFontSizes.bodySmall,
            color: AppColors.subtleColor(context),
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
