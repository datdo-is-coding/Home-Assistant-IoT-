import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/gateway_client.dart';
import '../../widgets/home_connection_name.dart';
import '../../widgets/soft_3d_decorations.dart';
import '../../widgets/app_update_tile.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  bool _showEngineering = false;
  String _homeName = 'My Home';

  @override
  void initState() {
    super.initState();
    _loadHomeName();
    _loadAccess();
  }

  Future<void> _loadAccess() async {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.usesFirebase) return;
    try {
      await gateway.request('/api/commissioning/context');
      if (mounted) setState(() {});
    } catch (_) {
      // Offline settings remain usable; device management still verifies on the Gateway.
    }
  }

  Future<void> _loadHomeName() async {
    final gateway = ref.read(gatewayClientProvider);
    final saved = await ref.read(appPreferencesServiceProvider).loadHomeName(
          gatewayUrl: gateway.serverUrl,
          userId: gateway.currentUserId,
        );
    if (mounted) {
      setState(() => _homeName = saved);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final themeMode = ref.watch(themeModeProvider);
    final gateway = ref.read(gatewayClientProvider);
    ref.watch(gatewayClientProvider
        .select((c) => (c.connected, c.error, c.usesFirebase)));
    final iconColor = theme.colorScheme.onSurfaceVariant;
    final appVersion = ref
        .watch(appUpdateProvider.select((update) => update.installedVersion));

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
          child: CustomScrollView(
        physics: const BouncingScrollPhysics(),
        slivers: [
          const SliverPadding(
            padding: EdgeInsets.fromLTRB(20, 16, 20, 12),
            sliver: SliverToBoxAdapter(
                child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Cài đặt',
                    style: TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.w600,
                        letterSpacing: -0.9)),
                HomeConnectionName(),
              ],
            )),
          ),
          _buildSectionHeader('Giao diện'),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            sliver: SliverToBoxAdapter(
                child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SegmentedButton<ThemeMode>(
                segments: const [
                  ButtonSegment(
                      value: ThemeMode.light,
                      label: Text('Sáng'),
                      icon: Icon(Icons.light_mode_rounded, size: 16)),
                  ButtonSegment(
                      value: ThemeMode.dark,
                      label: Text('Tối'),
                      icon: Icon(Icons.dark_mode_rounded, size: 16)),
                  ButtonSegment(
                      value: ThemeMode.system,
                      label: Text('Hệ thống'),
                      icon: Icon(Icons.settings_suggest_rounded, size: 16)),
                ],
                selected: {themeMode},
                onSelectionChanged: (selection) {
                  HapticFeedback.selectionClick();
                  ref.read(themeModeProvider.notifier).state = selection.first;
                },
              ),
            )),
          ),
          _buildSectionHeader('Ngôi nhà'),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            sliver: SliverToBoxAdapter(
                child: _SettingsGroup(children: [
              _SettingsTile(
                  icon: Icons.home_rounded,
                  iconColor: iconColor,
                  title: 'Tên ngôi nhà',
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => _showEditHomeNameDialog(context)),
              const Divider(height: 1, indent: 56),
              _SettingsTile(
                  icon: Icons.meeting_room_rounded,
                  iconColor: iconColor,
                  title: 'Phòng',
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => context.push('/devices')),
              const Divider(height: 1, indent: 56),
              _SettingsTile(
                  icon: Icons.record_voice_over_rounded,
                  iconColor: iconColor,
                  title: 'Giọng nói',
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => context.push('/voice')),
            ])),
          ),
          _buildSectionHeader('Ứng dụng'),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            sliver: SliverToBoxAdapter(
                child: _SettingsGroup(children: [
              _SettingsTile(
                  icon: Icons.person_rounded,
                  iconColor: iconColor,
                  title: 'Tài khoản',
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => _showUserAccountSheet(context, gateway)),
              const Divider(height: 1, indent: 56),
              _SettingsTile(
                  icon: Icons.notifications_none_rounded,
                  iconColor: iconColor,
                  title: 'Thông báo',
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => showDialog<void>(
                      context: context,
                      builder: (dialogContext) => AlertDialog(
                            title: const Text('Thông báo'),
                            content: const Text(
                                'Cảnh báo hiển thị trong ứng dụng. Chưa hỗ trợ thông báo đẩy khi ứng dụng ở nền.'),
                            actions: [
                              TextButton(
                                  onPressed: () => Navigator.pop(dialogContext),
                                  child: const Text('Đóng'))
                            ],
                          ))),
              const Divider(height: 1, indent: 56),
              const AppUpdateTile(),
              const Divider(height: 1, indent: 56),
              _SettingsTile(
                  icon: Icons.info_outline_rounded,
                  iconColor: iconColor,
                  title: 'HomeCompetition',
                  trailing:
                      Text(appVersion, style: const TextStyle(fontSize: 12)),
                  onTap: () => showAboutDialog(
                        context: context,
                        applicationName: 'HomeCompetition',
                        applicationVersion: appVersion,
                        children: [
                          const Text(
                              'Trạng thái được đồng bộ qua Firebase. Giọng nói được xử lý tại Gateway.')
                        ],
                      )),
            ])),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
            sliver: SliverToBoxAdapter(
                child: _SettingsGroup(children: [
              _SettingsTile(
                  icon: Icons.tune_rounded,
                  iconColor: iconColor,
                  title: 'Nâng cao',
                  trailing: Icon(_showEngineering
                      ? Icons.expand_less_rounded
                      : Icons.expand_more_rounded),
                  onTap: () =>
                      setState(() => _showEngineering = !_showEngineering)),
              if (_showEngineering) ...[
                const Divider(height: 1),
                _SettingsTile(
                    icon: Icons.cloud_outlined,
                    iconColor: iconColor,
                    title: 'Kết nối',
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => _showGatewayInfoSheet(context, gateway)),
                _SettingsTile(
                    icon: Icons.terminal_rounded,
                    iconColor: iconColor,
                    title: 'Nhật ký',
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => _showPacketLogSheet(context, gateway)),
                _SettingsTile(
                    icon: Icons.refresh_rounded,
                    iconColor: iconColor,
                    title: 'Đồng bộ lại',
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () async {
                      try {
                        await gateway.refresh();
                        if (context.mounted)
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                                content: Text(gateway.error ??
                                    (gateway.connected
                                        ? 'Đã đồng bộ.'
                                        : 'Chưa kết nối được.'))),
                          );
                      } catch (e) {
                        if (context.mounted)
                          ScaffoldMessenger.of(context)
                              .showSnackBar(SnackBar(content: Text('$e')));
                      }
                    }),
              ],
            ])),
          ),
        ],
      )),
    );
  }

  void _showEditHomeNameDialog(BuildContext context) {
    final ctrl = TextEditingController(text: _homeName);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Đổi tên ngôi nhà'),
        content: TextField(
          controller: ctrl,
          decoration: InputDecoration(
            labelText: 'Tên ngôi nhà',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
          ),
        ),
        actions: [
          TextButton(
            style: TextButton.styleFrom(minimumSize: const Size(64, 48)),
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size(64, 48)),
            onPressed: () {
              final newName = ctrl.text.trim();
              if (newName.isNotEmpty) {
                setState(() => _homeName = newName);
                ref.read(homeNameProvider.notifier).updateHomeName(newName);
                final gateway = ref.read(gatewayClientProvider);
                ref.read(appPreferencesServiceProvider).saveHomeName(
                      newName,
                      gatewayUrl: gateway.serverUrl,
                      userId: gateway.currentUserId,
                    );
              }
              Navigator.pop(ctx);
            },
            child: const Text('Lưu'),
          ),
        ],
      ),
    );
  }

  void _showUserAccountSheet(BuildContext context, GatewayClient gateway) {
    final theme = Theme.of(context);
    final user = gateway.user;

    showModalBottomSheet(
      context: context,
      useRootNavigator: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Tài khoản người dùng',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: theme.colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 16),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: CircleAvatar(
                  backgroundColor: theme.colorScheme.primary.withOpacity(0.12),
                  child: Icon(Icons.person_rounded,
                      color: theme.colorScheme.primary),
                ),
                title: Text(
                  user['username']?.toString() ?? 'Tài khoản Gateway',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(gateway.isAdmin ? 'Quản trị nhà' : 'Thành viên'),
                trailing: gateway.usesFirebase
                    ? IconButton(
                        tooltip: 'Cập nhật quyền',
                        onPressed: _loadAccess,
                        icon: const Icon(Icons.refresh_rounded))
                    : null,
              ),
              const Divider(height: 24),
              Text(
                'Trạng thái phiên: ${gateway.authenticated ? "Đã đăng nhập" : "Chưa xác thực"}',
                style: TextStyle(
                    fontSize: 13, color: theme.colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.error,
                    side: BorderSide(
                        color: theme.colorScheme.error.withOpacity(0.4)),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                  ),
                  icon: const Icon(Icons.logout_rounded),
                  label: const Text('Đăng xuất'),
                  onPressed: () {
                    Navigator.pop(ctx);
                    gateway.logout();
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showGatewayInfoSheet(BuildContext context, GatewayClient gateway) {
    final theme = Theme.of(context);

    showModalBottomSheet(
      context: context,
      useRootNavigator: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Máy chủ Gateway IoT',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: (gateway.connected
                              ? const Color(0xFF43A047)
                              : const Color(0xFFE53935))
                          .withOpacity(0.12),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      gateway.connected ? 'Đang kết nối' : 'Ngoại tuyến',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: gateway.connected
                            ? const Color(0xFF43A047)
                            : const Color(0xFFE53935),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _buildInfoRow('Địa chỉ URL', gateway.serverUrl),
              _buildInfoRow(
                  'Thời gian cập nhật',
                  gateway.updatedAt != null
                      ? '${gateway.updatedAt!.hour}:${gateway.updatedAt!.minute.toString().padLeft(2, "0")}:${gateway.updatedAt!.second.toString().padLeft(2, "0")}'
                      : 'Chưa có'),
              _buildInfoRow(
                  'Số node trực tuyến', '${gateway.nodes.length} thiết bị'),
              _buildInfoRow('Thiết bị chờ ghép nối',
                  '${gateway.pending.length} thiết bị'),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16)),
                  ),
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Làm mới kết nối'),
                  onPressed: () async {
                    Navigator.pop(ctx);
                    await gateway.refresh();
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showPacketLogSheet(BuildContext context, GatewayClient gateway) {
    final theme = Theme.of(context);
    final nodesList = gateway.nodes.entries.toList();

    showModalBottomSheet(
      context: context,
      useRootNavigator: true,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.6,
        maxChildSize: 0.85,
        builder: (_, scrollController) => Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Nhật ký telemetry node',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                  Text(
                    '${nodesList.length} nodes',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Expanded(
                child: nodesList.isEmpty
                    ? const Center(
                        child: Text('Không có telemetry nào từ các node.'),
                      )
                    : ListView.builder(
                        controller: scrollController,
                        itemCount: nodesList.length,
                        itemBuilder: (context, index) {
                          final entry = nodesList[index];
                          final node = asMap(entry.value);
                          final pzem = asMap(node['pzem']).isNotEmpty
                              ? asMap(node['pzem'])
                              : asMap(node['last_telemetry']);
                          final power = readNumber(pzem['power']) ?? 0.0;
                          final voltage = readNumber(pzem['voltage']) ?? 0.0;
                          final relayState =
                              node['relay_state']?.toString() ?? '[0, 0]';

                          return Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.surfaceContainerHighest
                                  .withOpacity(0.3),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment:
                                      MainAxisAlignment.spaceBetween,
                                  children: [
                                    Text(
                                      entry.key,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w700,
                                          fontFamily: 'monospace'),
                                    ),
                                    Text(
                                      node['status']?.toString() ?? 'online',
                                      style: const TextStyle(
                                          fontSize: 11,
                                          color: Color(0xFF43A047),
                                          fontWeight: FontWeight.w700),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  'IP: ${node['ip'] ?? "N/A"} · MAC: ${node['mac'] ?? "N/A"}',
                                  style: TextStyle(
                                      fontSize: 11,
                                      color:
                                          theme.colorScheme.onSurfaceVariant),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Rơ-le: $relayState · Công suất: ${power.toStringAsFixed(1)}W · Điện áp: ${voltage.toStringAsFixed(1)}V',
                                  style: const TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                      fontFamily: 'monospace'),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(fontSize: 13, color: Colors.grey)),
          Text(value,
              style:
                  const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
      sliver: SliverToBoxAdapter(
        child: Text(
          title,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.2,
          ),
        ),
      ),
    );
  }
}

class _SettingsGroup extends StatelessWidget {
  final List<Widget> children;

  const _SettingsGroup({required this.children});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return DecoratedBox(
      decoration: Soft3DDecorations.card(isDark: isDark),
      child: Material(
        color: Colors.transparent,
        clipBehavior: Clip.antiAlias,
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        child: Column(children: children),
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final Widget? trailing;
  final VoidCallback onTap;

  const _SettingsTile({
    required this.icon,
    required this.iconColor,
    required this.title,
    this.trailing,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48),
        child: ListTile(
          onTap: onTap,
          minLeadingWidth: 24,
          minVerticalPadding: 12,
          leading: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: iconColor.withOpacity(0.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: iconColor, size: 20),
          ),
          title: Text(
            title,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          ),
          trailing: trailing,
        ),
      ),
    );
  }
}
