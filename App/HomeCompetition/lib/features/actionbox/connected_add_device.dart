import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/gateway_client.dart';
import '../core_v1/core_app.dart';
import '../core_v1/core_client.dart';
import 'add_device_flow.dart';

class ConnectedAddDeviceScreen extends ConsumerStatefulWidget {
  const ConnectedAddDeviceScreen({super.key});
  @override
  ConsumerState<ConnectedAddDeviceScreen> createState() =>
      _ConnectedAddDeviceState();
}

class _ConnectedAddDeviceState extends ConsumerState<ConnectedAddDeviceScreen> {
  CoreClient? client;
  Map<String, dynamic> defaults = {};
  CoreRoomData? room;
  String? error;
  bool legacy = false, loading = true;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.usesFirebase) {
      setState(() {
        legacy = true;
        loading = false;
      });
      return;
    }
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final context = await gateway.request('/api/commissioning/context');
      if (!mounted) return;
      if (context['profile'] == 'legacy') {
        setState(() {
          legacy = true;
          loading = false;
        });
        return;
      }
      if (context['profile'] != 'core-v1')
        throw const GatewayException(
            'Không đọc được cấu hình ghép nối của bộ trung tâm.');
      client?.dispose();
      client = CoreClient(gateway.serverUrl, 'firebase-session',
          requestTransport: (path, {required method, body, query}) async {
        try {
          return await gateway.request(
              Uri(path: '/api/v1$path', queryParameters: query).toString(),
              method: method,
              body: body);
        } on GatewayException catch (e) {
          throw CoreException('gateway', e.message);
        }
      });
      client!.snapshot = CoreSnapshot.fromJson(asMap(context['snapshot']));
      client!.connected = true;
      client!.updatedAt = DateTime.now();
      defaults = asMap(context['defaults']);
      setState(() {
        room = client!.snapshot!.rooms.firstOrNull;
        loading = false;
      });
    } catch (e) {
      if (mounted)
        setState(() {
          error = e.toString();
          loading = false;
        });
    }
  }

  @override
  void dispose() {
    client?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (legacy) return const AddDeviceFlowScreen();
    final parents = client?.snapshot?.nodes
            .where((n) =>
                n.isSubBox &&
                n.registration == 'REGISTERED' &&
                n.roomId == room?.id)
            .toList() ??
        <CoreNodeData>[];
    return Scaffold(
        appBar: AppBar(title: const Text('Thêm thiết bị')),
        body: loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(padding: const EdgeInsets.all(24), children: [
                if (error != null) ...[
                  Text(error!),
                  TextButton(onPressed: load, child: const Text('Thử lại'))
                ] else if (room == null)
                  const Text(
                      'Chưa có phòng được cấp quyền. Bộ trung tâm cần thiết lập phòng trước khi ghép Box.')
                else ...[
                  const Text(
                      'Chọn phòng và loại Box cần thêm. Mã thiết lập và mật khẩu Wi-Fi riêng của Box nằm trên nhãn thiết bị.'),
                  const SizedBox(height: 20),
                  DropdownButtonFormField<CoreRoomData>(
                      initialValue: room,
                      decoration:
                          const InputDecoration(labelText: 'Phòng lắp đặt'),
                      items: client!.snapshot!.rooms
                          .map((r) =>
                              DropdownMenuItem(value: r, child: Text(r.name)))
                          .toList(),
                      onChanged: (r) => setState(() => room = r)),
                  const SizedBox(height: 20),
                  if (parents.isEmpty)
                    const Text(
                        'Thêm SubBox trước để làm trạm thu phát trong phòng.'),
                  FilledButton.tonal(
                      onPressed: parents.isEmpty
                          ? () => openClaim(true, parents)
                          : null,
                      child: const Text('Đăng ký SubBox')),
                  const SizedBox(height: 12),
                  FilledButton(
                      onPressed: parents.isEmpty
                          ? null
                          : () => openClaim(false, parents),
                      child: const Text('Đăng ký ActionBox')),
                  const SizedBox(height: 16),
                  for (final parent in parents)
                    Text(
                        'SubBox: ${parent.factoryId} · ${parent.availability}'),
                ]
              ]));
  }

  Future<void> openClaim(bool subbox, List<CoreNodeData> parents) async {
    await Navigator.push<void>(
        context,
        MaterialPageRoute(
            builder: (_) => CoreClaim(
                client: client!,
                room: room!,
                parents: parents,
                isSubBox: subbox,
                defaults: defaults)));
    if (mounted) await load();
  }
}
