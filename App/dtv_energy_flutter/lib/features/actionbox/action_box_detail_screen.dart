import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../../models/action_box.dart';
import '../../models/device.dart';
import '../../providers/smart_home_providers.dart';

class FeatureActionBoxDetailScreen extends ConsumerWidget {
  final String actionBoxId;

  const FeatureActionBoxDetailScreen({super.key, required this.actionBoxId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    final actionBoxesAsync = ref.watch(actionBoxesStreamProvider);

    return actionBoxesAsync.when(
      data: (boxes) {
        final ab = boxes.firstWhere(
          (b) => b.id == actionBoxId,
          orElse: () => const ActionBox(id: 'unknown', name: 'Không tìm thấy ActionBox', roomId: '', channels: []),
        );

        return Scaffold(
          appBar: AppBar(
            title: Text(ab.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          ),
          body: SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Controller Overview Card
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: colors.cardSurface,
                    borderRadius: BorderRadius.circular(AppTheme.cardRadius),
                    border: Border.all(color: colors.cardBorder),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Icon(Icons.developer_board_rounded, size: 24, color: theme.colorScheme.primary),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(ab.name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                            const SizedBox(height: 3),
                            Text(
                              'WiFi: ${ab.signalStrength} dBm · Firmware: ${ab.firmwareVersion}',
                              style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: ab.online ? colors.online.withValues(alpha: 0.12) : colors.offline.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          ab.online ? 'Online' : 'Offline',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: ab.online ? colors.online : colors.offline),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                Text(
                  '${ab.channels.length} Kênh rơ-le phần cứng',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, letterSpacing: -0.3),
                ),
                const SizedBox(height: 4),
                Text(
                  'Chạm vào kênh để đổi tên, đổi loại tải hoặc gán phòng',
                  style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: 16),

                // Channel Cards
                ...ab.channels.map((ch) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _ChannelItemCard(
                      channel: ch,
                      online: ab.online,
                      onEdit: () {
                        _showEditChannelDialog(context, ref, ab, ch);
                      },
                    ),
                  );
                }),
              ],
            ),
          ),
        );
      },
      loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (e, _) => Scaffold(body: Center(child: Text('Lỗi: $e'))),
    );
  }

  void _showEditChannelDialog(BuildContext context, WidgetRef ref, ActionBox ab, ActionBoxChannel ch) {
    final nameCtrl = TextEditingController(text: ch.name);
    final aliasCtrl = TextEditingController(text: ch.name.toLowerCase());
    var selectedType = ch.type;
    var selectedRoom = ab.roomId;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Padding(
              padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Cấu hình ${ch.channelKey.toUpperCase()}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                      IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
                    ],
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: nameCtrl,
                    decoration: const InputDecoration(labelText: 'Tên thiết bị (ví dụ: Quạt trần, Đèn chính)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<DeviceType>(
                    value: selectedType,
                    decoration: const InputDecoration(labelText: 'Loại thiết bị', border: OutlineInputBorder()),
                    items: const [
                      DropdownMenuItem(value: DeviceType.light, child: Text('💡 Đèn chiếu sáng')),
                      DropdownMenuItem(value: DeviceType.fan, child: Text('💨 Quạt làm mát')),
                      DropdownMenuItem(value: DeviceType.socket, child: Text('⚡ Ổ cắm điện')),
                      DropdownMenuItem(value: DeviceType.airConditioner, child: Text('❄️ Điều hòa nhiệt độ')),
                      DropdownMenuItem(value: DeviceType.custom, child: Text('🔌 Tải tùy chỉnh')),
                    ],
                    onChanged: (val) {
                      if (val != null) setModalState(() => selectedType = val);
                    },
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: aliasCtrl,
                    decoration: const InputDecoration(labelText: 'Tên gọi giọng nói (cách nhau bởi dấu phẩy)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 14)),
                      onPressed: () async {
                        HapticFeedback.mediumImpact();
                        final aliases = aliasCtrl.text.split(',').map((s) => s.trim().toLowerCase()).where((s) => s.isNotEmpty).toList();
                        await ref.read(actionBoxRepositoryProvider).updateChannel(
                              actionBoxId: ab.id,
                              channelIndex: ch.index,
                              name: nameCtrl.text.trim(),
                              type: selectedType,
                              roomId: selectedRoom,
                              voiceAliases: aliases,
                            );
                        if (context.mounted) Navigator.pop(context);
                      },
                      child: const Text('Lưu thay đổi & Đồng bộ toàn hệ thống'),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _ChannelItemCard extends StatelessWidget {
  final ActionBoxChannel channel;
  final bool online;
  final VoidCallback onEdit;

  const _ChannelItemCard({
    required this.channel,
    required this.online,
    required this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.cardSurface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: colors.cardBorder),
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: channel.isOn && online ? colors.lightWash : (isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9)),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              channel.type == DeviceType.light
                  ? Icons.lightbulb_rounded
                  : (channel.type == DeviceType.fan ? Icons.air_rounded : Icons.power_rounded),
              color: channel.isOn && online ? colors.lightAccent : theme.colorScheme.onSurfaceVariant,
              size: 20,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${channel.channelKey.toUpperCase()} · ${channel.name}',
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  channel.configured ? 'Đã gán · ${channel.isOn && online ? "Đang bật" : "Đã tắt"}' : 'Chưa cấu hình thiết bị',
                  style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          OutlinedButton(
            onPressed: onEdit,
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: const Text('Cấu hình', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}
