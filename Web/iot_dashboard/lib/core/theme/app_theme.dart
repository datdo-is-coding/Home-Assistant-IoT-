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
    canvas: Color(0xFFF1F5F1),
    cardSurface: Color(0xFFF8FAF7),
    cardBorder: Color(0xFFDCE5DD),
    lightAccent: Color(0xFF547B64),
    lightWash: Color(0xFFE2ECE1),
    fanAccent: Color(0xFF48796E),
    fanWash: Color(0xFFDFEDE6),
    socketAccent: Color(0xFF587569),
    socketWash: Color(0xFFE3ECE5),
    climateAccent: Color(0xFF457D77),
    climateWash: Color(0xFFDFECE8),
    online: Color(0xFF39755D),
    offline: Color(0xFF9B5B53),
    warning: Color(0xFFA86722),
  );

  static const dark = AppColors(
    canvas: Color(0xFF10191A),
    cardSurface: Color(0xFF1C2A28),
    cardBorder: Color(0xFF35443E),
    lightAccent: Color(0xFFBBD5AC),
    lightWash: Color(0xFF2D3C2D),
    fanAccent: Color(0xFFA6D0BE),
    fanWash: Color(0xFF233B32),
    socketAccent: Color(0xFFB4CBBD),
    socketWash: Color(0xFF2B3931),
    climateAccent: Color(0xFFA4D2C9),
    climateWash: Color(0xFF233B36),
    online: Color(0xFF8AC5A7),
    offline: Color(0xFFD6A59A),
    warning: Color(0xFFD8A25B),
  );
}

class AppTheme {
  static const double cardRadius = 24;
  static const double iconRadius = 12;
  static const double pillRadius = 100;
  static const double modalRadius = 30;

  static ThemeData light() => _theme(Brightness.light);
  static ThemeData dark() => _theme(Brightness.dark);

  static ThemeData _theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final colors = dark ? AppColors.dark : AppColors.light;
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF628C74),
      brightness: brightness,
    ).copyWith(
      primary: dark ? const Color(0xFFBBDAC7) : const Color(0xFF315E4B),
      onPrimary: dark ? const Color(0xFF162D23) : Colors.white,
      primaryContainer:
          dark ? const Color(0xFF334F41) : const Color(0xFFDDEADD),
      onPrimaryContainer:
          dark ? const Color(0xFFE1EFE3) : const Color(0xFF284B38),
      surface: colors.cardSurface,
      onSurface: dark ? const Color(0xFFECF2EA) : const Color(0xFF24362E),
      onSurfaceVariant:
          dark ? const Color(0xFFB0C0B5) : const Color(0xFF607367),
      outline: dark ? const Color(0xFF607268) : const Color(0xFFA2B5A6),
      outlineVariant: colors.cardBorder,
      error: dark ? const Color(0xFFF0AAA0) : const Color(0xFFB23930),
    );
    final text = ThemeData(brightness: brightness).textTheme.apply(
          fontFamily: 'Roboto',
          bodyColor: scheme.onSurface,
          displayColor: scheme.onSurface,
        );
    final round = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(18),
    );
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: colors.canvas,
      extensions: [colors],
      fontFamily: 'Roboto',
      textTheme: text.copyWith(
        headlineMedium: text.headlineMedium?.copyWith(
            fontSize: 30, fontWeight: FontWeight.w600, letterSpacing: -1.0),
        titleLarge: text.titleLarge?.copyWith(
            fontSize: 21, fontWeight: FontWeight.w600, letterSpacing: -0.5),
        titleMedium: text.titleMedium?.copyWith(
            fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: -0.2),
        bodyMedium: text.bodyMedium?.copyWith(height: 1.4),
        bodySmall: text.bodySmall?.copyWith(
            color: scheme.onSurfaceVariant,
            fontFeatures: const [FontFeature.tabularFigures()]),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: colors.canvas,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: text.titleLarge?.copyWith(fontWeight: FontWeight.w600),
      ),
      cardTheme: CardThemeData(
        color: colors.cardSurface,
        elevation: 0,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(cardRadius)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.cardSurface.withValues(alpha: 0.8),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide:
              BorderSide(color: colors.cardBorder.withValues(alpha: 0.6)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide(color: scheme.primary, width: 1.5),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
            minimumSize: const Size(48, 50), shape: round),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
            minimumSize: const Size(48, 50),
            side: BorderSide(color: colors.cardBorder),
            shape: round),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.selected)
                ? (dark ? const Color(0xFF1C3428) : Colors.white)
                : scheme.onSurfaceVariant),
        trackColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.selected)
                ? scheme.primary
                : scheme.onSurface.withValues(alpha: 0.08)),
        trackOutlineColor: WidgetStateProperty.all(Colors.transparent),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: colors.cardSurface,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius:
              BorderRadius.vertical(top: Radius.circular(modalRadius)),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: colors.cardSurface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(modalRadius)),
      ),
      dividerTheme: DividerThemeData(
          color: scheme.outlineVariant.withValues(alpha: 0.5), thickness: 0.6),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: Colors.transparent,
        elevation: 0,
        indicatorColor: scheme.primaryContainer,
        indicatorShape: const StadiumBorder(),
        iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
              size: 23,
              color: states.contains(WidgetState.selected)
                  ? scheme.primary
                  : scheme.onSurfaceVariant,
            )),
        labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
              fontSize: 11,
              letterSpacing: -0.2,
              fontWeight: states.contains(WidgetState.selected)
                  ? FontWeight.w600
                  : FontWeight.w500,
              color: states.contains(WidgetState.selected)
                  ? scheme.onSurface
                  : scheme.onSurfaceVariant,
            )),
      ),
    );
  }
}
