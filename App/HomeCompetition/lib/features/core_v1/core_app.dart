import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'core_client.dart';
import 'core_provisioning.dart';

const deviceKinds = {
  'light': 'Đèn',
  'fan': 'Quạt',
  'outlet': 'Ổ cắm',
  'other': 'Thiết bị khác'
};
Future<T?> openCore<T>(BuildContext context, Widget page) =>
    Navigator.push<T>(context, MaterialPageRoute(builder: (_) => page));
void coreMessage(BuildContext context, Object error) {
  if (context.mounted)
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text('$error')));
}

String coreTime(double value) =>
    DateTime.fromMillisecondsSinceEpoch((value * 1000).round())
        .toLocal()
        .toString()
        .split('.')
        .first;
Widget section(String title) => Padding(
    padding: const EdgeInsets.only(top: 24, bottom: 8),
    child: Text(title,
        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600)));
Widget detail(String label, String value) => ListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(label),
    subtitle: SelectableText(value));

class CoreApp extends StatelessWidget {
  const CoreApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
      title: 'Home Competition',
      theme: ThemeData(
          useMaterial3: true,
          colorSchemeSeed: const Color(0xff185c4a),
          scaffoldBackgroundColor: const Color(0xfff7f9f8),
          inputDecorationTheme:
              const InputDecorationTheme(border: OutlineInputBorder())),
      home: const CoreLogin());
}

class CoreLogin extends StatefulWidget {
  const CoreLogin({super.key});
  @override
  State<CoreLogin> createState() => _CoreLoginState();
}

class _CoreLoginState extends State<CoreLogin> {
  final url = TextEditingController(text: 'https://'),
      token = TextEditingController();
  String? error;
  bool busy = false;
  @override
  void dispose() {
    url.dispose();
    token.dispose();
    super.dispose();
  }

  Future<void> login() async {
    setState(() {
      busy = true;
      error = null;
    });
    CoreClient? client;
    try {
      client = CoreClient(url.text.trim(), token.text.trim());
      final response = await client.request('/homes');
      if (!mounted) {
        client.dispose();
        return;
      }
      token.clear();
      await openCore<void>(
          context,
          CoreDashboard(
              client: client,
              homes: (response['items'] as List)
                  .map((h) => CoreHome.fromJson(h as Map<String, dynamic>))
                  .toList()));
      client.dispose();
    } on Object catch (e) {
      client?.dispose();
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Home Competition')),
      body: Center(
          child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: ListView(
                  shrinkWrap: true,
                  padding: const EdgeInsets.all(24),
                  children: [
                    const Icon(Icons.home_work_outlined, size: 56),
                    section('Kết nối ngôi nhà'),
                    const Text(
                        'Dùng địa chỉ Gateway và access token do quản trị viên cấp qua CLI. Token chỉ giữ trong phiên làm việc này.'),
                    const SizedBox(height: 24),
                    TextField(
                        controller: url,
                        decoration: const InputDecoration(
                            labelText: 'Địa chỉ Gateway',
                            hintText: 'https://gateway.example'),
                        keyboardType: TextInputType.url),
                    const SizedBox(height: 16),
                    TextField(
                        controller: token,
                        decoration:
                            const InputDecoration(labelText: 'Access token'),
                        obscureText: true,
                        enableSuggestions: false,
                        autocorrect: false),
                    if (error != null)
                      Padding(
                          padding: const EdgeInsets.only(top: 16),
                          child: Text(error!,
                              style: TextStyle(
                                  color: Theme.of(context).colorScheme.error))),
                    const SizedBox(height: 24),
                    FilledButton(
                        onPressed: busy ? null : login,
                        child: Text(busy ? 'Đang kết nối…' : 'Kết nối')),
                  ]))));
}

class CoreConnection extends StatelessWidget {
  final CoreClient client;
  const CoreConnection({super.key, required this.client});
  @override
  Widget build(BuildContext context) => Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
          color:
              client.fresh ? const Color(0xffe3f1e9) : const Color(0xffffefcd),
          borderRadius: BorderRadius.circular(12)),
      child: Row(children: [
        Icon(client.fresh
            ? Icons.cloud_done_outlined
            : Icons.cloud_off_outlined),
        const SizedBox(width: 10),
        Expanded(
            child: Text(client.fresh
                ? 'Đang đồng bộ với Gateway'
                : client.error ?? 'Đang tải trạng thái mới…'))
      ]));
}

class CoreDashboard extends StatefulWidget {
  final CoreClient client;
  final List<CoreHome> homes;
  const CoreDashboard({super.key, required this.client, required this.homes});
  @override
  State<CoreDashboard> createState() => _CoreDashboardState();
}

class _CoreDashboardState extends State<CoreDashboard> {
  late List<CoreHome> homes = List.of(widget.homes);
  String? home;
  int tab = 0;
  @override
  void initState() {
    super.initState();
    if (homes.isNotEmpty) {
      home = homes.first.id;
      unawaited(widget.client.connect(home!));
    }
  }

  Future<void> createHome() async {
    final result = await openCore<Map<String, dynamic>>(
        context,
        CoreNameForm(
            title: 'Tạo nhà',
            label: 'Tên nhà',
            submit: (name) => widget.client
                .request('/homes', method: 'POST', body: {'name': name})));
    if (result == null || !mounted) return;
    try {
      final d = await widget.client.request('/homes');
      if (!mounted) return;
      setState(() {
        homes = (d['items'] as List)
            .map((h) => CoreHome.fromJson(h as Map<String, dynamic>))
            .toList();
        home = result['home_id'] as String;
      });
      await widget.client.connect(home!);
    } on Object catch (e) {
      if (mounted) coreMessage(context, e);
    }
  }

