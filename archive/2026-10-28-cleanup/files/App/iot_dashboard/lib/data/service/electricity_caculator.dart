class ElectricityCaculator {
  static const double vatRate = 0.08;

  /// Tính tiền điện chi tiết theo từng bậc lũy tiến EVN
  /// Nếu truyền [dayOfMonth] và [totalDaysInMonth], định mức các bậc sẽ được nén/chia theo tỉ lệ (dayOfMonth / totalDaysInMonth)
  static Map<String, dynamic> calculateCost(
    double totalKwh, {
    int? dayOfMonth,
    int? totalDaysInMonth,
  }) {
    double remaining = totalKwh;
    double totalCostNoVat = 0;

    // Tỉ lệ nén định mức ngày
    double ratio = 1.0;
    if (dayOfMonth != null &&
        totalDaysInMonth != null &&
        totalDaysInMonth > 0) {
      ratio = (dayOfMonth / totalDaysInMonth).clamp(0.01, 1.0);
    }

    List<double> tierKwh = [0, 0, 0, 0, 0, 0];
    List<double> baseLimits = [50, 50, 100, 100, 100, double.infinity];
    List<double> tierLimits = baseLimits
        .map((l) => l.isInfinite ? l : (l * ratio))
        .toList();

    List<double> tierPrices = [1893, 1956, 2271, 2860, 3197, 3302];
    int currentTierIndex = 0;
    for (int i = 0; i < 6; i++) {
      if (remaining <= 0) break;
      double limit = tierLimits[i];
      double usedInTier = (remaining > limit) ? limit : remaining;

      tierKwh[i] = usedInTier;
      totalCostNoVat += usedInTier * tierPrices[i];
      remaining -= usedInTier;
      currentTierIndex = i + 1;
    }
    double vatAmount = totalCostNoVat * vatRate;
    double totalCostWithVat = totalCostNoVat + vatAmount;
    return {
      'totalKwh': totalKwh,
      'totalCost': totalCostWithVat,
      'vatAmount': vatAmount,
      'currentTier': currentTierIndex,
      'tierBreakdown': tierKwh, // Lượng kWh của từng bậc
      'daysRatio': ratio,
    };
  }

  /// Dự báo tiêu thụ điện & tiền điện đến cuối tháng (tính theo định mức tròn 30/31 ngày)
  static Map<String, dynamic> predictMonthlyCost({
    required double currentKwh,
    required int dayOfMonth,
    required int totalDaysInMonth,
  }) {
    if (dayOfMonth <= 0) dayOfMonth = 1;
    double avgDailyKwh = currentKwh / dayOfMonth;
    double predictedKwh = avgDailyKwh * totalDaysInMonth;

    var predictedCalculation = calculateCost(predictedKwh);

    return {
      'avgDailyKwh': avgDailyKwh,
      'predictedKwh': predictedKwh,
      'predictedCost': predictedCalculation['totalCost'],
      'predictedTier': predictedCalculation['currentTier'],
    };
  }
}
