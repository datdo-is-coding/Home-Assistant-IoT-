import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../models/device.dart';
import '../../providers/smart_home_providers.dart';
import '../../widgets/connectivity_dot.dart';
import '../../widgets/home_connection_name.dart';
import '../../widgets/soft_3d_decorations.dart';

class EnergyScreen extends ConsumerWidget {
  const EnergyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final readings = ref.watch(devicesStreamProvider);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
          child: readings.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => const Center(
            child: Text('Không tải được số đo. Vui lòng thử lại.')),
        data: (devices) {
          final measured = devices
              .where((d) =>
                  d.online &&
                  d.powerWatts != null &&
                  d.powerWatts!.isFinite &&
                  d.powerWatts! >= 0)
              .toList();
          final watts =
              measured.fold<double>(0, (sum, d) => sum + d.powerWatts!);
          final energies = devices
              .map((d) => d.metadata['energy'])
              .whereType<num>()
              .where((v) => v.isFinite && v >= 0)
              .toList();
          final kwh = energies.fold<double>(0, (sum, value) => sum + value);
          final offline = devices.where((d) => !d.online).length;
          return CustomScrollView(
            key: const PageStorageKey('energy-scroll'),
            slivers: [
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
                sliver: SliverToBoxAdapter(
                    child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Expanded(
                          child: Text('Điện năng',
                              style: TextStyle(
                                  fontSize: 30,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: -0.9))),
                      IconButton(
                        tooltip: 'Thông tin số đo',
                        icon: const Icon(Icons.info_outline_rounded, size: 21),
                        onPressed: () => showDialog<void>(
                            context: context,
                            builder: (dialogContext) => AlertDialog(
                                  title: const Text('Số đo điện năng'),
                                  content: Text(
                                      '${measured.length}/${devices.length} kênh có công suất mới.\n'
                                      '${energies.length}/${devices.length} kênh có chỉ số điện năng tích lũy.\n\n'
                                      'Tích lũy là chỉ số công tơ đã ghi nhận, không phải lượng dùng riêng hôm nay. '
                                      'Thanh ngang thể hiện tỷ trọng công suất. Chưa có lịch sử theo giờ/ngày.'),
                                  actions: [
                                    TextButton(
                                        onPressed: () =>
                                            Navigator.pop(dialogContext),
                                        child: const Text('Đóng'))
                                  ],
                                )),
                      ),
                    ]),
                    const HomeConnectionName(),
                    const SizedBox(height: 18),
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: Soft3DDecorations.card(isDark: isDark),
                      child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                                child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                  Text('Công suất',
                                      style: theme.textTheme.bodySmall),
                                  const SizedBox(height: 10),
                                  Text(
                                      measured.isEmpty
                                          ? '— W'
                                          : '${watts.toStringAsFixed(1)} W',
                                      style: const TextStyle(
                                          fontSize: 24,
                                          fontWeight: FontWeight.w700,
                                          letterSpacing: -0.6)),
                                ])),
                            const SizedBox(width: 16),
                            Expanded(
                                child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                  Text(
                                      energies.length < devices.length
                                          ? 'Tích lũy · ${energies.length}/${devices.length}'
                                          : 'Tích lũy',
                                      style: theme.textTheme.bodySmall),
                                  const SizedBox(height: 10),
                                  Text(
                                      energies.isEmpty
                                          ? '— kWh'
                                          : '${kwh.toStringAsFixed(3)} kWh',
                                      style: const TextStyle(
                                          fontSize: 21,
                                          fontWeight: FontWeight.w700,
                                          letterSpacing: -0.6)),
                                ])),
                          ]),
                    ),
                    if (measured.length < devices.length) ...[
                      const SizedBox(height: 10),
                      Text(
                          '${measured.length}/${devices.length} kênh có số đo mới',
                          style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant)),
                    ],
                    if (offline > 0) ...[
                      const SizedBox(height: 10),
                      Text('$offline thiết bị ngoại tuyến',
                          style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant)),
                    ],
                    const SizedBox(height: 26),
                    Text('Theo thiết bị',
                        style: theme.textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w600)),
                    if (devices.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 24),
                        child: Text('Chưa có thiết bị.'),
                      ),
                  ],
                )),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                sliver: SliverList.builder(
                  itemCount: devices.length,
                  itemBuilder: (context, index) =>
                      _PowerRow(device: devices[index], totalPower: watts),
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 24)),
            ],
          );
        },
      )),
    );
  }
}

class _PowerRow extends StatelessWidget {
  const _PowerRow({required this.device, required this.totalPower});
  final Device device;
  final double totalPower;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final power = device.online &&
            device.powerWatts != null &&
            device.powerWatts!.isFinite &&
            device.powerWatts! >= 0
        ? device.powerWatts
        : null;
    final fraction = power != null && totalPower > 0
        ? (power / totalPower).clamp(0.0, 1.0)
        : 0.0;
    final current = device.currentAmps;
    final energy = device.metadata['energy'];
    final hasEnergy = energy is num && energy.isFinite && energy >= 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => context.push('/devices/${device.id}'),
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: Soft3DDecorations.card(isDark: isDark),
            child: Column(children: [
              Row(children: [
                Icon(device.iconData,
                    size: 21, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 12),
                Expanded(
                    child: Text(device.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w600))),
                const SizedBox(width: 8),
                ConnectivityDot(online: device.online),
                const SizedBox(width: 10),
                Text(power == null ? '— W' : '${power.toStringAsFixed(1)} W',
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 13)),
              ]),
              const SizedBox(height: 16),
              if (power == null)
                Semantics(
                  label: '${device.name}: chưa có mẫu mới',
                  child: Container(
                      height: 4,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(2),
                      )),
                )
              else
                LinearProgressIndicator(
                  value: fraction,
                  minHeight: 4,
                  borderRadius: BorderRadius.circular(2),
                  semanticsLabel: 'Tỷ trọng công suất ${device.name}',
                  semanticsValue: '${(fraction * 100).toStringAsFixed(0)}%',
                ),
              if (current != null || hasEnergy) ...[
                const SizedBox(height: 10),
                SizedBox(
                    width: double.infinity,
                    child: Wrap(
                      alignment: WrapAlignment.spaceBetween,
                      spacing: 16,
                      runSpacing: 4,
                      children: [
                        if (current != null)
                          Text('${current.toStringAsFixed(3)} A',
                              style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant)),
                        if (hasEnergy)
                          Tooltip(
                              message: 'Điện năng tích lũy',
                              child: Text('${energy.toStringAsFixed(3)} kWh',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                      color:
                                          theme.colorScheme.onSurfaceVariant))),
                      ],
                    )),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}