  Future<void> createRoom() async {
    await openCore<Map<String, dynamic>>(
        context,
        CoreNameForm(
            title: 'Thêm phòng',
            label: 'Tên phòng',
            submit: (name) => widget.client.request('/rooms',
                method: 'POST', body: {'home_id': home, 'name': name})));
    if (home != null) {
      try {
        await widget.client.refresh(home!);
      } on Object catch (e) {
        if (mounted) coreMessage(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: widget.client,
      builder: (context, _) {
        final c = widget.client, s = c.snapshot;
        return Scaffold(
            appBar: AppBar(title: const Text('Home Competition'), actions: [
              IconButton(
                  tooltip: 'Cài đặt Gateway',
                  icon: const Icon(Icons.settings_outlined),
                  onPressed: () =>
                      openCore<void>(context, CoreSettings(client: c))),
              PopupMenuButton<String>(
                  onSelected: (_) => createHome(),
                  itemBuilder: (_) => [
                        const PopupMenuItem(
                            value: 'home', child: Text('Tạo nhà'))
                      ])
            ]),
            bottomNavigationBar: NavigationBar(
                selectedIndex: tab,
                onDestinationSelected: (i) => setState(() => tab = i),
                destinations: const [
                  NavigationDestination(
                      icon: Icon(Icons.dashboard_outlined), label: 'Tổng quan'),
                  NavigationDestination(
                      icon: Icon(Icons.meeting_room_outlined), label: 'Phòng'),
                  NavigationDestination(
                      icon: Icon(Icons.electrical_services_outlined),
                      label: 'Thiết bị')
                ]),
            body: RefreshIndicator(
                onRefresh: () async {
                  if (home != null) await c.refresh(home!);
                },
                child: ListView(padding: const EdgeInsets.all(16), children: [
                  if (homes.isNotEmpty)
                    DropdownButtonFormField<String>(
                        initialValue: home,
                        key: ValueKey(home),
                        decoration: const InputDecoration(
                            labelText: 'Nhà đang quản lý'),
                        items: homes
                            .map((h) => DropdownMenuItem(
                                value: h.id, child: Text(h.name)))
                            .toList(),
                        onChanged: (v) {
                          setState(() => home = v);
                          if (v != null) unawaited(c.connect(v));
                        }),
                  const SizedBox(height: 16),
                  if (home == null) ...[
                    section('Bắt đầu với ngôi nhà của bạn'),
                    const Text(
                        'Tạo nhà, thêm phòng, sau đó đăng ký SubBox và ActionBox.'),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                        onPressed: createHome,
                        icon: const Icon(Icons.add),
                        label: const Text('Tạo nhà'))
                  ],
                  if (home != null) CoreConnection(client: c),
                  if (s != null) ...[
                    if (tab == 0) ...[
                      section('Tổng quan toàn nhà'),
                      Wrap(spacing: 12, runSpacing: 12, children: [
                        Chip(label: Text('${s.rooms.length} phòng')),
                        Chip(
                            label: Text(
                                '${s.nodes.where((n) => n.registration == 'REGISTERED').length} Box')),
                        Chip(label: Text('${s.devices.length} thiết bị')),
                        Chip(
                            label: Text(
                                '${c.fresh ? s.nodes.where((n) => n.availability == 'ONLINE').length : 0} Box online'))
                      ]),
                      section('Quản trị'),
                      ListTile(
                          leading: const Icon(Icons.system_update),
                          title: const Text('Firmware & cập nhật'),
                          subtitle: const Text(
                              'Phiên bản, tiến trình và lịch sử OTA'),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => openCore<void>(
                              context, CoreFirmware(client: c, home: home!))),
                      ListTile(
                          leading: const Icon(Icons.history),
                          title: const Text('Nhật ký sự kiện và lỗi'),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => openCore<void>(
                              context, CoreRecords(client: c, home: home!))),
                    ],
                    if (tab != 2) ...[
                      section('Phòng'),
                      if (s.rooms.isEmpty)
                        const Text('Chưa có phòng. Thêm phòng để đăng ký Box.'),
                      for (final r in s.rooms)
                        ListTile(
                            leading: const Icon(Icons.meeting_room_outlined),
                            title: Text(r.name),
                            subtitle: Text(
                                '${s.nodes.where((n) => n.roomId == r.id && n.registration == "REGISTERED").length} Box đã đăng ký'),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () => openCore<void>(
                                context, CoreRoom(client: c, room: r))),
                      TextButton.icon(
                          onPressed: createRoom,
                          icon: const Icon(Icons.add),
                          label: const Text('Thêm phòng'))
                    ],
                    if (tab != 1) ...[
                      section('Thiết bị điện'),
                      if (s.devices.isEmpty)
                        const Text(
                            'Mở phòng → ActionBox → Channel để thêm thiết bị điện.'),
                      for (final d in s.devices)
                        CoreDeviceTile(client: c, device: d)
                    ],
                  ],
                ])));
      });
}

class CoreDeviceTile extends StatelessWidget {
  final CoreClient client;
  final CoreDevice device;
  const CoreDeviceTile({super.key, required this.client, required this.device});
  @override
  Widget build(BuildContext context) {
    final matches =
        client.snapshot?.channels.where((c) => c.deviceId == device.id);
    final ch = matches == null || matches.isEmpty ? null : matches.first;
    final status = client.commandStatus[device.id];
    final enabled = ch != null &&
        ch.on != null &&
        ch.online &&
        client.fresh &&
        !client.pending.containsKey(device.id) &&
        !client.hasUncertainCommand(device.id);
    return ListTile(
        contentPadding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        title: Text(device.name),
        subtitle: Text(
            '${deviceKinds[device.kind] ?? device.kind} · ${ch == null ? 'Chưa gán Channel' : ch.reportedLabel(client.fresh)}\n${ch?.current == null ? 'Dòng điện chưa hợp lệ' : '${ch!.current!.toStringAsFixed(3)} A${client.fresh && ch.online ? '' : ' (dữ liệu cũ)'}'}${status == null ? '' : ' · Lệnh: $status'}'),
        isThreeLine: true,
        trailing: Switch(
            value: ch?.on ?? false,
            onChanged: enabled
                ? (v) async {
                    try {
                      await client.command(device.id, v);
                    } on Object catch (e) {
                      if (context.mounted) coreMessage(context, e);
                    }
                  }
                : null),
        onTap: () => openCore<void>(
            context, CoreDevicePage(client: client, deviceId: device.id)));
  }
}

class CoreRoom extends StatelessWidget {
  final CoreClient client;
  final CoreRoomData room;
  const CoreRoom({super.key, required this.client, required this.room});
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: client,
      builder: (context, _) {
        final nodes = client.snapshot?.nodes
                .where(
                    (n) => n.roomId == room.id && n.registration != 'REVOKED')
                .toList() ??
            [];
        final parents = nodes
            .where((n) => n.isSubBox && n.registration == 'REGISTERED')
            .toList();
        return Scaffold(
            appBar: AppBar(title: Text(room.name)),
            body: ListView(padding: const EdgeInsets.all(16), children: [
              CoreConnection(client: client),
              section('SubBox chính'),
              for (final n in nodes.where((n) => n.isSubBox))
                CoreNodeTile(client: client, node: n),
              if (parents.isEmpty)
                const Text(
                    'Đăng ký SubBox trước để quản lý ActionBox trong phòng.'),
              FilledButton.tonal(
                  onPressed: parents.isNotEmpty
                      ? null
                      : () => openCore<void>(
                          context,
                          CoreClaim(
                              client: client,
                              room: room,
                              parents: parents,
                              isSubBox: true)),
                  child: const Text('Đăng ký SubBox')),
              section('ActionBox trong phòng'),
              for (final n in nodes.where((n) => !n.isSubBox))
                CoreNodeTile(client: client, node: n),
              if (nodes.where((n) => !n.isSubBox).isEmpty)
                const Padding(
                    padding: EdgeInsets.only(bottom: 12),
                    child: Text('Chưa có ActionBox đã đăng ký.')),
              FilledButton.tonal(
                  onPressed: parents.isEmpty
                      ? null
                      : () => openCore<void>(
                          context,
                          CoreClaim(
                              client: client,
                              room: room,
                              parents: parents,
                              isSubBox: false)),
                  child: const Text('Đăng ký ActionBox')),
            ]));
      });
}

class CoreNodeTile extends StatelessWidget {
  final CoreClient client;
  final CoreNodeData node;
  const CoreNodeTile({super.key, required this.client, required this.node});
  @override
  Widget build(BuildContext context) => ListTile(
      leading:
          Icon(node.isSubBox ? Icons.router_outlined : Icons.developer_board),
      title: Text(node.factoryId),
      subtitle: Text(
          '${node.model} · ${client.fresh ? node.availability : 'STALE'}\n${node.registration} · ${node.firmware}'),
      isThreeLine: true,
      trailing: const Icon(Icons.chevron_right),
      onTap: () =>
          openCore<void>(context, CoreNode(client: client, nodeId: node.id)));
}

class CoreNode extends StatelessWidget {
  final CoreClient client;
  final int nodeId;
  const CoreNode({super.key, required this.client, required this.nodeId});
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: client,
      builder: (context, _) {
        final matches = client.snapshot?.nodes.where((n) => n.id == nodeId);
        final node = matches == null || matches.isEmpty ? null : matches.first;
        return Scaffold(
            appBar: AppBar(title: Text(node?.factoryId ?? 'Box')),
            body: node == null
                ? const Center(
                    child: Text('Box không còn trong nhà đang chọn.'))
                : ListView(padding: const EdgeInsets.all(16), children: [
                    CoreConnection(client: client),
                    section(node.isSubBox
                        ? 'Chi tiết SubBox'
                        : 'Chi tiết ActionBox'),
                    detail(
                        'Model / firmware', '${node.model} / ${node.firmware}'),
                    detail('Đăng ký / kết nối',
                        '${node.registration} / ${client.fresh ? node.availability : 'STALE'}'),
                    detail('Định danh logic / cấu hình',
                        '${node.id} / revision ${node.configRev}'),
                    if (node.parentId != null)
                      detail(
                          'SubBox cha',
                          client.snapshot!.nodes
                                  .where((n) => n.id == node.parentId)
                                  .map((n) => n.factoryId)
                                  .firstOrNull ??
                              '${node.parentId}'),
                    if (node.isSubBox) ...[
                      section('ActionBox con'),
                      for (final child in client.snapshot!.nodes
                          .where((n) => n.parentId == node.id))
                        CoreNodeTile(client: client, node: child)
                    ],
                    if (!node.isSubBox) ...[
                      section('SmartChannel · Relay + CT'),
                      const Text(
                          'Dòng RMS chỉ hiển thị khi cảm biến hợp lệ. Không suy diễn công suất hoặc điện năng từ dòng điện.'),
                      for (final ch in client.snapshot!.channels
                          .where((c) => c.nodeId == node.id))
                        ListTile(
                            title: Text(
                                'CH${ch.number} · ${ch.deviceId == null ? 'Chưa gán' : client.snapshot!.devices.where((d) => d.id == ch.deviceId).map((d) => d.name).firstOrNull ?? ch.deviceId}'),
                            subtitle: Text(
                                '${ch.reportedLabel(client.fresh)} · ${ch.current == null ? 'CT chưa hợp lệ' : '${ch.current!.toStringAsFixed(3)} A'}${ch.faults == 0 ? '' : ' · Lỗi ${ch.faults}'}'),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () => openCore<void>(
                                context,
                                CoreChannelPage(
                                    client: client, channelId: ch.id)))
                    ],
                    section('Quản lý Box'),
                    OutlinedButton.icon(
                        onPressed: node.registration != 'REGISTERED'
                            ? null
                            : () => openCore<void>(context,
                                CoreAssign(client: client, node: node)),
                        icon: const Icon(Icons.drive_file_move_outline),
                        label: const Text('Chuyển phòng / SubBox cha')),
                    TextButton(
                        onPressed: node.registration == 'REVOKED'
                            ? null
                            : () async {
                                final yes = await showDialog<bool>(
                                    context: context,
                                    builder: (ctx) => AlertDialog(
                                            title: const Text(
                                                'Thu hồi quyền Box?'),
                                            content: const Text(
                                                'Box mất quyền điều khiển, các liên kết Channel được gỡ. Thiết bị điện giữ nguyên ID để gán sang Box thay thế.'),
                                            actions: [
                                              TextButton(
                                                  onPressed: () =>
                                                      Navigator.pop(ctx, false),
                                                  child: const Text('Hủy')),
                                              FilledButton(
                                                  onPressed: () =>
                                                      Navigator.pop(ctx, true),
                                                  child: const Text('Thu hồi'))
                                            ]));
                                if (yes != true) return;
                                try {
                                  await client.request('/nodes/$nodeId/unpair',
                                      method: 'POST');
                                  await client.refresh(node.homeId);
                                } on Object catch (e) {
                                  if (context.mounted) coreMessage(context, e);
                                }
                              },
                        child: const Text('Thu hồi quyền / hủy ghép nối')),
                  ]));
      });
}

