import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'services/gateway_client.dart';

final gateway = GatewayClient();
final appTheme = ValueNotifier<ThemeMode>(ThemeMode.system);

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await gateway.restore();
  runApp(const DTVEnergyApp());
}

ThemeData homeTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF147D68),
    brightness: brightness,
    primary: dark ? const Color(0xFF80D8BE) : const Color(0xFF147D68),
    secondary: const Color(0xFFCC8A27),
    surface: dark ? const Color(0xFF191D1C) : Colors.white,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor:
        dark ? const Color(0xFF101312) : const Color(0xFFF4F6F5),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
          fontSize: 28, fontWeight: FontWeight.w700, letterSpacing: 0),
      titleLarge: TextStyle(
          fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: 0),
      titleMedium: TextStyle(
          fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: 0),
      bodyMedium: TextStyle(fontSize: 14, height: 1.45, letterSpacing: 0),
    ),
    appBarTheme: AppBarTheme(
        backgroundColor:
            dark ? const Color(0xFF101312) : const Color(0xFFF4F6F5),
        scrolledUnderElevation: 0),
    cardTheme: CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        color: scheme.surface,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: BorderSide(
                color: scheme.outlineVariant.withValues(alpha: .55)))),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
      enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: scheme.outlineVariant)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
    ),
    filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
            minimumSize: const Size(48, 52),
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            textStyle: const TextStyle(
                fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: 0))),
    outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
            minimumSize: const Size(48, 48),
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8)))),
    navigationBarTheme: NavigationBarThemeData(
        backgroundColor: scheme.surface,
        elevation: 0,
        indicatorColor: scheme.primaryContainer,
        labelTextStyle: const WidgetStatePropertyAll(
            TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
    dividerTheme:
        DividerThemeData(color: scheme.outlineVariant.withValues(alpha: .5)),
  );
}

class DTVEnergyApp extends StatelessWidget {
  const DTVEnergyApp({super.key, this.client});
  final GatewayClient? client;
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
        home: service.authenticated
            ? HomeScreen(gateway: service)
            : LoginScreen(client: service),
      ),
    );
  }
}
