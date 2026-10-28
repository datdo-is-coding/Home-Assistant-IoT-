import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:iot_dashboard/data/constants.dart';

class QuarterlyConsumptionChart extends StatelessWidget {
  final List<String> monthNames; // Ví dụ: ['Tháng 6', 'Tháng 7', 'Tháng 8']
  final List<double> monthlyKwh; // Ví dụ: [310.0, 395.0, 345.0]

  const QuarterlyConsumptionChart({
    super.key,
    required this.monthNames,
    required this.monthlyKwh,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);

    // Tính % chênh lệch giữa tháng hiện tại và tháng trước
    double prevKwh = monthlyKwh.length >= 2
        ? monthlyKwh[monthlyKwh.length - 2]
        : 0;
    double currentKwh = monthlyKwh.isNotEmpty ? monthlyKwh.last : 0;
    double percentChange = prevKwh > 0
        ? ((currentKwh - prevKwh) / prevKwh) * 100
        : 0;
    bool isIncreased = percentChange > 0;

    // Tính toán minY và maxY để đường biểu đồ cân đối
    double minKwh = monthlyKwh.isEmpty
        ? 0
        : monthlyKwh.reduce((a, b) => a < b ? a : b);
    double maxKwh = monthlyKwh.isEmpty
        ? 100
        : monthlyKwh.reduce((a, b) => a > b ? a : b);

    double range = maxKwh - minKwh;
    double yPadding = range == 0 ? 50 : range * 0.35;
    double minY = (minKwh - yPadding) > 0 ? (minKwh - yPadding) : 0;
    double maxY = maxKwh + yPadding;

    double yInterval = ((maxY - minY) / 4).clamp(10.0, 500.0);

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
                '3 Tháng gần nhất',
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
                  color: isIncreased
                      ? (isDark ? const Color(0xFF451A03).withValues(alpha: 0.6) : Colors.red.shade50)
                      : (isDark ? const Color(0xFF064E3B).withValues(alpha: 0.6) : Colors.green.shade50),
                  borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                  border: Border.all(
                    color: isIncreased
                        ? (isDark ? const Color(0xFF78350F) : Colors.red.shade200)
                        : (isDark ? const Color(0xFF047857) : Colors.green.shade200),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      isIncreased ? Icons.arrow_upward : Icons.arrow_downward,
                      size: 14,
                      color: isIncreased ? AppColors.danger : Colors.tealAccent.shade400,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      '${percentChange.abs().toStringAsFixed(1)}%',
                      style: TextStyle(
                        fontSize: AppFontSizes.bodySmall,
                        fontWeight: FontWeight.bold,
                        color: isIncreased ? AppColors.danger : Colors.tealAccent.shade400,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.xl),
          Expanded(
            child: LineChart(
              LineChartData(
                minX: 0,
                maxX: (monthNames.length > 1 ? monthNames.length - 1 : 1)
                    .toDouble(),
                minY: minY,
                maxY: maxY,
                lineTouchData: LineTouchData(
                  enabled: true,
                  touchTooltipData: LineTouchTooltipData(
                    getTooltipItems: (touchedSpots) {
                      return touchedSpots.map((spot) {
                        int idx = spot.x.toInt();
                        String monthStr =
                            (idx >= 0 && idx < monthNames.length)
                            ? monthNames[idx]
                            : '';
                        return LineTooltipItem(
                          '$monthStr\n${spot.y.toStringAsFixed(0)} kWh',
                          const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                        );
                      }).toList();
                    },
                  ),
                ),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: yInterval,
                  getDrawingHorizontalLine: (value) => FlLine(
                    color: borderColor,
                    strokeWidth: 1,
                  ),
                ),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  rightTitles: const AxisTitles(
                    sideTitles: SideTitles(showTitles: false),
                  ),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 40,
                      interval: yInterval,
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
                      interval: 1,
                      getTitlesWidget: (value, meta) {
                        int idx = value.toInt();
                        if (value == idx.toDouble() &&
                            idx >= 0 &&
                            idx < monthNames.length) {
                          return Padding(
                            padding: const EdgeInsets.only(top: 8.0),
                            child: Text(
                              monthNames[idx],
                              style: TextStyle(
                                fontSize: AppFontSizes.bodySmall,
                                fontWeight: FontWeight.w500,
                                color: AppColors.titleColor(context),
                              ),
                            ),
                          );
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                lineBarsData: [
                  LineChartBarData(
                    spots: List.generate(
                      monthlyKwh.length,
                      (i) => FlSpot(i.toDouble(), monthlyKwh[i]),
                    ),
                    isCurved: true,
                    color: isDark ? const Color(0xFF2DD4BF) : Colors.teal.shade600,
                    barWidth: 3.5,
                    isStrokeCapRound: true,
                    dotData: FlDotData(
                      show: true,
                      getDotPainter: (spot, percent, barData, index) =>
                          FlDotCirclePainter(
                            radius: 5,
                            color: isDark ? const Color(0xFF0F766E) : Colors.teal.shade700,
                            strokeWidth: 2,
                            strokeColor: Colors.white,
                          ),
                    ),
                    belowBarData: BarAreaData(
                      show: true,
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          (isDark ? const Color(0xFF2DD4BF) : Colors.teal.shade300).withValues(alpha: 0.35),
                          (isDark ? const Color(0xFF0F766E) : Colors.teal.shade50).withValues(alpha: 0.05),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