class CoreChannelPage extends StatelessWidget {
  final CoreClient client;
  final String channelId;
  const CoreChannelPage(
      {super.key, required this.client, required this.channelId});
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: client,
      builder: (context, _) {
        final ch = client.snapshot?.channels
            .where((c) => c.id == channelId)
            .firstOrNull;
        return Scaffold(
            appBar: AppBar(
                title:
                    Text(ch == null ? 'Channel' : 'SmartChannel ${ch.number}')),
            body: ch == null
                ? const Center(child: Text('Không tìm thấy Channel.'))
                : ListView(padding: const EdgeInsets.all(16), children: [
                    CoreConnection(client: client),
                    detail('Channel ID', ch.id),
                    detail('Relay đã báo cáo', ch.reportedLabel(client.fresh)),
                    detail(
                        'Dòng RMS',
                        ch.current == null
                            ? 'CT chưa hợp lệ'
                            : '${ch.current!.toStringAsFixed(3)} A${client.fresh && ch.online ? '' : ' · dữ liệu cũ'}'),
                    detail('Fault flags', '${ch.faults}'),
                    detail('Revision đã báo cáo', '${ch.configRev}'),
                    if (ch.deviceId == null) ...[
                      FilledButton(
                          onPressed: () => openCore<void>(context,
                              CoreDeviceEditor(client: client, channel: ch)),
                          child: const Text('Thêm thiết bị điện')),
                      TextButton(
                          onPressed: () => openCore<void>(context,
                              CoreBinding(client: client, targetChannel: ch)),
                          child: const Text('Gán thiết bị đã có / thay Box'))
                    ] else
                      FilledButton(
                          onPressed: () => openCore<void>(
                              context,
                              CoreDevicePage(
                                  client: client, deviceId: ch.deviceId!)),
                          child: const Text('Quản lý thiết bị điện')),
                    TextButton(
                        onPressed: () => openCore<void>(
                            context,
                            CoreRecords(
                                client: client,
                                home: client.snapshot!.homeId,
                                filter: ch.id)),
                        child: const Text('Lịch sử Channel')),
                  ]));
      });
}

