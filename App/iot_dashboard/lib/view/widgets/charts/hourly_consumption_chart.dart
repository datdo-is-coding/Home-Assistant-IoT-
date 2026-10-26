import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';
import 'package:iot_dashboard/view/widgets/common/device_power_manager.dart';

// Model đại diện cho dữ liệu tiêu thụ điện của 1 giờ
class HourlyEnergyData {
  final String hour; // Ví dụ: "08:00", "09:00"...
  final double kwh; // Mức tiêu thụ (kWh)
  final bool isPeak; // Giờ cao điểm hay không

  HourlyEnergyData({
    required this.hour,
    required this.kwh,
    this.isPeak = false,
  });
}

class HourlyConsumptionChart extends StatefulWidget {
  const HourlyConsumptionChart({super.key});

  @override
  State<HourlyConsumptionChart> createState() =>
      _HourlyConsumptionChartState();
}

class _HourlyConsumptionChartState extends State<HourlyConsumptionChart> {
  int? hoveredIndex; // Lưu vị trí cột đang chọn/rê chuột
  late final ScrollController _scrollController;
  double _lastWidth = 0;

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToCurrentHour();
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToCurrentHour() {
    if (!_scrollController.hasClients) return;
    final maxExtent = _scrollController.position.maxScrollExtent;
    _scrollController.animateTo(
      maxExtent,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);

    final powerManager = DevicePowerManager();
    final int currentHour = DateTime.now().hour;

    // Lấy dữ liệu thực tế từ DevicePowerManager
    final rawHourlyData = powerManager.getHourlyDataUntilCurrentHour();
    final List<HourlyEnergyData> visibleData = rawHourlyData.map((item) {
      return HourlyEnergyData(
        hour: item['hour'] as String,
        kwh: item['kwh'] as double,
        isPeak: item['isPeak'] as bool,
      );
    }).toList();

    final double maxKwh = visibleData.isNotEmpty
        ? visibleData.map((e) => e.kwh).reduce((a, b) => a > b ? a : b)
        : 1.0;
    final double totalKwhToday = powerManager.calculateTotalKwhToday();

    return Container(
      padding: const EdgeInsets.all(AppSizes.md + 2),
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
          // 1. Header Row 1: Tiêu đề bên trái, Tổng kWh bên phải
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'Tiêu Thụ Điện Theo Giờ',
                  style: TextStyle(
                    fontSize: AppFontSizes.bodyMedium,
                    fontWeight: FontWeight.bold,
                    color: AppColors.titleColor(context),
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: AppSizes.xs + 2),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSizes.sm,
                  vertical: 3,
                ),
                decoration: BoxDecoration(
                  color: isDark
                      ? Colors.blue.shade900.withValues(alpha: 0.4)
                      : Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(AppSizes.radiusFull),
                ),
                child: Text(
                  '${totalKwhToday.toStringAsFixed(1)} kWh',
                  style: TextStyle(
                    fontSize: AppFontSizes.bodySmall,
                    fontWeight: FontWeight.bold,
                    color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade700,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSizes.xs),

          // Header Row 2: Cập nhật giờ bên trái, Nút "Hiện tại" bên phải
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'Cập nhật: ${currentHour.toString().padLeft(2, '0')}:00 (Hiện tại)',
                  style: TextStyle(
                    fontSize: 10,
                    color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade700,
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: AppSizes.xs + 2),
              InkWell(
                onTap: _scrollToCurrentHour,
                borderRadius: BorderRadius.circular(AppSizes.radiusLg),
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppColors.inputBg(context),
                    borderRadius: BorderRadius.circular(AppSizes.radiusLg),
                    border: Border.all(color: borderColor),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.schedule,
                        size: 11,
                        color: isDark ? Colors.white70 : Colors.grey.shade700,
                      ),
                      const SizedBox(width: 3),
                      Text(
                        'Hiện tại',
                        style: TextStyle(
                          fontSize: 10,
                          color: isDark ? Colors.white70 : Colors.grey.shade800,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSizes.sm),

          // 2. Chú thích Chú Giải (Legend)
          Wrap(
            spacing: 10,
            runSpacing: 4,
            children: [
              _buildLegendItem(
                context: context,
                color: AppColors.info,
                label: 'Bình thường',
              ),
              _buildLegendItem(
                context: context,
                color: AppColors.warning,
                label: 'Cao điểm',
              ),
            ],
          ),

          const SizedBox(height: AppSizes.sm),

          // 3. Khung vẽ Biểu Đồ Cột
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                if ((_lastWidth - constraints.maxWidth).abs() > 3) {
                  _lastWidth = constraints.maxWidth;
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    _scrollToCurrentHour();
                  });
                }

                final double maxBarHeight =
                    (constraints.maxHeight - 65).clamp(35.0, 300.0);

                return Scrollbar(
                  controller: _scrollController,
                  thumbVisibility: true,
                  trackVisibility: true,
                  thickness: 5,
                  radius: const Radius.circular(4),
                  child: SingleChildScrollView(
                    controller: _scrollController,
                    scrollDirection: Axis.horizontal,
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.only(bottom: 12),
                    child: SizedBox(
                      width: visibleData.length * 36.0 < 240
                          ? 240
                          : visibleData.length * 36.0,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: List.generate(visibleData.length, (index) {
                          final item = visibleData[index];
                          final double barHeightRatio = item.kwh / maxKwh;
                          final isHovered = hoveredIndex == index;
                          final isCurrentHourIndex =
                              index == visibleData.length - 1;

                          return GestureDetector(
                            onTap: () {
                              setState(() {
                                hoveredIndex = isHovered ? null : index;
                              });
                            },
                            child: Tooltip(
                              message:
                                  '${item.hour}\n${item.kwh} kWh${isCurrentHourIndex ? ' (Giờ hiện tại)' : ''}',
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.end,
                                children: [
                                  AnimatedOpacity(
                                    duration: const Duration(milliseconds: 200),
                                    opacity: (isHovered || isCurrentHourIndex)
                                        ? 1.0
                                        : 0.0,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 4,
                                        vertical: 2,
                                      ),
                                      margin: const EdgeInsets.only(bottom: 4),
                                      decoration: BoxDecoration(
                                        color: isCurrentHourIndex
                                            ? Colors.blue.shade700
                                            : Colors.black87,
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                      child: Text(
                                        '${item.kwh}',
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 9,
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ),
                                  ),

                                  // Thân Cột Biểu Đồ
                                  AnimatedContainer(
                                    duration: const Duration(milliseconds: 250),
                                    width: isHovered
                                        ? 16
                                        : (isCurrentHourIndex ? 14 : 12),
                                    height: (barHeightRatio * maxBarHeight)
                                        .clamp(6.0, maxBarHeight),
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(4),
                                      border: isCurrentHourIndex
                                          ? Border.all(
                                              color: Colors.blue.shade900,
                                              width: 1.5)
                                          : null,
                                      gradient: LinearGradient(
                                        begin: Alignment.topCenter,
                                        end: Alignment.bottomCenter,
                                        colors: item.isPeak
                                            ? [
                                                Colors.deepOrangeAccent,
                                                Colors.orange.shade300,
                                              ]
                                            : [
                                                Colors.blueAccent,
                                                Colors.lightBlue.shade200,
                                              ],
                                      ),
                                      boxShadow:
                                          (isHovered || isCurrentHourIndex)
                                              ? [
                                                  BoxShadow(
                                                    color: (item.isPeak
                                                            ? Colors.deepOrange
                                                            : Colors.blue)
                                                        .withValues(alpha: 0.4),
                                                    blurRadius: 6,
                                                  ),
                                                ]
                                              : [],
                                    ),
                                  ),

                                  const SizedBox(height: 6),

                                  Text(
                                    (index % 2 == 0 || isCurrentHourIndex)
                                        ? '${item.hour.split(':')[0]}h'
                                        : '',
                                    style: TextStyle(
                                      fontSize: 9,
                                      color: isCurrentHourIndex
                                          ? (isDark ? const Color(0xFF60A5FA) : Colors.blue.shade800)
                                          : (isHovered
                                              ? (isDark ? const Color(0xFF60A5FA) : Colors.blue.shade800)
                                              : AppColors.subtleColor(context)),
                                      fontWeight:
                                          (isHovered || isCurrentHourIndex)
                                              ? FontWeight.bold
                                              : FontWeight.normal,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        }),
                      ),
                    ),
                  ),
                );
              },
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
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 5),
        Text(
          label,
          style: TextStyle(
            fontSize: AppFontSizes.caption,
            color: AppColors.subtleColor(context),
          ),
        ),
      ],
    );
  }
}
