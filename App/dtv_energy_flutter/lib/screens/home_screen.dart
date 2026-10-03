import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../main.dart' show appTheme;
import '../services/gateway_client.dart';
import 'device_screen.dart';
import 'manage_screen.dart';

String roomName(String id) =>
    const {
      'livingroom': 'Phòng khách',
      'living_room': 'Phòng khách',
      'phong_khach': 'Phòng khách',
      'bedroom': 'Phòng ngủ',
      'phong_ngu': 'Phòng ngủ',
      'kitchen': 'Phòng bếp',
      'phong_bep': 'Phòng bếp',
      'bathroom': 'Phòng tắm',
      'office': 'Phòng làm việc',
      'garden': 'Sân vườn',
      '': 'Chưa phân phòng',
    }[id] ??
    id.replaceAll('_', ' ');

String nodeName(String id, Map<String, dynamic> node) =>
    '${node['name'] ?? node['display_name'] ?? id}';

Map<String, dynamic> telemetry(Map<String, dynamic> node) => {
      ...asMap(node['pzem']),
      ...asMap(node['last_telemetry']),
    };

String metric(dynamic value, String unit, [int digits = 1]) {
  final number = readNumber(value);
  return number == null ? '— $unit' : '${number.toStringAsFixed(digits)} $unit';
}

bool? relayState(Map<String, dynamic> node, String channel) {
  final index = {'ch1': 0, 'ch2': 1}[channel];
  final states = node['relay_state'];
  if (index == null || states is! List || states.length <= index) return null;
  final value = states[index];
  if (value == 1 || value == true || value == 'ON') return true;
  if (value == 0 || value == false || value == 'OFF') return false;
  return null;
}

IconData deviceIcon(String type) => switch (type) {
      'light' || 'lamp' => Icons.lightbulb_outline_rounded,
      'fan' => Icons.air_rounded,
      'ac' || 'air_conditioner' => Icons.ac_unit_rounded,
      'pump' => Icons.water_drop_outlined,
      _ => Icons.power_outlined,
    };

String channelName(String channel, dynamic info) {
  final data = asMap(info);
  return '${data['name'] ?? data['description'] ?? const {
        'light': 'Đèn',
        'fan': 'Quạt',
        'pump': 'Máy bơm',
        'ac': 'Điều hòa'
      }[data['device_type'] ?? info] ?? channel.toUpperCase()}';
}

