import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/gateway_client.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  bool _offlineAlerts = true;
  bool _sensorNotifications = true;
  bool _showEngineering = false;
  String _homeName = 'My Home';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final themeMode = ref.watch(themeModeProvider);
    final gateway = ref.watch(gatewayClientProvider);

    final roomsAsync = ref.watch(roomsStreamProvider);
    final actionBoxesAsync = ref.watch(actionBoxesStreamProvider);
    final devicesAsync = ref.watch(devicesStreamProvider);

    final rooms = roomsAsync.value ?? [];
    final actionBoxes = actionBoxesAsync.value ?? [];
    final devices = devicesAsync.value ?? [];
    final onlineCount = devices.where((d) => d.online).length;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: CustomScrollView(
          physics: const BouncingScrollPhysics(),
          slivers: [
            // Header
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Cài đặt',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Cấu hình nhà, phần cứng và kết nối Gateway',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // APPEARANCE SECTION
            _buildSectionHeader('Giao diện & Hiển thị'),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: _SettingsGroup(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Chế độ màu (Theme)',
                            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Gam màu trung tính ấm áp (Light) hoặc tối sang trọng (Dark)',
                            style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                          ),
                          const SizedBox(height: 14),
                          SegmentedButton<ThemeMode>(
                            segments: const [
                              ButtonSegment(
                                value: ThemeMode.light,
                                label: Text('Sáng'),
                                icon: Icon(Icons.light_mode_rounded, size: 16),
                              ),
                              ButtonSegment(
                                value: ThemeMode.dark,
                                label: Text('Tối'),
                                icon: Icon(Icons.dark_mode_rounded, size: 16),
                              ),
                              ButtonSegment(
                                value: ThemeMode.system,
                                label: Text('Hệ thống'),
                                icon: Icon(Icons.settings_suggest_rounded, size: 16),
                              ),
                            ],
                            selected: {themeMode},
                            onSelectionChanged: (Set<ThemeMode> newSelection) {
                              HapticFeedback.lightImpact();
                              ref.read(themeModeProvider.notifier).state = newSelection.first;
                            },
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // HOME MANAGEMENT
            _buildSectionHeader('Quản lý ngôi nhà'),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: _SettingsGroup(
                  children: [
                    _SettingsTile(
                      icon: Icons.home_rounded,
                      iconColor: const Color(0xFF1E88E5),
                      title: 'Tên ngôi nhà',
                      subtitle: _homeName,
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => _showEditHomeNameDialog(context),
                    ),
                    const Divider(height: 1, indent: 56),
                    _SettingsTile(
                      icon: Icons.meeting_room_rounded,
                      iconColor: const Color(0xFFFF9800),
                      title: 'Phòng và không gian',
                      subtitle: '${rooms.length} phòng đã cấu hình',
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => context.push('/devices'),
                    ),
                    const Divider(height: 1, indent: 56),
                    _SettingsTile(
                      icon: Icons.people_alt_rounded,
                      iconColor: const Color(0xFF00897B),
                      title: 'Tài khoản người dùng',
                      subtitle:
                          '${gateway.user['username'] ?? "Người dùng"} · ${gateway.user['role'] ?? "Thành viên"}',
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => _showUserAccountSheet(context, gateway),
                    ),
                  ],
                ),
              ),
            ),

            // HARDWARE & NETWORK
            _buildSectionHeader('Phần cứng & Trợ lý ảo'),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: _SettingsGroup(
                  children: [
                    _SettingsTile(
                      icon: Icons.developer_board_rounded,
                      iconColor: const Color(0xFF43A047),
                      title: 'Bộ điều khiển ActionBox',
                      subtitle:
                          '${actionBoxes.length} bộ điều khiển · $onlineCount thiết bị trực tuyến',
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => context.push('/devices'),
                    ),
                    const Divider(height: 1, indent: 56),
                    _SettingsTile(
                      icon: Icons.record_voice_over_rounded,
                      iconColor: const Color(0xFFD81B60),
                      title: 'Nhận diện giọng nói',
                      subtitle: 'Trợ lý ngoại tuyến Sherpa-ONNX',
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => context.push('/voice'),
                    ),
                    const Divider(height: 1, indent: 56),
                    _SettingsTile(
                      icon: Icons.router_rounded,
                      iconColor: const Color(0xFF5E35B1),
                      title: 'Máy chủ Gateway IoT',
                      subtitle: '${gateway.serverUrl} (HTTP / WS / MQTT)',
                      trailing: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: (gateway.connected
                                  ? const Color(0xFF43A047)
                                  : const Color(0xFFE53935))
                              .withOpacity(0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          gateway.connected ? 'Trực tuyến' : 'Mất kết nối',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: gateway.connected
                                ? const Color(0xFF43A047)
                                : const Color(0xFFE53935),
                          ),
                        ),
                      ),
                      onTap: () => _showGatewayInfoSheet(context, gateway),
                    ),
                  ],
                ),
              ),
            ),

            // NOTIFICATIONS
            _buildSectionHeader('Thông báo'),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: _SettingsGroup(
                  children: [
                    SwitchListTile(
                      secondary: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE53935).withOpacity(0.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.notification_important_rounded,
                            size: 20, color: Color(0xFFE53935)),
                      ),
                      title: const Text('Cảnh báo thiết bị mất mạng',
                          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                      subtitle: const Text('Nhận thông báo khi ActionBox ngắt kết nối',
                          style: TextStyle(fontSize: 12)),
                      value: _offlineAlerts,
                      onChanged: (val) {
                        HapticFeedback.lightImpact();
                        setState(() => _offlineAlerts = val);
                      },
                    ),
                    const Divider(height: 1, indent: 56),
                    SwitchListTile(
                      secondary: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFB8C00).withOpacity(0.12),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.sensors_rounded,
                            size: 20, color: Color(0xFFFB8C00)),
                      ),
                      title: const Text('Thông báo cảm biến',
                          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                      subtitle: const Text('Báo động mở cửa hoặc phát hiện bất thường',
                          style: TextStyle(fontSize: 12)),
                      value: _sensorNotifications,
                      onChanged: (val) {
                        HapticFeedback.lightImpact();
                        setState(() => _sensorNotifications = val);
                      },
                    ),
                  ],
                ),
              ),
            ),

            // ENGINEERING / ADVANCED
            _buildSectionHeader('Kỹ thuật & Cấu hình nâng cao'),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: _SettingsGroup(
                  children: [
                    _SettingsTile(
                      icon: Icons.code_rounded,
                      iconColor: theme.colorScheme.onSurfaceVariant,
                      title: _showEngineering
                          ? 'Thu gọn cài đặt kỹ thuật'
                          : 'Hiển thị tùy chọn kỹ sư',
                      subtitle: 'MQTT topics, trạng thái Gateway, nhật ký telemetry',
                      trailing: Icon(
                        _showEngineering ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                      ),
                      onTap: () => setState(() => _showEngineering = !_showEngineering),
                    ),
                    if (_showEngineering) ...[
                      const Divider(height: 1),
                      _SettingsTile(
                        icon: Icons.terminal_rounded,
                        iconColor: const Color(0xFF546E7A),
                        title: 'Nhật ký kết nối Gateway (Live Telemetry)',
                        subtitle:
                            'Đã ghi nhận ${gateway.nodes.length} nodes · ${gateway.pending.length} pending',
                        trailing: const Icon(Icons.chevron_right_rounded),
                        onTap: () => _showPacketLogSheet(context, gateway),
                      ),
                      const Divider(height: 1, indent: 56),
                      _SettingsTile(
                        icon: Icons.restart_alt_rounded,
                        iconColor: const Color(0xFFD32F2F),
                        title: 'Khởi động lại kết nối Gateway',
                        subtitle: 'Đồng bộ lại danh sách thiết bị và trạng thái rơ-le',
                        trailing: const Icon(Icons.chevron_right_rounded),
                        onTap: () async {
                          HapticFeedback.heavyImpact();
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Đang làm mới kết nối với Gateway...'),
                              duration: Duration(seconds: 1),
                            ),
                          );
                          try {
                            await ref.read(gatewayClientProvider).refresh();
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Đã cập nhật trạng thái Gateway thành công.'),
                                  backgroundColor: Color(0xFF43A047),
                                ),
                              );
                            }
                          } catch (e) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text('Lỗi kết nối Gateway: $e'),
                                  backgroundColor: theme.colorScheme.error,
                                ),
                              );
                            }
                          }
                        },
                      ),
                    ],
                  ],
                ),
              ),
            ),

            // ABOUT
            _buildSectionHeader('Thông tin ứng dụng'),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: _SettingsGroup(
                  children: [
                    _SettingsTile(
                      icon: Icons.info_outline_rounded,
                      iconColor: const Color(0xFF1E88E5),
                      title: 'Smart Home IoT Consumer Edition',
                      subtitle: 'Phiên bản 2.4.0 (Flutter & Riverpod)',
                      trailing: const Text('v2.4.0',
                          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                      onTap: () {},
                    ),
                    const Divider(height: 1, indent: 56),
                    _SettingsTile(
                      icon: Icons.verified_user_outlined,
                      iconColor: const Color(0xFF43A047),
                      title: 'Quyền riêng tư & Bảo mật',
                      subtitle: 'Xử lý dữ liệu hoàn toàn trong mạng cục bộ',
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () {},
                    ),
                  ],
                ),
              ),
            ),

            const SliverToBoxAdapter(child: SizedBox(height: 48)),
          ],
        ),
      ),
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
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () {
              final newName = ctrl.text.trim();
              if (newName.isNotEmpty) {
                setState(() => _homeName = newName);
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
                  child: Icon(Icons.person_rounded, color: theme.colorScheme.primary),
                ),
                title: Text(
                  user['username']?.toString() ?? 'Tài khoản Gateway',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text('Vai trò: ${user['role'] ?? "Quản trị viên"}'),
              ),
              const Divider(height: 24),
              Text(
                'Trạng thái phiên: ${gateway.authenticated ? "Đã đăng nhập" : "Chưa xác thực"}',
                style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.error,
                    side: BorderSide(color: theme.colorScheme.error.withOpacity(0.4)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
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
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: (gateway.connected ? const Color(0xFF43A047) : const Color(0xFFE53935))
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
              _buildInfoRow('Thời gian cập nhật',
                  gateway.updatedAt != null ? '${gateway.updatedAt!.hour}:${gateway.updatedAt!.minute.toString().padLeft(2, "0")}:${gateway.updatedAt!.second.toString().padLeft(2, "0")}' : 'Chưa có'),
              _buildInfoRow('Số node trực tuyến', '${gateway.nodes.length} thiết bị'),
              _buildInfoRow('Thiết bị chờ ghép nối', '${gateway.pending.length} thiết bị'),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
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
                          final relayState = node['relay_state']?.toString() ?? '[0, 0]';

                          return Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.surfaceContainerHighest.withOpacity(0.3),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
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
                                      fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
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
          Text(value, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
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

    return Material(
      color: isDark ? const Color(0xFF1E242B) : Colors.white,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        side: BorderSide(
          color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
        ),
      ),
      child: Column(
        children: children,
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final Widget? trailing;
  final VoidCallback onTap;

  const _SettingsTile({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    this.trailing,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListTile(
      onTap: onTap,
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
      subtitle: Text(
        subtitle,
        style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
      ),
      trailing: trailing,
    );
  }
}
