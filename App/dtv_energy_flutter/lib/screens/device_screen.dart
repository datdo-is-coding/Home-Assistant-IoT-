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
      if (mounted)
        setState(() => _history = history is List
            ? history.map(asMap).toList().reversed.toList()
            : []);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _edit(Map<String, dynamic> node) async {
    final name = TextEditingController(text: nodeName(widget.nodeId, node));
    final room = TextEditingController(text: '${node['room'] ?? ''}');
    final form = GlobalKey<FormState>();
    bool busy = false;
    String? error;
    await showDialog<void>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
            builder: (context, setDialog) => AlertDialog(
                  title: const Text('Chỉnh sửa thiết bị'),
                  content: SingleChildScrollView(
                      child: Form(
                          key: form,
                          child:
                              Column(mainAxisSize: MainAxisSize.min, children: [
                            TextFormField(
                                controller: name,
                                maxLength: 64,
                                decoration: const InputDecoration(
                                    labelText: 'Tên thiết bị'),
                                validator: (s) => s == null || s.trim().isEmpty
                                    ? 'Nhập tên thiết bị'
                                    : null),
                            const SizedBox(height: 16),
                            TextFormField(
                                controller: room,
                                maxLength: 64,
                                decoration:
                                    const InputDecoration(labelText: 'Phòng'),
                                validator: (s) => s == null || s.trim().isEmpty
                                    ? 'Nhập phòng'
                                    : null),
                            if (error != null)
                              Text(error!,
                                  style: TextStyle(
                                      color:
                                          Theme.of(context).colorScheme.error)),
                          ]))),
                  actions: [
                    TextButton(
                        onPressed:
                            busy ? null : () => Navigator.pop(dialogContext),
                        child: const Text('Hủy')),
                    FilledButton(
                        onPressed: busy
                            ? null
                            : () async {
                                if (!form.currentState!.validate()) return;
                                setDialog(() => busy = true);
                                try {
                                  final result = await widget.client
                                      .request('/api/device/update', body: {
                                    'device_id': widget.nodeId,
                                    'name': name.text.trim(),
                                    'room': room.text.trim()
                                  });
                                  if (result['success'] != true)
                                    throw GatewayException(
                                        '${result['error'] ?? 'Không thể lưu thiết bị'}');
                                  await widget.client.refresh();
                                  if (dialogContext.mounted)
                                    Navigator.pop(dialogContext);
                                } catch (e) {
                                  if (context.mounted)
                                    setDialog(() {
                                      error = e.toString();
                                      busy = false;
                                    });
                                }
                              },
                        child: Text(busy ? 'Đang lưu...' : 'Lưu'))
                  ],
                )));
    // Wait until the dialog's closing animation releases its text fields.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    name.dispose();
    room.dispose();
  }

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
            if (widget.client.isAdmin && node.isNotEmpty)
              IconButton(
                  tooltip: 'Chỉnh sửa',
                  onPressed: () => _edit(node),
                  icon: const Icon(Icons.edit_outlined)),
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
                        color: online ? colors.primary : colors.error),
                    label: Text(online ? 'Trực tuyến' : 'Ngoại tuyến')),
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
                            painter: PowerChart(values, colors.primary,
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
    final maximum = math.max(1.0, values.reduce(math.max));
    final line = Paint()
      ..color = grid
      ..strokeWidth = .5;
    for (int i = 0; i < 4; i++) {
      final y = 8 + (size.height - 16) * i / 3;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), line);
    }
    final path = Path();
    for (int i = 0; i < values.length; i++) {
      final x = values.length == 1
          ? size.width / 2
          : i * size.width / (values.length - 1);
      final y = size.height -
          8 -
          values[i].clamp(0, maximum) / maximum * (size.height - 16);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
      if (values.length == 1)
        canvas.drawCircle(Offset(x, y), 4, Paint()..color = color);
    }
    canvas.drawPath(
        path,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5
          ..strokeJoin = StrokeJoin.round);
  }

  @override
  bool shouldRepaint(covariant PowerChart old) =>
      old.values != values || old.color != color || old.grid != grid;
}
