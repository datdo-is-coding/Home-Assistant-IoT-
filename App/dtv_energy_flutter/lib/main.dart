import 'package:flutter/material.dart';
import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/provisioning_screen.dart';
import 'screens/ota_update_screen.dart';
import 'screens/analytics_screen.dart';
import 'screens/settings_screen.dart';
import 'services/energy_service.dart';
import 'services/notification_service.dart';
import 'services/theme_service.dart';
import 'widgets/weather_glass_overlay.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final hasSession = await EnergyService().loadSettings();
  await NotificationService().init();
  await ThemeService().loadTheme();
  runApp(DTVEnergyApp(hasValidSession: hasSession));
}

class DTVEnergyApp extends StatelessWidget {
  final bool hasValidSession;
  const DTVEnergyApp({super.key, required this.hasValidSession});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: ThemeService(),
      builder: (context, child) {
        final currentTheme = ThemeService().currentTheme;
        return MaterialApp(
          title: 'AETHERIA OS — Spatial Smart Home',
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            brightness: Brightness.dark,
            scaffoldBackgroundColor: currentTheme.bg,
            colorScheme: ColorScheme.dark(
              primary: currentTheme.primary,
              secondary: currentTheme.secondary,
              surface: currentTheme.surface,
            ),
            useMaterial3: true,
          ),
          home: hasValidSession ? const MainTabNavigator() : const LoginScreen(),
        );
      },
    );
  }
}

class MainTabNavigator extends StatefulWidget {
  const MainTabNavigator({super.key});

  @override
  State<MainTabNavigator> createState() => _MainTabNavigatorState();
}

class _MainTabNavigatorState extends State<MainTabNavigator> {
  int _currentIndex = 0;

  final List<Widget> _screens = const [
    DashboardScreen(),
    ProvisioningScreen(),
    OTAUpdateScreen(),
    AnalyticsScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = ThemeService().currentTheme;
    return Scaffold(
      backgroundColor: theme.bg,
      body: WeatherGlassOverlay(
        child: IndexedStack(
          index: _currentIndex,
          children: _screens,
        ),
      ),
      bottomNavigationBar: Container(
        margin: const EdgeInsets.fromLTRB(14, 0, 14, 16),
        height: 64,
        decoration: BoxDecoration(
          color: theme.surface.withOpacity(0.9),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: theme.primary.withOpacity(0.3), width: 1.2),
          boxShadow: [
            BoxShadow(
              color: theme.primary.withOpacity(0.12),
              blurRadius: 20,
              spreadRadius: 2,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _navItem(0, Icons.grid_view_rounded, "Tổng Quan", theme),
            _navItem(1, Icons.sensors_rounded, "Gán Thiết Bị", theme),
            _navItem(2, Icons.system_update_rounded, "OTA", theme),
            _navItem(3, Icons.show_chart_rounded, "Phân Tích", theme),
            _navItem(4, Icons.settings_rounded, "Cài Đặt", theme),
          ],
        ),
      ),
    );
  }

  Widget _navItem(int index, IconData icon, String label, AppThemeData theme) {
    final isSelected = _currentIndex == index;
    return GestureDetector(
      onTap: () => setState(() => _currentIndex = index),
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: isSelected
            ? BoxDecoration(
                gradient: LinearGradient(
                  colors: [theme.primary.withOpacity(0.25), theme.secondary.withOpacity(0.25)],
                ),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: theme.primary.withOpacity(0.5)),
              )
            : null,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 20,
              color: isSelected ? theme.primary : Colors.white.withOpacity(0.5),
            ),
            const SizedBox(height: 3),
            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                color: isSelected ? Colors.white : Colors.white.withOpacity(0.5),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