void showMessage(BuildContext context, String text) {
  ScaffoldMessenger.of(context).hideCurrentSnackBar();
  ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(text), behavior: SnackBarBehavior.floating));
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.gateway});
  final GatewayClient gateway;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  int _tab = 0;
  String? _room;
  String _search = '';
  bool _favoritesOnly = false;
  Set<String> _favorites = {};
  Timer? _timer;
  GatewayClient get client => widget.gateway;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadFavorites();
    _startPolling();
    WidgetsBinding.instance.addPostFrameCallback((_) => client.refresh());
  }

  Future<void> _loadFavorites() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted)
      setState(() => _favorites = (prefs.getStringList(
                  'sic_favorites_${client.serverUrl}_${client.user['id']}') ??
              [])
          .toSet());
  }

  Future<void> _favorite(String id) async {
    setState(() =>
        _favorites.contains(id) ? _favorites.remove(id) : _favorites.add(id));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
        'sic_favorites_${client.serverUrl}_${client.user['id']}',
        _favorites.toList());
  }

  void _startPolling() {
    _timer?.cancel();
    // ponytail: one snapshot every 5 seconds; use authenticated SSE if scale requires it.
    _timer =
        Timer.periodic(const Duration(seconds: 5), (_) => client.refresh());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      client.refresh();
      _startPolling();
    } else {
      _timer?.cancel();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _openDevice(String id) => Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => DeviceScreen(client: client, nodeId: id)));

  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: client,
      builder: (context, _) {
        final colors = Theme.of(context).colorScheme;
        return Scaffold(
          appBar: AppBar(
              title: Row(children: [
                Icon(Icons.home_rounded, color: colors.primary),
                const SizedBox(width: 10),
                const Text('SIC Home',
                    style: TextStyle(fontWeight: FontWeight.w700)),
              ]),
              actions: [
                IconButton(
                    tooltip: 'Làm mới',
                    onPressed: client.loading ? null : client.refresh,
                    icon: const Icon(Icons.refresh_rounded)),
                if (client.isAdmin)
                  IconButton(
                      tooltip: 'Thêm thiết bị',
                      icon: const Icon(Icons.add_rounded),
                      onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                              builder: (_) => ManageScreen(client: client)))),
                const SizedBox(width: 8),
              ]),
          body: SafeArea(
              top: false,
              child: Column(children: [
                if (client.error != null)
                  Container(
                      width: double.infinity,
                      color: colors.errorContainer,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 10),
                      child: Row(children: [
                        Icon(Icons.wifi_off_rounded,
                            size: 18, color: colors.onErrorContainer),
                        const SizedBox(width: 10),
                        Expanded(
                            child: Semantics(
                                liveRegion: true,
                                child: Text(client.error!,
                                    style: TextStyle(
                                        color: colors.onErrorContainer,
                                        fontSize: 13)))),
                      ])),
                if (client.loading && client.nodes.isEmpty)
                  const LinearProgressIndicator(minHeight: 2),
                Expanded(
                    child: RefreshIndicator(
                  onRefresh: client.refresh,
                  child: SingleChildScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                    child: Center(
                        child: ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 960),
                            child: switch (_tab) {
                              0 => _home(context),
                              1 => _devices(context),
                              2 => _energy(context),
                              _ => _settings(context)
                            })),
                  ),
                )),
              ])),
          bottomNavigationBar: NavigationBar(
              selectedIndex: _tab,
              onDestinationSelected: (index) => setState(() => _tab = index),
              destinations: const [
                NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    selectedIcon: Icon(Icons.home_rounded),
                    label: 'Nhà'),
                NavigationDestination(
                    icon: Icon(Icons.devices_other_outlined),
                    selectedIcon: Icon(Icons.devices_other_rounded),
                    label: 'Thiết bị'),
                NavigationDestination(
                    icon: Icon(Icons.bolt_outlined),
                    selectedIcon: Icon(Icons.bolt_rounded),
                    label: 'Điện năng'),
                NavigationDestination(
                    icon: Icon(Icons.settings_outlined),
                    selectedIcon: Icon(Icons.settings_rounded),
                    label: 'Cài đặt'),
              ]),
        );
      });

  Widget _heading(String title, String subtitle, {Widget? trailing}) => Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 24),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 6),
          Text(subtitle,
              style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ])),
        if (trailing != null) trailing,
      ]));

  List<MapEntry<String, dynamic>> get _entries =>
      client.nodes.entries.where((e) {
        final node = asMap(e.value);
        return (_room == null || node['room'] == _room) &&
            ('${nodeName(e.key, node)} ${roomName('${node['room'] ?? ''}')} ${e.key}'
                .toLowerCase()
                .contains(_search.toLowerCase()));
      }).toList();

  Widget _rooms() {
    final rooms = client.nodes.values
        .map((n) => '${asMap(n)['room'] ?? ''}')
        .toSet()
        .toList()
      ..sort();
    if (_room != null && !rooms.contains(_room)) _room = null;
    return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(children: [
          Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                  label: const Text('Tất cả'),
                  selected: _room == null,
                  onSelected: (_) => setState(() => _room = null))),
          for (final room in rooms)
            Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(
                    label: Text(roomName(room)),
                    selected: _room == room,
                    onSelected: (_) => setState(() => _room = room))),
        ]));
  }

  Widget _home(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final online =
        client.nodes.values.where((n) => asMap(n)['status'] == 'online').length;
    final rooms =
        client.nodes.values.map((n) => asMap(n)['room']).toSet().length;
    final relays = <Widget>[];
    int active = 0;
    for (final entry in client.nodes.entries) {
      final node = asMap(entry.value);
      for (final ch in asMap(node['channels']).keys) {
        if (client.connected &&
            node['status'] == 'online' &&
            relayState(node, ch) == true) active++;
      }
    }
    for (final entry in _entries) {
      final node = asMap(entry.value);
      for (final ch in asMap(node['channels']).entries) {
        if (!['ch1', 'ch2'].contains(ch.key)) continue;
        final id = '${entry.key}/${ch.key}';
        if (_favoritesOnly && !_favorites.contains(id)) continue;
        relays.add(RelayTile(
            key: ValueKey(id),
            client: client,
            nodeId: entry.key,
            channel: ch.key,
            favorite: _favorites.contains(id),
            onFavorite: () => _favorite(id),
            onDetails: () => _openDevice(entry.key)));
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _heading(
          'Nhà của bạn',
          client.user['fullname']?.toString().isNotEmpty == true
              ? 'Xin chào, ${client.user['fullname']}'
              : 'Chào mừng bạn về nhà',
          trailing: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                  color: colors.primaryContainer, shape: BoxShape.circle),
              child:
                  Icon(Icons.spa_outlined, color: colors.primary, size: 24))),
      Wrap(
          spacing: 8,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Icon(
                client.connected
                    ? Icons.cloud_done_outlined
                    : Icons.cloud_off_outlined,
                color: client.connected ? colors.primary : colors.error,
                size: 17),
            Text(
                client.connected ? 'Gateway đã kết nối' : 'Gateway ngoại tuyến',
                style: TextStyle(
                    color: client.connected ? colors.primary : colors.error,
                    fontWeight: FontWeight.w600,
                    fontSize: 13)),
            if (client.updatedAt != null)
              Text(
                  '· ${TimeOfDay.fromDateTime(client.updatedAt!).format(context)}',
                  style:
                      TextStyle(color: colors.onSurfaceVariant, fontSize: 12)),
          ]),
      const SizedBox(height: 22),
      Wrap(spacing: 28, runSpacing: 16, children: [
        _stat('$online/${client.nodes.length}', 'Trực tuyến', colors.primary),
        _stat('$active', 'Đang bật', const Color(0xFFB37A18)),
        _stat('$rooms', 'Phòng', colors.onSurface),
      ]),
      const Padding(
          padding: EdgeInsets.symmetric(vertical: 18), child: Divider()),
      _rooms(),
      Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: Row(children: [
            const Expanded(
                child: Text('Điều khiển nhanh',
                    style:
                        TextStyle(fontSize: 18, fontWeight: FontWeight.w700))),
            IconButton(
                tooltip: _favoritesOnly ? 'Hiện tất cả' : 'Chỉ yêu thích',
                onPressed: () =>
                    setState(() => _favoritesOnly = !_favoritesOnly),
                icon: Icon(
                    _favoritesOnly
                        ? Icons.star_rounded
                        : Icons.star_outline_rounded,
                    color: _favoritesOnly ? const Color(0xFFB37A18) : null)),
          ])),
      if (relays.isEmpty)
        EmptyState(
            icon: Icons.touch_app_outlined,
            title:
                client.nodes.isEmpty ? 'Chưa có thiết bị' : 'Chưa có công tắc',
            subtitle: _favoritesOnly
                ? 'Danh sách yêu thích đang trống.'
                : client.isAdmin
                    ? 'Thiết bị mới sẽ xuất hiện trong danh sách chờ ghép nối.'
                    : 'Thiết bị được quản trị viên chia sẻ sẽ xuất hiện ở đây.'),
      ResponsiveTiles(children: relays),
      if (client.isAdmin && client.pending.isNotEmpty)
        Padding(
            padding: const EdgeInsets.only(top: 18),
            child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(Icons.add_link_rounded, color: colors.primary),
                title: Text('${client.pending.length} thiết bị chờ kết nối'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => ManageScreen(client: client))))),
    ]);
  }

  Widget _stat(String value, String label, Color color) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value,
            style: TextStyle(
                fontSize: 30, fontWeight: FontWeight.w700, color: color)),
        Text(label,
            style: TextStyle(
                fontSize: 13,
                color: Theme.of(context).colorScheme.onSurfaceVariant)),
      ]);

  Widget _devices(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _heading('Thiết bị', '${client.nodes.length} thiết bị trong nhà'),
        TextField(
            onChanged: (value) => setState(() => _search = value),
            decoration: const InputDecoration(
                hintText: 'Tìm thiết bị, phòng...',
                prefixIcon: Icon(Icons.search_rounded))),
        const SizedBox(height: 16),
        _rooms(),
        const SizedBox(height: 16),
        if (_entries.isEmpty)
          const EmptyState(
              icon: Icons.devices_other,
              title: 'Không tìm thấy thiết bị',
              subtitle: 'Thử chọn phòng khác hoặc làm mới danh sách.'),
        for (final entry in _entries)
          Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Card(
                  child: ListTile(
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                leading: Icon(Icons.developer_board_rounded,
                    color: asMap(entry.value)['status'] == 'online'
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.outline),
                title: Text(nodeName(entry.key, asMap(entry.value)),
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text(
                    '${roomName('${asMap(entry.value)['room'] ?? ''}')} · ${asMap(entry.value)['status'] == 'online' ? 'Trực tuyến' : 'Ngoại tuyến'}'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => _openDevice(entry.key),
              ))),
      ]);

  Widget _energy(BuildContext context) {
    final metered = client.nodes.entries
        .where((e) => telemetry(asMap(e.value)).isNotEmpty)
        .toList();
    final online =
        metered.where((e) => asMap(e.value)['status'] == 'online').toList();
    final values = online
        .map((e) => telemetry(asMap(e.value)))
        .map((t) => readNumber(t['power'] ?? t['p']))
        .whereType<double>()
        .toList();
    final total = values.isEmpty ? null : values.reduce((a, b) => a + b);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _heading('Điện năng', 'Số đo từ các thiết bị của bạn'),
      Text('CÔNG SUẤT THIẾT BỊ',
          style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Theme.of(context).colorScheme.onSurfaceVariant)),
      const SizedBox(height: 8),
      Text(metric(total, 'W'),
          style: const TextStyle(fontSize: 42, fontWeight: FontWeight.w700)),
      const SizedBox(height: 6),
      Text(
          '${values.length} thiết bị có số đo · ${client.connected ? 'Cập nhật gần nhất' : 'Dữ liệu cũ'}',
          style:
              TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
      const Padding(
          padding: EdgeInsets.symmetric(vertical: 18), child: Divider()),
      if (metered.isEmpty)
        const EmptyState(
            icon: Icons.electric_meter_outlined,
            title: 'Chưa có số đo điện',
            subtitle: 'Số đo xuất hiện khi Gateway nhận dữ liệu cảm biến.'),
      for (final entry in metered)
        Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Card(
                child: InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () => _openDevice(entry.key),
              child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(children: [
                          Expanded(
                              child: Text(
                                  nodeName(entry.key, asMap(entry.value)),
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w700))),
                          const Icon(Icons.chevron_right)
                        ]),
                        const SizedBox(height: 4),
                        Text(roomName('${asMap(entry.value)['room'] ?? ''}')),
                        if (asMap(entry.value)['status'] != 'online')
                          const Text('Ngoại tuyến · số đo cuối cùng'),
                        const SizedBox(height: 18),
                        MetricStrip(data: telemetry(asMap(entry.value))),
                      ])),
            ))),
    ]);
  }

  Widget _settings(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _heading('Cài đặt', 'Ngôi nhà & tài khoản'),
        ListTile(
            contentPadding: EdgeInsets.zero,
            leading: CircleAvatar(
                child: Icon(client.isAdmin
                    ? Icons.admin_panel_settings_outlined
                    : Icons.person_outline)),
            title: Text(
                '${client.user['fullname'] ?? client.user['username'] ?? 'Tài khoản'}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(client.isAdmin ? 'Quản trị viên' : 'Thành viên')),
        const SizedBox(height: 16),
        const Divider(),
        ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.router_outlined),
            title: const Text('Gateway'),
            subtitle: Text(client.serverUrl),
            trailing: Icon(
                client.connected
                    ? Icons.check_circle_outline
                    : Icons.error_outline,
                color: Theme.of(context).colorScheme.primary)),
        const SizedBox(height: 16),
        const Text('Giao diện', style: TextStyle(fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        SizedBox(
            width: double.infinity,
            child: SegmentedButton<ThemeMode>(
                selected: {appTheme.value},
                onSelectionChanged: (value) => appTheme.value = value.first,
                segments: const [
                  ButtonSegment(
                      value: ThemeMode.system,
                      icon: Icon(Icons.brightness_auto_outlined),
                      label: Text('Tự động')),
                  ButtonSegment(
                      value: ThemeMode.light,
                      icon: Icon(Icons.light_mode_outlined),
                      label: Text('Sáng')),
                  ButtonSegment(
                      value: ThemeMode.dark,
                      icon: Icon(Icons.dark_mode_outlined),
                      label: Text('Tối'))
                ])),
        const SizedBox(height: 20),
        const Divider(),
        if (client.isAdmin) ...[
          ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.add_link_rounded),
              title: const Text('Thêm thiết bị'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => ManageScreen(client: client)))),
          ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.system_update_outlined),
              title: const Text('Firmware thiết bị'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => FirmwareScreen(client: client)))),
          const Divider(),
        ],
        const ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(Icons.info_outline),
            title: Text('SIC Home'),
            subtitle: Text('Phiên bản 1.1.0')),
        const SizedBox(height: 16),
        SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Đăng xuất / đổi Gateway'),
                onPressed: () async {
                  final confirmed = await showDialog<bool>(
                      context: context,
                      builder: (context) => AlertDialog(
                              title: const Text('Đăng xuất?'),
                              content: const Text(
                                  'Phiên đăng nhập trên điện thoại này sẽ được xóa.'),
                              actions: [
                                TextButton(
                                    onPressed: () =>
                                        Navigator.pop(context, false),
                                    child: const Text('Hủy')),
                                FilledButton(
                                    onPressed: () =>
                                        Navigator.pop(context, true),
                                    child: const Text('Đăng xuất')),
                              ]));
                  if (confirmed == true) await client.logout();
                })),
      ]);
}

