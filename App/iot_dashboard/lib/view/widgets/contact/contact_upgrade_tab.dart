import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/contact/animated_order_button.dart';

class ContactUpgradeTab extends StatefulWidget {
  const ContactUpgradeTab({super.key});

  @override
  State<ContactUpgradeTab> createState() => _ContactUpgradeTabState();
}

class _ContactUpgradeTabState extends State<ContactUpgradeTab> {
  final _upgradeFormKey = GlobalKey<FormState>();

  // 1. Cảm biến công suất dòng
  bool _isCurrentSensorSelected = true;
  int _currentSensorQuantity = 1;
  String _currentSensorLocation = 'Tủ điện tổng (Main Panel)';
  final TextEditingController _customSensorLocationController =
      TextEditingController();

  // 2. Bộ Gateway trung tâm
  bool _isGatewaySelected = true;
  int _gatewayQuantity = 1;
  String _gatewayLocation = 'Phòng khách (Trung tâm nhà)';

  // Thông tin hẹn khảo sát & khách hàng
  String _selectedTargetRoom = 'Phòng khách';
  final DateTime _selectedSurveyDate =
      DateTime.now().add(const Duration(days: 2));
  String _selectedTimeSlot = '09:00 - 11:00 (Buổi sáng)';

  final TextEditingController _upgradeCustomerNameController =
      TextEditingController();
  final TextEditingController _upgradeCustomerPhoneController =
      TextEditingController();
  final TextEditingController _upgradeAddressController =
      TextEditingController();
  final TextEditingController _upgradeNoteController = TextEditingController();

  final List<String> _sensorLocationOptions = [
    'Tủ điện tổng (Main Panel)',
    'Tủ điện Tầng 1',
    'Tủ điện Tầng 2',
    'Tủ điện Tầng 3',
    'Aptomat tổng điều hòa / Bình nóng lạnh',
    'Vị trí tùy chỉnh...',
  ];

  final List<String> _gatewayLocationOptions = [
    'Phòng khách (Trung tâm nhà)',
    'Phòng Server / Kỹ thuật',
    'Tủ điện trung tâm',
    'Phòng làm việc',
  ];

  @override
  void initState() {
    super.initState();
    final user = currentUserNotifier.value;
    _upgradeCustomerNameController.text = user.name;
    _upgradeCustomerPhoneController.text = user.phone;
    _upgradeAddressController.text = user.address;
  }

  @override
  void dispose() {
    _upgradeCustomerNameController.dispose();
    _upgradeCustomerPhoneController.dispose();
    _upgradeAddressController.dispose();
    _upgradeNoteController.dispose();
    _customSensorLocationController.dispose();
    super.dispose();
  }

