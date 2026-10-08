import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../models/device.dart';
import '../../providers/smart_home_providers.dart';
import '../../services/gateway_client.dart';

class AddDeviceFlowScreen extends ConsumerStatefulWidget {
  const AddDeviceFlowScreen({super.key});

  @override
  ConsumerState<AddDeviceFlowScreen> createState() => _AddDeviceFlowScreenState();
}

class _AddDeviceFlowScreenState extends ConsumerState<AddDeviceFlowScreen>
    with SingleTickerProviderStateMixin {
  final PageController _pageController = PageController();
  int _currentStep = 0;
  bool _isSubmitting = false;

  // Selected hardware info
  String _selectedBoxModel = 'ESP32-S3 Voice ActionBox';
  String _selectedBoxId = '';
  String _selectedMac = '';
  String _boxName = 'ActionBox Phòng Khách';

  // Room selection
  String _selectedRoomId = 'livingroom';
  String _selectedRoomName = 'Phòng khách';

  // 2 Hardware channels (ESP32-S3 physical relays: ch1, ch2)
  final List<String> _channelNames = [
    'Đèn chính',
    'Quạt trần',
  ];

  final List<DeviceType> _channelTypes = [
    DeviceType.light,
    DeviceType.fan,
  ];

  final List<List<String>> _channelAliases = [
    ['đèn chính', 'đèn phòng'],
    ['quạt trần', 'quạt số 1'],
  ];

  late AnimationController _pulseController;
  late TextEditingController _boxNameController;
  late TextEditingController _ch1NameController;
  late TextEditingController _ch2NameController;

  @override
  void initState() {
    super.initState();
    _boxNameController = TextEditingController(text: _boxName);
    _ch1NameController = TextEditingController(text: _channelNames[0]);
    _ch2NameController = TextEditingController(text: _channelNames[1]);

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _pageController.dispose();
    _boxNameController.dispose();
    _ch1NameController.dispose();
    _ch2NameController.dispose();
    super.dispose();
  }

  void _nextStep() {
    HapticFeedback.lightImpact();

    // Guard step 1 -> step 2
    if (_currentStep == 0) {
      // Trigger scan
      ref.read(gatewayClientProvider).refresh();
    }

    // Guard step 2 -> step 3 (must have selected a pending device or allow retry)
    if (_currentStep == 1) {
      final gateway = ref.read(gatewayClientProvider);
      if (gateway.pending.isEmpty && _selectedBoxId.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Vui lòng đưa ActionBox vào chế độ ghép nối hoặc nhấn "Quét lại".'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        return;
      }
    }

    if (_currentStep < 8) {
      setState(() => _currentStep++);
      _pageController.animateToPage(
        _currentStep,
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeInOutCubic,
      );
    } else {
      _finishOnboarding();
    }
  }

  void _prevStep() {
    HapticFeedback.lightImpact();
    if (_currentStep > 0) {
      setState(() => _currentStep--);
      _pageController.animateToPage(
        _currentStep,
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeInOutCubic,
      );
    } else {
      context.pop();
    }
  }

  Future<void> _finishOnboarding() async {
    if (_isSubmitting) return;
    setState(() => _isSubmitting = true);
    HapticFeedback.heavyImpact();

    final gateway = ref.read(gatewayClientProvider);

    try {
      String relayTypeStr(DeviceType t) => switch (t) {
            DeviceType.light => 'light',
            DeviceType.fan => 'fan',
            DeviceType.socket => 'switch',
            _ => 'light',
          };

      final targetDevId = _selectedBoxId.isNotEmpty
          ? _selectedBoxId
          : 'node_${DateTime.now().millisecondsSinceEpoch % 10000}';
      final targetMac = _selectedMac.isNotEmpty ? _selectedMac : targetDevId;

      await gateway.provisionDevice(
        deviceId: targetDevId,
        mac: targetMac,
        name: _boxNameController.text.trim().isNotEmpty
            ? _boxNameController.text.trim()
            : _boxName,
        room: _selectedRoomId,
        location: _selectedRoomName,
        rl1: relayTypeStr(_channelTypes[0]),
        rl2: relayTypeStr(_channelTypes[1]),
      );

      // Also persist channel names and voice aliases if specified
      try {
        await gateway.updateDevice(
          deviceId: targetDevId,
          ch1Name: _ch1NameController.text.trim().isNotEmpty
              ? _ch1NameController.text.trim()
              : _channelNames[0],
          ch1Aliases: _channelAliases[0],
          ch2Name: _ch2NameController.text.trim().isNotEmpty
              ? _ch2NameController.text.trim()
              : _channelNames[1],
          ch2Aliases: _channelAliases[1],
        );
      } catch (_) {
        // Name update is best-effort if provision succeeded
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text('Đã gán thành công ${_boxNameController.text} vào $_selectedRoomName'),
                ),
              ],
            ),
            backgroundColor: const Color(0xFF43A047),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          ),
        );
        context.go('/home');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Lỗi ghép nối: $e'),
            backgroundColor: Theme.of(context).colorScheme.error,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final gateway = ref.watch(gatewayClientProvider);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1E242B) : Colors.white,
              shape: BoxShape.circle,
              border: Border.all(
                color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
              ),
            ),
            child: Icon(
              Icons.arrow_back_ios_new_rounded,
              size: 16,
              color: theme.colorScheme.onSurface,
            ),
          ),
          onPressed: _prevStep,
        ),
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (int i = 0; i < 9; i++)
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                margin: const EdgeInsets.symmetric(horizontal: 2.5),
                height: 5,
                width: _currentStep == i ? 18 : 6,
                decoration: BoxDecoration(
                  color: _currentStep == i
                      ? theme.colorScheme.primary
                      : (isDark ? Colors.white24 : Colors.black12),
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
          ],
        ),
        centerTitle: true,
        actions: [
          TextButton(
            onPressed: () => context.pop(),
            child: Text(
              'Hủy',
              style: TextStyle(
                color: theme.colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: PageView(
          controller: _pageController,
          physics: const NeverScrollableScrollPhysics(),
          children: [
            _buildStep1Search(theme, isDark, gateway),
            _buildStep2Select(theme, isDark, gateway),
            _buildStep3Connecting(theme, isDark),
            _buildStep4Connected(theme, isDark),
            _buildStep5SelectRoom(theme, isDark),
            _buildStep6ConfigureChannels(theme, isDark),
            _buildStep7NameDevices(theme, isDark),
            _buildStep8VoiceAliases(theme, isDark),
            _buildStep9Finish(theme, isDark),
          ],
        ),
      ),
      bottomNavigationBar: Container(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        decoration: BoxDecoration(
          color: theme.scaffoldBackgroundColor,
          border: Border(
            top: BorderSide(
              color: isDark ? Colors.white.withOpacity(0.05) : Colors.black.withOpacity(0.04),
            ),
          ),
        ),
        child: SizedBox(
          width: double.infinity,
          height: 54,
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: theme.colorScheme.onPrimary,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),
            ),
            onPressed: _isSubmitting ? null : _nextStep,
            child: _isSubmitting
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
                  )
                : Text(
                    _currentStep == 0
                        ? 'Bắt đầu quét thiết bị'
                        : _currentStep == 8
                            ? 'Hoàn tất & Khám phá'
                            : 'Tiếp tục',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
          ),
        ),
      ),
    );
  }

  // STEP 1: Search
  Widget _buildStep1Search(ThemeData theme, bool isDark, GatewayClient gateway) {
    return _StepContainer(
      icon: Icons.wifi_tethering_rounded,
      iconColor: theme.colorScheme.primary,
      title: 'Tìm kiếm bộ điều khiển',
      subtitle:
          'Đảm bảo ActionBox hoặc SubBox đã được cấp nguồn và đèn LED trạng thái đang nhấp nháy.',
      child: Column(
        children: [
          Center(
            child: AnimatedBuilder(
              animation: _pulseController,
              builder: (context, child) {
                return Container(
                  width: 140 + (_pulseController.value * 20),
                  height: 140 + (_pulseController.value * 20),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: theme.colorScheme.primary
                        .withOpacity(0.08 + (_pulseController.value * 0.08)),
                  ),
                  child: Center(
                    child: Container(
                      width: 90,
                      height: 90,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: theme.colorScheme.primary.withOpacity(0.2),
                      ),
                      child: Icon(
                        Icons.bluetooth_searching_rounded,
                        size: 42,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 28),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1E242B) : const Color(0xFFF1F5F9),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline_rounded,
                    size: 20, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Trạng thái Gateway: ${gateway.connected ? "Đã kết nối (${gateway.serverUrl})" : "Đang ngoại tuyến"}',
                    style: TextStyle(
                      fontSize: 12,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // STEP 2: Select ActionBox / SubBox
  Widget _buildStep2Select(ThemeData theme, bool isDark, GatewayClient gateway) {
    final pendingNodes = gateway.pending;

    if (pendingNodes.isEmpty) {
      return _StepContainer(
        icon: Icons.search_off_rounded,
        iconColor: const Color(0xFFFB8C00),
        title: 'Chưa phát hiện thiết bị',
        subtitle:
            'Chưa có ActionBox nào đang ở chế độ chờ ghép nối (Provisioning mode).',
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E242B) : Colors.white,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Hướng dẫn kích hoạt chế độ ghép nối:',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                  ),
                  const SizedBox(height: 10),
                  _buildGuideBullet('1. Cấp nguồn 220V/5V cho ActionBox ESP32-S3.'),
                  _buildGuideBullet(
                      '2. Nhấn giữ nút BUT1 (hoặc nút BOOT) trên bo mạch trong 10 giây cho đến khi đèn LED nhấp nháy xanh nhanh.'),
                  _buildGuideBullet('3. Đảm bảo thiết bị và Gateway cùng trong vùng phủ sóng Wi-Fi.'),
                ],
              ),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
              onPressed: () async {
                HapticFeedback.lightImpact();
                await gateway.refresh();
              },
              icon: gateway.loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh_rounded),
              label: Text(gateway.loading ? 'Đang quét...' : 'Quét lại mạng'),
            ),
          ],
        ),
      );
    }

    return _StepContainer(
      icon: Icons.developer_board_rounded,
      iconColor: const Color(0xFF43A047),
      title: 'Chọn bộ điều khiển',
      subtitle: 'Tìm thấy ${pendingNodes.length} thiết bị mới đang chờ kết nối.',
      child: Column(
        children: pendingNodes.entries.map((entry) {
          final p = asMap(entry.value);
          final devId = (p['device_id'] ?? entry.key).toString();
          final mac = (p['mac'] ?? entry.key).toString();
          final hw = (p['hardware'] ?? 'ESP32-S3 ActionBox').toString();
          final ip = p['ip']?.toString() ?? 'Chưa gán IP';
          final rssi = p['rssi'] != null ? '${p['rssi']} dBm' : 'Tốt';

          final isSelected = _selectedBoxId == devId;

          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: _DeviceFoundCard(
              title: '$hw ($devId)',
              subtitle: 'MAC: $mac · IP: $ip · Tín hiệu: $rssi',
              isSelected: isSelected,
              onTap: () {
                setState(() {
                  _selectedBoxId = devId;
                  _selectedMac = mac;
                  _selectedBoxModel = hw;
                  _boxName = 'ActionBox $_selectedRoomName';
                  _boxNameController.text = _boxName;
                });
              },
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildGuideBullet(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('• ', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
          Expanded(
            child: Text(text, style: const TextStyle(fontSize: 13, height: 1.35)),
          ),
        ],
      ),
    );
  }

  // STEP 3: Connecting
  Widget _buildStep3Connecting(ThemeData theme, bool isDark) {
    return _StepContainer(
      icon: Icons.sync_rounded,
      iconColor: const Color(0xFF1E88E5),
      title: 'Đang kết nối an toàn',
      subtitle:
          'Hệ thống đang cấu hình mã hóa WPA/TLS và đồng bộ với ${_selectedBoxId.isNotEmpty ? _selectedBoxId : "thiết bị"}...',
      child: const Center(
        child: Padding(
          padding: EdgeInsets.all(40),
          child: CircularProgressIndicator(strokeWidth: 3),
        ),
      ),
    );
  }

  // STEP 4: Connected
  Widget _buildStep4Connected(ThemeData theme, bool isDark) {
    return _StepContainer(
      icon: Icons.check_circle_rounded,
      iconColor: const Color(0xFF43A047),
      title: 'Kết nối thành công!',
      subtitle:
          'Đã nhận diện phần cứng ESP32-S3 với 2 rơ-le độc lập và cảm biến đo năng lượng PZEM-004T.',
      child: Center(
        child: Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: const Color(0xFF43A047).withOpacity(0.12),
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.verified_rounded,
            size: 64,
            color: Color(0xFF43A047),
          ),
        ),
      ),
    );
  }

  // STEP 5: Select Room
  Widget _buildStep5SelectRoom(ThemeData theme, bool isDark) {
    final rooms = [
      {'id': 'livingroom', 'name': 'Phòng khách', 'icon': Icons.weekend_rounded},
      {'id': 'bedroom', 'name': 'Phòng ngủ', 'icon': Icons.bed_rounded},
      {'id': 'kitchen', 'name': 'Phòng bếp', 'icon': Icons.kitchen_rounded},
      {'id': 'office', 'name': 'Phòng làm việc', 'icon': Icons.computer_rounded},
    ];

    return _StepContainer(
      icon: Icons.room_preferences_rounded,
      iconColor: const Color(0xFFE65100),
      title: 'Đặt thiết bị vào phòng',
      subtitle: 'Chọn không gian để gom nhóm các thiết bị giúp quản lý trực quan.',
      child: Wrap(
        spacing: 12,
        runSpacing: 12,
        children: rooms.map((r) {
          final isSel = _selectedRoomId == r['id'];
          return InkWell(
            borderRadius: BorderRadius.circular(20),
            onTap: () {
              setState(() {
                _selectedRoomId = r['id'] as String;
                _selectedRoomName = r['name'] as String;
                _boxName = 'ActionBox $_selectedRoomName';
                _boxNameController.text = _boxName;
              });
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: 156,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
              decoration: BoxDecoration(
                color: isSel
                    ? theme.colorScheme.primary.withOpacity(0.1)
                    : (isDark ? const Color(0xFF1E242B) : Colors.white),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: isSel
                      ? theme.colorScheme.primary
                      : (isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06)),
                  width: isSel ? 2 : 1,
                ),
              ),
              child: Column(
                children: [
                  Icon(
                    r['icon'] as IconData,
                    size: 32,
                    color: isSel ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    r['name'] as String,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: isSel ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                    ),
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  // STEP 6: Configure Channels (2 physical relays)
  Widget _buildStep6ConfigureChannels(ThemeData theme, bool isDark) {
    return _StepContainer(
      icon: Icons.tune_rounded,
      iconColor: const Color(0xFF7B1FA2),
      title: 'Cấu hình 2 cổng rơ-le',
      subtitle:
          'ESP32-S3 ActionBox trang bị 2 kênh rơ-le vật lý (Kênh 1: GPIO 4, Kênh 2: GPIO 5).',
      child: Column(
        children: List.generate(2, (index) {
          return Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1E242B) : Colors.white,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
              ),
            ),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: theme.colorScheme.primary.withOpacity(0.12),
                  child: Text(
                    '${index + 1}',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Kênh ${index + 1} (${index == 0 ? "GPIO 4" : "GPIO 5"})',
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        'Tải kết nối: ${_channelTypes[index].name}',
                        style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                DropdownButton<DeviceType>(
                  value: _channelTypes[index],
                  underline: const SizedBox(),
                  borderRadius: BorderRadius.circular(16),
                  items: const [
                    DropdownMenuItem(value: DeviceType.light, child: Text('Đèn (Light)')),
                    DropdownMenuItem(value: DeviceType.fan, child: Text('Quạt (Fan)')),
                    DropdownMenuItem(value: DeviceType.socket, child: Text('Ổ cắm (Socket)')),
                    DropdownMenuItem(
                        value: DeviceType.airConditioner, child: Text('Điều hòa (AC)')),
                  ],
                  onChanged: (val) {
                    if (val != null) {
                      setState(() => _channelTypes[index] = val);
                    }
                  },
                ),
              ],
            ),
          );
        }),
      ),
    );
  }

  // STEP 7: Name Devices
  Widget _buildStep7NameDevices(ThemeData theme, bool isDark) {
    return _StepContainer(
      icon: Icons.edit_note_rounded,
      iconColor: const Color(0xFF00897B),
      title: 'Đặt tên thiết bị',
      subtitle: 'Tên ngắn gọn, dễ nhớ giúp bạn thao tác nhanh và nhận diện giọng nói chính xác.',
      child: Column(
        children: [
          Container(
            margin: const EdgeInsets.only(bottom: 12),
            child: TextField(
              controller: _boxNameController,
              decoration: InputDecoration(
                labelText: 'Tên bộ ActionBox',
                filled: true,
                fillColor: isDark ? const Color(0xFF1E242B) : Colors.white,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(18),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),
          Container(
            margin: const EdgeInsets.only(bottom: 12),
            child: TextField(
              controller: _ch1NameController,
              decoration: InputDecoration(
                labelText: 'Kênh 1 (${_channelTypes[0].name})',
                filled: true,
                fillColor: isDark ? const Color(0xFF1E242B) : Colors.white,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(18),
                  borderSide: BorderSide.none,
                ),
              ),
              onChanged: (text) => _channelNames[0] = text,
            ),
          ),
          Container(
            margin: const EdgeInsets.only(bottom: 12),
            child: TextField(
              controller: _ch2NameController,
              decoration: InputDecoration(
                labelText: 'Kênh 2 (${_channelTypes[1].name})',
                filled: true,
                fillColor: isDark ? const Color(0xFF1E242B) : Colors.white,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(18),
                  borderSide: BorderSide.none,
                ),
              ),
              onChanged: (text) => _channelNames[1] = text,
            ),
          ),
        ],
      ),
    );
  }

  // STEP 8: Voice Aliases
  Widget _buildStep8VoiceAliases(ThemeData theme, bool isDark) {
    return _StepContainer(
      icon: Icons.record_voice_over_rounded,
      iconColor: const Color(0xFFD81B60),
      title: 'Khẩu lệnh điều khiển giọng nói',
      subtitle: 'Trợ lý ảo ngoại tuyến sẽ nhận diện các cụm từ này để bật/tắt thiết bị tức thì.',
      child: Column(
        children: List.generate(2, (index) {
          final devName = index == 0 ? _ch1NameController.text : _ch2NameController.text;
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1E242B) : Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  devName.isNotEmpty ? devName : 'Kênh ${index + 1}',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: _channelAliases[index].map((alias) {
                    return Chip(
                      label: Text(alias, style: const TextStyle(fontSize: 11)),
                      backgroundColor: theme.colorScheme.primary.withOpacity(0.08),
                      side: BorderSide.none,
                      padding: EdgeInsets.zero,
                    );
                  }).toList(),
                ),
              ],
            ),
          );
        }),
      ),
    );
  }

  // STEP 9: Finish
  Widget _buildStep9Finish(ThemeData theme, bool isDark) {
    final name1 = _ch1NameController.text.isNotEmpty ? _ch1NameController.text : _channelNames[0];
    final name2 = _ch2NameController.text.isNotEmpty ? _ch2NameController.text : _channelNames[1];

    return _StepContainer(
      icon: Icons.rocket_launch_rounded,
      iconColor: const Color(0xFF43A047),
      title: 'Tất cả đã sẵn sàng!',
      subtitle:
          '${_boxNameController.text} ($_selectedBoxModel) sẽ được tích hợp vào $_selectedRoomName với 2 kênh tải độc lập.',
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1E242B) : Colors.white,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
          ),
        ),
        child: Column(
          children: [
            _buildReviewChannel(1, name1, _channelTypes[0], theme),
            const Divider(height: 16),
            _buildReviewChannel(2, name2, _channelTypes[1], theme),
          ],
        ),
      ),
    );
  }

  Widget _buildReviewChannel(int channelNum, String name, DeviceType type, ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          const Icon(Icons.check_circle_rounded, size: 18, color: Color(0xFF43A047)),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                ),
                Text(
                  'Kênh $channelNum · ${type.name}',
                  style: TextStyle(
                    fontSize: 12,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          Text(
            _selectedRoomName,
            style: TextStyle(
              fontSize: 12,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _StepContainer extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final Widget child;

  const _StepContainer({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
      physics: const BouncingScrollPhysics(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: iconColor.withOpacity(0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, size: 36, color: iconColor),
          ),
          const SizedBox(height: 18),
          Text(
            title,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.4,
              color: theme.colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 13,
              height: 1.4,
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 32),
          child,
        ],
      ),
    );
  }
}

class _DeviceFoundCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final bool isSelected;
  final VoidCallback onTap;

  const _DeviceFoundCard({
    required this.title,
    required this.subtitle,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: isSelected
              ? theme.colorScheme.primary.withOpacity(0.08)
              : (isDark ? const Color(0xFF1E242B) : Colors.white),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected
                ? theme.colorScheme.primary
                : (isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06)),
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: isSelected
                    ? theme.colorScheme.primary.withOpacity(0.15)
                    : (isDark ? Colors.white10 : Colors.black.withOpacity(0.04)),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(
                Icons.memory_rounded,
                color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 12,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              isSelected ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded,
              color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant,
            ),
          ],
        ),
      ),
    );
  }
}
