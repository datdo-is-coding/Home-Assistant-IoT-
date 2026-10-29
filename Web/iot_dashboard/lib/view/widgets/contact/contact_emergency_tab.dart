import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/notifiers.dart';

class ContactEmergencyTab extends StatefulWidget {
  final VoidCallback onEmergencyCallRequested;

  const ContactEmergencyTab({
    super.key,
    required this.onEmergencyCallRequested,
  });

  @override
  State<ContactEmergencyTab> createState() => _ContactEmergencyTabState();
}

class _ContactEmergencyTabState extends State<ContactEmergencyTab> {
  final _incidentFormKey = GlobalKey<FormState>();
  final TextEditingController _reporterNameController =
      TextEditingController();
  final TextEditingController _reporterPhoneController =
      TextEditingController();
  final TextEditingController _incidentDescController =
      TextEditingController();
  String _selectedIncidentType = 'Mất kết nối thiết bị / Gateway';
  String _selectedPriority = '🔴 Khẩn cấp (Cứu hộ điện)';
  bool _hasAttachedScreenshot = false;

  @override
  void initState() {
    super.initState();
    final currentUser = currentUserNotifier.value;
    _reporterNameController.text = currentUser.name;
    _reporterPhoneController.text = currentUser.phone;
  }

  @override
  void dispose() {
    _reporterNameController.dispose();
    _reporterPhoneController.dispose();
    _incidentDescController.dispose();
    super.dispose();
  }