class CoreDevicePage extends StatelessWidget {
  final CoreClient client;
  final String deviceId;
  const CoreDevicePage(
      {super.key, required this.client, required this.deviceId});
  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: client,
      builder: (context, _) {
        final d =
            client.snapshot?.devices.where((d) => d.id == deviceId).firstOrNull;
        final ch = client.snapshot?.channels
            .where((c) => c.deviceId == deviceId)
            .firstOrNull;
        return Scaffold(
            appBar: AppBar(title: Text(d?.name ?? 'Thiết bị điện')),
            body: d == null
                ? const Center(child: Text('Không tìm thấy thiết bị.'))
                : ListView(padding: const EdgeInsets.all(16), children: [
                    CoreConnection(client: client),
                    CoreDeviceTile(client: client, device: d),
                    detail('Device ID', d.id),
                    detail('Channel', ch?.id ?? 'Chưa gán'),
                    if (client.commandStatus[d.id] != null)
                      detail('Lệnh gần nhất',
                          '${client.commandStatus[d.id]}${client.commandReason[d.id] == null ? '' : ' · ${client.commandReason[d.id]}'}'),
                    if (client.hasUncertainCommand(d.id))
                      FilledButton.tonal(
                          onPressed: () async {
                            try {
                              await client.retryUncertain(d.id);
                            } on Object catch (e) {
                              if (context.mounted) coreMessage(context, e);
                            }
                          },
                          child: const Text('Kiểm tra / gửi lại cùng lệnh')),
                    FilledButton.tonal(
                        onPressed: () => openCore<void>(context,
                            CoreDeviceEditor(client: client, device: d)),
                        child: const Text('Đổi tên / loại thiết bị')),
                    OutlinedButton(
                        onPressed: () => openCore<void>(
                            context, CoreBinding(client: client, device: d)),
                        child: const Text('Chuyển Channel / thay ActionBox')),
                    if (ch != null)
                      TextButton(
                          onPressed: () async {
                            final yes = await showDialog<bool>(
                                context: context,
                                builder: (ctx) => AlertDialog(
                                        title:
                                            const Text('Gỡ liên kết Channel?'),
                                        content: const Text(
                                            'Thiết bị điện và Device ID được giữ lại. Hành động này không phải lệnh tắt relay.'),
                                        actions: [
                                          TextButton(
                                              onPressed: () =>
                                                  Navigator.pop(ctx, false),
                                              child: const Text('Hủy')),
                                          FilledButton(
                                              onPressed: () =>
                                                  Navigator.pop(ctx, true),
                                              child: const Text('Gỡ liên kết'))
                                        ]));
                            if (yes != true) return;
                            try {
                              await client.request(
                                  '/channels/${Uri.encodeComponent(ch.id)}/binding',
                                  method: 'DELETE');
                              await client.refresh(d.homeId);
                              if (context.mounted)
                                coreMessage(context,
                                    'Đã lưu liên kết trên Gateway; chờ Box đồng bộ cấu hình.');
                            } on Object catch (e) {
                              if (context.mounted) coreMessage(context, e);
                            }
                          },
                          child: const Text('Gỡ liên kết')),
                    TextButton(
                        onPressed: () => openCore<void>(
                            context,
                            CoreRecords(
                                client: client, home: d.homeId, filter: d.id)),
                        child: const Text('Lịch sử điều khiển / sự kiện')),
                  ]));
      });
}

class CoreNameForm extends StatefulWidget {
  final String title, label;
  final Future<Map<String, dynamic>> Function(String) submit;
  const CoreNameForm(
      {super.key,
      required this.title,
      required this.label,
      required this.submit});
  @override
  State<CoreNameForm> createState() => _CoreNameFormState();
}

class _CoreNameFormState extends State<CoreNameForm> {
  final name = TextEditingController();
  bool busy = false;
  String? error;
  @override
  void dispose() {
    name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        TextField(
            controller: name,
            maxLength: 120,
            decoration: InputDecoration(labelText: widget.label)),
        if (error != null) Text(error!),
        const SizedBox(height: 16),
        FilledButton(
            onPressed: busy
                ? null
                : () async {
                    if (name.text.trim().isEmpty) {
                      setState(
                          () => error = 'Nhập ${widget.label.toLowerCase()}.');
                      return;
                    }
                    setState(() => busy = true);
                    try {
                      final d = await widget.submit(name.text.trim());
                      if (context.mounted) Navigator.pop(context, d);
                    } on Object catch (e) {
                      if (mounted) setState(() => error = '$e');
                    } finally {
                      if (mounted) setState(() => busy = false);
                    }
                  },
            child: Text(busy ? 'Đang lưu…' : 'Lưu'))
      ]));
}

class CoreDeviceEditor extends StatefulWidget {
  final CoreClient client;
  final CoreChannel? channel;
  final CoreDevice? device;
  const CoreDeviceEditor(
      {super.key, required this.client, this.channel, this.device});
  @override
  State<CoreDeviceEditor> createState() => _CoreDeviceEditorState();
}

class _CoreDeviceEditorState extends State<CoreDeviceEditor> {
  late final name = TextEditingController(text: widget.device?.name);
  late String kind = widget.device?.kind ?? 'light';
  bool busy = false;
  String? error;
  @override
  void dispose() {
    name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(
          title: Text(
              widget.device == null ? 'Thêm thiết bị điện' : 'Đổi tên / loại')),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        if (widget.channel != null)
          detail('Channel được chọn', widget.channel!.id),
        TextField(
            controller: name,
            maxLength: 120,
            decoration: const InputDecoration(labelText: 'Tên thiết bị')),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
            initialValue: kind,
            decoration: const InputDecoration(labelText: 'Loại thiết bị'),
            items: deviceKinds.entries
                .map(
                    (e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                .toList(),
            onChanged: (v) => setState(() => kind = v!)),
        if (error != null) Text(error!),
        const SizedBox(height: 24),
        FilledButton(
            onPressed: busy
                ? null
                : () async {
                    if (name.text.trim().isEmpty) {
                      setState(() => error = 'Nhập tên thiết bị.');
                      return;
                    }
                    setState(() => busy = true);
                    try {
                      final d = widget.device;
                      await widget.client.request(
                          d == null
                              ? '/devices'
                              : '/devices/${Uri.encodeComponent(d.id)}',
                          method: d == null ? 'POST' : 'PATCH',
                          body: {
                            'name': name.text.trim(),
                            'kind': kind,
                            if (d == null) ...{
                              'home_id': widget.client.snapshot!.homeId,
                              'channel_id': widget.channel!.id
                            }
                          });
                      await widget.client
                          .refresh(widget.client.snapshot!.homeId);
                      if (context.mounted) {
                        coreMessage(context,
                            'Gateway đã lưu. Cấu hình Channel cần Box xác nhận trước khi điều khiển.');
                        Navigator.pop(context);
                      }
                    } on Object catch (e) {
                      if (mounted) setState(() => error = '$e');
                    } finally {
                      if (mounted) setState(() => busy = false);
                    }
                  },
            child: Text(busy ? 'Đang lưu…' : 'Xác nhận'))
      ]));
}

class CoreBinding extends StatefulWidget {
  final CoreClient client;
  final CoreDevice? device;
  final CoreChannel? targetChannel;
  const CoreBinding(
      {super.key, required this.client, this.device, this.targetChannel});
  @override
  State<CoreBinding> createState() => _CoreBindingState();
}

