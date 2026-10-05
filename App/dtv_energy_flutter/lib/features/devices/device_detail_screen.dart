import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../../models/device.dart';
import '../../providers/smart_home_providers.dart';

class FeatureDeviceDetailScreen extends ConsumerStatefulWidget {
  final String deviceId;

  const FeatureDeviceDetailScreen({super.key, required this.deviceId});

  @override
  ConsumerState<FeatureDeviceDetailScreen> createState() => _FeatureDeviceDetailScreenState();
}

class _FeatureDeviceDetailScreenState extends ConsumerState<FeatureDeviceDetailScreen> {
  bool _showAdvanced = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    final devicesAsync = ref.watch(devicesStreamProvider);

    return devicesAsync.when(
      data: (devices) {
        final device = devices.firstWhere(
          (d) => d.id == widget.deviceId,
          orElse: () => const Device(id: 'unknown', name: 'Thiết bị không tồn tại', type: DeviceType.light, roomId: ''),
        );

        final Color accentColor = switch (device.type) {
          DeviceType.light => colors.lightAccent,
          DeviceType.fan => colors.fanAccent,
          DeviceType.socket => colors.socketAccent,
          DeviceType.airConditioner => colors.climateAccent,
          _ => colors.socketAccent,
        };

        return Scaffold(
          appBar: AppBar(
            title: Text(device.name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
            actions: [
              IconButton(
                icon: Icon(
                  device.isFavorite ? Icons.star_rounded : Icons.star_outline_rounded,
                  color: device.isFavorite ? const Color(0xFFF59E0B) : null,
                ),
                onPressed: () {
                  HapticFeedback.selectionClick();
                  ref.read(deviceRepositoryProvider).toggleFavorite(device.id);
                },
              ),
            ],
          ),
          body: SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            child: Column(
              children: [
                // Hero Control Box
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 20),
                  decoration: BoxDecoration(
                    color: device.isOn && device.online
                        ? (isDark
                            ? Color.alphaBlend(accentColor.withValues(alpha: 0.14), const Color(0xFF161B26))
                            : Color.alphaBlend(accentColor.withValues(alpha: 0.08), Colors.white))
                        : colors.cardSurface,
                    borderRadius: BorderRadius.circular(AppTheme.cardRadius),
                    border: Border.all(
                      color: device.isOn && device.online
                          ? accentColor.withValues(alpha: 0.4)
                          : colors.cardBorder,
                    ),
                  ),
                  child: Column(
                    children: [
                      Container(
                        width: 72,
                        height: 72,
                        decoration: BoxDecoration(
                          color: device.isOn && device.online
                              ? accentColor.withValues(alpha: isDark ? 0.25 : 0.16)
                              : (isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9)),
                          borderRadius: BorderRadius.circular(22),
                        ),
                        child: Icon(
                          device.iconData,
                          size: 36,
                          color: device.isOn && device.online ? accentColor : colors.cardBorder,
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        device.name,
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        device.stateText,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: device.isOn && device.online ? accentColor : theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 24),

                      // Capability-driven Control: Slider only shown if device supports dimming or speed/temp
                      if (device.metadata['can_dim'] == true || device.type == DeviceType.airConditioner) ...[
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            trackHeight: 12,
                            activeTrackColor: accentColor,
                            thumbColor: accentColor,
                            thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 12),
                          ),
                          child: Slider(
                            value: device.value.clamp(0.0, 100.0),
                            min: 0.0,
                            max: 100.0,
                            onChanged: device.online
                                ? (val) {
                                    ref.read(deviceRepositoryProvider).setDeviceValue(device.id, val);
                                  }
                                : null,
                          ),
                        ),
                        const SizedBox(height: 12),
                      ] else if (device.metadata['power'] != null && (device.metadata['power'] as num) > 0) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                          decoration: BoxDecoration(
                            color: isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            'Công suất tiêu thụ: ${(device.metadata['power'] as num).toStringAsFixed(1)} W',
                            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                          ),
                        ),
                        const SizedBox(height: 16),
                      ],

                      FilledButton.icon(
                        icon: Icon(device.isOn ? Icons.power_settings_new_rounded : Icons.power_rounded),
                        label: Text(device.isOn ? 'Tắt nguồn' : 'Bật nguồn'),
                        style: FilledButton.styleFrom(
                          backgroundColor: device.isOn ? accentColor : (isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9)),
                          foregroundColor: device.isOn ? Colors.white : theme.colorScheme.onSurface,
                          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        ),
                        onPressed: device.online
                            ? () async {
                                HapticFeedback.lightImpact();
                                try {
                                  await ref.read(deviceRepositoryProvider).toggleDevice(device.id, !device.isOn);
                                } catch (e) {
                                  if (context.mounted) {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(content: Text('Lỗi điều khiển thiết bị: $e')),
                                    );
                                  }
                                }
                              }
                            : null,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),

