import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:iot_dashboard/core/theme/app_theme.dart';
import 'package:iot_dashboard/firebase_options.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/data/services/firebase_realtime_service.dart';
import 'package:iot_dashboard/view/pages/auth_wrapper.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
    FirebaseRealtimeService().init();
  } catch (e) {
    debugPrint('Firebase init notice: $e');
    FirebaseRealtimeService().init();
  }
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: isDarkModeNotifier,
      builder: (context, isDarkMode, child) {
        return MaterialApp(
          debugShowCheckedModeBanner: false,
          title: 'Home Companion - Smart IoT Dashboard',
          themeMode: isDarkMode ? ThemeMode.dark : ThemeMode.light,
          theme: AppTheme.light(),
          darkTheme: AppTheme.dark(),
          home: const AuthWrapper(),
        );
      },
    );
  }
}