class _CoreBindingState extends State<CoreBinding> {
  String? deviceId, channelId;
  int? nodeId;
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    deviceId = widget.device?.id;
    channelId = widget.targetChannel?.id;
    nodeId = widget.targetChannel?.nodeId;
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.client.snapshot!;
    final nodes = s.nodes
        .where((n) => !n.isSubBox && n.registration == 'REGISTERED')
        .toList();
    final channels = s.channels
        .where((c) => c.nodeId == nodeId && c.deviceId == null)
        .toList();
    return Scaffold(
        appBar: AppBar(title: const Text('Gán / chuyển Channel')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          const Text(
              'Device ID và tên thiết bị được giữ nguyên khi chuyển Channel hoặc thay Box. Liên kết cũ được chuyển trong cùng giao dịch trên Gateway.'),
          const SizedBox(height: 24),
          DropdownButtonFormField<String>(
              initialValue: deviceId,
              decoration: const InputDecoration(labelText: 'Thiết bị điện'),
              items: s.devices
                  .map((d) => DropdownMenuItem(
                      value: d.id,
                      child: Text(
                          '${d.name}${d.channelId == null ? ' · chưa gán' : ''}')))
                  .toList(),
              onChanged: widget.device != null
                  ? null
                  : (v) => setState(() => deviceId = v)),
          const SizedBox(height: 16),
          DropdownButtonFormField<int>(
              initialValue: nodeId,
              decoration: const InputDecoration(labelText: 'ActionBox đích'),
              items: nodes
                  .map((n) =>
                      DropdownMenuItem(value: n.id, child: Text(n.factoryId)))
                  .toList(),
              onChanged: widget.targetChannel != null
                  ? null
                  : (v) => setState(() {
                        nodeId = v;
                        channelId = null;
                      })),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
              key: ValueKey(nodeId),
              initialValue: channelId,
              decoration: const InputDecoration(labelText: 'Channel chưa gán'),
              items: channels
                  .map((c) => DropdownMenuItem(
                      value: c.id, child: Text('CH${c.number}')))
                  .toList(),
              onChanged: widget.targetChannel != null
                  ? null
                  : (v) => setState(() => channelId = v)),
          if (channels.isEmpty && nodeId != null)
            const Text('Box này không có Channel trống.'),
          if (error != null) Text(error!),
          const SizedBox(height: 24),
          FilledButton(
              onPressed: busy || deviceId == null || channelId == null
                  ? null
                  : () async {
                      setState(() => busy = true);
                      try {
                        await widget.client.request(
                            '/channels/${Uri.encodeComponent(channelId!)}/bind',
                            method: 'POST',
                            body: {'device_id': deviceId});
                        await widget.client.refresh(s.homeId);
                        if (context.mounted) {
                          coreMessage(context,
                              'Đã lưu liên kết. Đang chờ Box đồng bộ cấu hình.');
                          Navigator.pop(context);
                        }
                      } on Object catch (e) {
                        if (mounted) setState(() => error = '$e');
                      } finally {
                        if (mounted) setState(() => busy = false);
                      }
                    },
              child: Text(busy ? 'Đang gán…' : 'Xác nhận liên kết'))
        ]));
  }
}

class CoreSettings extends StatefulWidget {
  final CoreClient client;
  const CoreSettings({super.key, required this.client});
  @override
  State<CoreSettings> createState() => _CoreSettingsState();
}

class _CoreSettingsState extends State<CoreSettings> {
  String result = 'Chưa kiểm tra';
  bool busy = false;
  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Cài đặt Gateway')),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        detail('Địa chỉ', widget.client.base.toString()),
        const Text(
            'Token được giữ trong bộ nhớ. Quay lại màn hình kết nối để đổi Gateway hoặc kết thúc phiên. Quyền Owner / Member / Installer do Gateway kiểm tra.'),
        detail('Kiểm tra dịch vụ', result),
        FilledButton(
            onPressed: busy
                ? null
                : () async {
                    setState(() => busy = true);
                    try {
                      final d = await widget.client.request('/health');
                      if (mounted)
                        setState(() => result =
                            '${d['product']} · API ${d['api_version']} · database: ${d['database']}');
                    } catch (e) {
                      if (mounted) setState(() => result = '$e');
                    } finally {
                      if (mounted) setState(() => busy = false);
                    }
                  },
            child: const Text('Kiểm tra kết nối')),
      ]));
}

class CoreRecords extends StatefulWidget {
  final CoreClient client;
  final String home;
  final String? filter;
  const CoreRecords(
      {super.key, required this.client, required this.home, this.filter});
  @override
  State<CoreRecords> createState() => _CoreRecordsState();
}

class _CoreRecordsState extends State<CoreRecords> {
  final List<CoreEvent> events = [];
  bool busy = false, more = true;
  String? error;
  @override
  void initState() {
    super.initState();
    unawaited(load());
  }

  Future<void> load() async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final d = await widget.client.request('/events', query: {
        'home_id': widget.home,
        'after': events.isEmpty ? '0' : '${events.last.id}'
      });
      final batch = (d['items'] as List)
          .map((e) => CoreEvent.fromJson(e as Map<String, dynamic>))
          .toList();
      if (mounted)
        setState(() {
          events.addAll(batch);
          more = batch.length == 256;
        });
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final visible = events
        .where((e) =>
            widget.filter == null ||
            jsonEncode(e.data).contains(widget.filter!))
        .toList()
        .reversed;
    return Scaffold(
        appBar: AppBar(title: const Text('Nhật ký sự kiện'), actions: [
          IconButton(
              onPressed: busy ? null : load,
              icon: const Icon(Icons.refresh),
              tooltip: 'Lấy sự kiện mới')
        ]),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          if (widget.filter != null) detail('Bộ lọc', widget.filter!),
          const Text(
              'Nhật ký được lưu trên Gateway. Dòng điện xuất hiện khi Gateway có bản ghi telemetry; không tạo mẫu giả.'),
          if (error != null) Text(error!),
          if (visible.isEmpty && !busy)
            const Padding(
                padding: EdgeInsets.all(24),
                child: Text('Chưa có bản ghi phù hợp trong dữ liệu đã tải.')),
          for (final e in visible)
            ExpansionTile(
                title: Text(e.kind),
                subtitle: Text(coreTime(e.created)),
                children: [
                  Padding(
                      padding: const EdgeInsets.all(16),
                      child: SelectableText(
                          const JsonEncoder.withIndent('  ').convert(e.data)))
                ]),
          if (busy) const Center(child: CircularProgressIndicator()),
          if (more)
            TextButton(
                onPressed: busy ? null : load,
                child: const Text('Tải tiếp nhật ký'))
        ]));
  }
}

class CoreFirmware extends StatefulWidget {
  final CoreClient client;
  final String home;
  const CoreFirmware({super.key, required this.client, required this.home});
  @override
  State<CoreFirmware> createState() => _CoreFirmwareState();
}

