import 'package:flutter/material.dart';

class AppColors extends ThemeExtension<AppColors> {
  final Color canvas;
  final Color cardSurface;
  final Color cardBorder;
  final Color lightAccent;
  final Color lightWash;
  final Color fanAccent;
  final Color fanWash;
  final Color socketAccent;
  final Color socketWash;
  final Color climateAccent;
  final Color climateWash;
  final Color online;
  final Color offline;
  final Color warning;

  const AppColors({
    required this.canvas,
    required this.cardSurface,
    required this.cardBorder,
    required this.lightAccent,
    required this.lightWash,
    required this.fanAccent,
    required this.fanWash,
    required this.socketAccent,
    required this.socketWash,
    required this.climateAccent,
    required this.climateWash,
    required this.online,
    required this.offline,
    required this.warning,
  });

  @override
  ThemeExtension<AppColors> copyWith({
    Color? canvas,
    Color? cardSurface,
    Color? cardBorder,
    Color? lightAccent,
    Color? lightWash,
    Color? fanAccent,
    Color? fanWash,
    Color? socketAccent,
    Color? socketWash,
    Color? climateAccent,
    Color? climateWash,
    Color? online,
    Color? offline,
    Color? warning,
  }) {
    return AppColors(
      canvas: canvas ?? this.canvas,
      cardSurface: cardSurface ?? this.cardSurface,
      cardBorder: cardBorder ?? this.cardBorder,
      lightAccent: lightAccent ?? this.lightAccent,
      lightWash: lightWash ?? this.lightWash,
      fanAccent: fanAccent ?? this.fanAccent,
      fanWash: fanWash ?? this.fanWash,
      socketAccent: socketAccent ?? this.socketAccent,
      socketWash: socketWash ?? this.socketWash,
      climateAccent: climateAccent ?? this.climateAccent,
      climateWash: climateWash ?? this.climateWash,
      online: online ?? this.online,
      offline: offline ?? this.offline,
      warning: warning ?? this.warning,
    );
  }

  @override
  ThemeExtension<AppColors> lerp(
      covariant ThemeExtension<AppColors>? other, double t) {
    if (other is! AppColors) return this;
    return AppColors(
      canvas: Color.lerp(canvas, other.canvas, t)!,
      cardSurface: Color.lerp(cardSurface, other.cardSurface, t)!,
      cardBorder: Color.lerp(cardBorder, other.cardBorder, t)!,
      lightAccent: Color.lerp(lightAccent, other.lightAccent, t)!,
      lightWash: Color.lerp(lightWash, other.lightWash, t)!,
      fanAccent: Color.lerp(fanAccent, other.fanAccent, t)!,
      fanWash: Color.lerp(fanWash, other.fanWash, t)!,
      socketAccent: Color.lerp(socketAccent, other.socketAccent, t)!,
      socketWash: Color.lerp(socketWash, other.socketWash, t)!,
      climateAccent: Color.lerp(climateAccent, other.climateAccent, t)!,
      climateWash: Color.lerp(climateWash, other.climateWash, t)!,
      online: Color.lerp(online, other.online, t)!,
      offline: Color.lerp(offline, other.offline, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
    );
  }

  static const light = AppColors(
    canvas: Color(0xFFF8F9FA),
    cardSurface: Color(0xFFFFFFFF),
    cardBorder: Color(0xFFE5E7EB),
    lightAccent: Color(0xFFD97706),
    lightWash: Color(0xFFFEF3C7),
    fanAccent: Color(0xFF0284C7),
    fanWash: Color(0xFFE0F2FE),
    socketAccent: Color(0xFF7C3AED),
    socketWash: Color(0xFFEDE9FE),
    climateAccent: Color(0xFF0D9488),
    climateWash: Color(0xFFCCFBF1),
    online: Color(0xFF10B981),
    offline: Color(0xFFEF4444),
    warning: Color(0xFFF59E0B),
  );

  static const dark = AppColors(
    canvas: Color(0xFF0E1117),
    cardSurface: Color(0xFF161B26),
    cardBorder: Color(0xFF232B3B),
    lightAccent: Color(0xFFF59E0B),
    lightWash: Color(0xFF261E14),
    fanAccent: Color(0xFF38BDF8),
    fanWash: Color(0xFF102232),
    socketAccent: Color(0xFFA78BFA),
    socketWash: Color(0xFF1E1730),
    climateAccent: Color(0xFF2DD4BF),
    climateWash: Color(0xFF112926),
    online: Color(0xFF34D399),
    offline: Color(0xFFF87171),
    warning: Color(0xFFFBBF24),
  );
}

class AppTheme {
  static const double cardRadius = 24.0;
  static const double iconRadius = 12.0;