                // Settings Cards Group
                _SettingTile(
                  icon: Icons.meeting_room_outlined,
                  title: 'Khu vực / Phòng',
                  value: device.roomId.isNotEmpty ? device.roomId : 'Chưa phân phòng',
                ),
                const SizedBox(height: 8),
                _SettingTile(
                  icon: Icons.developer_board_outlined,
                  title: 'Bộ điều khiển ActionBox',
                  value: device.actionBoxId ?? 'Kết nối trực tiếp',
                ),
                const SizedBox(height: 8),
                _SettingTile(
                  icon: Icons.alt_route_rounded,
                  title: 'Kênh rơ-le phần cứng',
                  value: device.channel?.toUpperCase() ?? 'Kênh 1',
                ),
                const SizedBox(height: 8),
                _SettingTile(
                  icon: Icons.record_voice_over_outlined,
                  title: 'Tên gọi giọng nói',
                  value: device.voiceAliases.isNotEmpty ? device.voiceAliases.join(', ') : 'Chưa thiết lập',
                ),
                const SizedBox(height: 16),

                // Collapsible Advanced Settings (Engineering Internals)
                Theme(
                  data: theme.copyWith(dividerColor: Colors.transparent),
                  child: ExpansionTile(
                    initiallyExpanded: _showAdvanced,
                    onExpansionChanged: (val) => setState(() => _showAdvanced = val),
                    tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppTheme.cardRadius),
                      side: BorderSide(color: colors.cardBorder),
                    ),
                    collapsedShape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppTheme.cardRadius),
                      side: BorderSide(color: colors.cardBorder),
                    ),
                    backgroundColor: colors.cardSurface,
                    collapsedBackgroundColor: colors.cardSurface,
                    leading: const Icon(Icons.code_rounded, size: 20),
                    title: const Text(
                      'Cấu hình nâng cao (Kỹ thuật)',
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                    ),
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        child: Column(
                          children: [
                            const Divider(height: 1),
                            const SizedBox(height: 12),
                            _TechRow(label: 'Node ID', value: device.actionBoxId ?? device.id),
                            _TechRow(label: 'Kênh phần cứng', value: '${device.channel ?? "ch1"} (${device.channel == "ch2" ? "GPIO 5" : "GPIO 4"})'),
                            _TechRow(label: 'Địa chỉ MAC', value: device.metadata['mac']?.toString().isNotEmpty == true ? device.metadata['mac'].toString() : '30:ED:A0:BD:69:D4'),
                            _TechRow(label: 'Chủ đề MQTT Lệnh', value: 'smarthome/cmd/${device.actionBoxId ?? "esp32s3_master"}'),
                            _TechRow(label: 'Chủ đề MQTT Trạng thái', value: 'smarthome/status/${device.actionBoxId ?? "esp32s3_master"}'),
                            _TechRow(label: 'Phần cứng', value: 'ESP32-S3 N16R8 (Active-LOW)'),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 32),
              ],
            ),
          ),
        );
      },
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (e, _) => Scaffold(body: Center(child: Text('Lỗi: $e'))),
    );
  }
}

class _SettingTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String value;

  const _SettingTile({
    required this.icon,
    required this.title,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: colors.cardSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.cardBorder),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const Spacer(),
          Text(value, style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurfaceVariant)),
        ],
      ),
    );
  }
}

class _TechRow extends StatelessWidget {
  final String label;
  final String value;

  const _TechRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
          Text(value, style: const TextStyle(fontSize: 12, fontFamily: 'monospace')),
        ],
      ),
    );
  }
}
