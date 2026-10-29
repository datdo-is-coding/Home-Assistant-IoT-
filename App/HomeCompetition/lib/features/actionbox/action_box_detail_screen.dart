// ignore_for_file: deprecated_member_use
import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_theme.dart';
import '../../models/action_box.dart';
import '../../models/device.dart';
import '../../models/device_lifecycle.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/gateway_client.dart';
import '../voice/kws_config_screen.dart';
import '../../widgets/channel_editor_sheet.dart';

class FeatureActionBoxDetailScreen extends ConsumerStatefulWidget {
  final String actionBoxId;

  const FeatureActionBoxDetailScreen({super.key, required this.actionBoxId});

  @override
  ConsumerState<FeatureActionBoxDetailScreen> createState() =>
      _FeatureActionBoxDetailScreenState();
}

class _FeatureActionBoxDetailScreenState
    extends ConsumerState<FeatureActionBoxDetailScreen> {
  bool _isIdentifying = false;
  int _identifyCountdown = 0;
  Timer? _identifyTimer;

  bool _isOperationRunning = false;
  String _operationTitle = '';
  String _operationStatusText = '';
  DeviceOperationState? _currentOpState;
  String? _operationError;

  @override
  void initState() {
    super.initState();
    _loadAccess();
  }

  Future<void> _loadAccess() async {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.usesFirebase) return;
    try {
      await gateway.request('/api/commissioning/context');
      if (mounted) setState(() {});
    } catch (e) {
      if (mounted)
        setState(
            () => _operationError = 'Không cập nhật được quyền quản trị: $e');
    }
  }

  @override
  void dispose() {
    _identifyTimer?.cancel();
    super.dispose();
  }

  Future<void> _handleIdentify(ActionBox ab) async {
    if (_isIdentifying) return;
    final gateway = ref.read(gatewayClientProvider);

    try {
      await gateway.identifyDevice(ab.id);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Không thể nhận diện thiết bị: $e'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
      return;
    }

    if (!mounted) return;
    setState(() {
      _isIdentifying = true;
      _identifyCountdown = 15;
    });

    _identifyTimer?.cancel();
    _identifyTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        if (_identifyCountdown > 1) {
          _identifyCountdown--;
        } else {
          _isIdentifying = false;
          _identifyCountdown = 0;
          timer.cancel();
        }
      });
    });
  }

  Future<void> _runDeviceOperation({
    required ActionBox ab,
    required String title,
    required DeviceOperationKind kind,
    bool confirmation = false,
  }) async {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.isAdmin) {
      _showAdminRequiredDialog();
      return;
    }

    setState(() {
      _isOperationRunning = true;
      _operationTitle = title;
      _operationStatusText = 'Đang gửi lệnh tới Gateway...';
      _currentOpState = DeviceOperationState.accepted;
      _operationError = null;
    });

    try {
      final op = await gateway.startDeviceOperation(
        ab.id,
        kind,
        confirmation: confirmation,
        idempotencyKey:
            'op_${kind.name}_${ab.id}_${DateTime.now().millisecondsSinceEpoch}',
      );

      setState(() {
        _currentOpState = op.state;
        _operationStatusText = _statusMessageForState(op.state);
      });

      // Poll until finished
      final finalOp = await gateway.pollOperation(
        op.operationId,
        timeout: const Duration(seconds: 40),
        interval: const Duration(milliseconds: 700),
      );

      if (!mounted) return;

      if (finalOp.state == DeviceOperationState.succeeded) {
        setState(() {
          _currentOpState = DeviceOperationState.succeeded;
          _operationStatusText = 'Thao tác hoàn tất thành công!';
        });
        await gateway.refresh();
      } else {
        setState(() {
          _currentOpState = finalOp.state;
          _operationError = finalOp.errorMessage ??
              finalOp.errorCode ??
              'Lỗi thực thi (Mã: ${finalOp.state.name})';
          _operationStatusText = 'Thiết bị phản hồi không thành công';
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _operationError = e is GatewayException ? e.message : e.toString();
        _operationStatusText = 'Lỗi kết nối';
      });
    }
  }

  Future<void> _handleRemoveDevice(ActionBox ab) async {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.isAdmin) {
      _showAdminRequiredDialog();
      return;
    }

    setState(() {
      _isOperationRunning = true;
      _operationTitle = 'Gỡ thiết bị khỏi Nhà';
      _operationStatusText = 'Đang thu hồi quyền và xóa đăng ký...';
      _currentOpState = DeviceOperationState.running;
      _operationError = null;
    });

    try {
      var op = await gateway.removeDeviceFromHome(ab.id, confirmation: true);
      if (!mounted) return;

      if (op.operationId.isNotEmpty &&
          (op.state == DeviceOperationState.accepted ||
              op.state == DeviceOperationState.running)) {
        op = await gateway.pollOperation(op.operationId);
        if (!mounted) return;
      }

      if (op.state == DeviceOperationState.succeeded) {
        setState(() {
          _currentOpState = DeviceOperationState.succeeded;
          _operationStatusText = 'Đã gỡ thiết bị thành công!';
        });
        await gateway.refresh();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Đã gỡ ${ab.name} khỏi hệ thống Nhà.'),
              backgroundColor: const Color(0xFF43A047),
            ),
          );
          context.go('/home');
        }
      } else {
        setState(() {
          _currentOpState = op.state;
          _operationError = op.errorMessage ?? 'Gỡ thiết bị thất bại';
          _operationStatusText = 'Lỗi gỡ thiết bị';
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _operationError = e is GatewayException ? e.message : e.toString();
        _operationStatusText = 'Lỗi kết nối';
      });
    }
  }

  String _statusMessageForState(DeviceOperationState state) {
    switch (state) {
      case DeviceOperationState.accepted:
        return 'Yêu cầu đã được tiếp nhận...';
      case DeviceOperationState.awaitingConfirmation:
        return 'Chờ xác nhận bảo mật...';
      case DeviceOperationState.running:
        return 'Đang nạp cấu hình xuống phần cứng...';
      case DeviceOperationState.awaitingReconnect:
        return 'Đang đợi thiết bị khởi động lại và kết nối lại...';
      case DeviceOperationState.succeeded:
        return 'Thiết bị đã xác nhận thành công!';
      case DeviceOperationState.failed:
        return 'Thao tác không thành công';
      case DeviceOperationState.timedOut:
        return 'Hết thời gian chờ phản hồi từ thiết bị';
    }
  }

  void _showAdminRequiredDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.shield_outlined, color: Colors.orange),
            SizedBox(width: 8),
            Expanded(child: Text('Yêu cầu quyền Quản trị')),
          ],
        ),
        content: const Text(
          'Chỉ Quản trị viên (Admin) mới có quyền thực hiện các thao tác bảo trì phần cứng, đặt lại mạng hoặc gỡ thiết bị khỏi hệ thống.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Đã hiểu'),
          ),
        ],
      ),
    );
  }

  void _confirmRebootDialog(ActionBox ab) {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.isAdmin) {
      _showAdminRequiredDialog();
      return;
    }
    final channelNames = ab.channels.map((c) => c.name).toList();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const Key('reboot_confirm_dialog'),
        title: Text('Khởi động lại ${ab.name}?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Model bo mạch: ${ab.boardModel.toUpperCase()}'),
            const SizedBox(height: 8),
            Text(
              'Thao tác này sẽ khởi động lại chip ESP32. ${ab.channels.length} kênh rơ-le phụ tải (${channelNames.join(', ')}) có thể bị ngắt điện tạm thời.',
              style: const TextStyle(height: 1.4),
            ),
            const SizedBox(height: 8),
            const Text(
              'Thiết bị sẽ tự động kết nối lại mạng sau khoảng 5-10 giây.',
              style: TextStyle(fontSize: 13, color: Colors.grey),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy bỏ'),
          ),
          FilledButton(
            key: const Key('confirm_reboot_button'),
            onPressed: () {
              Navigator.pop(ctx);
              _runDeviceOperation(
                ab: ab,
                title: 'Khởi động lại bo mạch',
                kind: DeviceOperationKind.reboot,
              );
            },
            child: const Text('Khởi động lại'),
          ),
        ],
      ),
    );
  }

  void _confirmNetworkResetDialog(ActionBox ab) {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.isAdmin) {
      _showAdminRequiredDialog();
      return;
    }
    final channelNames = ab.channels.map((c) => c.name).toList();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const Key('network_reset_confirm_dialog'),
        title: const Row(
          children: [
            Icon(Icons.wifi_protected_setup_rounded, color: Colors.orange),
            SizedBox(width: 8),
            Expanded(child: Text('Đặt lại mạng & Khôi phục tuyến?')),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Thiết bị: ${ab.name} (${ab.boardModel.toUpperCase()})'),
            const SizedBox(height: 10),
            Text(ab.isSubBox
                ? 'SubBox sẽ mất kết nối Wi-Fi. Các ActionBox qua SubBox này tạm thời không điều khiển được từ app.'
                : 'Số kênh bị ảnh hưởng: ${ab.channels.length} kênh (${channelNames.join(', ')}).'),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                ab.isSubBox
                    ? 'Tên phòng và danh sách ActionBox đã ghép nối được giữ nguyên.'
                    : '✓ DỮ LIỆU ĐƯỢC BẢO LƯU: Tên phòng, tên 3 kênh rơ-le, phân loại phụ tải, bí danh giọng nói và dữ liệu đo công suất (calibration) được giữ nguyên.',
                style: const TextStyle(fontSize: 12, color: Colors.black87),
              ),
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                ab.isSubBox
                    ? 'Xóa Wi-Fi đã lưu. Bạn cần ở gần SubBox để thiết lập lại mạng.'
                    : '! DỮ LIỆU BỊ ĐẶT LẠI: Khóa ghép nối tuyến SubBox hiện tại sẽ bị xóa để quét tuyến mới.',
                style: const TextStyle(fontSize: 12, color: Colors.black87),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy bỏ'),
          ),
          FilledButton(
            key: const Key('confirm_network_reset_button'),
            style:
                FilledButton.styleFrom(backgroundColor: Colors.orange.shade800),
            onPressed: () {
              Navigator.pop(ctx);
              _runDeviceOperation(
                ab: ab,
                title: 'Đặt lại mạng / Khôi phục tuyến',
                kind: DeviceOperationKind.networkReset,
                confirmation: true,
              );
            },
            child: const Text('Xác nhận đặt lại mạng'),
          ),
        ],
      ),
    );
  }

  void _confirmFactoryResetDialog(ActionBox ab) {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.isAdmin) {
      _showAdminRequiredDialog();
      return;
    }
    final channelNames = ab.channels.map((c) => c.name).toList();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const Key('factory_reset_confirm_dialog'),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.red),
            SizedBox(width: 8),
            Expanded(child: Text('CẢNH BÁO: Khôi phục cài đặt gốc?')),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Thiết bị: ${ab.name} (${ab.boardModel.toUpperCase()})'),
            const SizedBox(height: 8),
            Text(
              gateway.usesFirebase &&
                      asMap(gateway.nodes[ab.id])['core_node_id'] != null
                  ? 'Xóa cấu hình ghép nối và đăng ký trong nhà. Các relay được đưa về OFF; giữ dữ liệu nhà máy và hiệu chuẩn. SubBox chỉ reset sau khi đã gỡ các ActionBox con.'
                  : ab.isSubBox
                      ? 'Xóa Wi-Fi, cấu hình SubBox và danh sách ghép nối. Các ActionBox qua SubBox này sẽ mất kết nối và cần được ghép lại.'
                      : 'Thao tác này sẽ xóa toàn bộ flash NVS người dùng. Toàn bộ ${ab.channels.length} kênh rơ-le (${channelNames.join(', ')}) sẽ bị ngắt điện về trạng thái an toàn (OFF).',
              style: const TextStyle(
                  fontWeight: FontWeight.bold, color: Colors.red),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                      '✗ SẼ XÓA HOÀN TOÀN: Cấu hình phòng, tên kênh, tuyến SubBox, quyền sở hữu (epoch tăng).',
                      style: TextStyle(fontSize: 12, color: Colors.red)),
                  SizedBox(height: 4),
                  Text(
                      '✓ ĐƯỢC BẢO TỒN NGUYÊN VẸN: Dữ liệu hiệu chuẩn cảm biến (PZEM/BL0942 calibration) và MAC gốc của phần cứng.',
                      style: TextStyle(fontSize: 12, color: Colors.green)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy bỏ'),
          ),
          FilledButton(
            key: const Key('confirm_factory_reset_button'),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () {
              Navigator.pop(ctx);
              _runDeviceOperation(
                ab: ab,
                title: 'Khôi phục cài đặt gốc (Factory Reset)',
                kind: DeviceOperationKind.factoryReset,
                confirmation: true,
              );
            },
            child: const Text('Xác nhận xóa gốc'),
          ),
        ],
      ),
    );
  }

  void _confirmRemoveDialog(ActionBox ab) {
    final gateway = ref.read(gatewayClientProvider);
    if (!gateway.isAdmin) {
      _showAdminRequiredDialog();
      return;
    }
    final isSubbox = ab.isSubBox;
    final isCore = gateway.usesFirebase &&
        asMap(gateway.nodes[ab.id])['core_node_id'] != null;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        key: const Key('remove_device_confirm_dialog'),
        title: Text('Gỡ ${ab.name} khỏi Nhà?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Model: ${ab.boardModel.toUpperCase()} · Trạng thái: ${ab.online ? "Trực tuyến" : "Ngoại tuyến"}'),
            const SizedBox(height: 10),
            if (isSubbox) ...[
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  isCore
                      ? 'Hãy gỡ các ActionBox con trước khi gỡ SubBox. Hệ thống không tự xóa các bo con.'
                      : 'ℹ LƯU Ý SUBBOX: Các ActionBox con đang kết nối qua SubBox này sẽ được giữ lại trong hệ thống ở trạng thái Chờ khôi phục tuyến (Route Recovery), tuyệt đối không bị xóa ngầm.',
                  style: const TextStyle(
                      fontSize: 12,
                      color: Colors.blueGrey,
                      fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(height: 8),
            ],
            Text(
              isCore
                  ? 'Bo cần đang kết nối để xác nhận tắt relay, xóa cấu hình ghép nối rồi gỡ khỏi nhà. Dữ liệu nhà máy và hiệu chuẩn được giữ lại.'
                  : ab.online
                      ? 'Thiết bị sẽ được xóa khỏi bảng đăng ký và thu hồi toàn bộ quyền điều khiển.'
                      : 'Thiết bị đang ngoại tuyến. Hệ thống sẽ ghi nhận thẻ bài (Tombstone) để chặn kết nối lại trái phép và thu hồi toàn bộ quyền ngay lập tức.',
              style: const TextStyle(fontSize: 13, height: 1.4),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Hủy bỏ'),
          ),
          FilledButton(
            key: const Key('confirm_remove_button'),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () {
              Navigator.pop(ctx);
              _handleRemoveDevice(ab);
            },
            child: const Text('Xác nhận gỡ'),
          ),
        ],
      ),
    );
  }

  void _exportDiagnostics(ActionBox ab) {
    final sanitized = {
      'device_uid': ab.id,
      'name': ab.name,
      'room_id': ab.roomId,
      'online': ab.online,
      'board_model': ab.boardModel,
      'board_revision': ab.boardRevision,
      'firmware_version': ab.firmwareVersion,
      'protocol_version': ab.protocolVersion,
      'owner_epoch': ab.ownerEpoch,
      'subbox_parent': ab.subboxId ?? 'none',
      'rssi_dbm': ab.signalStrength,
      'channels_count': ab.channels.length,
      'capabilities': ab.capabilities,
      'exported_at': DateTime.now().toIso8601String(),
    };
    final jsonStr = const JsonEncoder.withIndent('  ').convert(sanitized);

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Dữ liệu chẩn đoán bo mạch'),
        content: SizedBox(
          width: double.maxFinite,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Dữ liệu an toàn đã được khử bỏ toàn bộ mật khẩu, token và thông tin riêng tư:',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: SelectableText(
                    jsonStr,
                    style:
                        const TextStyle(fontFamily: 'monospace', fontSize: 11),
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Đóng'),
          ),
          FilledButton.icon(
            icon: const Icon(Icons.copy_rounded, size: 16),
            label: const Text('Sao chép JSON'),
            onPressed: () {
              Clipboard.setData(ClipboardData(text: jsonStr));
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                    content:
                        Text('Đã sao chép dữ liệu chẩn đoán vào clipboard')),
              );
            },
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ??
        (isDark ? AppColors.dark : AppColors.light);

    final actionBoxesAsync = ref.watch(actionBoxesStreamProvider);
    final gateway = ref.watch(gatewayClientProvider);

    return actionBoxesAsync.when(
      data: (boxes) {
        final ab = boxes.firstWhere(
          (b) => b.id == widget.actionBoxId,
          orElse: () => ActionBox(
            id: widget.actionBoxId,
            name: 'Bộ điều khiển ${widget.actionBoxId}',
            roomId: 'livingroom',
            online: false,
            channels: const [],
          ),
        );

        return Scaffold(
          appBar: AppBar(
            title: Text(ab.name,
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            actions: [
              IconButton(
                key: const Key('export_diagnostics_button'),
                tooltip: 'Xuất dữ liệu chẩn đoán',
                icon: const Icon(Icons.analytics_outlined),
                onPressed: () => _exportDiagnostics(ab),
              ),
            ],
          ),
          body: Stack(
            children: [
              SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Header Card
                    _buildHeaderCard(ab, theme, isDark, colors),
                    const SizedBox(height: 20),

                    // Admin Warning Banner if member
                    if (!gateway.isAdmin)
                      Container(
                        key: const Key('admin_required_banner'),
                        margin: const EdgeInsets.only(bottom: 20),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.amber.shade50,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.amber.shade300),
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.info_outline_rounded,
                                color: Colors.amber.shade900, size: 20),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                'Bạn đang đăng nhập với quyền Thành viên. Các thao tác bảo trì và khôi phục bo mạch yêu cầu quyền Quản trị viên (Admin).',
                                style: TextStyle(
                                    fontSize: 12, color: Colors.amber.shade900),
                              ),
                            ),
                          ],
                        ),
                      ),

                    if (gateway.isAdmin) ...[
                      ListTile(
                        key: const Key('kws_config_tile'),
                        leading: const Icon(Icons.record_voice_over_outlined),
                        title: const Text('Khẩu lệnh tại SubBox'),
                        subtitle: const Text(
                            'Gán phòng, đèn/quạt và kênh điều khiển'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => const KwsConfigScreen(),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // Hardware Channels Section
                    if (!ab.isSubBox) ...[
                      Text(
                        '${ab.channels.length} Kênh phụ tải phần cứng',
                        style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.3),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Chạm vào kênh để đổi tên, loại thiết bị hoặc tên gọi giọng nói. Phòng được gán theo SubBox.',
                        style: TextStyle(
                            fontSize: 12,
                            color: theme.colorScheme.onSurfaceVariant),
                      ),
                      const SizedBox(height: 12),
                      ...ab.channels.map((ch) {
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _ChannelItemCard(
                            channel: ch,
                            online: ab.online,
                            isLatching: ab.boardModel.contains('v2') ||
                                ch.channelKey == 'ch3' ||
                                ch.index == 2,
                            onEdit: () =>
                                _showEditChannelDialog(context, ref, ab, ch),
                          ),
                        );
                      }),
                    ],
                    const SizedBox(height: 24),
                    const Divider(),
                    const SizedBox(height: 16),

                    // Board Maintenance & Recovery Section
                    const Text(
                      'Bảo trì & Khôi phục bo mạch',
                      style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.3),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Các thao tác cấp phần cứng tác động lên toàn bộ bo điều khiển.',
                      style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 16),

                    if (!gateway.usesFirebase ||
                        asMap(gateway.nodes[ab.id])['core_node_id'] == null) ...[
                      _buildIdentifyCard(ab, theme, isDark),
                      const SizedBox(height: 12),
                    ],

                    // Reboot Card
                    _buildActionTile(
                      key: const Key('reboot_tile'),
                      icon: Icons.restart_alt_rounded,
                      iconColor: theme.colorScheme.primary,
                      title: 'Khởi động lại bo mạch',
                      subtitle:
                          'Khởi động lại chip ESP32 mà không làm mất cấu hình.',
                      onTap: () => _confirmRebootDialog(ab),
                    ),
                    const SizedBox(height: 12),

                    // Network Reset Tile
                    if (!gateway.usesFirebase ||
                        asMap(gateway.nodes[ab.id])['core_node_id'] == null)
                      _buildActionTile(
                        key: const Key('network_reset_tile'),
                        icon: Icons.wifi_protected_setup_rounded,
                        iconColor: Colors.orange.shade700,
                        title: 'Đặt lại mạng & Khôi phục tuyến',
                        subtitle: ab.isSubBox
                            ? 'Xóa Wi-Fi đã lưu và mở thiết lập mạng. Giữ danh sách ActionBox đã ghép nối.'
                            : 'Xóa liên kết SubBox cũ và quét lại mạng ESP-NOW mới. Cấu hình phụ tải được bảo toàn.',
                        onTap: () => _confirmNetworkResetDialog(ab),
                      ),
                    const SizedBox(height: 12),

                    // Factory Reset Tile
                    _buildActionTile(
                      key: const Key('factory_reset_tile'),
                      icon: Icons.restore_rounded,
                      iconColor: Colors.red.shade700,
                      title: 'Khôi phục cài đặt gốc (Factory Reset)',
                      subtitle: gateway.usesFirebase &&
                              asMap(gateway.nodes[ab.id])['core_node_id'] !=
                                  null
                          ? 'Xóa cấu hình ghép nối và đăng ký trong nhà; giữ hiệu chuẩn.'
                          : 'Xóa toàn bộ flash NVS người dùng. Bảo tồn hiệu chuẩn cảm biến công suất (PZEM/BL0942).',
                      onTap: () => _confirmFactoryResetDialog(ab),
                      isDestructive: true,
                    ),
                    const SizedBox(height: 12),

                    // Remove from Home Tile
                    _buildActionTile(
                      key: const Key('remove_device_tile'),
                      icon: Icons.delete_forever_rounded,
                      iconColor: Colors.red.shade900,
                      title: 'Gỡ thiết bị khỏi Nhà',
                      subtitle:
                          'Thu hồi toàn bộ quyền truy cập và xóa khỏi danh sách Nhà.',
                      onTap: () => _confirmRemoveDialog(ab),
                      isDestructive: true,
                    ),

                    const SizedBox(height: 28),

                    // Hardware Button Timing Guide
                    _buildHardwareButtonGuide(theme, isDark, ab),
                    const SizedBox(height: 32),
                  ],
                ),
              ),

              // Running Operation Progress Overlay
              if (_isOperationRunning)
                _buildOperationProgressOverlay(theme, isDark),
            ],
          ),
        );
      },
      loading: () =>
          const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (e, _) => Scaffold(body: Center(child: Text('Lỗi: $e'))),
    );
  }

  Widget _buildHeaderCard(
      ActionBox ab, ThemeData theme, bool isDark, AppColors colors) {
    final isSubbox = ab.isSubBox;
    final modelDisplayName = isSubbox
        ? 'SubBox Mesh Router & Audio'
        : (ab.boardModel == 'actionbox_v2'
            ? 'ActionBox V2 (3 Kênh Rơ-le, Đo công suất)'
            : ab.boardModel.toUpperCase());

    final routeInfo = isSubbox
        ? 'Wi-Fi LAN + ESP-NOW Master · ${ab.signalStrength} dBm'
        : 'ESP-NOW Mesh (Qua SubBox: ${ab.subboxId ?? 'Trạm gần nhất'}) · ${ab.signalStrength} dBm';

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colors.cardSurface,
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        border: Border.all(color: colors.cardBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF1E2532)
                      : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  isSubbox
                      ? Icons.router_rounded
                      : Icons.developer_board_rounded,
                  size: 24,
                  color: theme.colorScheme.primary,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(ab.name,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 3),
                    Text(
                      modelDisplayName,
                      style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: ab.online
                      ? colors.online.withValues(alpha: 0.12)
                      : colors.offline.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  ab.online ? 'Trực tuyến' : 'Ngoại tuyến',
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: ab.online ? colors.online : colors.offline),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const Divider(height: 1),
          const SizedBox(height: 10),
          Row(
            children: [
              Icon(Icons.hub_outlined,
                  size: 14, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  routeInfo,
                  style: TextStyle(
                      fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
              Text(
                'FW: ${ab.firmwareVersion}',
                style: TextStyle(
                    fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildIdentifyCard(ActionBox ab, ThemeData theme, bool isDark) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E2532) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: _isIdentifying
              ? theme.colorScheme.primary
              : (isDark ? Colors.white10 : Colors.black12),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withOpacity(0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(
              _isIdentifying ? Icons.timer_rounded : Icons.flash_on_rounded,
              color: theme.colorScheme.primary,
              size: 22,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Nhận diện thiết bị',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  _isIdentifying
                      ? 'Đang nhấp nháy đèn LED (${_identifyCountdown}s)...'
                      : 'Nháy LED 15s để nhận diện bo mạch, không ảnh hưởng tải điện.',
                  style: TextStyle(
                      fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          FilledButton.tonal(
            key: const Key('identify_button'),
            onPressed: _isIdentifying ? null : () => _handleIdentify(ab),
            child: Text(_isIdentifying ? '${_identifyCountdown}s' : 'Nháy đèn'),
          ),
        ],
      ),
    );
  }

  Widget _buildActionTile({
    required Key key,
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
    bool isDestructive = false,
  }) {
    return InkWell(
      key: key,
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isDestructive
                ? Colors.red.withOpacity(0.25)
                : Colors.grey.withOpacity(0.2),
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: iconColor.withOpacity(0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: iconColor, size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: isDestructive ? Colors.red.shade900 : null,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: const TextStyle(
                        fontSize: 11, color: Colors.grey, height: 1.3),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  Widget _buildHardwareButtonGuide(ThemeData theme, bool isDark, ActionBox ab) {
    final buttonName = ab.isSubBox ? 'CONFIG (GPIO 1)' : 'CONFIG (GPIO 9)';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF19202A) : const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.touch_app_rounded,
                  size: 18, color: Colors.blueGrey),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Hướng dẫn thao tác nút vật lý ($buttonName)',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 13),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          _buildTimingRow(
              'Giữ 3 giây', 'Nhận diện bo mạch (LED nhấp nháy 15s)'),
          _buildTimingRow('Giữ 5 giây',
              'Đặt lại mạng / Quét tuyến ESP-NOW mới (LED nháy vàng)'),
          _buildTimingRow('Giữ 10 giây',
              'Khởi động quy trình khôi phục cài đặt gốc 2 pha an toàn (LED nháy đỏ nhanh, nhả trong 3s để commit)'),
          const SizedBox(height: 6),
          const Text(
            'Lưu ý: Nút vật lý trên bo mạch thương mại là nút CONFIG, không dùng nút BOOT bất kỳ.',
            style: TextStyle(
                fontSize: 11, fontStyle: FontStyle.italic, color: Colors.grey),
          ),
        ],
      ),
    );
  }

  Widget _buildTimingRow(String timing, String action) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 85,
            child: Text(
              timing,
              style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: Colors.blueGrey),
            ),
          ),
          Expanded(
            child:
                Text(action, style: const TextStyle(fontSize: 12, height: 1.3)),
          ),
        ],
      ),
    );
  }

  Widget _buildOperationProgressOverlay(ThemeData theme, bool isDark) {
    return Container(
      color: Colors.black54,
      padding: const EdgeInsets.all(24),
      alignment: Alignment.center,
      child: Card(
        key: const Key('operation_progress_card'),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_currentOpState == DeviceOperationState.succeeded)
                const Icon(Icons.check_circle_rounded,
                    color: Colors.green, size: 48)
              else if (_operationError != null)
                const Icon(Icons.error_outline_rounded,
                    color: Colors.red, size: 48)
              else
                const SizedBox(
                  width: 40,
                  height: 40,
                  child: CircularProgressIndicator(strokeWidth: 3),
                ),
              const SizedBox(height: 16),
              Text(
                _operationTitle,
                style:
                    const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                _operationStatusText,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 13, color: Colors.grey),
              ),
              if (_operationError != null) ...[
                const SizedBox(height: 12),
                Text(
                  _operationError!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 12, color: Colors.red),
                ),
              ],
              const SizedBox(height: 20),
              if (_currentOpState == DeviceOperationState.succeeded ||
                  _operationError != null)
                FilledButton(
                  key: const Key('operation_dismiss_button'),
                  onPressed: () {
                    setState(() {
                      _isOperationRunning = false;
                      _operationError = null;
                    });
                  },
                  child: const Text('Đóng'),
                )
              else
                const Text(
                  'Hủy giao diện không hủy thao tác phần cứng đã bắt đầu.',
                  style: TextStyle(fontSize: 11, color: Colors.grey),
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _showEditChannelDialog(
      BuildContext context, WidgetRef ref, ActionBox ab, ActionBoxChannel ch) {
    showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (_) => ChannelEditorSheet(
            channelLabel: ch.channelKey.toUpperCase(),
            initialName: ch.name,
            initialType: ch.type,
            initialAliases: ch.voiceAliases,
            onSave: (name, type, aliases) => ref
                .read(actionBoxRepositoryProvider)
                .updateChannel(
                    actionBoxId: ab.id,
                    channelIndex: ch.index,
                    name: name,
                    type: type,
                    roomId: ab.roomId,
                    voiceAliases: aliases)));
  }
}

