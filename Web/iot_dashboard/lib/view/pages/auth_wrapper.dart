import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import '../../data/notifiers.dart';
import '../../data/services/auth_service.dart';
import '../widgets_tree.dart';
import 'login_page.dart';

class AuthWrapper extends StatelessWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    final authService = AuthService();

    return ValueListenableBuilder<bool>(
      valueListenable: isGuestModeNotifier,
      builder: (context, isGuest, child) {
        if (isGuest) {
          return const WidgetsTree();
        }

        return StreamBuilder<User?>(
          stream: authService.authStateChanges,
          builder: (context, snapshot) {
            // Đang tải dữ liệu từ Firebase
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Scaffold(
                body: Center(
                  child: CircularProgressIndicator(),
                ),
              );
            }

            // Người dùng đã đăng nhập -> Chuyển vào WidgetsTree (Dashboard)
            if (snapshot.hasData && snapshot.data != null) {
              return const WidgetsTree();
            }

            // Chưa đăng nhập -> Chuyển vào Màn hình Đăng nhập
            return const LoginPage();
          },
        );
      },
    );
  }
}
