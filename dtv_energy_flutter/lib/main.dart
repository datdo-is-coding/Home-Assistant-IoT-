import 'package:flutter/material.dart';
import 'screens/dashboard_screen.dart';
import 'screens/analytics_screen.dart';
import 'screens/alerts_screen.dart';
import 'screens/ota_update_screen.dart';
import 'screens/settings_screen.dart';
import 'services/energy_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await EnergyService().loadSettings();
  runApp(const DTVEnergyApp());
}

class DTVEnergyApp extends StatelessWidget {
  const DTVEnergyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DTV Energy Hub',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0F172A),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF38BDF8),
          surface: Color(0xFF1E293B),
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
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: Color(0xFF1E293B), width: 1)),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) => setState(() => _currentIndex = index),
          backgroundColor: const Color(0xFF0F172A),
          selectedItemColor: const Color(0xFF38BDF8),
          unselectedItemColor: const Color(0xFF64748B),
          type: BottomNavigationBarType.fixed,
          selectedFontSize: 11,
          unselectedFontSize: 10,
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.dashboard_rounded), label: "Tổng Quan"),
            BottomNavigationBarItem(icon: Icon(Icons.bar_chart_rounded), label: "Phân Tích"),
            BottomNavigationBarItem(icon: Icon(Icons.notifications_active), label: "Cảnh Báo"),
            BottomNavigationBarItem(icon: Icon(Icons.system_update_alt), label: "OTA"),
            BottomNavigationBarItem(icon: Icon(Icons.settings), label: "Cài Đặt"),
          ],
        ),
      ),
    );
  }
}