class ResponsiveTiles extends StatelessWidget {
  const ResponsiveTiles({super.key, required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) =>
      LayoutBuilder(builder: (context, constraints) {
        final scale = MediaQuery.textScalerOf(context).scale(14) / 14;
        final columns = constraints.maxWidth >= 720
            ? 3
            : constraints.maxWidth >= 330 && scale < 1.3
                ? 2
                : 1;
        final width = (constraints.maxWidth - 12 * (columns - 1)) / columns;
        return Wrap(
            spacing: 12,
            runSpacing: 12,
            children: children
                .map((child) => SizedBox(width: width, child: child))
                .toList());
      });
}

class RelayTile extends StatefulWidget {
  const RelayTile(
      {super.key,
      required this.client,
      required this.nodeId,
      required this.channel,
      this.favorite = false,
      this.onFavorite,
      this.onDetails});
  final GatewayClient client;
  final String nodeId, channel;
  final bool favorite;
  final VoidCallback? onFavorite, onDetails;
  @override
  State<RelayTile> createState() => _RelayTileState();
}

class _RelayTileState extends State<RelayTile> {
  bool _busy = false;
  Future<void> _toggle(bool value) async {
    setState(() => _busy = true);
    try {
      final result =
          await widget.client.relay(widget.nodeId, widget.channel, value);
      if (!mounted) return;
      final message = switch (result['verify']) {
        'confirmed_load' =>
          'Đã ${value ? 'bật' : 'tắt'} · đã xác minh tải điện',
        'ack_only' =>
          'Thiết bị đã xác nhận ${value ? 'bật' : 'tắt'} · chưa xác minh tải điện',
        'timeout' =>
          'Chưa nhận được xác nhận. Hãy kiểm tra trạng thái thiết bị.',
        _ => 'Thiết bị chưa xác nhận lệnh. Vui lòng kiểm tra lại.',
      };
      showMessage(context, message);
    } catch (e) {
      if (mounted) showMessage(context, e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final node = asMap(widget.client.nodes[widget.nodeId]);
    final ch = asMap(node['channels'])[widget.channel];
    final on = relayState(node, widget.channel);
    final online = widget.client.connected && node['status'] == 'online';
    final colors = Theme.of(context).colorScheme;
    final name = channelName(widget.channel, ch);
    final type = '${asMap(ch)['device_type'] ?? ch}';
    return Card(
      color: on == true && online
          ? colors.primaryContainer.withValues(alpha: .45)
          : null,
      child: Padding(
          padding: const EdgeInsets.all(14),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                      color: on == true
                          ? colors.primary
                          : colors.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(8)),
                  child: Icon(deviceIcon(type),
                      color: on == true
                          ? colors.onPrimary
                          : colors.onSurfaceVariant,
                      size: 24)),
              const Spacer(),
              if (widget.onFavorite != null)
                IconButton(
                    tooltip: widget.favorite ? 'Bỏ yêu thích' : 'Yêu thích',
                    onPressed: widget.onFavorite,
                    icon: Icon(
                        widget.favorite
                            ? Icons.star_rounded
                            : Icons.star_outline_rounded,
                        size: 21),
                    color: widget.favorite
                        ? const Color(0xFFB37A18)
                        : colors.onSurfaceVariant),
            ]),
            const SizedBox(height: 14),
            Text(name,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style:
                    const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(roomName('${node['room'] ?? ''}'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: colors.onSurfaceVariant, fontSize: 12)),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                  child: Text(
                      _busy
                          ? 'Đang gửi...'
                          : !online
                              ? 'Ngoại tuyến'
                              : on == null
                                  ? 'Chưa rõ'
                                  : on
                                      ? 'Đang bật'
                                      : 'Đã tắt',
                      style: TextStyle(
                          color: online && on == true
                              ? colors.primary
                              : colors.onSurfaceVariant,
                          fontWeight: FontWeight.w600,
                          fontSize: 12))),
              Semantics(
                  label: '$name ${roomName('${node['room'] ?? ''}')}',
                  child: Switch(
                      value: on ?? false,
                      onChanged:
                          online && !_busy && on != null ? _toggle : null)),
            ]),
            if (widget.onDetails != null)
              SizedBox(
                  width: double.infinity,
                  child: TextButton(
                      onPressed: widget.onDetails,
                      child: const Text('Chi tiết'))),
          ])),
    );
  }
}

class MetricStrip extends StatelessWidget {
  const MetricStrip({super.key, required this.data});
  final Map<String, dynamic> data;
  @override
  Widget build(BuildContext context) =>
      Wrap(spacing: 24, runSpacing: 16, children: [
        for (final entry in {
          'Công suất': metric(data['power'] ?? data['p'], 'W'),
          'Điện áp': metric(data['voltage'] ?? data['v'], 'V'),
          'Dòng điện':
              metric(data['current'] ?? data['i'] ?? data['c'], 'A', 2),
          'Tích lũy': metric(data['energy'] ?? data['e'], 'kWh', 2),
        }.entries)
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(entry.key,
                style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 4),
            Text(entry.value,
                style:
                    const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          ]),
      ]);
}

class EmptyState extends StatelessWidget {
  const EmptyState(
      {super.key,
      required this.icon,
      required this.title,
      required this.subtitle});
  final IconData icon;
  final String title, subtitle;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 16),
      child: Center(
          child: Column(children: [
        Icon(icon, size: 42, color: Theme.of(context).colorScheme.outline),
        const SizedBox(height: 16),
        Text(title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(subtitle,
            textAlign: TextAlign.center,
            style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant)),
      ])));
}
