import 'package:flutter/material.dart';

// Model đại diện cho dữ liệu tiêu thụ điện
class EnergyData {
  final String hour; // Nhãn: "08:00", "T2", "Thg 1"...
  final double kwh; // Mức tiêu thụ (kWh)
  final bool isPeak; // Cao điểm hay không

  EnergyData({required this.hour, required this.kwh, this.isPeak = false});
}

class ConsumptionChart extends StatefulWidget {
  final bool showDropdown;
  final String initialMode; // 'hourly', 'daily', 'monthly'

  const ConsumptionChart({
    super.key,
    this.showDropdown = false,
    this.initialMode = 'hourly',
  });

  @override
  State<ConsumptionChart> createState() => _ConsumptionChartState();
}

class _ConsumptionChartState extends State<ConsumptionChart> {
  late String currentMode;
  int? hoveredIndex;
  late final ScrollController _scrollController;
  double _lastWidth = 0;

  // 1. Dữ liệu tiêu thụ điện theo 24 giờ
  final List<EnergyData> hourlyData = [
    EnergyData(hour: '00:00', kwh: 0.8),
    EnergyData(hour: '01:00', kwh: 0.6),
    EnergyData(hour: '02:00', kwh: 0.5),
    EnergyData(hour: '03:00', kwh: 0.5),
    EnergyData(hour: '04:00', kwh: 0.6),
    EnergyData(hour: '05:00', kwh: 1.1),
    EnergyData(hour: '06:00', kwh: 2.2),
    EnergyData(hour: '07:00', kwh: 3.5),
    EnergyData(hour: '08:00', kwh: 4.2),
    EnergyData(hour: '09:00', kwh: 3.8),
    EnergyData(hour: '10:00', kwh: 3.1),
    EnergyData(hour: '11:00', kwh: 3.6),
    EnergyData(hour: '12:00', kwh: 4.8, isPeak: true),
    EnergyData(hour: '13:00', kwh: 4.5, isPeak: true),
    EnergyData(hour: '14:00', kwh: 3.9),
    EnergyData(hour: '15:00', kwh: 3.2),
    EnergyData(hour: '16:00', kwh: 2.8),
    EnergyData(hour: '17:00', kwh: 3.4),
    EnergyData(hour: '18:00', kwh: 4.9, isPeak: true),
    EnergyData(hour: '19:00', kwh: 5.2, isPeak: true),
    EnergyData(hour: '20:00', kwh: 4.6),
    EnergyData(hour: '21:00', kwh: 3.7),
    EnergyData(hour: '22:00', kwh: 2.3),
    EnergyData(hour: '23:00', kwh: 1.4),
  ];

  // 2. Dữ liệu tiêu thụ điện theo các ngày trong tuần
  final List<EnergyData> dailyData = [
    EnergyData(hour: 'T2', kwh: 18.5),
    EnergyData(hour: 'T3', kwh: 22.1),
    EnergyData(hour: 'T4', kwh: 19.8),
    EnergyData(hour: 'T5', kwh: 25.4, isPeak: true),
    EnergyData(hour: 'T6', kwh: 21.0),
    EnergyData(hour: 'T7', kwh: 28.6, isPeak: true),
    EnergyData(hour: 'CN', kwh: 24.2),
  ];

  // 3. Dữ liệu tiêu thụ điện theo các tháng trong năm
  final List<EnergyData> monthlyData = [
    EnergyData(hour: 'Thg 1', kwh: 420.0),
    EnergyData(hour: 'Thg 2', kwh: 380.0),
    EnergyData(hour: 'Thg 3', kwh: 450.0),
    EnergyData(hour: 'Thg 4', kwh: 510.0),
    EnergyData(hour: 'Thg 5', kwh: 620.0, isPeak: true),
    EnergyData(hour: 'Thg 6', kwh: 680.0, isPeak: true),
    EnergyData(hour: 'Thg 7', kwh: 650.0, isPeak: true),
    EnergyData(hour: 'Thg 8', kwh: 590.0),
    EnergyData(hour: 'Thg 9', kwh: 480.0),
    EnergyData(hour: 'Thg 10', kwh: 440.0),
    EnergyData(hour: 'Thg 11', kwh: 410.0),
    EnergyData(hour: 'Thg 12', kwh: 460.0),
  ];

