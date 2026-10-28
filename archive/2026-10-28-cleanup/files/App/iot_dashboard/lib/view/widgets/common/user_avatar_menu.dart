import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/model/user_model.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/data/services/auth_service.dart';

class UserAvatarMenu extends StatelessWidget {
  const UserAvatarMenu({super.key});

  // Hàm tạo màu đại diện dựa trên tên người dùng
  Color _getAvatarColor(String name) {
    final List<Color> colors = [
      Colors.deepOrange,
      Colors.purple,
      Colors.teal,
      Colors.indigo,
      Colors.pink,
      Colors.blue,
      Colors.amber.shade800,
      Colors.green.shade700,
    ];
    return colors[name.hashCode.abs() % colors.length];
  }

  // Hàm hiển thị Popup Menu ngay BÊN DƯỚI Avatar người dùng
  void _showUserMenu(BuildContext context, UserModel user) {
    final RenderBox button = context.findRenderObject() as RenderBox;
    final RenderBox overlay =
        Overlay.of(context).context.findRenderObject() as RenderBox;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final RelativeRect position = RelativeRect.fromRect(
      Rect.fromPoints(
        button.localToGlobal(
          Offset(0, button.size.height + 6),
          ancestor: overlay,
        ),
        button.localToGlobal(
          button.size.bottomRight(Offset.zero),
          ancestor: overlay,
        ),
      ),
      Offset.zero & overlay.size,
    );

    showMenu<String>(
      context: context,
      position: position,
      elevation: 6,
      color: isDark ? const Color(0xFF1E293B) : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isDark ? const Color(0xFF334155) : Colors.grey.shade200,
          width: 1,
        ),
      ),
      items: <PopupMenuEntry<String>>[
        // 1. HEADER: Hiển thị đúng Tên & Email từ currentUserNotifier
        PopupMenuItem(
          enabled: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                user.name,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.white : Colors.black87,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                user.email,
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                ),
              ),
            ],
          ),
        ),
        const PopupMenuDivider(height: 1),
        // 2. CHUYỂN TỚI TRANG HỒ SƠ
        PopupMenuItem(
          value: 'profile',
          onTap: () => selectedPageNotifier.value = 2,
          child: Row(
            children: [
              Icon(
                Icons.person_outline,
                size: 18,
                color: isDark ? Colors.white70 : Colors.black87,
              ),
              const SizedBox(width: 10),
              Text(
                'Hồ sơ cá nhân',
                style: TextStyle(
                  fontSize: 13,
                  color: isDark ? Colors.white : Colors.black87,
                ),
              ),
            ],
          ),
        ),
        // 3. CHUYỂN TỚI TRANG CÀI ĐẶT
        PopupMenuItem(
          value: 'settings',
          onTap: () => selectedPageNotifier.value = 5,
          child: Row(
            children: [
              Icon(
                Icons.settings_outlined,
                size: 18,
                color: isDark ? Colors.white70 : Colors.black87,
              ),
              const SizedBox(width: 10),
              Text(
                'Cài đặt hệ thống',
                style: TextStyle(
                  fontSize: 13,
                  color: isDark ? Colors.white : Colors.black87,
                ),
              ),
            ],
          ),
        ),
        const PopupMenuDivider(height: 1),
        // 4. ĐĂNG XUẤT
        PopupMenuItem(
          value: 'logout',
          onTap: () async {
            selectedPageNotifier.value = 0;
            await AuthService().signOut();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Đã đăng xuất hệ thống!')),
              );
            }
          },
          child: const Row(
            children: [
              Icon(Icons.logout, size: 18, color: Colors.redAccent),
              SizedBox(width: 10),
              Text(
                'Đăng xuất',
                style: TextStyle(fontSize: 13, color: Colors.redAccent),
              ),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return ValueListenableBuilder<UserModel>(
      valueListenable: currentUserNotifier,
      builder: (context, user, child) {
        final String firstLetter = user.name.trim().isNotEmpty
            ? user.name.trim()[0].toUpperCase()
            : 'U';
        final Color avatarBgColor = _getAvatarColor(user.name);

        return Builder(
          builder: (avatarContext) {
            return InkWell(
              borderRadius: BorderRadius.circular(20),
              splashColor: Colors.blue.shade50,
              highlightColor:
                  isDark ? Colors.grey.shade800 : Colors.grey.shade100,
              hoverColor: isDark ? Colors.grey.shade900 : Colors.grey.shade50,
              onTap: () => _showUserMenu(avatarContext, user),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Hiển thị Avatar ảnh nếu có URL, hoặc CircleAvatar ký tự đại diện
                    CircleAvatar(
                      radius: 16,
                      backgroundColor: avatarBgColor,
                      backgroundImage: user.avatarUrl.isNotEmpty
                          ? NetworkImage(user.avatarUrl)
                          : null,
                      child: user.avatarUrl.isEmpty
                          ? Text(
                              firstLetter,
                              style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                fontSize: 14,
                              ),
                            )
                          : null,
                    ),
                    const SizedBox(width: 2),
                    Icon(
                      Icons.arrow_drop_down,
                      size: 20,
                      color:
                          isDark ? Colors.grey.shade300 : Colors.grey.shade600,
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
}
