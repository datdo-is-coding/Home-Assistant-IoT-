import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';
import 'package:iot_dashboard/data/notifiers.dart';

class UiExperienceCard extends StatefulWidget {
  const UiExperienceCard({super.key});

  @override
  State<UiExperienceCard> createState() => _UiExperienceCardState();
}

class _UiExperienceCardState extends State<UiExperienceCard> {
  String _selectedLanguage = 'Tiếng Việt';
  bool _soundEnabled = true;

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
                  Icons.palette_outlined,
                  color: AppColors.info,
                  size: AppSizes.iconMd,
                ),
              ),
              const SizedBox(width: AppSizes.md),
              Text(
                "Giao Diện & Trải Nghiệm",
                style: AppTextStyles.getTitle(context),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.lg),
          const Divider(height: 1),
          const SizedBox(height: AppSizes.md),
          ValueListenableBuilder<bool>(
            valueListenable: isDarkModeNotifier,
            builder: (context, isDarkMode, child) {
              return SwitchListTile(
                contentPadding: EdgeInsets.zero,
                secondary: Icon(
                  isDarkMode ? Icons.dark_mode : Icons.light_mode,
                  color: isDarkMode ? Colors.amber : AppColors.info,
                ),
                title: Text(
                  "Chế độ tối (Dark Mode)",
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: AppColors.titleColor(context),
                  ),
                ),
                subtitle: Text(
                  "Chuyển đổi tông màu sáng / tối cho toàn bộ Dashboard",
                  style: TextStyle(
                    fontSize: AppFontSizes.bodySmall,
                    color: AppColors.subtleColor(context),
                  ),
                ),
                value: isDarkMode,
                onChanged: (value) {
                  isDarkModeNotifier.value = value;
                },
              );
            },
          ),
          const Divider(height: AppSizes.lg),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(
              Icons.language,
              color: Colors.teal,
            ),
            title: Text(
              "Ngôn ngữ hiển thị",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            subtitle: Text(
              "Chọn ngôn ngữ sử dụng trên bảng điều khiển",
              style: TextStyle(
                fontSize: AppFontSizes.bodySmall,
                color: AppColors.subtleColor(context),
              ),
            ),
            trailing: DropdownButton<String>(
              value: _selectedLanguage,
              dropdownColor: cardBg,
              underline: const SizedBox.shrink(),
              style: TextStyle(
                color: AppColors.titleColor(context),
                fontSize: AppFontSizes.bodyMedium,
              ),
              items: [
                DropdownMenuItem(
                  value: 'Tiếng Việt',
                  child: Text(
                    'Tiếng Việt 🇻🇳',
                    style: TextStyle(color: AppColors.titleColor(context)),
                  ),
                ),
                DropdownMenuItem(
                  value: 'English',
                  child: Text(
                    'English 🇺🇸',
                    style: TextStyle(color: AppColors.titleColor(context)),
                  ),
                ),
              ],
              onChanged: (value) {
                if (value != null) {
                  setState(() {
                    _selectedLanguage = value;
                  });
                }
              },
            ),
          ),
          const Divider(height: AppSizes.lg),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            secondary: const Icon(
              Icons.volume_up_outlined,
              color: Colors.purple,
            ),
            title: Text(
              "Âm thanh hiệu ứng & Cảnh báo",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            subtitle: Text(
              "Phát âm thanh thông báo khi có sự cố điện",
              style: TextStyle(
                fontSize: AppFontSizes.bodySmall,
                color: AppColors.subtleColor(context),
              ),
            ),
            value: _soundEnabled,
            onChanged: (value) {
              setState(() {
                _soundEnabled = value;
              });
            },
          ),
        ],
      ),
    );
  }
}