  static ThemeData light() {
    const scheme = ColorScheme.light(
      primary: Color(0xFF0F172A),
      onPrimary: Colors.white,
      primaryContainer: Color(0xFFE2E8F0),
      onPrimaryContainer: Color(0xFF0F172A),
      secondary: Color(0xFF475569),
      onSecondary: Colors.white,
      surface: Color(0xFFFFFFFF),
      onSurface: Color(0xFF0F172A),
      onSurfaceVariant: Color(0xFF64748B),
      outline: Color(0xFFD1D5DB),
      outlineVariant: Color(0xFFE5E7EB),
      error: Color(0xFFDC2626),
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.light.canvas,
      extensions: const [AppColors.light],
      fontFamily: 'Roboto',
      cardTheme: CardThemeData(
        color: AppColors.light.cardSurface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(cardRadius),
          side: const BorderSide(color: Color(0xFFE5E7EB), width: 1.0),
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: Colors.white.withValues(alpha: 0.92),
        elevation: 0,
        indicatorColor: const Color(0xFFE2E8F0),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            fontSize: 12,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: selected ? const Color(0xFF0F172A) : const Color(0xFF64748B),
          );
        }),
      ),
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 26,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.5,
          color: Color(0xFF0F172A),
        ),
        titleLarge: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.3,
          color: Color(0xFF0F172A),
        ),
        titleMedium: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.2,
          color: Color(0xFF0F172A),
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          height: 1.4,
          color: Color(0xFF0F172A),
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: Color(0xFF64748B),
        ),
        labelLarge: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.1,
          color: Color(0xFF0F172A),
        ),
      ),
    );
  }

  static ThemeData dark() {
    const scheme = ColorScheme.dark(
      primary: Colors.white,
      onPrimary: Color(0xFF07090C),
      primaryContainer: Color(0xFF1E2532),
      onPrimaryContainer: Color(0xFFF8FAFC),
      secondary: Color(0xFF94A3B8),
      onSecondary: Color(0xFF07090C),
      surface: Color(0xFF161B26),
      onSurface: Color(0xFFF8FAFC),
      onSurfaceVariant: Color(0xFF94A3B8),
      outline: Color(0xFF334155),
      outlineVariant: Color(0xFF232B3B),
      error: Color(0xFFF87171),
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: AppColors.dark.canvas,
      extensions: const [AppColors.dark],
      fontFamily: 'Roboto',
      cardTheme: CardThemeData(
        color: AppColors.dark.cardSurface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(cardRadius),
          side: const BorderSide(color: Color(0xFF232B3B), width: 1.0),
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Color(0xFF161B26),
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: const Color(0xFF10131A).withValues(alpha: 0.95),
        elevation: 0,
        indicatorColor: const Color(0xFF232B3B),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            fontSize: 12,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: selected ? Colors.white : const Color(0xFF94A3B8),
          );
        }),
      ),
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 26,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.5,
          color: Color(0xFFF8FAFC),
        ),
        titleLarge: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.3,
          color: Color(0xFFF8FAFC),
        ),
        titleMedium: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.2,
          color: Color(0xFFF8FAFC),
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          height: 1.4,
          color: Color(0xFFF8FAFC),
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: Color(0xFF94A3B8),
        ),
        labelLarge: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.1,
          color: Color(0xFFF8FAFC),
        ),
      ),
    );
  }
}