class _CoreFirmwareState extends State<CoreFirmware> {
  List<CoreArtifact> artifacts = [];
  List<CoreOtaJob> jobs = [];
  bool loading = false;
  String? error;
  Timer? timer;
  DateTime? loaded;
  @override
  void initState() {
    super.initState();
    unawaited(load());
    timer = Timer.periodic(const Duration(seconds: 3), (_) => load());
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<void> load() async {
    if (loading) return;
    loading = true;
    try {
      final results = await Future.wait([
        widget.client.request('/firmware', query: {'home_id': widget.home}),
        widget.client.request('/ota/jobs', query: {'home_id': widget.home})
      ]);
      if (mounted)
        setState(() {
          artifacts = (results[0]['items'] as List)
              .map((d) => CoreArtifact.fromJson(d as Map<String, dynamic>))
              .toList();
          jobs = (results[1]['items'] as List)
              .map((d) => CoreOtaJob.fromJson(d as Map<String, dynamic>))
              .toList();
          error = null;
          loaded = DateTime.now();
        });
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      loading = false;
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Firmware & OTA'), actions: [
        IconButton(
            onPressed: load,
            icon: const Icon(Icons.refresh),
            tooltip: 'Làm mới')
      ]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (error != null)
          Text(
              'Không cập nhật được: $error. Tiến trình bên dưới có thể đã cũ.'),
        if (loaded != null)
          Text('Cập nhật: ${loaded!.toLocal().toString().split('.').first}'),
        const Text(
            '100% truyền dữ liệu chưa có nghĩa cập nhật thành công. Chờ Gateway xác nhận boot và health check. Gateway thực hiện tuần tự theo phòng.'),
        section('Firmware đã xác minh'),
        if (artifacts.isEmpty)
          const Text(
              'Chưa có firmware. Owner có thể tải lên image và manifest có chữ ký.'),
        for (final a in artifacts)
          ListTile(
              title: Text('${a.model} · ${a.version}'),
              subtitle: Text('${a.size} bytes · ${a.id}'),
              trailing: const Icon(Icons.system_update),
              onTap: () async {
                await openCore<void>(
                    context,
                    CoreOtaCreate(
                        client: widget.client, home: widget.home, artifact: a));
                await load();
              }),
        OutlinedButton.icon(
            onPressed: () async {
              await openCore<void>(context,
                  CoreFirmwareUpload(client: widget.client, home: widget.home));
              await load();
            },
            icon: const Icon(Icons.upload_file),
            label: const Text('Tải firmware có chữ ký')),
        section('Lịch sử OTA'),
        if (jobs.isEmpty) const Text('Chưa có tác vụ OTA.'),
        for (final j in jobs)
          ExpansionTile(
              initiallyExpanded: j.targets.any((t) => !t.terminal),
              title: Text(j.id),
              subtitle: Text(coreTime(j.created)),
              children: [
                for (final t in j.targets)
                  Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                                'Node ${t.nodeId} · ${t.model} → ${t.version}'),
                            Text(
                                '${t.status}${t.reason == null ? '' : ' · ${t.reason}'}'),
                            const SizedBox(height: 8),
                            LinearProgressIndicator(
                                value: (t.percent / 100).clamp(0, 1)),
                            Text(
                                '${t.percent.toStringAsFixed(1)}% dữ liệu đã truyền'),
                            if (t.status == 'ROLLED_BACK')
                              const Text('Gateway báo firmware đã rollback.'),
                            if (t.status == 'SUCCEEDED')
                              const Text(
                                  'Gateway đã xác minh boot và health check.')
                          ]))
              ]),
      ]));
}

class CoreOtaCreate extends StatefulWidget {
  final CoreClient client;
  final String home;
  final CoreArtifact artifact;
  const CoreOtaCreate(
      {super.key,
      required this.client,
      required this.home,
      required this.artifact});
  @override
  State<CoreOtaCreate> createState() => _CoreOtaCreateState();
}

class _CoreOtaCreateState extends State<CoreOtaCreate> {
  final Set<int> selected = {};
  bool busy = false;
  String? error;
  @override
  Widget build(BuildContext context) {
    final nodes = widget.client.snapshot?.nodes
            .where((n) =>
                n.homeId == widget.home &&
                n.model == widget.artifact.model &&
                n.registration == 'REGISTERED')
            .toList() ??
        [];
    return Scaffold(
        appBar: AppBar(title: const Text('Tạo tác vụ OTA')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          detail('Firmware đích',
              '${widget.artifact.model} · ${widget.artifact.version}'),
          const Text(
              'Chọn Box cần cập nhật. Relay và dịch vụ trên Box có thể gián đoạn khi reboot; chỉ tiến hành khi tải điện ở trạng thái an toàn.'),
          for (final n in nodes)
            CheckboxListTile(
                value: selected.contains(n.id),
                title: Text(n.factoryId),
                subtitle: Text('Hiện tại ${n.firmware} · ${n.availability}'),
                onChanged: busy
                    ? null
                    : (v) => setState(() {
                          if (v == true) {
                            selected.add(n.id);
                          } else {
                            selected.remove(n.id);
                          }
                        })),
          if (nodes.isEmpty)
            const Text('Không có Box đã đăng ký đúng model trong nhà này.'),
          if (error != null) Text(error!),
          FilledButton(
              onPressed: busy || selected.isEmpty
                  ? null
                  : () async {
                      setState(() => busy = true);
                      try {
                        await widget.client
                            .request('/ota/jobs', method: 'POST', body: {
                          'home_id': widget.home,
                          'artifact_id': widget.artifact.id,
                          'node_ids': selected.toList()
                        });
                        if (context.mounted) Navigator.pop(context);
                      } catch (e) {
                        if (mounted) setState(() => error = '$e');
                      } finally {
                        if (mounted) setState(() => busy = false);
                      }
                    },
              child: Text(busy ? 'Đang gửi…' : 'Xếp lịch cập nhật'))
        ]));
  }
}

class CoreFirmwareUpload extends StatefulWidget {
  final CoreClient client;
  final String home;
  const CoreFirmwareUpload(
      {super.key, required this.client, required this.home});
  @override
  State<CoreFirmwareUpload> createState() => _CoreFirmwareUploadState();
}

class _CoreFirmwareUploadState extends State<CoreFirmwareUpload> {
  final manifest = TextEditingController(), signature = TextEditingController();
  PlatformFile? file;
  bool busy = false;
  String? error;
  @override
  void dispose() {
    manifest.dispose();
    signature.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: const Text('Tải firmware')),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        const Text(
            'Manifest JSON: model, version, size, sha256. Chữ ký ECDSA P-256 dạng hex 128 ký tự do hệ thống ký offline cấp. App không giữ khóa ký.'),
        const SizedBox(height: 16),
        TextField(
            controller: manifest,
            minLines: 4,
            maxLines: 8,
            decoration: const InputDecoration(labelText: 'Manifest JSON')),
        const SizedBox(height: 16),
        TextField(
            controller: signature,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(labelText: 'Chữ ký manifest')),
        TextButton.icon(
            onPressed: busy
                ? null
                : () async {
                    try {
                      final selected = await FilePicker.platform.pickFiles(
                          type: FileType.custom,
                          allowedExtensions: ['bin'],
                          withData: true);
                      if (selected != null && mounted) {
                        final f = selected.files.single;
                        if (f.size <= 0 || f.size > 0x2f0000 || f.bytes == null)
                          throw const CoreException('invalid_image',
                              'Image phải từ 1 đến 3.080.192 bytes.');
                        setState(() => file = f);
                      }
                    } catch (e) {
                      if (mounted) setState(() => error = '$e');
                    }
                  },
            icon: const Icon(Icons.attach_file),
            label: Text(file?.name ?? 'Chọn image .bin')),
        if (error != null) Text(error!),
        FilledButton(
            onPressed: busy || file == null
                ? null
                : () async {
                    setState(() => busy = true);
                    try {
                      final m =
                          jsonDecode(manifest.text) as Map<String, dynamic>;
                      if (!RegExp(r'^[0-9a-f]{128}$')
                              .hasMatch(signature.text.trim()) ||
                          m['size'] != file!.size)
                        throw const CoreException('invalid_manifest',
                            'Kiểm tra chữ ký hex và kích thước image trong manifest.');
                      await widget.client
                          .request('/firmware', method: 'POST', body: {
                        'home_id': widget.home,
                        'manifest': m,
                        'signature': signature.text.trim(),
                        'image': base64Encode(file!.bytes!)
                      });
                      if (context.mounted) {
                        coreMessage(
                            context, 'Gateway đã xác minh và lưu firmware.');
                        Navigator.pop(context);
                      }
                    } catch (e) {
                      if (mounted) setState(() => error = '$e');
                    } finally {
                      if (mounted) setState(() => busy = false);
                    }
                  },
            child: Text(busy ? 'Đang tải / xác minh…' : 'Tải lên Gateway'))
      ]));
}

