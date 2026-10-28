import 'package:flutter/material.dart';
import 'package:iot_dashboard/view/widgets/common/custom_searchbar.dart';
import 'package:iot_dashboard/view/widgets/common/user_avatar_menu.dart';

class TopbarWidget extends StatelessWidget {
  const TopbarWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final pillBg = isDark ? const Color(0xFF1E293B) : Colors.grey.shade100;
    final pillBorder = isDark ? const Color(0xFF334155) : Colors.white70;

    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(
          bottom: BorderSide(color: theme.dividerColor, width: 1),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 1. Bên trái: Ô tìm kiếm (có lề trái 16px để không sát mép)
          const Expanded(
            child: Row(
              children: [
                SizedBox(width: 16),
                CustomSearchAutocomplete(),
              ],
            ),
          ),

          const SizedBox(width: 16),

          // 2. Bên phải: Badge thông báo "You have 27 new leads", Chuông thông báo & Avatar
          Row(
            children: [
              // Thanh thông báo pill: "Bạn có 27 thông báo mới 👉"
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: pillBg,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: pillBorder, width: 0.8),
                ),
                child: RichText(
                  text: TextSpan(
                    style: TextStyle(
                      fontSize: 12,
                      color: isDark ? Colors.white : Colors.black87,
                    ),
                    children: [
                      TextSpan(
                        text: 'Bạn có ',
                        style: TextStyle(
                          color: isDark ? Colors.grey.shade400 : Colors.grey,
                        ),
                      ),
                      TextSpan(
                        text: '27 thông báo mới ',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : Colors.black87,
                        ),
                      ),
                      const TextSpan(text: '👉'),
                    ],
                  ),
                ),
              ),

              const SizedBox(width: 12),

              // Icon chuông thông báo (kèm chấm đỏ/xanh chuẩn thiết kế)
              Stack(
                children: [
                  IconButton(
                    icon: const Icon(Icons.notifications_none_rounded),
                    color: isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                    iconSize: 22,
                    onPressed: () {},
                  ),
                  Positioned(
                    right: 12,
                    top: 12,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: Colors.blueAccent,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(width: 4),

              // Avatar không còn phần chữ bên cạnh (Chỉ có CircleAvatar + Arrow Dropdown)
              const UserAvatarMenu(),
            ],
          ),
        ],
      ),
    );
  }
}
