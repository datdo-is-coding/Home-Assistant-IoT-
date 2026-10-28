import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/pages/welcome_page.dart';

class SystemInfoLogoutCard extends StatelessWidget {
  const SystemInfoLogoutCard({super.key});

  void _showLogoutDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.cardBg(context),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSizes.radiusXl),
        ),
        title: Row(
          children: [
            const Icon(Icons.logout_rounded, color: AppColors.danger),
            const SizedBox(width: AppSizes.md),
            Text(
              "Đăng xuất",
              style: TextStyle(color: AppColors.titleColor(context)),
            ),
          ],
        ),
        content: Text(
          "Bạn có chắc chắn muốn đăng xuất khỏi hệ thống Smart Home Dashboard không?",
          style: TextStyle(color: AppColors.bodyColor(context)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              "Hủy",
              style: TextStyle(color: AppColors.subtleColor(context)),
            ),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.danger,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppSizes.radiusSm),
              ),
            ),
            onPressed: () {
              Navigator.pop(context);
              selectedPageNotifier.value = 0;
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (context) => const WelcomePage()),
                (route) => false,
              );
            },
            child: const Text("Đăng xuất"),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cardBg = AppColors.cardBg(context);
    final borderColor = AppColors.borderColor(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Container(
      padding: const EdgeInsets.all(AppSizes.xl),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSizes.radiusLg),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 15,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(AppSizes.sm),
                decoration: BoxDecoration(
                  color: AppColors.info.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppSizes.radiusSm + 2),
                ),
                child: const Icon(
                  Icons.info_outline_rounded,
                  color: AppColors.info,
                  size: AppSizes.iconMd,
                ),
              ),
              const SizedBox(width: AppSizes.md),
              Text(
                "Thông Tin Hệ Thống & Đăng Xuất",
                style: AppTextStyles.getTitle(context),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.lg),
          const Divider(height: 1),
          const SizedBox(height: AppSizes.md),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.verified_user_outlined),
            title: Text(
              "Phiên bản ứng dụng",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            trailing: const Text(
              "v1.0.0 (Build 2026)",
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: AppColors.info,
              ),
            ),
          ),
          const Divider(height: AppSizes.lg),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.memory_rounded),
            title: Text(
              "Phiên bản Firmware Gateway",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            trailing: Text(
              "ESP32-v2.4.1",
              style: TextStyle(color: AppColors.subtleColor(context)),
            ),
          ),
          const SizedBox(height: AppSizes.xl),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton.icon(
              onPressed: () => _showLogoutDialog(context),
              icon: const Icon(Icons.logout_rounded),
              label: const Text(
                "Đăng xuất khỏi hệ thống",
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                ),
              ),
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.danger,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSizes.radiusMd),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
