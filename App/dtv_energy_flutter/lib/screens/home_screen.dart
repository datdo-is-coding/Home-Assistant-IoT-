import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../main.dart' show appTheme;
import '../services/gateway_client.dart';
import 'device_screen.dart';
import 'manage_screen.dart';
import '../widgets/huawei_boot_screen.dart';

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

Color deviceColor(String type, {bool isDark = true}) =>
    switch (type.toLowerCase()) {
      'light' ||
      'lamp' =>
        isDark ? const Color(0xFFF59E0B) : const Color(0xFFD97706),
      'fan' => isDark ? const Color(0xFF0EA5E9) : const Color(0xFF0284C7),
      'ac' ||
      'air_conditioner' =>
        isDark ? const Color(0xFF38BDF8) : const Color(0xFF0369A1),
      'pump' => isDark ? const Color(0xFF14B8A6) : const Color(0xFF0D9488),
      'switch' ||
      'outlet' =>
        isDark ? const Color(0xFF10B981) : const Color(0xFF059669),
      _ => isDark ? const Color(0xFF8B5CF6) : const Color(0xFF7C3AED),
    };

String channelName(String channel, dynamic info) {
  final data = asMap(info);
  final raw = data['name'] ?? data['description'];
  if (raw != null && raw.toString().trim().isNotEmpty) {
    final s = raw.toString().trim();
    final lower = s.toLowerCase();
    if (lower == 'light' || lower == 'lamp') return 'Đèn';
    if (lower == 'fan') return 'Quạt';
    if (lower == 'pump') return 'Máy bơm';
    if (lower == 'ac' || lower == 'air_conditioner') return 'Điều hòa';
    if (lower == 'switch') return 'Công tắc';
    final mLight = RegExp(r'^(light|lamp)[_\s]+(\d+)$', caseSensitive: false).firstMatch(s);
    if (mLight != null) return 'Đèn ${mLight.group(2)}';
    final mFan = RegExp(r'^fan[_\s]+(\d+)$', caseSensitive: false).firstMatch(s);
    if (mFan != null) return 'Quạt ${mFan.group(2)}';
    final mPump = RegExp(r'^pump[_\s]+(\d+)$', caseSensitive: false).firstMatch(s);
    if (mPump != null) return 'Máy bơm ${mPump.group(2)}';
    return s;
  }
  final devType = '${data['device_type'] ?? info}'.toLowerCase();
  return switch (devType) {
    'light' || 'lamp' => 'Đèn',
    'fan' => 'Quạt',
    'pump' => 'Máy bơm',
    'ac' || 'air_conditioner' => 'Điều hòa',
    'switch' => 'Công tắc',
    _ => const {'ch1': 'Kênh 1', 'ch2': 'Kênh 2'}[channel] ?? channel.toUpperCase(),
  };
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
    if (mounted) {
      setState(() => _favorites = (prefs.getStringList(
                  'sic_favorites_${client.serverUrl}_${client.user['id']}') ??
              [])
          .toSet());
    }
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
    final colors = Theme.of(context).colorScheme;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final rooms = client.nodes.values
        .map((n) => '${asMap(n)['room'] ?? ''}')
        .toSet()
        .toList()
      ..sort();
    if (_room != null && !rooms.contains(_room)) _room = null;
    return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        child: Row(children: [
          _roomFilterChip(
            label: 'Tất cả',
            count: client.nodes.length,
            selected: _room == null,
            onSelected: () => setState(() => _room = null),
            colors: colors,
            isDark: isDark,
          ),
          for (final room in rooms)
            _roomFilterChip(
              label: roomName(room),
              count: client.nodes.values
                  .where((n) => '${asMap(n)['room'] ?? ''}' == room)
                  .length,
              selected: _room == room,
              onSelected: () => setState(() => _room = room),
              colors: colors,
              isDark: isDark,
            ),
        ]));
  }

  Widget _roomFilterChip({
    required String label,
    required int count,
    required bool selected,
    required VoidCallback onSelected,
    required ColorScheme colors,
    required bool isDark,
  }) {
    final activeBg = isDark ? Colors.white : const Color(0xFF1E2430);
    final activeFg = isDark ? const Color(0xFF07090C) : Colors.white;
    final unselectedBg =
        isDark ? const Color(0xFF131720) : const Color(0xFFF1F3F7);
    final unselectedBorder =
        isDark ? const Color(0xFF222836) : const Color(0xFFE2E6EC);

    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onSelected,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: selected ? activeBg : unselectedBg,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selected ? activeBg : unselectedBorder,
              width: 1,
            ),
            boxShadow: selected
                ? [
                    BoxShadow(
                      color: isDark
                          ? Colors.white.withValues(alpha: 0.12)
                          : const Color(0xFF1E2430).withValues(alpha: 0.15),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    )
                  ]
                : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: TextStyle(
                  color: selected
                      ? activeFg
                      : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF334155)),
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
                  fontSize: 13,
                  letterSpacing: 0.1,
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
                decoration: BoxDecoration(
                  color: selected
                      ? (isDark
                          ? Colors.black.withValues(alpha: 0.15)
                          : Colors.white.withValues(alpha: 0.2))
                      : (isDark
                          ? const Color(0xFF1E2430)
                          : const Color(0xFFE2E6EC)),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  '$count',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: selected
                        ? activeFg
                        : (isDark ? const Color(0xFF94A3B8) : const Color(0xFF334155)),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
            relayState(node, ch) == true) {
          active++;
        }
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
      Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'HỆ THỐNG NHÀ THÔNG MINH',
                  style: TextStyle(
                    color: colors.onSurfaceVariant,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.4,
                  ),
                ),
                const SizedBox(height: 3),
                Builder(builder: (context) {
                  final isDark = Theme.of(context).brightness == Brightness.dark;
                  final rawFullname = client.user['fullname']?.toString().trim();
                  String name = 'Không gian sống';
                  if (rawFullname != null && rawFullname.isNotEmpty) {
                    name = rawFullname
                        .replaceAll(RegExp(r'\s*\((Admin|Thành viên|User)\)', caseSensitive: false), '')
                        .trim();
                    if (name.isEmpty) name = rawFullname;
                    name = 'Xin chào, $name';
                  }
                  return Row(
                    children: [
                      Flexible(
                        child: Text(
                          name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.4,
                            color: colors.onSurface,
                          ),
                        ),
                      ),
                      if (client.isAdmin) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: isDark ? const Color(0xFF1E2430) : const Color(0xFFE2E6EC),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            'ADMIN',
                            style: TextStyle(
                              fontSize: 9,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.8,
                              color: isDark ? const Color(0xFFE2E8F0) : const Color(0xFF334155),
                            ),
                          ),
                        ),
                      ],
                    ],
                  );
                }),
              ],
            ),
          ),
          Builder(builder: (context) {
            final isDark = Theme.of(context).brightness == Brightness.dark;
            final statusColor =
                client.connected ? const Color(0xFF10B981) : colors.error;
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: isDark ? 0.12 : 0.08),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: statusColor.withValues(alpha: 0.35),
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: statusColor,
                      boxShadow: [
                        BoxShadow(
                          color: statusColor.withValues(alpha: 0.75),
                          blurRadius: 5,
                          spreadRadius: 1,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    client.connected ? 'Trực tuyến' : 'Ngoại tuyến',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.2,
                      color: statusColor,
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
      const SizedBox(height: 16),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: colors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: client.connected
                ? colors.outlineVariant.withValues(alpha: 0.9)
                : colors.error.withValues(alpha: 0.4),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Theme.of(context).brightness == Brightness.dark
                  ? Colors.black.withValues(alpha: 0.3)
                  : Colors.black.withValues(alpha: 0.03),
              blurRadius: 16,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    client.connected
                        ? 'GATEWAY TRỰC TUYẾN'
                        : 'MẤT KẾT NỐI GATEWAY',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                      color: client.connected
                          ? (Theme.of(context).brightness == Brightness.dark
                              ? const Color(0xFFE2E8F0)
                              : const Color(0xFF0F1318))
                          : colors.error,
                    ),
                  ),
                ),
                if (client.updatedAt != null)
                  Text(
                    TimeOfDay.fromDateTime(client.updatedAt!).format(context),
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: colors.onSurfaceVariant,
                      letterSpacing: 0.2,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                _bentoStat(
                  label: 'Trực tuyến',
                  value: '$online/${client.nodes.length}',
                  icon: Icons.wifi_tethering_rounded,
                  color: const Color(0xFF10B981),
                  isDark: Theme.of(context).brightness == Brightness.dark,
                ),
                const SizedBox(width: 8),
                _bentoStat(
                  label: 'Đang bật',
                  value: '$active',
                  icon: Icons.bolt_rounded,
                  color: const Color(0xFFF59E0B),
                  isDark: Theme.of(context).brightness == Brightness.dark,
                ),
                const SizedBox(width: 8),
                _bentoStat(
                  label: 'Khu vực',
                  value: '$rooms',
                  icon: Icons.meeting_room_outlined,
                  color: const Color(0xFF8B5CF6),
                  isDark: Theme.of(context).brightness == Brightness.dark,
                ),
              ],
            ),
          ],
        ),
      ),

      const SizedBox(height: 20),
      _rooms(),
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Text(
                'Điều khiển nhanh',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                  color: colors.onSurface,
                ),
              ),
            ),
            IconButton(
              tooltip: _favoritesOnly ? 'Hiện tất cả' : 'Chỉ yêu thích',
              onPressed: () => setState(() => _favoritesOnly = !_favoritesOnly),
              icon: Icon(
                _favoritesOnly
                    ? Icons.star_rounded
                    : Icons.star_outline_rounded,
                color: _favoritesOnly
                    ? const Color(0xFFF59E0B)
                    : colors.onSurfaceVariant.withValues(alpha: 0.5),
              ),
            ),
          ],
        ),
      ),
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


  Widget _bentoStat({
    required String label,
    required String value,
    required IconData icon,
    required Color color,
    required bool isDark,
  }) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF141822) : const Color(0xFFF4F6F9),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isDark ? const Color(0xFF222836) : const Color(0xFFE2E6EC),
            width: 0.8,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(3.5),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: isDark ? 0.20 : 0.12),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(icon, size: 12, color: color),
                ),
                const Spacer(),
                Text(
                  value,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.3,
                    color: isDark ? Colors.white : const Color(0xFF0F1318),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }


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
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
                side: BorderSide(
                  color: Theme.of(context).colorScheme.outlineVariant,
                  width: 1,
                ),
              ),
              child: ListTile(
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                leading: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: asMap(entry.value)['status'] == 'online'
                        ? const Color(0xFF0EA5E9).withValues(
                            alpha:
                                Theme.of(context).brightness == Brightness.dark
                                    ? 0.16
                                    : 0.10)
                        : (Theme.of(context).brightness == Brightness.dark
                            ? const Color(0xFF161A22)
                            : const Color(0xFFEFF1F5)),
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: asMap(entry.value)['status'] == 'online'
                          ? const Color(0xFF0EA5E9).withValues(alpha: 0.35)
                          : Theme.of(context).colorScheme.outlineVariant,
                      width: 1,
                    ),
                  ),
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Icon(
                        Icons.developer_board_rounded,
                        size: 22,
                        color: asMap(entry.value)['status'] == 'online'
                            ? const Color(0xFF0EA5E9)
                            : Theme.of(context).colorScheme.outline,
                      ),
                      Positioned(
                        right: 8,
                        bottom: 8,
                        child: Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: asMap(entry.value)['status'] == 'online'
                                ? const Color(0xFF10B981)
                                : const Color(0xFF94A3B8),
                            boxShadow: asMap(entry.value)['status'] == 'online'
                                ? [
                                    const BoxShadow(
                                      color: Color(0xFF10B981),
                                      blurRadius: 5,
                                      spreadRadius: 1,
                                    ),
                                  ]
                                : null,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                title: Text(
                  nodeName(entry.key, asMap(entry.value)),
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                    letterSpacing: -0.2,
                  ),
                ),
                subtitle: Text(
                  '${roomName('${asMap(entry.value)['room'] ?? ''}')} · ${asMap(entry.value)['status'] == 'online' ? 'Trực tuyến' : 'Ngoại tuyến'}',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: asMap(entry.value)['status'] == 'online'
                        ? (Theme.of(context).brightness == Brightness.dark
                            ? const Color(0xFF34D399)
                            : const Color(0xFF059669))
                        : Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
                trailing: Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Theme.of(context).brightness == Brightness.dark
                        ? const Color(0xFF161A22)
                        : const Color(0xFFEFF1F5),
                  ),
                  child: const Icon(Icons.chevron_right, size: 18),
                ),
                onTap: () => _openDevice(entry.key),
              ),
            ),
          ),
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
      Row(
        children: [
          Container(
            padding: const EdgeInsets.all(3),
            decoration: BoxDecoration(
              color: const Color(0xFFF59E0B).withValues(
                  alpha: Theme.of(context).brightness == Brightness.dark
                      ? 0.16
                      : 0.12),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.bolt_rounded,
                size: 14, color: Color(0xFFF59E0B)),
          ),
          const SizedBox(width: 6),
          Text('CÔNG SUẤT THIẾT BỊ',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ],
      ),
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
                    ? Icons.check_circle_rounded
                    : Icons.error_outline_rounded,
                color: client.connected
                    ? const Color(0xFF10B981)
                    : Theme.of(context).colorScheme.error)),
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
        const SizedBox(height: 16),
        ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Container(
              width: 38,
              height: 38,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  colors: [
                    Color(0xFF00E5FF),
                    Color(0xFFFBBF24),
                    Color(0xFFA855F7),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              child: const Icon(Icons.motion_photos_on_rounded,
                  size: 18, color: Colors.white),
            ),
            title: const Text('Hiệu ứng ánh sáng khởi động'),
            subtitle: const Text('Xem lại hiệu ứng vòng sáng quang học'),
            trailing: const Icon(Icons.play_circle_outline_rounded),
            onTap: () => Navigator.of(context).push(PageRouteBuilder(
                opaque: false,
                pageBuilder: (context, _, __) => HuaweiBootScreen(
                    onComplete: () => Navigator.of(context).pop(),
                    allowSkip: true)))),
        const SizedBox(height: 16),
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
    final type = '${asMap(ch)['device_type'] ?? ch}'.toLowerCase();

    final bool isDark = Theme.of(context).brightness == Brightness.dark;
    final bool isActive = on == true && online;
    final bool isSwitchActive = online && (on == true);
    final Color devColor = deviceColor(type, isDark: isDark);

    return Container(
      decoration: BoxDecoration(
        color: isActive
            ? (isDark ? const Color(0xFF141923) : Colors.white)
            : (isDark ? const Color(0xFF12151D) : Colors.white),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isActive
              ? devColor.withValues(alpha: isDark ? 0.38 : 0.48)
              : (isDark
                  ? const Color(0xFF1E2532)
                  : const Color(0xFFE2E8F0)),
          width: isActive ? 1.2 : 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: isActive
                ? devColor.withValues(alpha: isDark ? 0.14 : 0.08)
                : (isDark
                    ? Colors.black.withValues(alpha: 0.25)
                    : Colors.black.withValues(alpha: 0.03)),
            blurRadius: isActive ? 16 : 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: widget.onDetails,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          color: isActive
                              ? devColor.withValues(alpha: isDark ? 0.22 : 0.14)
                              : (isDark
                                  ? const Color(0xFF1C2230)
                                  : const Color(0xFFF1F5F9)),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: isActive
                                ? devColor.withValues(alpha: 0.5)
                                : colors.outlineVariant.withValues(alpha: 0.35),
                            width: 1,
                          ),
                        ),
                        child: Icon(
                          deviceIcon(type),
                          color: isActive
                              ? devColor
                              : (isDark
                                  ? const Color(0xFF94A3B8)
                                  : const Color(0xFF64748B)),
                          size: 20,
                        ),
                      ),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (widget.onFavorite != null)
                            IconButton(
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(
                                minWidth: 30,
                                minHeight: 30,
                              ),
                              tooltip: widget.favorite
                                  ? 'Bỏ yêu thích'
                                  : 'Yêu thích',
                              onPressed: widget.onFavorite,
                              icon: Icon(
                                widget.favorite
                                    ? Icons.star_rounded
                                    : Icons.star_outline_rounded,
                                size: 19,
                                color: widget.favorite
                                    ? const Color(0xFFF59E0B)
                                    : (isDark
                                        ? const Color(0xFF475569)
                                        : const Color(0xFF94A3B8)),
                              ),
                            ),
                          if (widget.onDetails != null) ...[
                            const SizedBox(width: 4),
                            Icon(
                              Icons.chevron_right_rounded,
                              size: 18,
                              color: isDark
                                  ? const Color(0xFF475569)
                                  : const Color(0xFF94A3B8),
                            ),
                          ],
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.2,
                      color: colors.onSurface,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    roomName('${node['room'] ?? ''}'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: colors.onSurfaceVariant,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Row(
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              margin: const EdgeInsets.only(right: 6),
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: !online
                                    ? (isDark
                                        ? const Color(0xFF475569)
                                        : const Color(0xFF94A3B8))
                                    : (isActive
                                        ? devColor
                                        : (isDark
                                            ? const Color(0xFF475569)
                                            : const Color(0xFF94A3B8))),
                                boxShadow: isActive
                                    ? [
                                        BoxShadow(
                                          color: devColor.withValues(alpha: 0.8),
                                          blurRadius: 5,
                                          spreadRadius: 1,
                                        )
                                      ]
                                    : null,
                              ),
                            ),
                            Expanded(
                              child: Text(
                                _busy
                                    ? (on == true ? 'Đang bật...' : 'Đang tắt...')
                                    : !online
                                        ? 'Ngoại tuyến'
                                        : on == null
                                            ? 'Chưa rõ'
                                            : on
                                                ? 'Đang bật'
                                                : 'Đã tắt',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: isActive
                                      ? devColor
                                      : colors.onSurfaceVariant,
                                  fontWeight: isActive
                                      ? FontWeight.w700
                                      : FontWeight.w600,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      Semantics(
                        label: '$name ${roomName('${node['room'] ?? ''}')}',
                        child: Transform.scale(
                          scale: 0.82,
                          alignment: Alignment.centerRight,
                          child: Switch(
                            value: isSwitchActive,
                            activeThumbColor: Colors.white,
                            activeTrackColor: devColor,
                            inactiveThumbColor: isDark
                                ? const Color(0xFF64748B)
                                : const Color(0xFF94A3B8),
                            inactiveTrackColor: isDark
                                ? const Color(0xFF1E2430)
                                : const Color(0xFFE2E8F0),
                            onChanged:
                                online && !_busy && on != null ? _toggle : null,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class MetricStrip extends StatelessWidget {
  const MetricStrip({super.key, required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cellBg = isDark ? const Color(0xFF13171F) : const Color(0xFFF1F3F6);
    final border = isDark ? const Color(0xFF1F2430) : const Color(0xFFE2E6EC);

    final metrics = [
      (
        key: 'Công suất',
        value: metric(data['power'] ?? data['p'], 'W'),
        icon: Icons.bolt_rounded,
        color: isDark ? const Color(0xFFF59E0B) : const Color(0xFFD97706),
      ),
      (
        key: 'Điện áp',
        value: metric(data['voltage'] ?? data['v'], 'V'),
        icon: Icons.speed_rounded,
        color: isDark ? const Color(0xFF0EA5E9) : const Color(0xFF0284C7),
      ),
      (
        key: 'Dòng điện',
        value: metric(data['current'] ?? data['i'] ?? data['c'], 'A', 2),
        icon: Icons.waves_rounded,
        color: isDark ? const Color(0xFF8B5CF6) : const Color(0xFF7C3AED),
      ),
      (
        key: 'Tích lũy',
        value: metric(data['energy'] ?? data['e'], 'kWh', 2),
        icon: Icons.hourglass_bottom_rounded,
        color: isDark ? const Color(0xFF10B981) : const Color(0xFF059669),
      ),
    ];

    return LayoutBuilder(builder: (context, constraints) {
      final width = (constraints.maxWidth - 12) / 2;
      return Wrap(
        spacing: 12,
        runSpacing: 10,
        children: [
          for (final item in metrics)
            Container(
              width: width > 130 ? width : constraints.maxWidth,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: cellBg,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: border, width: 1),
              ),
              child: Row(
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      color: item.color.withValues(alpha: isDark ? 0.16 : 0.12),
                      shape: BoxShape.circle,
                      border: Border.all(
                        color:
                            item.color.withValues(alpha: isDark ? 0.35 : 0.25),
                        width: 1,
                      ),
                    ),
                    child: Icon(item.icon, size: 17, color: item.color),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          item.key,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: colors.onSurfaceVariant,
                            letterSpacing: 0.2,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          item.value,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.2,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      );
    });
  }
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