class _ChannelItemCard extends StatelessWidget {
  final ActionBoxChannel channel;
  final bool online;
  final bool isLatching;
  final VoidCallback onEdit;

  const _ChannelItemCard({
    required this.channel,
    required this.online,
    this.isLatching = false,
    required this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ??
        (isDark ? AppColors.dark : AppColors.light);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.cardSurface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: colors.cardBorder),
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: channel.isOn && online
                  ? colors.lightWash
                  : (isDark
                      ? const Color(0xFF1E2532)
                      : const Color(0xFFF1F5F9)),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              channel.type == DeviceType.light
                  ? Icons.lightbulb_rounded
                  : (channel.type == DeviceType.fan
                      ? Icons.air_rounded
                      : Icons.power_rounded),
              color: channel.isOn && online
                  ? colors.lightAccent
                  : theme.colorScheme.onSurfaceVariant,
              size: 20,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        '${channel.channelKey.toUpperCase()} · ${channel.name}',
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w700),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (isLatching) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.amber.shade100,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          'Rơ-le chốt',
                          style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              color: Colors.amber.shade900),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  channel.commandPending
                      ? (channel.isOn ? 'Đang bật…' : 'Đang tắt…')
                      : channel.configured
                          ? 'Đã gán · ${channel.isOn && online ? "Đang bật" : "Đã tắt"}'
                          : 'Chưa cấu hình thiết bị',
                  style: TextStyle(
                      fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          OutlinedButton(
            onPressed: onEdit,
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
            child: const Text('Cấu hình',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}
