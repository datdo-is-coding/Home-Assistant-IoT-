import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../models/device.dart';
import '../../providers/smart_home_providers.dart';

class EnergyScreen extends ConsumerWidget {
  const EnergyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final readings = ref.watch(devicesStreamProvider);
    final status =
        ref.watch(gatewayClientProvider.select((c) => (c.connected, c.error)));
    return Scaffold(
      appBar: AppBar(
          title: const Text('Điện năng & Cảnh báo'),
          automaticallyImplyLeading: false),
      body: readings.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => const Center(
            child: Text('Không tải được số đo. Vui lòng thử lại.')),
        data: (devices) {
          final measured =
              devices.where((d) => d.online && d.powerWatts != null).toList();
          final totalPower =
              measured.fold<double>(0, (sum, d) => sum + d.powerWatts!);
          final energies = devices
              .map((d) => d.metadata['energy'])
              .whereType<num>()
              .where((v) => v.isFinite && v >= 0)
              .toList();
          final totalEnergy = energies.fold<double>(0, (sum, v) => sum + v);
          final offline = devices.where((d) => !d.online).length;
          return CustomScrollView(
            key: const PageStorageKey('energy-scroll'),
            slivers: [
              SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (status.$2 != null)
                            Padding(
                                padding: const EdgeInsets.only(bottom: 12),
                                child: Text(status.$2!,
                                    style: TextStyle(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .error))),
                          Card(
                              child: Padding(
                                  padding: const EdgeInsets.all(20),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      const Row(children: [
                                        Icon(Icons.bolt_rounded),
                                        SizedBox(width: 8),
                                        Expanded(
                                            child: Text('Công suất đang đo'))
                                      ]),
                                      const SizedBox(height: 8),
                                      Text(
                                          measured.isEmpty
                                              ? 'Chưa có mẫu mới'
                                              : '${totalPower.toStringAsFixed(1)} W',
                                          style: Theme.of(context)
                                              .textTheme
                                              .headlineMedium),
                                      Text(
                                          '${measured.length}/${devices.length} kênh có số đo mới'),
                                      const Divider(height: 28),
                                      Text(
                                          energies.isEmpty
                                              ? 'Điện năng tích lũy: chưa có mẫu'
                                              : 'Điện năng tích lũy: ${totalEnergy.toStringAsFixed(3)} kWh',
                                          style: Theme.of(context)
                                              .textTheme
                                              .titleMedium),
                                      Text(
                                          'Đã có chỉ số của ${energies.length}/${devices.length} kênh · Không phải mức tiêu thụ riêng hôm nay',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall),
                                    ],
                                  ))),
                          const SizedBox(height: 24),
                          Text('Công suất theo thiết bị',
                              style: Theme.of(context).textTheme.titleLarge),
                          const SizedBox(height: 4),
                          const Text(
                              'Độ dài thanh thể hiện tỷ trọng trong tổng công suất đang đo.'),
                          if (devices.isEmpty)
                            const Padding(
                                padding: EdgeInsets.symmetric(vertical: 24),
                                child: Text(
                                    'Chưa có thiết bị trên Firebase. Dữ liệu sẽ xuất hiện khi thiết bị được đồng bộ.')),
                        ]),
                  )),
              SliverPadding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  sliver: SliverList.builder(
                    itemCount: devices.length,
                    itemBuilder: (context, index) => _PowerRow(
                        device: devices[index], totalPower: totalPower),
                  )),
              SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Divider(),
                          Text('Cảnh báo kết nối',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 8),
                          if (!status.$1)
                            const Text(
                                'Mất kết nối Firebase hoặc chưa đọc được dữ liệu. Điều khiển đã khóa.'),
                          if (offline > 0)
                            Text(
                                '$offline kênh ngoại tuyến hoặc số đo đã quá hạn.'),
                          if (status.$1 && offline == 0 && devices.isNotEmpty)
                            const Text('Không có cảnh báo mất kết nối'),
                          const SizedBox(height: 16),
                          Text(
                              'Chưa có lịch sử theo giờ/ngày trên Firebase. Biểu đồ đang dùng số đo hiện tại; điện năng tích lũy có thể là chỉ số của mẫu cũ.',
                              style: Theme.of(context).textTheme.bodySmall),
                        ]),
                  )),
            ],
          );
        },
      ),
    );
  }
}

class _PowerRow extends StatelessWidget {
  const _PowerRow({required this.device, required this.totalPower});
  final Device device;
  final double totalPower;

  @override
  Widget build(BuildContext context) {
    final power = device.online ? device.powerWatts : null;
    final fraction = power != null && totalPower > 0
        ? (power / totalPower).clamp(0.0, 1.0)
        : 0.0;
    final energy = device.metadata['energy'];
    return Padding(
        padding: const EdgeInsets.only(bottom: 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(device.iconData, size: 22),
              const SizedBox(width: 10),
              Expanded(
                  child: Text(device.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleSmall)),
              const SizedBox(width: 8),
              Text(power == null
                  ? 'Chưa có mẫu'
                  : '${power.toStringAsFixed(1)} W'),
            ]),
            const SizedBox(height: 10),
            if (power == null)
              Semantics(
                  label: '${device.name}: Chưa có mẫu mới',
                  child: Container(
                      height: 10,
                      decoration: BoxDecoration(
                          color: Theme.of(context)
                              .colorScheme
                              .surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(5))))
            else
              LinearProgressIndicator(
                value: fraction,
                minHeight: 10,
                borderRadius: BorderRadius.circular(5),
                semanticsLabel: 'Tỷ trọng công suất ${device.name}',
                semanticsValue: '${(fraction * 100).toStringAsFixed(0)}%',
              ),
            const SizedBox(height: 6),
            Text(
                '${device.currentText} · ${energy is num && energy.isFinite && energy >= 0 ? '${energy.toStringAsFixed(3)} kWh tích lũy' : 'Chưa có chỉ số điện năng'}',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ));
  }
}
