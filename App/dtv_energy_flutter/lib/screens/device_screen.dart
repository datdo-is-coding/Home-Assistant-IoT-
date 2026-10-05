import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../services/gateway_client.dart';
import 'home_screen.dart';

class DeviceScreen extends StatefulWidget {
  const DeviceScreen({super.key, required this.client, required this.nodeId});
  final GatewayClient client;
  final String nodeId;
  @override
  State<DeviceScreen> createState() => _DeviceScreenState();
}

class _DeviceScreenState extends State<DeviceScreen> {
  List<Map<String, dynamic>> _history = [];
  bool _loading = true;
  String? _error;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.client.request(
          '/api/device/${Uri.encodeComponent(widget.nodeId)}/telemetry?limit=50');
      final history = data['telemetry'];
      if (mounted) {
        setState(() => _history = history is List
            ? history.map(asMap).toList().reversed.toList()
            : []);
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit(Map<String, dynamic> node) async {
    final channels = asMap(node['channels']);
    final ch1 = asMap(channels['ch1']);
    final ch2 = asMap(channels['ch2']);

    final name = TextEditingController(text: nodeName(widget.nodeId, node));
    final room = TextEditingController(text: '${node['room'] ?? ''}');
    final location = TextEditingController(text: '${node['location'] ?? ''}');
    final ch1Name = TextEditingController(text: '${ch1['name'] ?? 'Đèn'}');
    final ch2Name = TextEditingController(text: '${ch2['name'] ?? 'Quạt'}');
    String ch1Type = '${ch1['device_type'] ?? 'light'}';
    String ch2Type = '${ch2['device_type'] ?? 'fan'}';
    if (!['light', 'fan', 'pump', 'switch'].contains(ch1Type)) {
      ch1Type = 'light';
    }
    if (!['light', 'fan', 'pump', 'switch'].contains(ch2Type)) {
      ch2Type = 'fan';
    }

    final form = GlobalKey<FormState>();
    bool busy = false;
    String? error;

    final saved = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
            builder: (context, setDialog) => AlertDialog(
                  title: const Text('Chỉnh sửa thiết bị'),
                  content: SizedBox(
                    width: 480,
                    child: SingleChildScrollView(
                      child: Form(
                          key: form,
                          child: Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                TextFormField(
                                    controller: name,
                                    maxLength: 64,
                                    decoration: const InputDecoration(
                                        labelText: 'Tên thiết bị'),
                                    validator: (s) =>
                                        s == null || s.trim().isEmpty
                                            ? 'Nhập tên thiết bị'
                                            : null),
                                const SizedBox(height: 12),
                                TextFormField(
                                    controller: room,
                                    maxLength: 64,
                                    decoration: const InputDecoration(
                                        labelText: 'Phòng',
                                        hintText: 'phong_khach'),
                                    validator: (s) =>
                                        s == null || s.trim().isEmpty
                                            ? 'Nhập phòng'
                                            : null),
                                const SizedBox(height: 12),
                                TextFormField(
                                    controller: location,
                                    maxLength: 64,
                                    decoration: const InputDecoration(
                                        labelText: 'Vị trí (tùy chọn)',
                                        hintText:
                                            'Bàn làm việc, góc phòng...')),
                                const SizedBox(height: 18),
                                Text('Cấu hình Kênh 1',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .primary)),
                                const SizedBox(height: 8),
                                TextFormField(
                                    controller: ch1Name,
                                    maxLength: 32,
                                    decoration: const InputDecoration(
                                        labelText: 'Tên Kênh 1'),
                                    validator: (s) =>
                                        s == null || s.trim().isEmpty
                                            ? 'Nhập tên kênh 1'
                                            : null),
                                const SizedBox(height: 8),
                                DropdownButtonFormField<String>(
                                    initialValue: ch1Type,
                                    decoration: const InputDecoration(
                                        labelText: 'Loại thiết bị Kênh 1'),
                                    items: _deviceTypes,
                                    onChanged: busy
                                        ? null
                                        : (v) => setDialog(() => ch1Type = v!)),
                                const SizedBox(height: 18),
                                Text('Cấu hình Kênh 2',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .primary)),
                                const SizedBox(height: 8),
                                TextFormField(
                                    controller: ch2Name,
                                    maxLength: 32,
                                    decoration: const InputDecoration(
                                        labelText: 'Tên Kênh 2'),
                                    validator: (s) =>
                                        s == null || s.trim().isEmpty
                                            ? 'Nhập tên kênh 2'
                                            : null),
                                const SizedBox(height: 8),
                                DropdownButtonFormField<String>(
                                    initialValue: ch2Type,
                                    decoration: const InputDecoration(
                                        labelText: 'Loại thiết bị Kênh 2'),
                                    items: _deviceTypes,
                                    onChanged: busy
                                        ? null
                                        : (v) => setDialog(() => ch2Type = v!)),
                                if (error != null)
                                  Padding(
                                      padding: const EdgeInsets.only(top: 12),
                                      child: Text(error!,
                                          style: TextStyle(
                                              color: Theme.of(context)
                                                  .colorScheme
                                                  .error))),
                              ])),
                    ),
                  ),
                  actions: [
                    TextButton(
                        onPressed: busy
                            ? null
                            : () => Navigator.pop(dialogContext, false),
                        child: const Text('Hủy')),
                    FilledButton(
                        onPressed: busy
                            ? null
                            : () async {
                                if (!form.currentState!.validate()) return;
                                setDialog(() => busy = true);
                                try {
                                  await widget.client.updateDevice(
                                    deviceId: widget.nodeId,
                                    name: name.text.trim(),
                                    room: room.text.trim(),
                                    location: location.text.trim(),
                                    ch1Name: ch1Name.text.trim(),
                                    ch1Type: ch1Type,
                                    ch2Name: ch2Name.text.trim(),
                                    ch2Type: ch2Type,
                                  );
                                  if (dialogContext.mounted) {
                                    Navigator.pop(dialogContext, true);
                                  }
                                } catch (e) {
                                  if (context.mounted) {
                                    setDialog(() {
                                      error = e.toString();
                                      busy = false;
                                    });
                                  }
                                }
                              },
                        child: Text(busy ? 'Đang lưu...' : 'Lưu')),
                  ],
                )));
    await Future<void>.delayed(const Duration(milliseconds: 300));
    name.dispose();
    room.dispose();
    location.dispose();
    ch1Name.dispose();
    ch2Name.dispose();
    if (saved == true && mounted) {
      showMessage(context, 'Đã cập nhật thiết bị thành công.');
    }
  }

  Future<void> _confirmDelete(Map<String, dynamic> node) async {
    final devName = nodeName(widget.nodeId, node);
    bool busy = false;
    String? error;

    final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
            builder: (context, setDialog) => AlertDialog(
                  title: const Row(children: [
                    Icon(Icons.warning_amber_rounded, color: Colors.amber),
                    SizedBox(width: 8),
                    Text('Xóa thiết bị?'),
                  ]),
                  content: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                          'Bạn có chắc chắn muốn xóa "$devName" (${widget.nodeId}) khỏi hệ thống?'),
                      const SizedBox(height: 8),
                      Text(
                          'Tất cả cấu hình và dữ liệu điện năng của thiết bị này sẽ bị xóa vĩnh viễn.',
                          style: TextStyle(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant,
                              fontSize: 13)),
                      if (error != null)
                        Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(error!,
                                style: TextStyle(
                                    color:
                                        Theme.of(context).colorScheme.error))),
                    ],
                  ),
                  actions: [
                    TextButton(
                        onPressed: busy
                            ? null
                            : () => Navigator.pop(dialogContext, false),
                        child: const Text('Hủy')),
                    FilledButton(
                        style: FilledButton.styleFrom(
                            backgroundColor:
                                Theme.of(context).colorScheme.error),
                        onPressed: busy
                            ? null
                            : () async {
                                setDialog(() => busy = true);
                                try {
                                  await widget.client
                                      .deleteDevice(widget.nodeId);
                                  if (dialogContext.mounted) {
                                    Navigator.pop(dialogContext, true);
                                  }
                                } catch (e) {
                                  if (context.mounted) {
                                    setDialog(() {
                                      error = e.toString();
                                      busy = false;
                                    });
                                  }
                                }
                              },
                        child: Text(busy ? 'Đang xóa...' : 'Xóa thiết bị')),
                  ],
                )));

    if (confirmed == true && mounted) {
      Navigator.pop(context);
      showMessage(context, 'Đã xóa thiết bị $devName.');
    }
  }

  static const List<DropdownMenuItem<String>> _deviceTypes = [
    DropdownMenuItem(value: 'light', child: Text('Đèn')),
    DropdownMenuItem(value: 'fan', child: Text('Quạt')),
    DropdownMenuItem(value: 'pump', child: Text('Máy bơm')),
    DropdownMenuItem(value: 'switch', child: Text('Công tắc')),
  ];

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: widget.client,
      builder: (context, _) {
        final node = asMap(widget.client.nodes[widget.nodeId]);
        final online = widget.client.connected && node['status'] == 'online';
        final colors = Theme.of(context).colorScheme;
        final values = _history
            .map((e) => readNumber(e['power']))
            .whereType<double>()
            .toList();
        return Scaffold(
          appBar: AppBar(title: Text(nodeName(widget.nodeId, node)), actions: [
            if (widget.client.isAdmin && node.isNotEmpty) ...[
              IconButton(
                  tooltip: 'Chỉnh sửa',
                  onPressed: () => _edit(node),
                  icon: const Icon(Icons.edit_outlined)),
              IconButton(
                  tooltip: 'Xóa thiết bị',
                  onPressed: () => _confirmDelete(node),
                  color: colors.error,
                  icon: const Icon(Icons.delete_outline)),
            ],
          ]),
          body: SafeArea(
              child: RefreshIndicator(
            onRefresh: () async {
              await widget.client.refresh();
              await _load();
            },
            child: ListView(padding: const EdgeInsets.all(20), children: [
              Wrap(spacing: 8, runSpacing: 8, children: [
                Chip(
                    avatar: Icon(Icons.circle,
                        size: 10,
                        color: online ? const Color(0xFF10B981) : colors.error),
                    label: Text(online ? 'Trực tuyến' : 'Ngoại tuyến',
                        style: TextStyle(
                            color: online ? const Color(0xFF10B981) : colors.error,
                            fontWeight: FontWeight.w600))),

                Chip(label: Text(roomName('${node['room'] ?? ''}'))),
              ]),
              const SizedBox(height: 24),
              const Text('Điều khiển',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
              const SizedBox(height: 16),
              ResponsiveTiles(children: [
                for (final ch in asMap(node['channels']).keys)
                  if (['ch1', 'ch2'].contains(ch))
                    RelayTile(
                        client: widget.client,
                        nodeId: widget.nodeId,
                        channel: ch)
              ]),
              const SizedBox(height: 28),
              const Text('Số đo gần nhất',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
              const SizedBox(height: 16),
              MetricStrip(data: telemetry(node)),
              const SizedBox(height: 28),
              Row(children: [
                const Expanded(
                    child: Text('Lịch sử công suất',
                        style: TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w700))),
                IconButton(
                    tooltip: 'Tải lịch sử',
                    onPressed: _loading ? null : _load,
                    icon: const Icon(Icons.refresh))
              ]),
              if (_loading)
                const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator())),
              if (_error != null)
                Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child:
                        Text(_error!, style: TextStyle(color: colors.error))),
              if (!_loading && _error == null && values.isEmpty)
                const EmptyState(
                    icon: Icons.show_chart,
                    title: 'Chưa có lịch sử',
                    subtitle: 'Chờ Gateway ghi nhận số đo đầu tiên.'),
              if (!_loading && values.isNotEmpty) ...[
                Text(
                    'Tối đa ${metric(values.reduce(math.max), 'W')} · ${values.length} mẫu',
                    style: TextStyle(color: colors.onSurfaceVariant)),
                const SizedBox(height: 12),
                Semantics(
                    label:
                        'Công suất từ ${metric(values.first, 'W')} đến ${metric(values.last, 'W')}',
                    child: SizedBox(
                        height: 140,
                        width: double.infinity,
                        child: CustomPaint(
                            painter: PowerChart(values, const Color(0xFF0EA5E9),
                                colors.outlineVariant)))),

                const SizedBox(height: 8),
                Row(children: [
                  Expanded(
                      child: Text(_time(_history.first['recorded_at']),
                          style: const TextStyle(fontSize: 12))),
                  Text(_time(_history.last['recorded_at']),
                      style: const TextStyle(fontSize: 12))
                ]),
              ],
              const SizedBox(height: 28),
              const Divider(),
              const SizedBox(height: 12),
              for (final entry in {
                'Mã thiết bị': widget.nodeId,
                'Phần cứng': node['hardware'] ?? node['device_type'] ?? '—',
                'Địa chỉ IP': node['ip'] ?? '—',
                'Wi-Fi': metric(node['rssi'], 'dBm', 0),
                'Firmware': node['firmware_version'] ?? node['fw'] ?? '—',
                'Đồng bộ': node['sync_status'] ?? '—'
              }.entries)
                Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                              child: Text(entry.key,
                                  style: TextStyle(
                                      color: colors.onSurfaceVariant))),
                          Expanded(
                              child: Text('${entry.value}',
                                  textAlign: TextAlign.right)),
                        ])),
              if (widget.client.isAdmin && node.isNotEmpty) ...[
                const SizedBox(height: 24),
                const Divider(),
                const SizedBox(height: 16),
                Row(children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _edit(node),
                      icon: const Icon(Icons.edit_outlined),
                      label: const Text('Chỉnh sửa'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      style: FilledButton.styleFrom(
                        foregroundColor: colors.error,
                        backgroundColor:
                            colors.errorContainer.withValues(alpha: 0.5),
                      ),
                      onPressed: () => _confirmDelete(node),
                      icon: const Icon(Icons.delete_outline),
                      label: const Text('Xóa thiết bị'),
                    ),
                  ),
                ]),
                const SizedBox(height: 16),
              ],
            ]),
          )),
        );
      });

  String _time(dynamic value) {
    final date = DateTime.tryParse('$value');
    return date == null
        ? ''
        : '${date.day}/${date.month} ${TimeOfDay.fromDateTime(date.toLocal()).format(context)}';
  }
}

