import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';
import 'package:iot_dashboard/data/service/electricity_caculator.dart';

class MonthlyTariffCard extends StatelessWidget {
  final double currentKwh; // kWh đã tiêu thụ trong tháng (VD: 345 kWh)
  final int dayOfMonth; // Ngày hiện tại trong tháng (VD: 18)
  final int totalDaysInMonth; // Tổng số ngày (VD: 31)

  const MonthlyTariffCard({
    super.key,
    required this.currentKwh,
    required this.dayOfMonth,
    required this.totalDaysInMonth,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);

    // 1. Tính toán giá tiền thực tế hiện tại với định mức nén theo ngày (18/31)
    final currentCostData = ElectricityCaculator.calculateCost(
      currentKwh,
      dayOfMonth: dayOfMonth,
      totalDaysInMonth: totalDaysInMonth,
    );
    final double totalCost = currentCostData['totalCost'];
    final int currentTier = currentCostData['currentTier'];
    final List<double> breakdown = List<double>.from(
      currentCostData['tierBreakdown'],
    );

    // 2. Tính toán dự báo cuối tháng
    final predictedData = ElectricityCaculator.predictMonthlyCost(
      currentKwh: currentKwh,
      dayOfMonth: dayOfMonth,
      totalDaysInMonth: totalDaysInMonth,
    );
    final double predictedCost = predictedData['predictedCost'];
    final int predictedTier = predictedData['predictedTier'];

    // Màu sắc theo bậc
    final List<Color> tierColors = [
      Colors.green,
      Colors.lightGreen,
      Colors.lime,
      Colors.orange,
      Colors.deepOrange,
      Colors.red,
    ];

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
          // Tiêu đề & Tổng tiền hiện tại
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'TÍNH TIỀN ĐIỆN BẬC THANG EVN',
                    style: TextStyle(
                      fontSize: AppFontSizes.caption,
                      fontWeight: FontWeight.bold,
                      color: AppColors.subtleColor(context),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${_formatCurrency(totalCost)} VNĐ',
                    style: TextStyle(
                      fontSize: AppFontSizes.h1,
                      fontWeight: FontWeight.w800,
                      color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade900,
                    ),
                  ),
                  Text(
                    'Đã dùng: ${currentKwh.toStringAsFixed(1)} kWh (Ngày $dayOfMonth/$totalDaysInMonth • Bậc $currentTier/6)',
                    style: TextStyle(
                      fontSize: AppFontSizes.bodySmall,
                      color: AppColors.subtleColor(context),
                    ),
                  ),
                ],
              ),

              // Card Dự báo cuối tháng
              Container(
                padding: const EdgeInsets.all(AppSizes.sm + 4),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF3B0764).withValues(alpha: 0.5)
                      : Colors.purple.shade50,
                  borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                  border: Border.all(
                    color: isDark ? const Color(0xFF6B21A8) : Colors.purple.shade100,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      'Dự báo cuối tháng',
                      style: TextStyle(
                        fontSize: AppFontSizes.caption,
                        color: isDark ? const Color(0xFFC084FC) : Colors.purple,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '~ ${_formatCurrency(predictedCost)} đ',
                      style: TextStyle(
                        fontSize: AppFontSizes.bodyLarge,
                        fontWeight: FontWeight.bold,
                        color: isDark ? const Color(0xFFE9D5FF) : Colors.purple,
                      ),
                    ),
                    Text(
                      'Dự kiến: Bậc $predictedTier',
                      style: TextStyle(
                        fontSize: AppFontSizes.caption,
                        color: isDark ? const Color(0xFFC084FC) : Colors.purple.shade700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSizes.xl),

          // Visualizing Thanh Tiến Trình Bậc Thang EVN Nén theo tỉ lệ Ngày đo (18/31)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Tiến trình định mức điện ($dayOfMonth/$totalDaysInMonth ngày):',
                style: TextStyle(
                  fontSize: AppFontSizes.bodySmall,
                  fontWeight: FontWeight.w600,
                  color: AppColors.titleColor(context),
                ),
              ),
              Text(
                'Chu kỳ: $totalDaysInMonth ngày',
                style: TextStyle(
                  fontSize: AppFontSizes.caption,
                  color: AppColors.subtleColor(context),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),

          // LayoutBuilder nén thanh tiến trình chuẩn theo tỉ lệ 18/31
          LayoutBuilder(
            builder: (context, constraints) {
              final double totalWidth = constraints.maxWidth;
              final double daysRatio = (dayOfMonth / totalDaysInMonth).clamp(
                0.05,
                1.0,
              );
              final double measuredWidth = totalWidth * daysRatio;
              final int remainingDays = totalDaysInMonth - dayOfMonth;
              int activeTierIndex = (currentTier - 1).clamp(0, 5);

              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 1. BADGE "18/31"
                  SizedBox(
                    height: 28,
                    width: totalWidth,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Positioned(
                          left: (measuredWidth - 26).clamp(
                            0.0,
                            totalWidth - 52,
                          ),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 2,
                                ),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF4F46E5),
                                  borderRadius: BorderRadius.circular(6),
                                  boxShadow: [
                                    BoxShadow(
                                      color: const Color(0xFF4F46E5).withValues(alpha: 0.35),
                                      blurRadius: 6,
                                      offset: const Offset(0, 2),
                                    ),
                                  ],
                                ),
                                child: Text(
                                  '$dayOfMonth/$totalDaysInMonth',
                                  style: const TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                              ),
                              const Icon(
                                Icons.arrow_drop_down,
                                size: 10,
                                color: Color(0xFF4F46E5),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  // 2. THANH TIẾN TRÌNH BẬC THANG
                  ClipRRect(
                    borderRadius: BorderRadius.circular(AppSizes.radiusSm + 2),
                    child: Container(
                      height: 22,
                      width: totalWidth,
                      decoration: BoxDecoration(
                        color: AppColors.inputBg(context),
                        borderRadius: BorderRadius.circular(AppSizes.radiusSm + 2),
                        border: Border.all(color: borderColor),
                      ),
                      child: Row(
                        children: [
                          SizedBox(
                            width: measuredWidth,
                            child: Row(
                              children: List.generate(6, (index) {
                                bool isFilled = breakdown[index] > 0;
                                bool isActiveTier = index == activeTierIndex;
                                int flexVal = (index == 0 || index == 1)
                                    ? 1
                                    : 2;

                                return Expanded(
                                  flex: flexVal,
                                  child: Container(
                                    margin: const EdgeInsets.only(right: 1),
                                    decoration: BoxDecoration(
                                      color: isFilled
                                          ? tierColors[index]
                                          : (isDark ? const Color(0xFF334155) : Colors.grey.shade300),
                                      borderRadius: BorderRadius.circular(3),
                                      border: isActiveTier
                                          ? Border.all(
                                              color: isDark ? Colors.white : Colors.black87,
                                              width: 1.5,
                                            )
                                          : null,
                                    ),
                                    child: Center(
                                      child: FittedBox(
                                        child: Padding(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 2,
                                          ),
                                          child: Text(
                                            'B${index + 1}',
                                            style: TextStyle(
                                              fontSize: 9,
                                              fontWeight: FontWeight.bold,
                                              color: isFilled
                                                  ? Colors.white
                                                  : Colors.grey.shade600,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                );
                              }),
                            ),
                          ),

                          Container(
                            width: 2,
                            height: double.infinity,
                            color: const Color(0xFF818CF8),
                          ),

                          Expanded(
                            child: Container(
                              color: AppColors.inputBg(context),
                              child: Center(
                                child: Text(
                                  'Còn $remainingDays ngày',
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.subtleColor(context),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 6),

                  // 3. NHÃN ĐỊNH MỨC KWH
                  Row(
                    children: [
                      SizedBox(
                        width: measuredWidth,
                        child: Row(
                          children: List.generate(6, (index) {
                            int flexVal = (index == 0 || index == 1) ? 1 : 2;
                            List<String> tierRanges = [
                              '${(50 * daysRatio).round()}k',
                              '${(100 * daysRatio).round()}k',
                              '${(200 * daysRatio).round()}k',
                              '${(300 * daysRatio).round()}k',
                              '${(400 * daysRatio).round()}k',
                              '>${(400 * daysRatio).round()}k',
                            ];
                            bool isActiveTier = index == activeTierIndex;

                            return Expanded(
                              flex: flexVal,
                              child: Text(
                                tierRanges[index],
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 9.5,
                                  fontWeight: isActiveTier
                                      ? FontWeight.bold
                                      : FontWeight.normal,
                                  color: isActiveTier
                                      ? tierColors[index]
                                      : AppColors.subtleColor(context),
                                ),
                              ),
                            );
                          }),
                        ),
                      ),
                      Expanded(
                        child: Text(
                          'Cuối tháng',
                          textAlign: TextAlign.right,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w500,
                            color: AppColors.subtleColor(context),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              );
            },
          ),

          const SizedBox(height: AppSizes.lg),

          // BANNER THÔNG BÁO CẢNH BÁO TỰ ĐỘNG
          if (currentTier >= 5 || predictedTier >= 5)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(AppSizes.md),
              decoration: BoxDecoration(
                color: isDark
                    ? const Color(0xFF451A03).withValues(alpha: 0.6)
                    : Colors.amber.shade50,
                borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                border: Border.all(
                  color: isDark ? const Color(0xFF78350F) : Colors.amber.shade300,
                ),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.warning_amber_rounded,
                    color: AppColors.warning,
                    size: 28,
                  ),
                  const SizedBox(width: AppSizes.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Cảnh báo tiêu thụ điện cao! (Bậc $currentTier)',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: AppFontSizes.bodyMedium,
                            color: AppColors.titleColor(context),
                          ),
                        ),
                        Text(
                          'Bạn đang sử dụng điện ở bậc giá đắt (${currentTier >= 5 ? '3.197đ+' : '2.860đ'}/kWh). Hãy giảm các thiết bị công suất lớn như Điều hòa để tiết kiệm tiền điện!',
                          style: TextStyle(
                            fontSize: AppFontSizes.bodySmall,
                            color: AppColors.subtleColor(context),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            )
          else
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(AppSizes.md),
              decoration: BoxDecoration(
                color: isDark
                    ? const Color(0xFF064E3B).withValues(alpha: 0.5)
                    : Colors.green.shade50,
                borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                border: Border.all(
                  color: isDark ? const Color(0xFF047857) : Colors.green.shade200,
                ),
              ),
              child: const Row(
                children: [
                  Icon(
                    Icons.check_circle_outline,
                    color: AppColors.success,
                    size: 24,
                  ),
                  SizedBox(width: AppSizes.sm + 2),
                  Text(
                    'Mức tiêu thụ nằm trong giới hạn tiết kiệm an toàn.',
                    style: TextStyle(
                      fontSize: AppFontSizes.bodySmall,
                      color: AppColors.success,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  String _formatCurrency(double amount) {
    return amount
        .toStringAsFixed(0)
        .replaceAll((RegExp(r'\B(?=(\d{3})+(?!\d))')), '.');
  }
}
