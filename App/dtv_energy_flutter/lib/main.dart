import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'app/smart_home_app.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'services/gateway_client.dart';
import 'widgets/huawei_boot_screen.dart';

final gateway = GatewayClient();
final appTheme = ValueNotifier<ThemeMode>(ThemeMode.system);

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    const ProviderScope(
      child: SmartHomeApp(),
    ),
  );
}

ThemeData homeTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;

  // Premium Monochrome Black & White Palette
  // Dark: Deep Obsidian & Titanium Silver with subtle luminous accents
  // Light: Pristine Alabaster & Graphite with sharp hairline contrasts
  final scheme = dark
      ? const ColorScheme.dark(
          primary: Color(0xFFFFFFFF), // Crisp Pure White
          onPrimary: Color(0xFF07090C), // Pure Obsidian
          primaryContainer: Color(0xFF181D26),
          onPrimaryContainer: Color(0xFFF1F5F9),
          secondary: Color(0xFFC7CBD3), // Platinum Silver
          onSecondary: Color(0xFF0F1318),
          secondaryContainer: Color(0xFF222834),
          onSecondaryContainer: Color(0xFFE2E8F0),
          tertiary: Color(0xFFA0A8B8), // Cool Titanium Muted
          surface: Color(0xFF0F1217), // Dark Graphite Slate Card
          surfaceContainerHighest: Color(0xFF161A22),
          onSurface: Color(0xFFF8FAFC), // Brilliant Off-White
          onSurfaceVariant: Color(0xFF88909D), // Soft Metallic Gray
          outline: Color(0xFF2A313E),
          outlineVariant: Color(0xFF1F2430), // Hairline Border
          error: Color(0xFFF87171),
          errorContainer: Color(0xFF451A1A),
          onErrorContainer: Color(0xFFFECACA),
        )
      : const ColorScheme.light(
          primary: Color(0xFF0F1318), // Deepest Graphite / Obsidian
          onPrimary: Colors.white,
          primaryContainer: Color(0xFFE8ECF2),
          onPrimaryContainer: Color(0xFF0F1318),
          secondary: Color(0xFF475569), // Slate
          onSecondary: Colors.white,
          secondaryContainer: Color(0xFFF1F5F9),
          onSecondaryContainer: Color(0xFF1E293B),
          tertiary: Color(0xFF64748B),
          surface: Colors.white,
          surfaceContainerHighest: Color(0xFFEFF1F5),
          onSurface: Color(0xFF0F1318),
          onSurfaceVariant: Color(0xFF5F6B7D),
          outline: Color(0xFFD6DBE2),
          outlineVariant: Color(0xFFE2E5EB),
          error: Color(0xFFDC2626),
          errorContainer: Color(0xFFFEE2E2),
          onErrorContainer: Color(0xFF991B1B),
        );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor:
        dark ? const Color(0xFF07090C) : const Color(0xFFF6F7FA),
    textTheme: TextTheme(
      headlineMedium: TextStyle(
        fontSize: 26,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.5,
        color: scheme.onSurface,
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
        color: scheme.onSurface,
      ),
      titleMedium: TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.2,
        color: scheme.onSurface,
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        height: 1.45,
        letterSpacing: 0,
        color: scheme.onSurface,
      ),
      labelLarge: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.1,
        color: scheme.onSurface,
      ),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: dark ? const Color(0xFF090B0E) : const Color(0xFFF7F8FA),
      scrolledUnderElevation: 0,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: scheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: BorderSide(color: scheme.outlineVariant, width: 1),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 52),
        elevation: 0,
        backgroundColor: scheme.primary,
        foregroundColor: scheme.onPrimary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.2,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 50),
        side: BorderSide(color: scheme.outlineVariant, width: 1.2),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return dark ? const Color(0xFF090B0E) : Colors.white;
        }
        return dark ? const Color(0xFF8E95A2) : const Color(0xFF94A3B8);
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return dark ? Colors.white : const Color(0xFF0F1318);
        }
        return dark ? const Color(0xFF222834) : const Color(0xFFE2E8F0);
      }),
      trackOutlineColor: WidgetStateProperty.resolveWith((states) {
        return Colors.transparent;
      }),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: dark ? const Color(0xFF0E1116) : Colors.white,
      elevation: 0,
      indicatorColor: dark
          ? Colors.white.withValues(alpha: 0.12)
          : const Color(0xFF0F1318).withValues(alpha: 0.08),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return IconThemeData(
              color: dark ? Colors.white : const Color(0xFF0F1318));
        }
        return IconThemeData(color: scheme.onSurfaceVariant);
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            color: dark ? Colors.white : const Color(0xFF0F1318),
            letterSpacing: 0.1,
          );
        }
        return TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: scheme.onSurfaceVariant,
          letterSpacing: 0.1,
        );
      }),
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant.withValues(alpha: 0.6),
      thickness: 1,
    ),
  );
}

class DTVEnergyApp extends StatelessWidget {
  const DTVEnergyApp({
    super.key,
    this.client,
    this.showBootAnimation = false,
  });

  final GatewayClient? client;
  final bool showBootAnimation;

  @override
  Widget build(BuildContext context) {
    final service = client ?? gateway;
    return ListenableBuilder(
      listenable: Listenable.merge([service, appTheme]),
      builder: (context, _) => MaterialApp(
        key: ValueKey(service.authenticated),
        title: 'SIC Home',
        debugShowCheckedModeBanner: false,
        theme: homeTheme(Brightness.light),
        darkTheme: homeTheme(Brightness.dark),
        themeMode: appTheme.value,
        home: showBootAnimation
            ? _AppBootWrapper(service: service)
            : (service.authenticated
                ? HomeScreen(gateway: service)
                : LoginScreen(client: service)),
      ),
    );
  }
}

class _AppBootWrapper extends StatefulWidget {
  const _AppBootWrapper({required this.service});
  final GatewayClient service;

  @override
  State<_AppBootWrapper> createState() => _AppBootWrapperState();
}

class _AppBootWrapperState extends State<_AppBootWrapper> {
  bool _bootDone = false;

  @override
  Widget build(BuildContext context) {
    if (!_bootDone) {
      return HuaweiBootScreen(
        onComplete: () {
          if (mounted) setState(() => _bootDone = true);
        },
      );
    }
    return widget.service.authenticated
        ? HomeScreen(gateway: widget.service)
        : LoginScreen(client: widget.service);
  }
}