  void _submitIncidentReport() {
    if (_incidentFormKey.currentState!.validate()) {
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Row(
            children: [
              Icon(Icons.check_circle_rounded, color: Colors.green, size: 28),
              SizedBox(width: 10),
              Text("Đã Tiếp Nhận Sự Cố"),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                "Mã sự cố: INC-2026-${(1000 + (DateTime.now().millisecond % 8999))}",
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  color: Colors.blue,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                "Cảm ơn ông/bà ${_reporterNameController.text}. Đội ngũ kỹ thuật viên trực ban đã nhận được thông tin báo lỗi khẩn cấp.",
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.timer_rounded, color: Colors.blue),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _selectedPriority.contains('Khẩn cấp')
                            ? "Thời gian liên hệ xử lý: Trong vòng 15-30 phút"
                            : "Thời gian liên hệ xử lý: Trong vòng 2-4 giờ",
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Colors.blue,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            FilledButton(
              onPressed: () {
                Navigator.pop(context);
                _incidentDescController.clear();
                setState(() {
                  _hasAttachedScreenshot = false;
                });
              },
              child: const Text("Xác nhận & Đóng"),
            ),
          ],
        ),
      );
    }
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
            child: IntrinsicHeight(
              child: Column(
                children: [
                  // Thẻ Cứu Hộ Khẩn Cấp Báo Động
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF3F1D1D) : Colors.red.shade50,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(
                        color: isDark ? Colors.red.shade900 : Colors.red.shade300,
                        width: 1.5,
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: const BoxDecoration(
                            color: Colors.red,
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.warning_amber_rounded,
                            color: Colors.white,
                            size: 32,
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                "SỰ CỐ ĐIỆN HOẶC HỎNG HÓC THIẾT BỊ KHẨN CẤP?",
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.red,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                "Nếu ngôi nhà bạn đang gặp sự cố chập cháy, quạt/đèn bị quá tải không ngắt được, hãy ấn nút Gọi Khẩn Cấp 24/7 để kết nối cứu hộ tức thì.",
                                style: TextStyle(
                                  fontSize: 13,
                                  color: isDark
                                      ? Colors.red.shade100
                                      : Colors.red.shade900,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 16),
                        FilledButton.icon(
                          onPressed: widget.onEmergencyCallRequested,
                          icon: const Icon(Icons.call),
                          label: const Text("GỌI SOS 1900 8888"),
                          style: FilledButton.styleFrom(
                            backgroundColor: Colors.red,
                            padding: const EdgeInsets.symmetric(
                              horizontal: 18,
                              vertical: 14,
                            ),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 24),

                  // Form Biểu Mẫu Báo Sự Cố
                  Expanded(
                    child: Container(
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
                        key: _incidentFormKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Column(
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
                                        Icons.report_problem_rounded,
                                        color: Colors.blue,
                                        size: 20,
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Text(
                                      "Biểu Mẫu Gửi Báo Sự Cố & Báo Lỗi Kỹ Thuật",
                                      style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                        color: isDark
                                            ? Colors.white
                                            : const Color(0xFF1E293B),
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
                                        controller: _reporterNameController,
                                        decoration: const InputDecoration(
                                          labelText: "Họ và tên người báo lỗi",
                                          prefixIcon: Icon(Icons.person_outline),
                                          border: OutlineInputBorder(),
                                          isDense: true,
                                        ),
                                        validator: (value) {
                                          if (value == null || value.isEmpty) {
                                            return "Vui lòng nhập họ tên";
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 16),
                                    Expanded(
                                      child: TextFormField(
                                        controller: _reporterPhoneController,
                                        decoration: const InputDecoration(
                                          labelText: "Số điện thoại liên hệ",
                                          prefixIcon: Icon(Icons.phone_outlined),
                                          border: OutlineInputBorder(),
                                          isDense: true,
                                        ),
                                        validator: (value) {
                                          if (value == null || value.isEmpty) {
                                            return "Vui lòng nhập số điện thoại";
                                          }
                                          return null;
                                        },
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 16),
                                Row(
                                  children: [
                                    Expanded(
                                      child: DropdownButtonFormField<String>(
                                        initialValue: _selectedIncidentType,
                                        decoration: const InputDecoration(
                                          labelText: "Loại sự cố gặp phải",
                                          prefixIcon: Icon(Icons.category_outlined),
                                          border: OutlineInputBorder(),
                                          isDense: true,
                                        ),
                                        items: const [
                                          DropdownMenuItem(
                                            value: 'Mất kết nối thiết bị / Gateway',
                                            child: Text('Mất kết nối thiết bị / Gateway'),
                                          ),
                                          DropdownMenuItem(
                                            value: 'Cảnh báo quá tải / Sai thông số',
                                            child: Text('Cảnh báo quá tải / Sai thông số'),
                                          ),
                                          DropdownMenuItem(
                                            value:
                                                'Lỗi ứng dụng Dashboard không bật/tắt được',
                                            child: Text('Lỗi ứng dụng không bật/tắt được'),
                                          ),
                                          DropdownMenuItem(
                                            value: 'Cảm biến công suất không cập nhật',
                                            child: Text('Cảm biến công suất không cập nhật'),
                                          ),
                                          DropdownMenuItem(
                                            value: 'Khác / Sự cố thiết bị phần cứng',
                                            child: Text('Khác / Sự cố phần cứng'),
                                          ),
                                        ],
                                        onChanged: (val) {
                                          if (val != null) {
                                            setState(() {
                                              _selectedIncidentType = val;
                                            });
                                          }
                                        },
                                      ),
                                    ),
                                    const SizedBox(width: 16),
                                    Expanded(
                                      child: DropdownButtonFormField<String>(
                                        initialValue: _selectedPriority,
                                        decoration: const InputDecoration(
                                          labelText: "Mức độ khẩn cấp",
                                          prefixIcon: Icon(Icons.priority_high_rounded),
                                          border: OutlineInputBorder(),
                                          isDense: true,
                                        ),
                                        items: const [
                                          DropdownMenuItem(
                                            value: '🟢 Bình thường (Xử lý trong 24h)',
                                            child: Text('🟢 Bình thường (Xử lý trong 24h)'),
                                          ),
                                          DropdownMenuItem(
                                            value: '🟡 Ưu tiên (Xử lý trong 4h)',
                                            child: Text('🟡 Ưu tiên (Xử lý trong 4h)'),
                                          ),
                                          DropdownMenuItem(
                                            value: '🔴 Khẩn cấp (Cứu hộ điện)',
                                            child: Text('🔴 Khẩn cấp (Cứu hộ điện)'),
                                          ),
                                        ],
                                        onChanged: (val) {
                                          if (val != null) {
                                            setState(() {
                                              _selectedPriority = val;
                                            });
                                          }
                                        },
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 16),
                                TextFormField(
                                  controller: _incidentDescController,
                                  maxLines: 4,
                                  decoration: const InputDecoration(
                                    labelText: "Mô tả chi tiết lỗi / hiện tượng sự cố",
                                    hintText:
                                        "Ví dụ: Đèn phòng khách đột nhiên chớp tắt liên tục và app báo quá tải 3500W mặc dù đã tắt hết thiết bị...",
                                    alignLabelWithHint: true,
                                    border: OutlineInputBorder(),
                                  ),
                                  validator: (value) {
                                    if (value == null || value.trim().length < 5) {
                                      return "Vui lòng nhập mô tả chi tiết sự cố (tối thiểu 5 ký tự)";
                                    }
                                    return null;
                                  },
                                ),
                                const SizedBox(height: 16),
                                Row(
                                  children: [
                                    OutlinedButton.icon(
                                      onPressed: () {
                                        setState(() {
                                          _hasAttachedScreenshot = !_hasAttachedScreenshot;
                                        });
                                      },
                                      icon: Icon(
                                        _hasAttachedScreenshot
                                            ? Icons.check_circle
                                            : Icons.attach_file_rounded,
                                        color: _hasAttachedScreenshot
                                            ? Colors.green
                                            : Colors.blue,
                                      ),
                                      label: Text(
                                        _hasAttachedScreenshot
                                            ? "Đã đính kèm 1 tệp ảnh lỗi"
                                            : "Đính kèm ảnh chụp màn hình / mã lỗi",
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    if (_hasAttachedScreenshot)
                                      const Text(
                                        "error_log_screen.png",
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: Colors.green,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                            const SizedBox(height: 24),
                            SizedBox(
                              width: double.infinity,
                              height: 48,
                              child: FilledButton.icon(
                                onPressed: _submitIncidentReport,
                                icon: const Icon(Icons.send_rounded),
                                label: const Text(
                                  "GỬI BÁO SỰ CỐ TỨC THÌ",
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                style: FilledButton.styleFrom(
                                  backgroundColor: Colors.blue.shade700,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
