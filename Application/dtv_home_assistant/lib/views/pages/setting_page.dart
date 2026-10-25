import 'package:flutter/material.dart';
import 'package:dtv_home_assistant/data/notifiers.dart';
import 'package:dtv_home_assistant/data/services/auth_service.dart';

class SettingPage extends StatefulWidget {
  const SettingPage({super.key, required this.title});

  final String title;

  @override
  State<SettingPage> createState() => _SettingPageState();
}

class _SettingPageState extends State<SettingPage> {
  bool _notificationsEnabled = true;
  bool _autoReconnect = true;
  final AuthService _authService = AuthService();

  void _showLogoutDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
        title: const Row(
          children: [
            Icon(Icons.logout, color: Colors.red),
            SizedBox(width: 10),
            Text("Đăng xuất"),
          ],
        ),
        content: const Text(
          "Bạn có chắc chắn muốn đăng xuất khỏi ứng dụng Home Companion không?",
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text("Hủy"),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Colors.red,
            ),
            onPressed: () async {
              final nav = Navigator.of(context);
              nav.pop();
              selectedPageNotifier.value = 0;
              await _authService.signOut();
              if (mounted) {
                nav.popUntil((route) => route.isFirst);
              }
            },
            child: const Text("Đăng xuất"),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title, ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, top: 16.0, bottom: 8.0),
      child: Text(
        title,
        style: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: theme.colorScheme.primary,
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Section 1: Tài khoản
            _buildSectionTitle("Tài khoản", theme),
            Card(
              elevation: 0,
              color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.person_outline),
                    title: Text(_authService.currentUser?.displayName ?? "Người dùng"),
                    subtitle: Text(_authService.currentUser?.email ?? "Chưa đăng nhập"),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {},
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  ListTile(
                    leading: const Icon(Icons.lock_outline),
                    title: const Text("Đổi mật khẩu"),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {},
                  ),
                ],
              ),
            ),

            // Section 2: Giao diện & Hệ thống
            _buildSectionTitle("Giao diện & Hệ thống", theme),
            Card(
              elevation: 0,
              color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  ValueListenableBuilder<bool>(
                    valueListenable: isDarkModeNotifier,
                    builder: (context, isDarkMode, child) {
                      return SwitchListTile.adaptive(
                        secondary: Icon(
                          isDarkMode
                              ? Icons.dark_mode_outlined
                              : Icons.light_mode_outlined,
                        ),
                        title: const Text("Chế độ tối (Dark Mode)"),
                        value: isDarkMode,
                        onChanged: (value) {
                          isDarkModeNotifier.value = value;
                        },
                      );
                    },
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  SwitchListTile.adaptive(
                    secondary: const Icon(Icons.notifications_none_outlined),
                    title: const Text("Thông báo đẩy"),
                    subtitle: const Text("Báo động thiết bị & Trạng thái"),
                    value: _notificationsEnabled,
                    onChanged: (value) {
                      setState(() {
                        _notificationsEnabled = value;
                      });
                    },
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  ListTile(
                    leading: const Icon(Icons.language_outlined),
                    title: const Text("Ngôn ngữ"),
                    trailing: const Text(
                      "Tiếng Việt",
                      style: TextStyle(fontWeight: FontWeight.w500),
                    ),
                    onTap: () {},
                  ),
                ],
              ),
            ),

            // Section 3: Kết nối Smart Home
            _buildSectionTitle("Kết nối & Thiết bị", theme),
            Card(
              elevation: 0,
              color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.hub_outlined),
                    title: const Text("Máy chủ MQTT / Broker"),
                    subtitle: const Text("192.168.1.100:1883"),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {},
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  SwitchListTile.adaptive(
                    secondary: const Icon(Icons.sync_outlined),
                    title: const Text("Tự động kết nối lại"),
                    value: _autoReconnect,
                    onChanged: (value) {
                      setState(() {
                        _autoReconnect = value;
                      });
                    },
                  ),
                ],
              ),
            ),

            // Section 4: Hỗ trợ & Thông tin
            _buildSectionTitle("Hỗ trợ & Thông tin", theme),
            Card(
              elevation: 0,
              color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.help_outline),
                    title: const Text("Trợ giúp & Hướng dẫn sử dụng"),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {},
                  ),
                  const Divider(height: 1, indent: 16, endIndent: 16),
                  ListTile(
                    leading: const Icon(Icons.info_outline),
                    title: const Text("Phiên bản ứng dụng"),
                    trailing: Text(
                      "v1.0.0",
                      style: TextStyle(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Nút Đăng xuất (Logout Button) ở cuối trang
            SizedBox(
              width: double.infinity,
              height: 54,
              child: OutlinedButton.icon(
                onPressed: _showLogoutDialog,
                icon: const Icon(Icons.logout, color: Colors.red),
                label: const Text(
                  "Đăng xuất",
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Colors.red,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.red, width: 1.5),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(32),
                  ),
                ),
              ),
            ),

            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