  @override
  void initState() {
    super.initState();
    currentMode = widget.initialMode;
    _scrollController = ScrollController();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (currentMode == 'hourly') {
        _scrollToCurrentHour();
      }
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

  List<EnergyData> _getActiveData() {
    if (currentMode == 'daily') {
      return dailyData;
    } else if (currentMode == 'monthly') {
      return monthlyData;
    } else {
      final int currentHour = DateTime.now().hour;
      return hourlyData.sublist(
        0,
        (currentHour + 1).clamp(1, hourlyData.length),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final int currentHour = DateTime.now().hour;
    final List<EnergyData> visibleData = _getActiveData();

    final double maxKwh = visibleData
        .map((e) => e.kwh)
        .reduce((a, b) => a > b ? a : b);
    final double totalKwh = visibleData.fold(0, (sum, item) => sum + item.kwh);

    final double itemWidth = currentMode == 'hourly'
        ? 36.0
        : (currentMode == 'daily' ? 48.0 : 42.0);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 15,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. Header Row 1: Tiêu đề / Dropdown bên trái, Tổng kWh bên phải
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: widget.showDropdown
                    ? Row(
                        children: [
                          const Text(
                            'Tiêu Thụ:',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF1E293B),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: Colors.grey.shade300),
                            ),
                            child: DropdownButtonHideUnderline(
                              child: DropdownButton<String>(
                                value: currentMode,
                                isDense: true,
                                icon: const Icon(
                                  Icons.keyboard_arrow_down_rounded,
                                  size: 18,
                                  color: Color(0xFF475569),
                                ),
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF1E293B),
                                ),
                                items: const [
                                  DropdownMenuItem(
                                    value: 'hourly',
                                    child: Text('Theo Giờ'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'daily',
                                    child: Text('Theo Ngày'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'monthly',
                                    child: Text('Theo Tháng'),
                                  ),
                                ],
                                onChanged: (val) {
                                  if (val != null) {
                                    setState(() {
                                      currentMode = val;
                                      hoveredIndex = null;
                                    });
                                    if (val == 'hourly') {
                                      WidgetsBinding.instance
                                          .addPostFrameCallback((_) {
                                            _scrollToCurrentHour();
                                          });
                                    }
                                  }
                                },
                              ),
                            ),
                          ),
                        ],
                      )
                    : const Text(
                        'Tiêu Thụ Điện Theo Giờ',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF1E293B),
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '${totalKwh.toStringAsFixed(currentMode == 'monthly' ? 0 : 1)} kWh',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: Colors.blue.shade700,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 4),

          // Header Row 2: Chi tiết mốc thời gian
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  currentMode == 'hourly'
                      ? 'Cập nhật: ${currentHour.toString().padLeft(2, '0')}:00 (Hiện tại)'
                      : (currentMode == 'daily'
                            ? 'Dữ liệu tiêu thụ tuần này (T2 - CN)'
                            : 'Dữ liệu tổng quan theo tháng năm 2026'),
                  style: TextStyle(
                    fontSize: 10,
                    color: Colors.blue.shade700,
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (currentMode == 'hourly') ...[
                const SizedBox(width: 6),
                InkWell(
                  onTap: _scrollToCurrentHour,
                  borderRadius: BorderRadius.circular(16),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade100,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.grey.shade300),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.schedule,
                          size: 11,
                          color: Colors.grey.shade700,
                        ),
                        const SizedBox(width: 3),
                        Text(
                          'Hiện tại',
                          style: TextStyle(
                            fontSize: 10,
                            color: Colors.grey.shade800,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),

          const SizedBox(height: 8),

          // 2. Chú thích Chú Giải (Legend)
          Wrap(
            spacing: 10,
            runSpacing: 4,
            children: [
              _buildLegendItem(color: Colors.blueAccent, label: 'Bình thường'),
              _buildLegendItem(color: Colors.deepOrange, label: 'Cao điểm'),
            ],
          ),

          const SizedBox(height: 8),

          // 3. Khung vẽ Biểu Đồ Cột
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                if (currentMode == 'hourly' &&
                    (_lastWidth - constraints.maxWidth).abs() > 3) {
                  _lastWidth = constraints.maxWidth;
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    _scrollToCurrentHour();
                  });
                }

                final double maxBarHeight = (constraints.maxHeight - 65).clamp(
                  35.0,
                  300.0,
                );

                final double totalWidth = visibleData.length * itemWidth;

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
                      width: totalWidth < 240 ? 240 : totalWidth,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: List.generate(visibleData.length, (index) {
                          final item = visibleData[index];
                          final double barHeightRatio = item.kwh / maxKwh;
                          final isHovered = hoveredIndex == index;
                          final isCurrentHourIndex =
                              currentMode == 'hourly' &&
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
                                              width: 1.5,
                                            )
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
                                                color:
                                                    (item.isPeak
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
                                    currentMode == 'hourly'
                                        ? ((index % 2 == 0 ||
                                                  isCurrentHourIndex)
                                              ? '${item.hour.split(':')[0]}h'
                                              : '')
                                        : item.hour,
                                    style: TextStyle(
                                      fontSize: 9,
                                      color: isCurrentHourIndex
                                          ? Colors.blue.shade800
                                          : (isHovered
                                                ? Colors.blue.shade800
                                                : Colors.grey.shade600),
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

  Widget _buildLegendItem({required Color color, required String label}) {
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
          style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
        ),
      ],
    );
  }
}