class CoreAssign extends StatefulWidget {
  final CoreClient client;
  final CoreNodeData node;
  const CoreAssign({super.key, required this.client, required this.node});
  @override
  State<CoreAssign> createState() => _CoreAssignState();
}

class _CoreAssignState extends State<CoreAssign> {
  String? roomId;
  @override
  Widget build(BuildContext context) {
    final rooms = widget.client.snapshot!.rooms;
    final room = rooms.where((r) => r.id == roomId).firstOrNull;
    final parents = widget.client.snapshot!.nodes
        .where((n) =>
            n.isSubBox && n.roomId == roomId && n.registration == 'REGISTERED')
        .toList();
    return Scaffold(
        appBar: AppBar(title: const Text('Chuyển Box')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          detail('Box', widget.node.factoryId),
          const Text(
              'Chuyển phòng cần mở cửa sổ ghép nối vật lý trên Box và xác nhận cấu hình mới. SubBox còn ActionBox con phải chuyển các Box con trước.'),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
              initialValue: roomId,
              decoration: const InputDecoration(labelText: 'Phòng đích'),
              items: rooms
                  .map(
                      (r) => DropdownMenuItem(value: r.id, child: Text(r.name)))
                  .toList(),
              onChanged: (v) => setState(() => roomId = v)),
          const SizedBox(height: 24),
          FilledButton(
              onPressed:
                  room == null || (!widget.node.isSubBox && parents.isEmpty)
                      ? null
                      : () => openCore<void>(
                          context,
                          CoreClaim(
                              client: widget.client,
                              room: room,
                              parents: parents,
                              isSubBox: widget.node.isSubBox,
                              transfer: widget.node)),
              child: const Text('Tiếp tục xác thực Box'))
        ]));
  }
}

class CoreClaim extends StatefulWidget {
  final CoreClient client;
  final CoreRoomData room;
  final List<CoreNodeData> parents;
  final bool isSubBox;
  final CoreNodeData? transfer;
  final Map<String, dynamic>? defaults;
  const CoreClaim(
      {super.key,
      required this.client,
      required this.room,
      required this.parents,
      required this.isSubBox,
      this.transfer,
      this.defaults});
  @override
  State<CoreClaim> createState() => _CoreClaimState();
}

class _CoreClaimState extends State<CoreClaim> {
  final factory = TextEditingController(),
      setup = TextEditingController(),
      qr = TextEditingController(),
      ssid = TextEditingController(),
      password = TextEditingController(),
      mqtt = TextEditingController(text: 'mqtts://'),
      parentMac = TextEditingController(),
      radioChannel = TextEditingController(text: '1'),
      otaKey = TextEditingController();
  int? parent;
  int stage = 0;
  bool busy = false;
  String? error;
  CoreProvisionInfo? info;
  Map<String, dynamic>? claim;
  String? packet, status;
  final String claimRequestId =
      DateTime.now().microsecondsSinceEpoch.toString();
  @override
  void initState() {
    super.initState();
    factory.text = widget.transfer?.factoryId ?? '';
    parent = widget.parents.firstOrNull?.id;
    if (widget.defaults != null) {
      radioChannel.text = '${widget.defaults!['channel']}';
      mqtt.text = widget.defaults!['mqtt_uri'] as String? ?? 'mqtts://';
      otaKey.text = widget.defaults!['ota_pubkey'] as String? ?? '';
      setParentMetadata();
    }
  }

  void setParentMetadata() {
    final parents = widget.defaults?['parents'];
    if (parents is Map) {
      final value = parents['$parent'];
      if (value is Map && value['sta_mac'] is String)
        parentMac.text = value['sta_mac'] as String;
    }
  }

  @override
  void dispose() {
    for (final c in [
      factory,
      setup,
      qr,
      ssid,
      password,
      mqtt,
      parentMac,
      radioChannel,
      otaKey
    ]) {
      c.clear();
      c.dispose();
    }
    packet = null;
    super.dispose();
  }

  Future<void> run(Future<void> Function() action) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> readInfo() async {
    if (!RegExp(r'^HC-[0-9A-F]{12}$').hasMatch(factory.text.trim()) ||
        setup.text.isEmpty)
      throw const CoreException('invalid_setup',
          'Nhập Factory ID và setup code từ nhãn riêng của Box.');
    final parsed = CoreProvisionInfo.parse(
        await CoreProvisioning.exchange(setup.text, 'hc-info', Uint8List(0)));
    if (parsed.factoryId != factory.text.trim() ||
        parsed.isSubBox != widget.isSubBox)
      throw const CoreException('identity_mismatch',
          'Box kết nối không khớp Factory ID hoặc loại sản phẩm đã chọn.');
    if (mounted)
      setState(() {
        info = parsed;
        stage = 1;
      });
  }

  Future<void> prepare() async {
    final channel = int.tryParse(radioChannel.text);
    if (channel == null || channel < 1 || channel > 13)
      throw const CoreException(
          'invalid_channel', 'Kênh Wi-Fi phải từ 1 đến 13.');
    if (widget.isSubBox &&
        (ssid.text.isEmpty || !mqtt.text.startsWith('mqtts://')))
      throw const CoreException(
          'invalid_network', 'Nhập Wi-Fi 2.4 GHz và địa chỉ MQTT TLS.');
    if (!widget.isSubBox &&
        !RegExp(r'^(?:[0-9a-fA-F]{2}:?){6}$').hasMatch(parentMac.text.trim()))
      throw const CoreException(
          'invalid_parent', 'Nhập STA MAC của SubBox cha.');
    claim ??= await widget.client.request(
        widget.transfer == null
            ? '/nodes/claim'
            : '/nodes/${widget.transfer!.id}/assign',
        method: 'POST',
        body: {
          'idempotency_key': '$claimRequestId-${info!.challenge}',
          'room_id': widget.room.id,
          if (!widget.isSubBox) 'parent_id': parent,
          if (widget.transfer == null) ...{
            'factory_id': info!.factoryId,
            'setup_code': setup.text
          }
        });
    final response = await widget.client
        .request('/provisioning/prepare', method: 'POST', body: {
      'claim_id': claim!['claim_id'],
      'challenge': info!.challenge,
      'radio_mac': info!.radioMac,
      'channel': channel,
      if (widget.isSubBox) ...{
        'wifi_ssid': ssid.text,
        'wifi_password': password.text,
        'mqtt_uri': mqtt.text.trim()
      },
      if (!widget.isSubBox) 'parent_mac': parentMac.text.trim(),
      if (otaKey.text.trim().isNotEmpty) 'ota_pubkey': otaKey.text.trim()
    });
    if (mounted)
      setState(() {
        packet = response['packet'] as String;
        stage = 2;
        password.clear();
      });
  }

