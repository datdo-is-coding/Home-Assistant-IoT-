import 'package:flutter/material.dart';

/// -------------------------------------------------------------------
/// APP NUMERIC CONSTANTS (KÍCH THƯỚC, KHOẢNG CÁCH, BO GÓC)
/// -------------------------------------------------------------------
abstract class AppSizes {
  // Khoảng cách & Padding (Spacing & Padding)
  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 12.0;
  static const double lg = 16.0;
  static const double xl = 20.0;
  static const double xxl = 24.0;
  static const double xxxl = 32.0;

  // Bán kính bo góc (Border Radius)
  static const double radiusSm = 8.0;
  static const double radiusMd = 12.0;
  static const double radiusLg = 16.0;
  static const double radiusXl = 20.0;
  static const double radiusFull = 999.0;

  // Kích thước Icon (Icon Sizes)
  static const double iconSm = 16.0;
  static const double iconMd = 20.0;
  static const double iconLg = 24.0;
  static const double iconXl = 32.0;

  // Chiều cao / Chiều rộng cố định khung Layout
  static const double topbarHeight = 64.0;
  static const double sidebarWidth = 240.0;
  static const double sidebarCollapsedWidth = 72.0;
}

/// -------------------------------------------------------------------
/// APP FONT SIZES (CỠ CHỮ NGUYÊN BẢN)
/// -------------------------------------------------------------------
abstract class AppFontSizes {
  static const double caption = 11.0;
  static const double bodySmall = 12.0;
  static const double bodyMedium = 14.0;
  static const double bodyLarge = 16.0;
  static const double titleSmall = 16.0;
  static const double titleMedium = 18.0;
  static const double titleLarge = 20.0;
  static const double h3 = 22.0;
  static const double h2 = 24.0;
  static const double h1 = 28.0;
  static const double display = 32.0;
}

/// -------------------------------------------------------------------
/// APP TEXT STYLES (MẪU CHỮ VÀ TIÊU ĐỀ CHUẨN HỆ THỐNG)
/// -------------------------------------------------------------------
abstract class AppTextStyles {
  // 1. Tiêu đề lớn & Banner (Headings)
  static const TextStyle display = TextStyle(
    fontSize: AppFontSizes.display,
    fontWeight: FontWeight.bold,
    letterSpacing: -0.5,
  );

  static const TextStyle h1 = TextStyle(
    fontSize: AppFontSizes.h1,
    fontWeight: FontWeight.bold,
    letterSpacing: -0.3,
  );

  static const TextStyle h2 = TextStyle(
    fontSize: AppFontSizes.h2,
    fontWeight: FontWeight.bold,
  );

  static const TextStyle h3 = TextStyle(
    fontSize: AppFontSizes.h3,
    fontWeight: FontWeight.w600,
  );

  // 2. Tiêu đề Thẻ / Khung (Card & Section Titles)
  static const TextStyle titleLarge = TextStyle(
    fontSize: AppFontSizes.titleLarge,
    fontWeight: FontWeight.bold,
  );

  static const TextStyle titleMedium = TextStyle(
    fontSize: AppFontSizes.titleMedium,
    fontWeight: FontWeight.bold,
  );

  static const TextStyle titleSmall = TextStyle(
    fontSize: AppFontSizes.titleSmall,
    fontWeight: FontWeight.w600,
  );

  // 3. Văn bản nội dung (Body Text)
  static const TextStyle bodyLarge = TextStyle(
    fontSize: AppFontSizes.bodyLarge,
    fontWeight: FontWeight.normal,
  );

  static const TextStyle bodyMedium = TextStyle(
    fontSize: AppFontSizes.bodyMedium,
    fontWeight: FontWeight.normal,
  );

  static const TextStyle bodySmall = TextStyle(
    fontSize: AppFontSizes.bodySmall,
    fontWeight: FontWeight.normal,
  );

  // 4. Chú thích, Nhãn & Nút bấm (Caption, Label & Button)
  static const TextStyle caption = TextStyle(
    fontSize: AppFontSizes.caption,
    fontWeight: FontWeight.w500,
  );

  static const TextStyle button = TextStyle(
    fontSize: AppFontSizes.bodyMedium,
    fontWeight: FontWeight.w600,
  );

  // -------------------------------------------------------------------
  // HELPER METHODS: Tự động điều chỉnh màu chữ tương thích Light / Dark Mode
  // -------------------------------------------------------------------
  static TextStyle getH1(BuildContext context) {
    return h1.copyWith(color: AppColors.titleColor(context));
  }

  static TextStyle getH2(BuildContext context) {
    return h2.copyWith(color: AppColors.titleColor(context));
  }

  static TextStyle getTitle(BuildContext context) {
    return titleMedium.copyWith(color: AppColors.titleColor(context));
  }

  static TextStyle getBody(BuildContext context) {
    return bodyMedium.copyWith(color: AppColors.bodyColor(context));
  }

  static TextStyle getCaption(BuildContext context) {
    return caption.copyWith(color: AppColors.subtleColor(context));
  }
}

/// -------------------------------------------------------------------
/// APP COLOR PALETTE CONSTANTS (BẢNG MÀU CHUẨN)
/// -------------------------------------------------------------------
abstract class AppColors {
  // Màu thương hiệu chủ đạo (Primary Accent - Emerald Noir Theme)
  static const Color primary = Color(0xFF10B981); // Emerald
  static const Color primaryDark = Color(0xFF059669);
  static const Color primaryLight = Color(0xFF34D399); // Mint

  // Màu Dark Mode (Nền trang, Nền Card, Viền - Obsidian Jade Emerald)
  static const Color darkBackground = Color(0xFF060907); // Obsidian Emerald Canvas
  static const Color darkCard = Color(0xFF0D1410); // Frosted Obsidian Jade
  static const Color darkBorder = Color(0xFF18281F); // Dark Emerald Bezel
  static const Color darkInputBg = Color(0xFF09100C);

  // Màu Light Mode (Nền trang, Nền Card, Viền)
  static const Color lightBackground = Color(0xFFF8FAFC); // Slate 50
  static const Color lightCard = Colors.white;
  static const Color lightBorder = Color(0xFFE2E8F0); // Slate 200
  static const Color lightInputBg = Color(0xFFF8FAFC);

  // Màu trạng thái hệ thống (Status Colors)
  static const Color success = Color(0xFF10B981); // Emerald Green
  static const Color warning = Color(0xFFF59E0B); // Amber
  static const Color danger = Color(0xFFEF4444); // Red
  static const Color info = Color(0xFF2DD4BF); // Teal Cyan Mint

  // -------------------------------------------------------------------
  // HELPER METHODS: Tự động chọn màu Thẻ, Viền, Nền theo Theme
  // -------------------------------------------------------------------
  static Color cardBg(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? darkCard : lightCard;
  }

  static Color borderColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? darkBorder : lightBorder;
  }

  static Color inputBg(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? darkInputBg : lightInputBg;
  }

  static Color background(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? darkBackground : lightBackground;
  }

  static Color titleColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? Colors.white : const Color(0xFF1E293B);
  }

  static Color bodyColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? Colors.grey.shade300 : const Color(0xFF334155);
  }

  static Color subtleColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? Colors.grey.shade400 : Colors.grey.shade600;
  }
}
