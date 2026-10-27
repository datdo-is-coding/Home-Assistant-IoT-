// ignore_for_file: deprecated_member_use
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../models/device.dart';
import '../../models/device_lifecycle.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/device_provisioning_service.dart';
import '../../services/gateway_client.dart';

enum DeviceTarget {
  actionBoxV2,
  subBox,
}

class AddDeviceFlowScreen extends ConsumerStatefulWidget {
  const AddDeviceFlowScreen({super.key});

  @override
  ConsumerState<AddDeviceFlowScreen> createState() =>
      _AddDeviceFlowScreenState();
}

class _AddDeviceFlowScreenState extends ConsumerState<AddDeviceFlowScreen> {
  int _currentStep = 0;
  DeviceTarget _deviceTarget = DeviceTarget.actionBoxV2;

  // Step 2: Candidates & Verification
  List<CommissioningCandidate> _candidates = [];
  bool _isLoadingCandidates = false;
  String? _candidateError;
  CommissioningCandidate? _selectedCandidate;
  bool _isIdentifying = false;
  int _identifyCountdown = 0;
  Timer? _identifyTimer;
  final TextEditingController _setupProofController = TextEditingController();

  // SubBox Provisioning
  final TextEditingController _subboxSsidController = TextEditingController();
  final TextEditingController _subboxPasswordController =
      TextEditingController();
  final TextEditingController _subboxPopController = TextEditingController();
  String _subboxStatusMessage = '';
  bool _isProvisioningSubbox = false;
  StreamSubscription<ProvisioningProgressEvent>? _subboxSub;
  DeviceProvisioningService? _provisioningService;

  // Step 3: Configuration
  late final TextEditingController _boxNameController;
  String _selectedRoomId = 'livingroom';
  String _selectedRoomName = 'Phòng khách';
  String _selectedSubboxId = '';

  late final TextEditingController _ch1NameController;
  DeviceType _ch1Type = DeviceType.light;
  final List<String> _ch1Aliases = ['đèn chính', 'đèn phòng'];
  final TextEditingController _ch1NewAliasController = TextEditingController();

  late final TextEditingController _ch2NameController;
  DeviceType _ch2Type = DeviceType.fan;
  final List<String> _ch2Aliases = ['quạt trần', 'quạt mát'];
  final TextEditingController _ch2NewAliasController = TextEditingController();

  late final TextEditingController _ch3NameController;
  DeviceType _ch3Type = DeviceType.socket;
  final List<String> _ch3Aliases = ['bình nóng lạnh', 'bình nước nóng'];
  final TextEditingController _ch3NewAliasController = TextEditingController();

  // Step 4: Commissioning & Confirmation
  bool _isSubmitting = false;
  bool _isSuccess = false;
  String? _errorMessage;
  String? _claimIdempotencyKey;
  String? _claimOperationId;

  @override
  void initState() {
    super.initState();
    _boxNameController = TextEditingController(text: 'ActionBox Phòng Khách');
    _ch1NameController = TextEditingController(text: 'Đèn chính');
    _ch2NameController = TextEditingController(text: 'Quạt trần');
    _ch3NameController = TextEditingController(text: 'Bình nóng lạnh');
  }

  @override
  void dispose() {
    _identifyTimer?.cancel();
    _subboxSub?.cancel();
    _provisioningService?.dispose();
    _setupProofController.dispose();
    _subboxSsidController.dispose();
    _subboxPasswordController.dispose();
    _subboxPopController.dispose();
    _boxNameController.dispose();
    _ch1NameController.dispose();
    _ch1NewAliasController.dispose();
    _ch2NameController.dispose();
    _ch2NewAliasController.dispose();
    _ch3NameController.dispose();
    _ch3NewAliasController.dispose();
    super.dispose();
  }

  String _deviceTypeToString(DeviceType type) => switch (type) {
        DeviceType.light => 'light',
        DeviceType.fan => 'fan',
        DeviceType.socket => 'switch',
        DeviceType.airConditioner => 'air_conditioner',
        _ => 'light',
      };

  String _deviceTypeLabel(DeviceType type) => switch (type) {
        DeviceType.light => 'Đèn',
        DeviceType.fan => 'Quạt',
        DeviceType.socket => 'Ổ cắm',
        DeviceType.airConditioner => 'Điều hòa',
        _ => 'Khác',
      };

  Future<void> _loadCandidates() async {
    setState(() {
      _isLoadingCandidates = true;
      _candidateError = null;
    });
    try {
      final gateway = ref.read(gatewayClientProvider);
      final list = await gateway.getCandidates();
      if (mounted) {
        setState(() {
          _candidates = list;
          if (_selectedCandidate != null) {
            final match =
                list.where((c) => c.deviceUid == _selectedCandidate!.deviceUid);
            _selectedCandidate = match.isNotEmpty ? match.first : null;
          }
          _isLoadingCandidates = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingCandidates = false;
          _candidates = [];
          _selectedCandidate = null;
          _candidateError = e is GatewayException
              ? e.message
              : 'Không tải được danh sách thiết bị. Hãy quét lại.';
        });
      }
    }
  }