  Future<void> deliver() async {
    if (DateTime.now().millisecondsSinceEpoch / 1000 >=
        (claim!['expires'] as num))
      throw const CoreException('claim_expired',
          'Yêu cầu đã hết hạn. Quay lại và mở quy trình ghép nối mới.');
    final response = await CoreProvisioning.exchange(
        setup.text, 'hc-config', CoreProvisioning.decodeHex(packet!));
    if (utf8.decode(response, allowMalformed: true) != 'STORED')
      throw const CoreException('not_stored',
          'Box chưa xác nhận lưu cấu hình. Kiểm tra Gateway trước khi thử lại.');
    if (mounted)
      setState(() {
        packet = null;
        setup.clear();
        stage = 3;
        status = 'Đã lưu trên Box; chờ khởi động lại và Gateway xác minh.';
      });
  }

  Future<void> check() async {
    final response = await widget.client.request(
        '/provisioning/${Uri.encodeComponent(claim!['claim_id'] as String)}');
    if (mounted) setState(() => status = response['status'] as String);
    if (response['status'] == 'EXPIRED') {
      throw const CoreException('claim_expired',
          'Phiên ghép đã hết hạn. Quay lại và mở quy trình ghép mới.');
    }
    if (response['status'] == 'REGISTERED') {
      await widget.client.refresh(widget.room.homeId);
      if (mounted) setState(() => stage = 4);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(
          title: Text(widget.transfer != null
              ? 'Chuyển Box'
              : widget.isSubBox
                  ? 'Đăng ký SubBox'
                  : 'Đăng ký ActionBox')),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        detail('Phòng', widget.room.name),
        Text('Bước ${stage + 1} / 5',
            style: Theme.of(context).textTheme.titleLarge),
        if (!CoreProvisioning.supported)
          const Text(
              'Secure provisioning hiện chỉ có trên Android. Trên nền tảng này có thể quản lý Box đã đăng ký bằng công cụ commissioning.'),
        if (stage == 0) ...[
          const Text(
              'Giữ BOOT khoảng 4 giây rồi thả để mở ghép nối. Trong cài đặt Wi-Fi Android, kết nối siciot_sub_XXXXXX hoặc siciot_act_XXXXXX bằng mật khẩu riêng trên nhãn. Cửa sổ ghép nối kéo dài 180 giây. Giữ điện thoại kết nối AP dù không có Internet. Không giữ BOOT tới 10 giây vì đó là thao tác reset.'),
          const SizedBox(height: 16),
          TextField(
              controller: qr,
              decoration: const InputDecoration(
                  labelText: 'Dán dữ liệu QR (JSON) nếu có')),
          TextButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                        final d = jsonDecode(qr.text) as Map<String, dynamic>;
                        final id = d['factory_id'];
                        final pop = d['setup_code'] ?? d['pop'];
                        if (id is! String || pop is! String)
                          throw const CoreException('invalid_qr',
                              'QR cần factory_id và setup_code/pop.');
                        factory.text = id.toUpperCase();
                        setup.text = pop;
                        qr.clear();
                      }),
              child: const Text('Đọc dữ liệu QR')),
          TextField(
              controller: factory,
              readOnly: widget.transfer != null,
              keyboardType: TextInputType.visiblePassword,
              autocorrect: false,
              enableSuggestions: false,
              decoration: const InputDecoration(labelText: 'Mã thiết bị')),
          const SizedBox(height: 16),
          TextField(
              controller: setup,
              obscureText: true,
              enableSuggestions: false,
              autocorrect: false,
              decoration: const InputDecoration(
                  labelText: 'Mã thiết lập trên nhãn Box')),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: busy || !CoreProvisioning.supported
                  ? null
                  : () => run(readInfo),
              child: const Text('Xác thực và đọc thông tin Box')),
        ],
        if (stage == 1) ...[
          detail('Đã xác thực', info!.factoryId),
          const Text(
              'Kết nối lại mạng của Gateway để cấp cấu hình. Sau đó quay về AP của Box trong cửa sổ ghép nối.'),
          const SizedBox(height: 16),
          if (!widget.isSubBox) ...[
            DropdownButtonFormField<int>(
                initialValue: parent,
                decoration: const InputDecoration(labelText: 'SubBox cha'),
                items: widget.parents
                    .map((n) =>
                        DropdownMenuItem(value: n.id, child: Text(n.factoryId)))
                    .toList(),
                onChanged: busy
                    ? null
                    : (v) => setState(() {
                          parent = v;
                          setParentMetadata();
                        })),
            const SizedBox(height: 16),
            if (widget.defaults == null)
              TextField(
                  controller: parentMac,
                  decoration: const InputDecoration(
                      labelText: 'STA MAC của SubBox cha'))
          ],
          if (widget.isSubBox) ...[
            TextField(
                controller: ssid,
                decoration:
                    const InputDecoration(labelText: 'Wi-Fi 2.4 GHz SSID')),
            const SizedBox(height: 16),
            TextField(
                controller: password,
                obscureText: true,
                enableSuggestions: false,
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'Mật khẩu Wi-Fi')),
            const SizedBox(height: 16),
            if (widget.defaults == null)
              TextField(
                  controller: mqtt,
                  decoration: const InputDecoration(labelText: 'MQTT TLS URI')),
            const Text(
                'CA tin cậy và tài khoản MQTT phải được provision qua USB theo hướng dẫn triển khai trước khi đăng ký.')
          ],
          const SizedBox(height: 16),
          if (widget.defaults == null)
            TextField(
                controller: radioChannel,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                    labelText: 'Kênh Wi-Fi của SubBox (1–13)')),
          const SizedBox(height: 16),
          if (widget.defaults == null)
            TextField(
                controller: otaKey,
                maxLines: 3,
                decoration: const InputDecoration(
                    labelText: 'Khóa công khai OTA P-256 hex (nếu được cấp)')),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: busy ? null : () => run(prepare),
              child: const Text('Gateway cấp cấu hình')),
        ],
        if (stage == 2) ...[
          detail('Claim', claim!['claim_id'] as String),
          const Text(
              'Kết nối lại AP của đúng Box. Cấu hình chỉ được truyền qua phiên Espressif Security1 có xác thực. Box sẽ reboot sau khi lưu.'),
          FilledButton(
              onPressed: busy ? null : () => run(deliver),
              child: const Text('Gửi cấu hình bảo mật')),
          TextButton(
              onPressed: busy ? null : () => run(check),
              child: const Text('Kiểm tra Gateway nếu kết quả gửi chưa rõ'))
        ],
        if (stage == 3) ...[
          const Text(
              'Kết nối lại mạng của Gateway. Chờ Box lưu cấu hình và khôi phục kết nối. ActionBox cần xác nhận độc lập từ SubBox cha; chỉ Gateway có thể xác nhận đăng ký.'),
          if (status != null) detail('Trạng thái', status!),
          FilledButton(
              onPressed: busy ? null : () => run(check),
              child: const Text('Kiểm tra đăng ký trên Gateway'))
        ],
        if (stage == 4) ...[
          const Icon(Icons.verified_outlined, size: 48),
          const Text(
              'Gateway đã xác minh đăng ký. Trạng thái online và relay được lấy riêng từ snapshot.'),
          FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Hoàn tất'))
        ],
        if (stage < 4 && CoreProvisioning.supported)
          TextButton.icon(
              onPressed: busy ? null : () => run(CoreProvisioning.wifiSettings),
              icon: const Icon(Icons.wifi),
              label: const Text('Mở cài đặt Wi-Fi')),
        if (error != null)
          Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Text(error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error))),
        if (busy)
          const Padding(
              padding: EdgeInsets.all(16), child: LinearProgressIndicator()),
      ]));
}