class PowerChart extends CustomPainter {
  PowerChart(this.values, this.color, this.grid);
  final List<double> values;
  final Color color, grid;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;

    final maximum = math.max(1.0, values.reduce(math.max));
    final line = Paint()
      ..color = grid.withValues(alpha: 0.4)
      ..strokeWidth = 0.8;

    for (int i = 0; i < 4; i++) {
      final y = 8 + (size.height - 16) * i / 3;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), line);
    }

    final path = Path();
    final fillPath = Path();

    for (int i = 0; i < values.length; i++) {
      final x = values.length == 1
          ? size.width / 2
          : i * size.width / (values.length - 1);
      final y = size.height -
          8 -
          values[i].clamp(0, maximum) / maximum * (size.height - 16);

      if (i == 0) {
        path.moveTo(x, y);
        fillPath.moveTo(x, size.height);
        fillPath.lineTo(x, y);
      } else {
        path.lineTo(x, y);
        fillPath.lineTo(x, y);
      }

      if (i == values.length - 1) {
        fillPath.lineTo(x, size.height);
        fillPath.close();

        // Terminal glowing point
        canvas.drawCircle(
          Offset(x, y),
          7.0,
          Paint()
            ..color = color.withValues(alpha: 0.25)
            ..style = PaintingStyle.fill,
        );
        canvas.drawCircle(
          Offset(x, y),
          3.8,
          Paint()..color = color,
        );
        canvas.drawCircle(
          Offset(x, y),
          1.8,
          Paint()..color = Colors.white,
        );
      }
    }

    // Draw smooth gradient fill under the line
    if (values.length > 1) {
      final fillPaint = Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            color.withValues(alpha: 0.28),
            color.withValues(alpha: 0.0),
          ],
        ).createShader(Rect.fromLTWH(0, 0, size.width, size.height))
        ..style = PaintingStyle.fill;

      canvas.drawPath(fillPath, fillPaint);
    }

    // Draw main stroke
    canvas.drawPath(
      path,
      Paint()
        ..shader = LinearGradient(
          colors: [
            const Color(0xFF00E5FF),
            color,
          ],
        ).createShader(Rect.fromLTWH(0, 0, size.width, size.height))
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );

  }

  @override
  bool shouldRepaint(covariant PowerChart old) =>
      old.values != values || old.color != color || old.grid != grid;
}
