import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/constants.dart';

class MqttConfigCard extends StatefulWidget {
  const MqttConfigCard({super.key});

  @override
  State<MqttConfigCard> createState() => _MqttConfigCardState();
}

class _MqttConfigCardState extends State<MqttConfigCard> {
  final TextEditingController _brokerController =
      TextEditingController(text: '192.168.1.100');
  final TextEditingController _portController =
      TextEditingController(text: '1883');
  bool _autoReconnect = true;

  @override
  void dispose() {
    _brokerController.dispose();
    _portController.dispose();
    super.dispose();
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
                  Icons.hub_outlined,
                  color: AppColors.info,
                  size: AppSizes.iconMd,
                ),
              ),
              const SizedBox(width: AppSizes.md),
              Text(
                "Kết Nối IoT & Máy Chủ MQTT",
                style: AppTextStyles.getTitle(context),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.lg),
          const Divider(height: 1),
          const SizedBox(height: AppSizes.lg),
          Row(
            children: [
              Expanded(
                flex: 2,
                child: TextField(
                  controller: _brokerController,
                  style: TextStyle(color: AppColors.titleColor(context)),
                  decoration: InputDecoration(
                    labelText: 'Địa chỉ IP Broker',
                    labelStyle: TextStyle(color: AppColors.subtleColor(context)),
                    hintText: '192.168.1.100',
                    border: const OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: AppSizes.md),
              Expanded(
                child: TextField(
                  controller: _portController,
                  style: TextStyle(color: AppColors.titleColor(context)),
                  decoration: InputDecoration(
                    labelText: 'Cổng (Port)',
                    labelStyle: TextStyle(color: AppColors.subtleColor(context)),
                    hintText: '1883',
                    border: const OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSizes.lg),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            secondary: const Icon(
              Icons.sync_rounded,
              color: AppColors.info,
            ),
            title: Text(
              "Tự động kết nối lại khi mất mạng",
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: AppColors.titleColor(context),
              ),
            ),
            subtitle: Text(
              "Đảm bảo luồng dữ liệu công suất không bị gián đoạn",
              style: TextStyle(
                fontSize: AppFontSizes.bodySmall,
                color: AppColors.subtleColor(context),
              ),
            ),
            value: _autoReconnect,
            onChanged: (value) {
              setState(() {
                _autoReconnect = value;
              });
            },
          ),
          const SizedBox(height: AppSizes.md),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text(
                      "Đã kiểm tra kết nối MQTT thành công!",
                    ),
                    backgroundColor: AppColors.success,
                  ),
                );
              },
              icon: const Icon(Icons.wifi_find_rounded),
              label: const Text("Kiểm tra kết nối Broker"),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: AppSizes.md),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSizes.radiusSm + 2),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