  Future<bool> _validateForm() async {
    if (!_isCurrentSensorSelected && !_isGatewaySelected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            "Vui lòng chọn ít nhất 1 thiết bị phần cứng để đăng ký nâng cấp!",
          ),
          backgroundColor: Colors.orange,
        ),
      );
      return false;
    }

    if (_isCurrentSensorSelected &&
        _currentSensorLocation == 'Vị trí tùy chỉnh...' &&
        _customSensorLocationController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            "Vui lòng điền chi tiết vị trí đặt Cảm biến công suất dòng!",
          ),
          backgroundColor: Colors.orange,
        ),
      );
      return false;
    }

    if (!_upgradeFormKey.currentState!.validate()) {
      return false;
    }

    return true;
  }

  void _showSuccessDialog() {
    final sensorLocationText =
        _currentSensorLocation == 'Vị trí tùy chỉnh...'
            ? _customSensorLocationController.text.trim()
            : _currentSensorLocation;

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Row(
            children: [
              Icon(Icons.check_circle_rounded, color: Colors.green, size: 28),
              SizedBox(width: 10),
              Text("Đã Tạo Đơn Đăng Ký Nâng Cấp"),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "Mã đơn đăng ký: UPG-2026-${(1000 + (DateTime.now().millisecond % 8999))}",
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                    color: Colors.blue,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  "Kỹ thuật viên sẽ tới khảo sát và hỗ trợ lắp đặt tại địa chỉ: ${_upgradeAddressController.text}.",
                ),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.blue.shade50,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.blue.shade100),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        "DANH SÁCH THIẾT BỊ ĐÃ CHỌN:",
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: Colors.blue,
                        ),
                      ),
                      const SizedBox(height: 6),
                      if (_isCurrentSensorSelected) ...[
                        Row(
                          children: [
                            const Icon(Icons.bolt, size: 16, color: Colors.amber),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                "⚡ Cảm biến công suất dòng: $_currentSensorQuantity cái (Vị trí: $sensorLocationText)",
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: Colors.black87,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                      ],
                      if (_isGatewaySelected) ...[
                        Row(
                          children: [
                            const Icon(Icons.router, size: 16, color: Colors.indigo),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                "📡 Bộ Gateway trung tâm Smart Hub Pro: $_gatewayQuantity bộ (Vị trí: $_gatewayLocation)",
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: Colors.black87,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                      ],
                      const Divider(height: 16),
                      Text(
                        "Khảo sát cho: $_selectedTargetRoom",
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.blue.shade900,
                        ),
                      ),
                      Text(
                        "Lịch hẹn: ${_selectedSurveyDate.day}/${_selectedSurveyDate.month}/${_selectedSurveyDate.year} ($_selectedTimeSlot)",
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.blue.shade900,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          actions: [
            FilledButton(
              onPressed: () {
                Navigator.pop(context);
              },
              child: const Text("Xác nhận & Hoàn tất"),
            ),
          ],
        ),
      );
    }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;

    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Column(
              children: [
                // Banner Nâng Cấp Hệ Thống
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: isDark
                          ? [const Color(0xFF1E1B4B), const Color(0xFF312E81)]
                          : [const Color(0xFF4F46E5), const Color(0xFF6366F1)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(18),
                  ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Icon(
                    Icons.add_to_photos_rounded,
                    color: Colors.white,
                    size: 36,
                  ),
                ),
                const SizedBox(width: 16),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        "ĐĂNG KÝ THÊM THIẾT BỊ & NÂNG CẤP HỆ THỐNG IOT",
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        "Điền số lượng và vị trí lắp đặt thiết bị để kỹ thuật viên tới khảo sát tận nơi.",
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.white70,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 24),

          // Danh Mục Thiết Bị Đăng Ký Nâng Cấp
          _buildCardContainer(
            context: context,
            title: "Danh Mục Thiết Bị Phần Cứng Cần Lắp Đặt Thêm",
            icon: Icons.grid_view_rounded,
            child: Column(
              children: [
                // THIẾT BỊ 1: CẢM BIẾN CÔNG SUẤT DÒNG
                _buildDeviceCard(
                  isDark: isDark,
                  isSelected: _isCurrentSensorSelected,
                  onToggle: (val) {
                    setState(() {
                      _isCurrentSensorSelected = val;
                    });
                  },
                  icon: Icons.electric_meter_rounded,
                  iconColor: Colors.amber,
                  title: "Cảm biến công suất dòng (CT Clamp Sensor)",
                  description:
                      "Đo dòng điện, theo dõi công suất tiêu thụ & phụ tải theo thời gian thực • Hàng chính hãng • BH 24T",
                  child: _isCurrentSensorSelected
                      ? Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Divider(height: 24),
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // SỐ LƯỢNG
                                Expanded(
                                  flex: 2,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          const Icon(Icons.pin_outlined,
                                              size: 16, color: Colors.blue),
                                          const SizedBox(width: 4),
                                          Text(
                                            "Số lượng cần điền:",
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w600,
                                              color: isDark
                                                  ? Colors.white70
                                                  : Colors.grey.shade800,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      Container(
                                        height: 42,
                                        decoration: BoxDecoration(
                                          color: isDark
                                              ? const Color(0xFF0F172A)
                                              : Colors.grey.shade100,
                                          borderRadius:
                                              BorderRadius.circular(8),
                                          border: Border.all(
                                            color: isDark
                                                ? const Color(0xFF334155)
                                                : Colors.grey.shade300,
                                          ),
                                        ),
                                        child: Row(
                                          mainAxisAlignment:
                                              MainAxisAlignment.spaceBetween,
                                          children: [
                                            IconButton(
                                              icon: const Icon(
                                                  Icons.remove,
                                                  size: 18),
                                              onPressed:
                                                  _currentSensorQuantity > 1
                                                      ? () {
                                                          setState(() {
                                                            _currentSensorQuantity--;
                                                          });
                                                        }
                                                      : null,
                                            ),
                                            Text(
                                              "$_currentSensorQuantity cái",
                                              style: TextStyle(
                                                fontSize: 14,
                                                fontWeight: FontWeight.bold,
                                                color: isDark
                                                    ? Colors.white
                                                    : const Color(0xFF1E293B),
                                              ),
                                            ),
                                            IconButton(
                                              icon: const Icon(Icons.add,
                                                  size: 18),
                                              onPressed: () {
                                                setState(() {
                                                  _currentSensorQuantity++;
                                                });
                                              },
                                            ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                ),

                                const SizedBox(width: 16),

                                // VỊ TRÍ ĐẶT CẢM BIẾN
                                Expanded(
                                  flex: 3,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          const Icon(
                                              Icons.location_on_outlined,
                                              size: 16,
                                              color: Colors.blue),
                                          const SizedBox(width: 4),
                                          Text(
                                            "Vị trí đặt cảm biến:",
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w600,
                                              color: isDark
                                                  ? Colors.white70
                                                  : Colors.grey.shade800,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      DropdownButtonFormField<String>(
                                        initialValue: _currentSensorLocation,
                                        decoration: const InputDecoration(
                                          contentPadding:
                                              EdgeInsets.symmetric(
                                            horizontal: 12,
                                            vertical: 10,
                                          ),
                                          border: OutlineInputBorder(),
                                          isDense: true,
                                        ),
                                        items: _sensorLocationOptions
                                            .map((loc) => DropdownMenuItem(
                                                  value: loc,
                                                  child: Text(
                                                    loc,
                                                    style: const TextStyle(
                                                        fontSize: 13),
                                                  ),
                                                ))
                                            .toList(),
                                        onChanged: (val) {
                                          if (val != null) {
                                            setState(() {
                                              _currentSensorLocation = val;
                                            });
                                          }
                                        },
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),

                            if (_currentSensorLocation == 'Vị trí tùy chỉnh...') ...[
                              const SizedBox(height: 12),
                              TextFormField(
                                controller: _customSensorLocationController,
                                decoration: const InputDecoration(
                                  labelText: "Điền cụ thể vị trí lắp đặt",
                                  hintText:
                                      "Ví dụ: Tủ điện nhánh phòng máy lạnh tầng 2...",
                                  prefixIcon: Icon(Icons.edit_location_alt_outlined),
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                ),
                              ),
                            ],
                          ],
                        )
                      : null,
                ),

                const SizedBox(height: 16),

                // THIẾT BỊ 2: BỘ GATEWAY TRUNG TÂM
                _buildDeviceCard(
                  isDark: isDark,
                  isSelected: _isGatewaySelected,
                  onToggle: (val) {
                    setState(() {
                      _isGatewaySelected = val;
                    });
                  },
                  icon: Icons.hub_rounded,
                  iconColor: Colors.indigo,
                  title: "Bộ Gateway trung tâm Smart Hub Pro",
                  description:
                      "Bộ điều khiển trung tâm kết nối sóng Zigbee/Wi-Fi & đồng bộ dữ liệu về Dashboard • BH 24T",
                  child: _isGatewaySelected
                      ? Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Divider(height: 24),
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // SỐ LƯỢNG
                                Expanded(
                                  flex: 2,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          const Icon(Icons.pin_outlined,
                                              size: 16, color: Colors.indigo),
                                          const SizedBox(width: 4),
                                          Text(
                                            "Số lượng Gateway:",
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w600,
                                              color: isDark
                                                  ? Colors.white70
                                                  : Colors.grey.shade800,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      Container(
                                        height: 42,
                                        decoration: BoxDecoration(
                                          color: isDark
                                              ? const Color(0xFF0F172A)
                                              : Colors.grey.shade100,
                                          borderRadius:
                                              BorderRadius.circular(8),
                                          border: Border.all(
                                            color: isDark
                                                ? const Color(0xFF334155)
                                                : Colors.grey.shade300,
                                          ),
                                        ),
                                        child: Row(
                                          mainAxisAlignment:
                                              MainAxisAlignment.spaceBetween,
                                          children: [
                                            IconButton(
                                              icon: const Icon(
                                                  Icons.remove,
                                                  size: 18),
                                              onPressed: _gatewayQuantity > 1
                                                  ? () {
                                                      setState(() {
                                                        _gatewayQuantity--;
                                                      });
                                                    }
                                                  : null,
                                            ),
                                            Text(
                                              "$_gatewayQuantity bộ",
                                              style: TextStyle(
                                                fontSize: 14,
                                                fontWeight: FontWeight.bold,
                                                color: isDark
                                                    ? Colors.white
                                                    : const Color(0xFF1E293B),
                                              ),
                                            ),
                                            IconButton(
                                              icon: const Icon(Icons.add,
                                                  size: 18),
                                              onPressed: () {
                                                setState(() {
                                                  _gatewayQuantity++;
                                                });
                                              },
                                            ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                ),

                                const SizedBox(width: 16),

                                // VỊ TRÍ ĐẶT GATEWAY
                                Expanded(
                                  flex: 3,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          const Icon(
                                              Icons.location_on_outlined,
                                              size: 16,
                                              color: Colors.indigo),
                                          const SizedBox(width: 4),
                                          Text(
                                            "Vị trí đặt Gateway:",
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w600,
                                              color: isDark
                                                  ? Colors.white70
                                                  : Colors.grey.shade800,
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      DropdownButtonFormField<String>(
                                        initialValue: _gatewayLocation,
                                        decoration: const InputDecoration(
                                          contentPadding:
                                              EdgeInsets.symmetric(
                                            horizontal: 12,
                                            vertical: 10,
                                          ),
                                          border: OutlineInputBorder(),
                                          isDense: true,
                                        ),
                                        items: _gatewayLocationOptions
                                            .map((loc) => DropdownMenuItem(
                                                  value: loc,
                                                  child: Text(
                                                    loc,
                                                    style: const TextStyle(
                                                        fontSize: 13),
                                                  ),
                                                ))
                                            .toList(),
                                        onChanged: (val) {
                                          if (val != null) {
                                            setState(() {
                                              _gatewayLocation = val;
                                            });
                                          }
                                        },
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ],
                        )
                      : null,
                ),
              ],
            ),
          ),

          const SizedBox(height: 24),

          // Form Đơn Đăng Ký & Lịch Hẹn Khảo Sát
          Container(
            padding: const EdgeInsets.all(20.0),
            decoration: BoxDecoration(
              color: cardBg,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: borderColor),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
                  blurRadius: 15,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Form(
              key: _upgradeFormKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.blue.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(
                          Icons.assignment_rounded,
                          color: Colors.blue,
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        "Thông Tin Đăng Ký Lắp Đặt & Lịch Hẹn Kỹ Thuật Viên",
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color:
                              isDark ? Colors.white : const Color(0xFF1E293B),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Divider(height: 1),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: _upgradeCustomerNameController,
                          decoration: const InputDecoration(
                            labelText: "Họ và tên người đăng ký",
                            prefixIcon: Icon(Icons.person_outline),
                            border: OutlineInputBorder(),
                            isDense: true,
                          ),
                          validator: (val) => val == null || val.isEmpty
                              ? "Vui lòng nhập tên"
                              : null,
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: TextFormField(
                          controller: _upgradeCustomerPhoneController,
                          decoration: const InputDecoration(
                            labelText: "Số điện thoại liên hệ",
                            prefixIcon: Icon(Icons.phone_outlined),
                            border: OutlineInputBorder(),
                            isDense: true,
                          ),
                          validator: (val) => val == null || val.isEmpty
                              ? "Vui lòng nhập SĐT"
                              : null,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _upgradeAddressController,
                    decoration: const InputDecoration(
                      labelText: "Địa chỉ lắp đặt tận nơi",
                      prefixIcon: Icon(Icons.location_on_outlined),
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    validator: (val) => val == null || val.isEmpty
                        ? "Vui lòng nhập địa chỉ"
                        : null,
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _selectedTargetRoom,
                          decoration: const InputDecoration(
                            labelText: "Khu vực / Phòng lắp đặt chính",
                            prefixIcon: Icon(Icons.meeting_room_outlined),
                            border: OutlineInputBorder(),
                            isDense: true,
                          ),
                          items: const [
                            DropdownMenuItem(
                              value: 'Phòng khách',
                              child: Text('Phòng khách'),
                            ),
                            DropdownMenuItem(
                              value: 'Phòng ngủ',
                              child: Text('Phòng ngủ'),
                            ),
                            DropdownMenuItem(
                              value: 'Phòng bếp',
                              child: Text('Phòng bếp'),
                            ),
                            DropdownMenuItem(
                              value: 'Toàn bộ ngôi nhà',
                              child: Text('Toàn bộ ngôi nhà'),
                            ),
                          ],
                          onChanged: (val) {
                            if (val != null) {
                              setState(() {
                                _selectedTargetRoom = val;
                              });
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _selectedTimeSlot,
                          decoration: const InputDecoration(
                            labelText: "Khung giờ hẹn khảo sát",
                            prefixIcon: Icon(Icons.access_time_rounded),
                            border: OutlineInputBorder(),
                            isDense: true,
                          ),
                          items: const [
                            DropdownMenuItem(
                              value: '09:00 - 11:00 (Buổi sáng)',
                              child: Text('09:00 - 11:00 (Buổi sáng)'),
                            ),
                            DropdownMenuItem(
                              value: '14:00 - 16:00 (Buổi chiều)',
                              child: Text('14:00 - 16:00 (Buổi chiều)'),
                            ),
                            DropdownMenuItem(
                              value: '18:00 - 20:00 (Buổi tối)',
                              child: Text('18:00 - 20:00 (Buổi tối)'),
                            ),
                          ],
                          onChanged: (val) {
                            if (val != null) {
                              setState(() {
                                _selectedTimeSlot = val;
                              });
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _upgradeNoteController,
                    maxLines: 2,
                    decoration: const InputDecoration(
                      labelText: "Ghi chú thêm cho kỹ thuật viên (nếu có)",
                      hintText:
                          "Ví dụ: Cần đi dây âm tường hoặc gọi điện trước khi tới 30 phút...",
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 24),
                  AnimatedOrderButton(
                    defaultText: "GỬI ĐƠN ĐĂNG KÝ NÂNG CẤP HỆ THỐNG",
                    successText: "Đã Gửi Đơn Đăng Ký Thành Công ✓",
                    onPressed: _validateForm,
                    onCompleted: _showSuccessDialog,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
  );
},
);
}

  Widget _buildDeviceCard({
    required bool isDark,
    required bool isSelected,
    required ValueChanged<bool> onToggle,
    required IconData icon,
    required Color iconColor,
    required String title,
    required String description,
    Widget? child,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isSelected
            ? (isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC))
            : (isDark ? const Color(0xFF0F172A).withValues(alpha: 0.5) : Colors.grey.shade50),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isSelected
              ? (isDark ? const Color(0xFF3B82F6) : Colors.blue.shade400)
              : (isDark ? const Color(0xFF334155) : Colors.grey.shade300),
          width: isSelected ? 1.8 : 1,
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: iconColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: iconColor, size: 24),
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
                        fontWeight: FontWeight.bold,
                        color: isDark ? Colors.white : const Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      description,
                      style: TextStyle(
                        fontSize: 12,
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Switch(
                value: isSelected,
                onChanged: onToggle,
                activeTrackColor: Colors.blue,
              ),
            ],
          ),
          ?child,
        ],
      ),
    );
  }

  Widget _buildCardContainer({
    required BuildContext context,
    required String title,
    required IconData icon,
    required Widget child,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;

    return Container(
      padding: const EdgeInsets.all(20.0),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 15,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.blue.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: Colors.blue, size: 20),
              ),
              const SizedBox(width: 12),
              Text(
                title,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.white : const Color(0xFF1E293B),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Divider(height: 1),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}
