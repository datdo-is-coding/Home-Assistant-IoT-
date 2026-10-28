import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';

class NotificationAlertCard extends StatefulWidget {
  const NotificationAlertCard({super.key});

  @override
  State<NotificationAlertCard> createState() => _NotificationAlertCardState();
}

class _NotificationAlertCardState extends State<NotificationAlertCard> {
  bool _notificationsEnabled = true;

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
                  Icons.notifications_active_outlined,
                  color: AppColors.info,
                  size: AppSizes.iconMd,
                ),
              ),
              const SizedBox(width: AppSizes.md),
              Text(
                "Thông Báo & Báo Động Năng Lượng",
                style: AppTextStyles.getTitle(context),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.lg),
          const Divider(height: 1),
          const SizedBox(height: AppSizes.md),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            secondary: const Icon(
              Icons.notifications_none_rounded,
              color: AppColors.warning,
            ),
            title: Text(
              "Thông báo đẩy (Push Notifications)",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            subtitle: Text(
              "Gửi thông báo tức thì khi công suất vượt định mức",
              style: TextStyle(
                fontSize: AppFontSizes.bodySmall,
                color: AppColors.subtleColor(context),
              ),
            ),
            value: _notificationsEnabled,
            onChanged: (value) {
              setState(() {
                _notificationsEnabled = value;
              });
            },
          ),
          const Divider(height: AppSizes.lg),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(
              Icons.speed_rounded,
              color: AppColors.danger,
            ),
            title: Text(
              "Ngưỡng công suất cảnh báo quá tải",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            subtitle: Text(
              "Cảnh báo tự động khi tổng công suất > 3500 W",
              style: TextStyle(
                fontSize: AppFontSizes.bodySmall,
                color: AppColors.subtleColor(context),
              ),
            ),
            trailing: TextButton(
              onPressed: () {},
              child: const Text("3500 W (Thay đổi)"),
            ),
          ),
        ],
      ),
    );
  }
}
