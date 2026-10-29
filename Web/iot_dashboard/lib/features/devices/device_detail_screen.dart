import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../../models/device.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/soft_3d_decorations.dart';

typedef DeviceDetailScreen = FeatureDeviceDetailScreen;

class FeatureDeviceDetailScreen extends ConsumerStatefulWidget {
  final String deviceId;

  const FeatureDeviceDetailScreen({super.key, required this.deviceId});

  @override
  ConsumerState<FeatureDeviceDetailScreen> createState() => _FeatureDeviceDetailScreenState();
}

class _FeatureDeviceDetailScreenState extends ConsumerState<FeatureDeviceDetailScreen> {
  bool _showAdvanced = false;

  String _getChannelPin(String? channel) {
    switch (channel) {
      case 'ch2':
        return 'GPIO 5';
      case 'ch3':
        return 'GPIO 6 / 7 (Latching)';
      case 'ch1':
      default:
        return 'GPIO 4';
    }
  }

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
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                tooltip: device.isFavorite ? 'Xóa khỏi yêu thích' : 'Thêm vào yêu thích',
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

                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 20),
                  decoration: Soft3DDecorations.card(
                    isDark: isDark,
                    isActive: device.isOn && device.online,
                    accentColor: accentColor,
                    radius: 26.0,
                  ),
                  child: Column(
                    children: [
                      Container(
                        width: 76,
                        height: 76,
                        decoration: Soft3DDecorations.iconWell(
                          isDark: isDark,
                          isActive: device.isOn && device.online,
                          accentColor: accentColor,
                          radius: 22,
                        ),
                        child: Icon(
                          device.iconData,
                          size: 38,
                          color: device.isOn && device.online
                              ? accentColor
                              : (isDark ? const Color(0xFF64748B) : const Color(0xFF94A3B8)),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        device.name,
                        textAlign: TextAlign.center,
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

                      if (device.metadata['can_dim'] == true || device.metadata['has_slider'] == true) ...[
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
                      ],
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        decoration: Soft3DDecorations.pill(
                          isDark: isDark,
                          isSelected: false,
                          radius: 14,
                        ),
                        child: Text(
                          device.measurementText,
                          textAlign: TextAlign.center,
                          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                        ),
                      ),
                      const SizedBox(height: 18),

                      SoftBounce(
                        onTap: device.online
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
                        child: Container(
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(18),
                            gradient: (device.isOn && device.online)
                                ? LinearGradient(
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                    colors: [
                                      accentColor,
                                      Color.alphaBlend(Colors.black.withValues(alpha: 0.16), accentColor),
                                    ],
                                  )
                                : LinearGradient(
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                    colors: isDark
                                        ? const [Color(0xFF242D3D), Color(0xFF161B26)]
                                        : const [Color(0xFFFFFFFF), Color(0xFFEEF2F6)],
                                  ),
                            border: Border.all(
                              color: (device.isOn && device.online)
                                  ? accentColor.withValues(alpha: 0.6)
                                  : (isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0)),
                              width: 1.0,
                            ),
                            boxShadow: [
                              if (device.isOn && device.online) ...[
                                BoxShadow(
                                  color: accentColor.withValues(alpha: isDark ? 0.45 : 0.35),
                                  blurRadius: 18,
                                  offset: const Offset(0, 6),
                                ),
                                BoxShadow(
                                  color: accentColor.withValues(alpha: 0.20),
                                  blurRadius: 6,
                                  offset: const Offset(0, 2),
                                ),
                              ] else ...[
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: isDark ? 0.35 : 0.05),
                                  blurRadius: 8,
                                  offset: const Offset(0, 3),
                                ),
                                if (!isDark)
                                  BoxShadow(
                                    color: Colors.white.withValues(alpha: 0.9),
                                    blurRadius: 2,
                                    offset: const Offset(0, -1),
                                  ),
                              ],
                            ],
                          ),
                          child: FilledButton.icon(
                            icon: Icon(device.isOn ? Icons.power_settings_new_rounded : Icons.power_rounded),
                            label: Text(device.isOn ? 'Tắt nguồn' : 'Bật nguồn'),
                            style: FilledButton.styleFrom(
                              minimumSize: const Size(168, 50),
                              backgroundColor: Colors.transparent,
                              shadowColor: Colors.transparent,
                              foregroundColor: (device.isOn && device.online)
                                  ? Colors.white
                                  : theme.colorScheme.onSurface,
                              padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 12),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
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
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),

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

                Container(
                  decoration: Soft3DDecorations.card(
                    isDark: isDark,
                    radius: 20.0,
                  ),
                  child: Theme(
                    data: theme.copyWith(dividerColor: Colors.transparent),
                    child: ExpansionTile(
                      initiallyExpanded: _showAdvanced,
                      onExpansionChanged: (val) => setState(() => _showAdvanced = val),
                      tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                      collapsedShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                      backgroundColor: Colors.transparent,
                      collapsedBackgroundColor: Colors.transparent,
                      leading: Container(
                        width: 32,
                        height: 32,
                        decoration: Soft3DDecorations.iconWell(
                          isDark: isDark,
                          radius: 10,
                        ),
                        child: const Icon(Icons.code_rounded, size: 18),
                      ),
                      title: const Text(
                        'Cấu hình nâng cao (Kỹ thuật)',
                        style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                      ),
                      children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          child: Column(
                            children: [
                              Divider(
                                height: 1,
                                color: isDark ? const Color(0xFF283446) : const Color(0xFFE2E8F0),
                              ),
                              const SizedBox(height: 12),
                              _TechRow(label: 'Node ID', value: device.actionBoxId ?? device.id),
                              _TechRow(label: 'Kênh phần cứng', value: '${device.channel ?? "ch1"} (${_getChannelPin(device.channel)})'),
                              _TechRow(label: 'Địa chỉ MAC', value: device.metadata['mac']?.toString().isNotEmpty == true ? device.metadata['mac'].toString() : '30:ED:A0:BD:69:D4'),
                              _TechRow(label: 'Chủ đề MQTT Lệnh', value: 'smarthome/cmd/${device.actionBoxId ?? "esp32s3_master"}'),
                              _TechRow(label: 'Chủ đề MQTT Trạng thái', value: 'smarthome/status/${device.actionBoxId ?? "esp32s3_master"}'),
                              const _TechRow(label: 'Phần cứng', value: 'ESP32-S3 N16R8 (Active-LOW)'),
                            ],
                          ),
                        ),
                      ],
                    ),
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

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: Soft3DDecorations.card(
        isDark: isDark,
        radius: 18.0,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: Soft3DDecorations.iconWell(
              isDark: isDark,
              radius: 10.0,
            ),
            child: Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: const TextStyle(fontSize: 12, fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }
}
