import 'package:flutter/material.dart';
import 'screens/dashboard_screen.dart';
import 'screens/analytics_screen.dart';
import 'screens/alerts_screen.dart';
import 'screens/ota_update_screen.dart';
import 'screens/settings_screen.dart';
import 'services/energy_service.dart';
import 'services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await EnergyService().loadSettings();
  await NotificationService().init();
  runApp(const DTVEnergyApp());
}

class DTVEnergyApp extends StatelessWidget {
  const DTVEnergyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DTV Energy Hub - Echo Nightly Edition',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF090D16),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00F2FE),
          secondary: Color(0xFF7C3AED),
          surface: Color(0xFF131B2E),
        ),
        useMaterial3: true,
      ),
      home: const MainTabNavigator(),
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
    AnalyticsScreen(),
    AlertsScreen(),
    OTAUpdateScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF090D16),
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: Container(
        margin: const EdgeInsets.fromLTRB(14, 0, 14, 16),
        height: 64,
        decoration: BoxDecoration(
          color: const Color(0xFF131B2E).withOpacity(0.85),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: const Color(0xFF00F2FE).withOpacity(0.25), width: 1.2),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF00F2FE).withOpacity(0.12),
              blurRadius: 20,
              spreadRadius: 2,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _navItem(0, Icons.grid_view_rounded, "Tổng Quan"),
            _navItem(1, Icons.show_chart_rounded, "Phân Tích"),
            _navItem(2, Icons.notifications_active_rounded, "Cảnh Báo"),
            _navItem(3, Icons.system_update_rounded, "OTA"),
            _navItem(4, Icons.settings_rounded, "Cài Đặt"),
          ],
        ),
      ),
    );
  }

  Widget _navItem(int index, IconData icon, String label) {
    final isSelected = _currentIndex == index;
    return GestureDetector(
      onTap: () => setState(() => _currentIndex = index),
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: isSelected
            ? BoxDecoration(
                gradient: LinearGradient(
                  colors: [const Color(0xFF00F2FE).withOpacity(0.25), const Color(0xFF7C3AED).withOpacity(0.25)],
                ),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF00F2FE).withOpacity(0.6), width: 1),
              )
            : null,
        child: Row(
          children: [
            Icon(
              icon,
              size: 20,
              color: isSelected ? const Color(0xFF00F2FE) : const Color(0xFF64748B),
            ),
            if (isSelected) ...[
              const SizedBox(width: 6),
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 11.5,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