  Future<void> _onIdentifyPressed() async {
    final candidate = _selectedCandidate;
    if (candidate == null || _isIdentifying) return;

    final gateway = ref.read(gatewayClientProvider);

    try {
      await gateway.identifyDevice(candidate.deviceUid);
    } catch (e) {
      if (mounted) {
        setState(() {
          _isIdentifying = false;
          _identifyCountdown = 0;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Không thể kích hoạt nhận diện: $e'),
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

  Future<void> _provisionSubBox() async {
    if (_isProvisioningSubbox) return;
    final ssid = _subboxSsidController.text.trim();
    final password = _subboxPasswordController.text;
    final pop = _subboxPopController.text.trim();

    if (ssid.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Vui lòng nhập tên mạng Wi-Fi.')),
      );
      return;
    }

    setState(() {
      _isProvisioningSubbox = true;
      _subboxStatusMessage = 'Đang bắt đầu cấu hình SubBox...';
    });

    _provisioningService ??= DeviceProvisioningService();
    _subboxSub?.cancel();
    _subboxSub = _provisioningService!.provisioningEvents.listen((event) {
      if (mounted) {
        setState(() => _subboxStatusMessage = event.message);
      }
    });

    final gateway = ref.read(gatewayClientProvider);
    try {
      final target = await gateway.getProvisioningTarget();
      await _provisioningService!.provisionSubBox(
        ssid: ssid,
        password: password,
        gatewayHost: target.host,
        gatewayPort: target.port,
        pop: pop,
        roomName: _selectedRoomName,
      );
      await gateway.refresh();
      if (mounted) {
        setState(() {
          _isProvisioningSubbox = false;
          _isSuccess = true;
          _currentStep = 3;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isProvisioningSubbox = false;
          _errorMessage = e.toString();
          _subboxStatusMessage = e.toString();
        });
      }
    }
  }

  Future<void> _executeClaim() async {
    if (_isSubmitting) return; // Prevent duplicate tap / re-submit
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final gateway = ref.read(gatewayClientProvider);
    final candidate = _selectedCandidate;
    if (candidate == null) {
      setState(() {
        _isSubmitting = false;
        _errorMessage = 'Chưa chọn thiết bị để thêm.';
      });
      return;
    }

    try {
      final idempotencyKey = _claimIdempotencyKey ??=
          'claim_${candidate.deviceUid}_${DateTime.now().millisecondsSinceEpoch}';

      final channelsPayload = {
        'ch1': {
          'name': _ch1NameController.text.trim().isNotEmpty
              ? _ch1NameController.text.trim()
              : 'Đèn chính',
          'type': _deviceTypeToString(_ch1Type),
          'aliases': List<String>.from(_ch1Aliases),
        },
        'ch2': {
          'name': _ch2NameController.text.trim().isNotEmpty
              ? _ch2NameController.text.trim()
              : 'Quạt trần',
          'type': _deviceTypeToString(_ch2Type),
          'aliases': List<String>.from(_ch2Aliases),
        },
        'ch3': {
          'name': _ch3NameController.text.trim().isNotEmpty
              ? _ch3NameController.text.trim()
              : 'Bình nóng lạnh',
          'type': _deviceTypeToString(_ch3Type),
          'aliases': List<String>.from(_ch3Aliases),
        },
      };

      final subboxTarget = _selectedSubboxId.isNotEmpty
          ? _selectedSubboxId
          : (candidate.subboxId.isNotEmpty
              ? candidate.subboxId
              : (gateway.onlineSubBoxes.isNotEmpty
                  ? (gateway.onlineSubBoxes.first['id']?.toString() ?? '')
                  : ''));

      final op = _claimOperationId != null
          ? await gateway.getOperation(_claimOperationId!)
          : await gateway.startClaim(
              candidateId: candidate.deviceUid,
              setupProof: _setupProofController.text.trim().isNotEmpty
                  ? _setupProofController.text.trim()
                  : null,
              subboxId: subboxTarget,
              roomId: _selectedRoomId,
              channels: channelsPayload,
              name: _boxNameController.text.trim().isNotEmpty
                  ? _boxNameController.text.trim()
                  : 'ActionBox Phòng Khách',
              idempotencyKey: idempotencyKey,
            );

      _claimOperationId = op.operationId;
      // Gateway owns the 120-second deadline; network retries resume this operation.
      final finalOp = await gateway.pollOperation(op.operationId,
          timeout: const Duration(seconds: 130));
      if (finalOp.state == DeviceOperationState.succeeded ||
          finalOp.state == DeviceOperationState.failed ||
          finalOp.state == DeviceOperationState.timedOut) {
        _claimOperationId = null;
        _claimIdempotencyKey = null;
      }

      // ONLY display success when state == DeviceOperationState.succeeded
      if (finalOp.state == DeviceOperationState.succeeded) {
        await gateway.refresh();
        if (mounted) {
          setState(() {
            _isSubmitting = false;
            _isSuccess = true;
          });
        }
      } else {
        if (mounted) {
          setState(() {
            _isSubmitting = false;
            _errorMessage = finalOp.errorMessage ??
                finalOp.errorCode ??
                'Cấu hình thất bại (Mã: ${finalOp.state.name})';
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
          _errorMessage = e is GatewayException ? e.message : e.toString();
        });
      }
    }
  }

  void _onBack() {
    if (_isSubmitting) return;
    if (_isSuccess) {
      _navigateHome();
      return;
    }
    if (_currentStep > 0) {
      setState(() {
        _currentStep--;
        _errorMessage = null;
      });
    } else {
      try {
        context.pop();
      } catch (_) {
        Navigator.of(context).maybePop();
      }
    }
  }

  void _navigateHome() {
    try {
      context.go('/home');
    } catch (_) {
      Navigator.of(context).maybePop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return PopScope(
      canPop: !_isSubmitting && _currentStep == 0 && !_isSuccess,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        _onBack();
      },
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          elevation: 0,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
            onPressed: _onBack,
          ),
          title: Column(
            children: [
              Text(
                'Thêm thiết bị (${_currentStep + 1}/4)',
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (int i = 0; i < 4; i++)
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 250),
                      margin: const EdgeInsets.symmetric(horizontal: 3),
                      height: 4,
                      width: _currentStep == i ? 24 : 8,
                      decoration: BoxDecoration(
                        color: _currentStep == i
                            ? theme.colorScheme.primary
                            : (isDark
                                ? Colors.white.withOpacity(0.2)
                                : Colors.black.withOpacity(0.12)),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                ],
              ),
            ],
          ),
          centerTitle: true,
        ),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: switch (_currentStep) {
              0 => _buildStep1Preparation(theme),
              1 => _buildStep2Discovery(theme),
              2 => _buildStep3Configuration(theme),
              3 => _buildStep4Confirmation(theme),
              _ => const SizedBox.shrink(),
            },
          ),
        ),
      ),
    );
  }

  // ==========================================
  // BƯỚC 1: CHUẨN BỊ (PREPARATION)
  // ==========================================
  Widget _buildStep1Preparation(ThemeData theme) {
    final gateway = ref.watch(gatewayClientProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Bước 1: Chuẩn bị thiết bị',
          style: theme.textTheme.headlineSmall
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        Text(
          'Chọn loại thiết bị bạn muốn kết nối và kiểm tra trạng thái đèn LED theo hướng dẫn.',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),

        // Device Target Selector
        SegmentedButton<DeviceTarget>(
          segments: const [
            ButtonSegment(
              value: DeviceTarget.actionBoxV2,
              label: Text('ActionBox V2'),
              icon: Icon(Icons.developer_board_rounded),
            ),
            ButtonSegment(
              value: DeviceTarget.subBox,
              label: Text('SubBox'),
              icon: Icon(Icons.router_rounded),
            ),
          ],
          selected: {_deviceTarget},
          onSelectionChanged: (selected) {
            setState(() {
              _deviceTarget = selected.first;
            });
          },
        ),
        const SizedBox(height: 20),

        if (_deviceTarget == DeviceTarget.actionBoxV2) ...[
          // SubBox Online Check / Warning
          if (!gateway.hasOnlineSubBox)
            Container(
              key: const Key('subbox_warning_card'),
              margin: const EdgeInsets.only(bottom: 16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.amber.shade50,
                border: Border.all(color: Colors.amber.shade400, width: 1.5),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.warning_amber_rounded,
                          color: Colors.amber.shade900, size: 24),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Chưa có SubBox trực tuyến',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.amber.shade900,
                            fontSize: 16,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'ActionBox V2 kết nối với Gateway thông qua SubBox bằng sóng ESP-NOW nội bộ. Hệ thống hiện chưa có SubBox nào trực tuyến. Bạn nên thêm SubBox trước để làm trạm thu phát.',
                    style: TextStyle(
                      color: Colors.amber.shade900,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.tonal(
                    key: const Key('switch_to_subbox_button'),
                    onPressed: () {
                      setState(() {
                        _deviceTarget = DeviceTarget.subBox;
                      });
                    },
                    child: const Text('Thêm SubBox trước'),
                  ),
                ],
              ),
            )
          else
            Container(
              margin: const EdgeInsets.only(bottom: 16),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.green.shade300),
              ),
              child: Row(
                children: [
                  Icon(Icons.check_circle_rounded,
                      color: Colors.green.shade700, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Đã có ${gateway.onlineSubBoxes.length} SubBox trực tuyến sẵn sàng chuyển tiếp.',
                      style:
                          TextStyle(color: Colors.green.shade900, fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),

          // Guidance Card for ActionBox V2
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            elevation: 0,
            color: theme.colorScheme.surfaceVariant.withOpacity(0.5),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Hướng dẫn cấp nguồn & Quan sát đèn LED:',
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  const _InstructionBullet(
                    number: '1',
                    text: 'Cấp nguồn điện 220V AC an toàn cho ActionBox V2.',
                  ),
                  const SizedBox(height: 8),
                  const _InstructionBullet(
                    number: '2',
                    text:
                        'Quan sát đèn LED hệ thống (LED1): Đèn nháy xanh chậm 1Hz (500ms sáng / 500ms tắt) biểu thị thiết bị chưa đăng ký và sẵn sàng ghép nối.',
                  ),
                  const SizedBox(height: 8),
                  const _InstructionBullet(
                    number: '3',
                    text:
                        'Nhấn rồi thả CONFIG trên SubBox trước. Với ActionBox chưa ghép nối: giữ BUT1 khoảng 6 giây rồi thả. Cửa sổ đăng ký mở trong 180 giây. LED nháy nhanh khi chờ kết nối. Không giữ 3–5 giây (khởi động lại) hoặc từ 10 giây (chờ xác nhận reset).',
                  ),
                ],
              ),
            ),
          ),
        ] else ...[
          // Guidance Card for SubBox
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            elevation: 0,
            color: theme.colorScheme.surfaceVariant.withOpacity(0.5),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Hướng dẫn cấp nguồn SubBox:',
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  const _InstructionBullet(
                    number: '1',
                    text: 'Cấp nguồn 5V DC qua cổng USB-C cho SubBox.',
                  ),
                  const SizedBox(height: 8),
                  const _InstructionBullet(
                    number: '2',
                    text:
                        'Quan sát đèn LED: Đèn nhấp nháy báo hiệu SoftAP (SubBox-xxxx) đang mở trong cửa sổ thiết lập 180 giây.',
                  ),
                  const SizedBox(height: 8),
                  const _InstructionBullet(
                    number: '3',
                    text:
                        'Chuẩn bị thông tin tên mạng Wi-Fi và mật khẩu băng tần 2.4GHz gia đình.',
                  ),
                ],
              ),
            ),
          ),
        ],

        const SizedBox(height: 28),
        FilledButton(
          key: const Key('step1_next_button'),
          onPressed: () {
            setState(() => _currentStep = 1);
            if (_deviceTarget == DeviceTarget.actionBoxV2) {
              _loadCandidates();
            }
          },
          child: const Text('Bắt đầu tìm kiếm'),
        ),
      ],
    );
  }

  // ==========================================
  // BƯỚC 2: TÌM KIẾM & IDENTIFY
  // ==========================================
  Widget _buildStep2Discovery(ThemeData theme) {
    if (_deviceTarget == DeviceTarget.subBox) {
      return _buildSubBoxProvisioningForm(theme);
    }

    final bool canContinue =
        _selectedCandidate != null && !_selectedCandidate!.isExpired();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Bước 2: Tìm kiếm & Nhận diện',
                    style: theme.textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Chọn thiết bị và nhấn Nhận diện để xác nhận đúng vị trí vật lý.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              key: const Key('refresh_candidates_button'),
              tooltip: 'Quét lại',
              icon: _isLoadingCandidates
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh_rounded),
              onPressed: _isLoadingCandidates ? null : _loadCandidates,
            ),
          ],
        ),
        const SizedBox(height: 16),

        if (_isLoadingCandidates && _candidates.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 40),
            child: Center(
              child: Column(
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Đang quét ActionBox chờ ghép nối...'),
                ],
              ),
            ),
          )
        else if (_candidates.isEmpty)
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            elevation: 0,
            color: theme.colorScheme.surfaceVariant.withOpacity(0.4),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Icon(Icons.radar_rounded,
                      size: 48, color: theme.colorScheme.primary),
                  const SizedBox(height: 12),
                  const Text(
                    'Chưa tìm thấy ActionBox nào',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _candidateError ??
                        'Đảm bảo ActionBox V2 đã được cấp nguồn và đèn LED đang nháy chậm 1Hz.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: theme.colorScheme.onSurfaceVariant,
                        fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  FilledButton.tonal(
                    onPressed: _loadCandidates,
                    child: const Text('Quét lại'),
                  ),
                ],
              ),
            ),
          )
        else ...[
          // Candidate Cards
          ..._candidates.map((candidate) {
            final isSelected =
                _selectedCandidate?.deviceUid == candidate.deviceUid;
            final isExp = candidate.isExpired();

            return Container(
              key: Key('candidate_card_${candidate.deviceUid}'),
              margin: const EdgeInsets.only(bottom: 12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: isSelected
                      ? theme.colorScheme.primary
                      : (isExp
                          ? Colors.red.shade200
                          : theme.colorScheme.outlineVariant),
                  width: isSelected ? 2.0 : 1.0,
                ),
                color: isSelected
                    ? theme.colorScheme.primaryContainer.withOpacity(0.2)
                    : (isExp
                        ? Colors.red.shade50.withOpacity(0.3)
                        : theme.cardColor),
              ),
              child: InkWell(
                borderRadius: BorderRadius.circular(16),
                onTap: () {
                  setState(() {
                    _selectedCandidate = candidate;
                    if (candidate.subboxId.isNotEmpty) {
                      _selectedSubboxId = candidate.subboxId;
                    }
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: isSelected
                              ? theme.colorScheme.primary
                              : theme.colorScheme.surfaceVariant,
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.developer_board_rounded,
                          color: isSelected
                              ? theme.colorScheme.onPrimary
                              : theme.colorScheme.onSurfaceVariant,
                          size: 24,
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
                                    candidate.boardModel.toUpperCase(),
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 15,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                if (isExp)
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: Colors.red.shade100,
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      'Hết hạn',
                                      style: TextStyle(
                                        color: Colors.red.shade900,
                                        fontSize: 11,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  )
                                else
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: Colors.green.shade100,
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      'Sẵn sàng',
                                      style: TextStyle(
                                        color: Colors.green.shade900,
                                        fontSize: 11,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'UID: ${candidate.deviceUid}',
                              style: TextStyle(
                                color: theme.colorScheme.onSurfaceVariant,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Trạm: ${candidate.subboxId} • RSSI: ${candidate.rssi} dBm',
                              style: TextStyle(
                                color: theme.colorScheme.onSurfaceVariant,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Icon(
                        isSelected
                            ? Icons.radio_button_checked_rounded
                            : Icons.radio_button_off_rounded,
                        color: isSelected
                            ? theme.colorScheme.primary
                            : theme.colorScheme.onSurfaceVariant,
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
        ],

        // Verification & PIN section when a candidate is selected
        if (_selectedCandidate != null) ...[
          const SizedBox(height: 12),
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            elevation: 0,
            color: theme.colorScheme.surfaceVariant.withOpacity(0.4),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Icon(Icons.lightbulb_rounded,
                          color: _isIdentifying
                              ? Colors.amber.shade700
                              : theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _isIdentifying
                              ? 'Đang nháy đèn LED nhận diện (${_identifyCountdown}s)...'
                              : 'Kiểm tra nhận diện vật lý:',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: _isIdentifying
                                ? Colors.amber.shade900
                                : theme.colorScheme.onSurface,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Đèn LED hệ thống sẽ nhấp nháy trong 15s để bạn nhận biết đúng board phần cứng (tuyệt đối không bật/tắt relay hay tải điện).',
                    style: TextStyle(
                      fontSize: 12,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.tonalIcon(
                    key: const Key('identify_button'),
                    onPressed: _isIdentifying ? null : _onIdentifyPressed,
                    icon: Icon(_isIdentifying
                        ? Icons.timer_rounded
                        : Icons.flash_on_rounded),
                    label: Text(_isIdentifying
                        ? 'Đang nhấp nháy LED (${_identifyCountdown}s)'
                        : 'Nhận diện (Nhấp nháy LED 15s)'),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    key: const Key('setup_proof_input'),
                    controller: _setupProofController,
                    decoration: InputDecoration(
                      labelText: 'Mã PIN / Setup Proof (nếu có trên tem)',
                      hintText: 'Nhập mã bảo mật của thiết bị',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      prefixIcon: const Icon(Icons.password_rounded),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],

        const SizedBox(height: 24),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                key: const Key('step2_back_button'),
                onPressed: () => setState(() => _currentStep = 0),
                child: const Text('Quay lại'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                key: const Key('step2_next_button'),
                // CRITICAL F1 FIX: Disabled if no candidate or candidate is expired
                onPressed:
                    canContinue ? () => setState(() => _currentStep = 2) : null,
                child: const Text('Tiếp tục'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildSubBoxProvisioningForm(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Cấu hình SubBox qua SoftAP',
          style: theme.textTheme.headlineSmall
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        Text(
          'Kết nối với Wi-Fi SoftAP của SubBox và nhập thông tin Wi-Fi nhà để cấu hình.',
          style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 20),
        TextField(
          key: const Key('subbox_ssid_input'),
          controller: _subboxSsidController,
          decoration: InputDecoration(
            labelText: 'Tên Wi-Fi nhà (SSID 2.4GHz)',
            prefixIcon: const Icon(Icons.wifi_rounded),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('subbox_password_input'),
          controller: _subboxPasswordController,
          obscureText: true,
          decoration: InputDecoration(
            labelText: 'Mật khẩu Wi-Fi',
            prefixIcon: const Icon(Icons.lock_rounded),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('subbox_pop_input'),
          controller: _subboxPopController,
          decoration: InputDecoration(
            labelText: 'Mã POP (Proof-of-Possession)',
            prefixIcon: const Icon(Icons.security_rounded),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 16),
        if (_subboxStatusMessage.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(
              _subboxStatusMessage,
              style: TextStyle(color: theme.colorScheme.primary, fontSize: 13),
            ),
          ),
        FilledButton(
          key: const Key('provision_subbox_button'),
          onPressed: _isProvisioningSubbox ? null : _provisionSubBox,
          child: _isProvisioningSubbox
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Text('Cấu hình SubBox'),
        ),
        const SizedBox(height: 12),
        OutlinedButton(
          onPressed: () => setState(() => _currentStep = 0),
          child: const Text('Quay lại'),
        ),
      ],
    );
  }

  // ==========================================
  // BƯỚC 3: ĐẶT TÊN, PHÒNG & KÊNH
  // ==========================================
  Widget _buildStep3Configuration(ThemeData theme) {
    final gateway = ref.watch(gatewayClientProvider);

    final roomOptions = <String, String>{
      'livingroom': 'Phòng khách',
      'bedroom': 'Phòng ngủ',
      'kitchen': 'Phòng bếp',
      'bathroom': 'Phòng tắm',
      'balcony': 'Ban công',
      'garden': 'Sân vườn',
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Bước 3: Đặt tên, Phòng & Kênh',
          style: theme.textTheme.headlineSmall
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 4),
        Text(
          'Cấu hình tên gọi, phòng lắp đặt và 3 kênh điều khiển cho ActionBox V2.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),

        // ActionBox Name
        TextField(
          key: const Key('box_name_input'),
          controller: _boxNameController,
          decoration: InputDecoration(
            labelText: 'Tên bộ điều khiển',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            prefixIcon: const Icon(Icons.badge_rounded),
          ),
        ),
        const SizedBox(height: 16),

        // Room Selection
        DropdownButtonFormField<String>(
          key: const Key('room_selector'),
          isExpanded: true,
          value: roomOptions.containsKey(_selectedRoomId)
              ? _selectedRoomId
              : 'livingroom',
          decoration: InputDecoration(
            labelText: 'Phòng lắp đặt',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            prefixIcon: const Icon(Icons.meeting_room_rounded),
          ),
          items: roomOptions.entries.map((entry) {
            return DropdownMenuItem(
              value: entry.key,
              child: Text(entry.value),
            );
          }).toList(),
          onChanged: (val) {
            if (val != null) {
              setState(() {
                _selectedRoomId = val;
                _selectedRoomName = roomOptions[val] ?? val;
              });
            }
          },
        ),
        const SizedBox(height: 16),

        // SubBox Route Selection
        if (gateway.onlineSubBoxes.isNotEmpty)
          DropdownButtonFormField<String>(
            key: const Key('subbox_route_selector'),
            isExpanded: true,
            value: _selectedSubboxId.isNotEmpty &&
                    gateway.onlineSubBoxes
                        .any((sb) => (sb['id'] ?? '') == _selectedSubboxId)
                ? _selectedSubboxId
                : (gateway.onlineSubBoxes.first['id']?.toString() ?? ''),
            decoration: InputDecoration(
              labelText: 'Trạm SubBox thu phát',
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              prefixIcon: const Icon(Icons.router_rounded),
            ),
            items: gateway.onlineSubBoxes.map((sb) {
              final id = sb['id']?.toString() ?? '';
              final name = sb['name']?.toString() ?? id;
              return DropdownMenuItem(
                value: id,
                child: Text('$name ($id)'),
              );
            }).toList(),
            onChanged: (val) {
              if (val != null) setState(() => _selectedSubboxId = val);
            },
          ),
        const SizedBox(height: 24),

        Text(
          'Cấu hình 3 kênh điều khiển (Relays):',
          style: theme.textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),

        // Channel 1
        _buildChannelCard(
          theme: theme,
          channelNumber: 1,
          nameController: _ch1NameController,
          nameInputKey: const Key('ch1_name_input'),
          typeDropdownKey: const Key('ch1_type_dropdown'),
          type: _ch1Type,
          onTypeChanged: (t) => setState(() => _ch1Type = t),
          aliases: _ch1Aliases,
          newAliasController: _ch1NewAliasController,
          newAliasInputKey: const Key('ch1_new_alias_input'),
          addAliasButtonKey: const Key('ch1_add_alias_button'),
        ),
        const SizedBox(height: 14),

        // Channel 2
        _buildChannelCard(
          theme: theme,
          channelNumber: 2,
          nameController: _ch2NameController,
          nameInputKey: const Key('ch2_name_input'),
          typeDropdownKey: const Key('ch2_type_dropdown'),
          type: _ch2Type,
          onTypeChanged: (t) => setState(() => _ch2Type = t),
          aliases: _ch2Aliases,
          newAliasController: _ch2NewAliasController,
          newAliasInputKey: const Key('ch2_new_alias_input'),
          addAliasButtonKey: const Key('ch2_add_alias_button'),
        ),
        const SizedBox(height: 14),

        // Channel 3 - Latching Relay
        _buildChannelCard(
          theme: theme,
          channelNumber: 3,
          isLatching: true,
          nameController: _ch3NameController,
          nameInputKey: const Key('ch3_name_input'),
          typeDropdownKey: const Key('ch3_type_dropdown'),
          type: _ch3Type,
          onTypeChanged: (t) => setState(() => _ch3Type = t),
          aliases: _ch3Aliases,
          newAliasController: _ch3NewAliasController,
          newAliasInputKey: const Key('ch3_new_alias_input'),
          addAliasButtonKey: const Key('ch3_add_alias_button'),
        ),
        const SizedBox(height: 20),

        // Collapsible Technical Diagnostics
        Card(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          elevation: 0,
          color: theme.colorScheme.surfaceVariant.withOpacity(0.35),
          child: ExpansionTile(
            initiallyExpanded: false,
            title: const Text(
              'Thông tin kỹ thuật / Chẩn đoán',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
            ),
            childrenPadding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            children: [
              _buildDiagRow(
                  'Device UID', _selectedCandidate?.deviceUid ?? 'N/A'),
              _buildDiagRow('Model', _selectedCandidate?.boardModel ?? 'N/A'),
              _buildDiagRow(
                  'Revision', _selectedCandidate?.boardRevision ?? 'N/A'),
              _buildDiagRow('Protocol Version',
                  'v${_selectedCandidate?.protocolVersion ?? 2}'),
              _buildDiagRow(
                  'SubBox Route',
                  _selectedSubboxId.isNotEmpty
                      ? _selectedSubboxId
                      : (_selectedCandidate?.subboxId ?? 'N/A')),
              _buildDiagRow('RSSI', '${_selectedCandidate?.rssi ?? 0} dBm'),
              _buildDiagRow('Capabilities',
                  _selectedCandidate?.capabilities.join(', ') ?? 'N/A'),
            ],
          ),
        ),

        const SizedBox(height: 24),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                key: const Key('step3_back_button'),
                onPressed: () => setState(() => _currentStep = 1),
                child: const Text('Quay lại'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                key: const Key('step3_next_button'),
                onPressed: () => setState(() => _currentStep = 3),
                child: const Text('Tiếp tục'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildChannelCard({
    required ThemeData theme,
    required int channelNumber,
    bool isLatching = false,
    required TextEditingController nameController,
    required Key nameInputKey,
    required Key typeDropdownKey,
    required DeviceType type,
    required ValueChanged<DeviceType> onTypeChanged,
    required List<String> aliases,
    required TextEditingController newAliasController,
    required Key newAliasInputKey,
    required Key addAliasButtonKey,
  }) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      elevation: 0,
      color: theme.colorScheme.surfaceVariant.withOpacity(0.4),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    'Kênh $channelNumber',
                    style: TextStyle(
                      color: theme.colorScheme.onPrimary,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    isLatching
                        ? 'Rơ-le chốt (Latching Relay)'
                        : 'Rơ-le tiêu chuẩn',
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                ),
              ],
            ),
            if (isLatching) ...[
              const SizedBox(height: 10),
              Container(
                key: const Key('ch3_latching_badge'),
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.amber.shade50,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.amber.shade300),
                ),
                child: Row(
                  children: [
                    Icon(Icons.lock_clock_rounded,
                        color: Colors.amber.shade900, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Kênh 3 - Rơ-le chốt (Latching), giữ trạng thái khi mất điện',
                        style: TextStyle(
                          color: Colors.amber.shade900,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 12),
            TextField(
              key: nameInputKey,
              controller: nameController,
              decoration: InputDecoration(
                labelText: 'Tên thiết bị kênh $channelNumber',
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 10),
            DropdownButtonFormField<DeviceType>(
              key: typeDropdownKey,
              isExpanded: true,
              value: type,
              decoration: InputDecoration(
                labelText: 'Loại tải điện',
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
              items: const [
                DropdownMenuItem(
                  value: DeviceType.light,
                  child: Text('Đèn (Light)'),
                ),
                DropdownMenuItem(
                  value: DeviceType.fan,
                  child: Text('Quạt (Fan)'),
                ),
                DropdownMenuItem(
                  value: DeviceType.socket,
                  child: Text('Ổ cắm / Công tắc (Socket/Switch)'),
                ),
                DropdownMenuItem(
                  value: DeviceType.airConditioner,
                  child: Text('Điều hòa (Air Conditioner)'),
                ),
              ],
              onChanged: (val) {
                if (val != null) onTypeChanged(val);
              },
            ),
            const SizedBox(height: 12),
            Text(
              'Bí danh giọng nói (Voice Aliases):',
              style: TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 12,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: aliases.map((alias) {
                return Chip(
                  label: Text(alias, style: const TextStyle(fontSize: 12)),
                  deleteIcon: const Icon(Icons.close_rounded, size: 14),
                  onDeleted: () {
                    setState(() => aliases.remove(alias));
                  },
                );
              }).toList(),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: newAliasInputKey,
                    controller: newAliasController,
                    decoration: InputDecoration(
                      hintText: 'Thêm bí danh khẩu lệnh mới...',
                      isDense: true,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                IconButton.filledTonal(
                  key: addAliasButtonKey,
                  icon: const Icon(Icons.add_rounded, size: 20),
                  onPressed: () {
                    final text = newAliasController.text.trim();
                    if (text.isNotEmpty && !aliases.contains(text)) {
                      setState(() {
                        aliases.add(text);
                        newAliasController.clear();
                      });
                    }
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDiagRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Text(label,
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ),
          const SizedBox(width: 8),
          Text(value,
              style:
                  const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  // ==========================================
  // BƯỚC 4: LƯU CẤU HÌNH & XÁC NHẬN
  // ==========================================
  Widget _buildStep4Confirmation(ThemeData theme) {
    if (_isSuccess) {
      return Container(
        key: const Key('claim_success_view'),
        padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(
              Icons.check_circle_rounded,
              color: Color(0xFF43A047),
              size: 80,
            ),
            const SizedBox(height: 20),
            Text(
              'Đã thêm thành công!',
              textAlign: TextAlign.center,
              style: theme.textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Text(
              'Thiết bị "${_boxNameController.text}" đã được lưu cấu hình an toàn trên flash và sẵn sàng điều khiển.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: theme.colorScheme.onSurfaceVariant,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 24),
            Card(
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16)),
              elevation: 0,
              color: theme.colorScheme.surfaceVariant.withOpacity(0.35),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    if (_deviceTarget == DeviceTarget.subBox) ...[
                      _buildSummaryRow(
                          'Loại thiết bị',
                          'SubBox (Bộ trung tâm phòng / Mesh router)',
                          Icons.router_rounded),
                      _buildSummaryRow('Phòng', _selectedRoomName,
                          Icons.meeting_room_rounded),
                      _buildSummaryRow(
                          'Wi-Fi kết nối',
                          _subboxSsidController.text.isNotEmpty
                              ? _subboxSsidController.text
                              : 'Đã kết nối',
                          Icons.wifi_rounded),
                    ] else ...[
                      _buildSummaryRow('Phòng', _selectedRoomName,
                          Icons.meeting_room_rounded),
                      _buildSummaryRow(
                          'Kênh 1',
                          '${_ch1NameController.text} (${_deviceTypeLabel(_ch1Type)})',
                          Icons.lightbulb_rounded),
                      _buildSummaryRow(
                          'Kênh 2',
                          '${_ch2NameController.text} (${_deviceTypeLabel(_ch2Type)})',
                          Icons.mode_fan_off_rounded),
                      _buildSummaryRow(
                          'Kênh 3',
                          '${_ch3NameController.text} (${_deviceTypeLabel(_ch3Type)} - Rơ-le chốt)',
                          Icons.bolt_rounded),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),
            FilledButton(
              key: const Key('go_home_button'),
              onPressed: _navigateHome,
              child: const Text('Về trang chủ'),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Bước 4: Lưu cấu hình & Xác nhận',
          style: theme.textTheme.headlineSmall
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 4),
        Text(
          'Vui lòng kiểm tra lại thông tin trước khi gửi cấu hình tới thiết bị.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),

        // Summary Card
        Card(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          elevation: 0,
          color: theme.colorScheme.surfaceVariant.withOpacity(0.4),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Tóm tắt thông tin đã cấu hình:',
                  style: theme.textTheme.titleSmall
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 14),
                if (_deviceTarget == DeviceTarget.subBox) ...[
                  _buildSummaryRow('Thiết bị', 'SubBox Controller',
                      Icons.developer_board_rounded),
                  _buildSummaryRow(
                      'Phòng', _selectedRoomName, Icons.meeting_room_rounded),
                  _buildSummaryRow(
                      'Wi-Fi',
                      _subboxSsidController.text.isNotEmpty
                          ? _subboxSsidController.text
                          : 'Mạng đã chọn',
                      Icons.wifi_rounded),
                ] else ...[
                  _buildSummaryRow(
                      'Thiết bị',
                      '${_selectedCandidate?.boardModel.toUpperCase()} (${_selectedCandidate?.deviceUid})',
                      Icons.developer_board_rounded),
                  _buildSummaryRow('Tên bộ điều khiển', _boxNameController.text,
                      Icons.badge_rounded),
                  _buildSummaryRow(
                      'Phòng', _selectedRoomName, Icons.meeting_room_rounded),
                  _buildSummaryRow(
                      'SubBox Route',
                      _selectedSubboxId.isNotEmpty
                          ? _selectedSubboxId
                          : (_selectedCandidate?.subboxId ?? 'Tự động'),
                      Icons.router_rounded),
                  const Divider(height: 20),
                  _buildSummaryRow(
                      'Kênh 1',
                      '${_ch1NameController.text} (${_deviceTypeLabel(_ch1Type)}) - Khẩu lệnh: ${_ch1Aliases.join(', ')}',
                      Icons.power_rounded),
                  const SizedBox(height: 6),
                  _buildSummaryRow(
                      'Kênh 2',
                      '${_ch2NameController.text} (${_deviceTypeLabel(_ch2Type)}) - Khẩu lệnh: ${_ch2Aliases.join(', ')}',
                      Icons.power_rounded),
                  const SizedBox(height: 6),
                  _buildSummaryRow(
                      'Kênh 3',
                      '${_ch3NameController.text} (${_deviceTypeLabel(_ch3Type)} - Rơ-le chốt) - Khẩu lệnh: ${_ch3Aliases.join(', ')}',
                      Icons.lock_clock_rounded),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),

        // Error Banner if previous submit failed
        if (_errorMessage != null)
          Container(
            key: const Key('claim_error_banner'),
            margin: const EdgeInsets.only(bottom: 16),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.red.shade50,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.red.shade300, width: 1.5),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.error_outline_rounded,
                        color: Colors.red.shade700, size: 24),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Thao tác thêm thất bại',
                        style: TextStyle(
                          color: Colors.red.shade900,
                          fontWeight: FontWeight.bold,
                          fontSize: 15,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  _errorMessage!,
                  style: TextStyle(color: Colors.red.shade900, fontSize: 13),
                ),
                const SizedBox(height: 8),
                Text(
                  'Toàn bộ dữ liệu bạn đã nhập vẫn được giữ nguyên. Bạn có thể nhấn "Thử lại" hoặc "Quay lại chỉnh sửa".',
                  style: TextStyle(
                    color: Colors.red.shade800,
                    fontSize: 12,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ),
          ),

        // In-progress submission indicator
        if (_isSubmitting)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 24),
            child: const Column(
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text(
                  'Đang gửi cấu hình và chờ phản hồi (ACK)...',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                SizedBox(height: 6),
                Text(
                  'Vui lòng không ngắt nguồn ActionBox hoặc đóng app.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ),

        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                key: const Key('step4_back_button'),
                onPressed: _isSubmitting
                    ? null
                    : () => setState(() {
                          _currentStep = 2;
                          _errorMessage = null;
                        }),
                child: const Text('Quay lại chỉnh sửa'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                key: const Key('confirm_claim_button'),
                onPressed: _isSubmitting ? null : _executeClaim,
                child: Text(_errorMessage != null
                    ? 'Thử lại'
                    : 'Xác nhận & Thêm thiết bị'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildSummaryRow(String label, String value, IconData icon) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: Colors.grey.shade600),
          const SizedBox(width: 10),
          Text(
            '$label: ',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _InstructionBullet extends StatelessWidget {
  final String number;
  final String text;

  const _InstructionBullet({
    required this.number,
    required this.text,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            color: theme.colorScheme.primary,
            shape: BoxShape.circle,
          ),
          child: Center(
            child: Text(
              number,
              style: TextStyle(
                color: theme.colorScheme.onPrimary,
                fontWeight: FontWeight.bold,
                fontSize: 12,
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(fontSize: 13, height: 1.4),
          ),
        ),
      ],
    );
  }
}
