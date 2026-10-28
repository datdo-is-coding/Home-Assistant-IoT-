import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/model/user_model.dart';

class UserMaintenancePackageCard extends StatelessWidget {
  final MaintenancePackageModel package;

  const UserMaintenancePackageCard({super.key, required this.package});

  @override
  Widget build(BuildContext context) {
    final pkg = package;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;
    final itemBg = isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC);

    return Card(
      margin: EdgeInsets.zero,
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: borderColor),
      ),
      color: cardBg,
      child: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: constraints.maxHeight - 48,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: isDark
                                  ? const Color(0xFF312E81).withValues(alpha: 0.5)
                                  : const Color(0xFFEEF2FF),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Icon(
                              Icons.workspace_premium,
                              color: Color(0xFF818CF8),
                              size: 26,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(
                            pkg.packageName,
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              color: isDark ? Colors.white : const Color(0xFF1E293B),
                            ),
                          ),
                        ],
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: isDark
                              ? const Color(0xFF064E3B).withValues(alpha: 0.5)
                              : Colors.green.shade50,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(
                            color: isDark ? const Color(0xFF047857) : Colors.green.shade300,
                          ),
                        ),
                        child: Row(
                          children: [
                            const Icon(
                              Icons.check_circle,
                              size: 14,
                              color: Colors.green,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'Đang hoạt động',
                              style: TextStyle(
                                color: isDark ? const Color(0xFF34D399) : Colors.green,
                                fontWeight: FontWeight.bold,
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  Divider(height: 32, color: borderColor),

                  // Ngày đăng ký & Ngày hết hạn
                  Row(
                    children: [
                      Expanded(
                        child: _buildDateCard(
                          isDark: isDark,
                          title: 'Ngày đăng ký',
                          date: pkg.registrationDate,
                          icon: Icons.calendar_today,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _buildDateCard(
                          isDark: isDark,
                          title: 'Ngày hết hạn',
                          date: pkg.expiryDate,
                          icon: Icons.event_available,
                          isHighlight: true,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 20),

                  // Thống kê số phòng & tổng thiết bị
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: itemBg,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: borderColor,
                      ),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            children: [
                              Text(
                                'Số phòng quản lý',
                                style: TextStyle(
                                  color: isDark ? Colors.grey.shade400 : Colors.grey,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${pkg.totalRooms} Phòng',
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold,
                                  color: isDark ? const Color(0xFFA5B4FC) : const Color(0xFF4F46E5),
                                ),
                              ),
                            ],
                          ),
                        ),
                        Container(
                          width: 1,
                          height: 40,
                          color: borderColor,
                        ),
                        Expanded(
                          child: Column(
                            children: [
                              Text(
                                'Tổng số thiết bị',
                                style: TextStyle(
                                  color: isDark ? Colors.grey.shade400 : Colors.grey,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${pkg.totalDevices} Thiết bị',
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold,
                                  color: isDark ? const Color(0xFFA5B4FC) : const Color(0xFF4F46E5),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 24),

                  Text(
                    'Danh sách các phòng & Thiết bị bảo trì :',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: isDark ? Colors.white70 : const Color(0xFF334155),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Expansion tiles cho từng phòng
                  ...pkg.roomDevicesDetails.entries.map((entry) {
                    final roomName = entry.key;
                    final devicesList = entry.value;

                    return Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: itemBg,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: borderColor),
                      ),
                      child: Theme(
                        data: Theme.of(context).copyWith(
                          dividerColor: Colors.transparent,
                        ),
                        child: ExpansionTile(
                          iconColor: isDark ? Colors.white70 : Colors.black54,
                          collapsedIconColor: isDark ? Colors.grey.shade400 : Colors.grey,
                          leading: const Icon(
                            Icons.meeting_room,
                            color: Color(0xFF818CF8),
                          ),
                          title: Text(
                            roomName,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 15,
                              color: isDark ? Colors.white : const Color(0xFF1E293B),
                            ),
                          ),
                          subtitle: Text(
                            '${devicesList.length} thiết bị bảo trì',
                            style: TextStyle(
                              fontSize: 12,
                              color: isDark ? Colors.grey.shade400 : Colors.grey,
                            ),
                          ),
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 8,
                              ),
                              color: itemBg,
                              child: Column(
                                children: devicesList.map((dev) {
                                  return ListTile(
                                    contentPadding: EdgeInsets.zero,
                                    leading: Icon(
                                      dev.isOn ? Icons.power : Icons.power_off,
                                      color: dev.isOn ? const Color(0xFF10B981) : Colors.grey,
                                      size: 20,
                                    ),
                                    title: Text(
                                      dev.deviceName,
                                      style: TextStyle(
                                        fontWeight: FontWeight.w500,
                                        fontSize: 14,
                                        color: isDark ? Colors.white : Colors.black87,
                                      ),
                                    ),
                                    subtitle: Text(
                                      'Công suất: ${dev.powerWatts}',
                                      style: TextStyle(
                                        fontSize: 12,
                                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                                      ),
                                    ),
                                    trailing: Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        color: dev.isOn
                                            ? (isDark ? const Color(0xFF064E3B) : Colors.teal.shade50)
                                            : (isDark ? const Color(0xFF1E293B) : Colors.grey.shade100),
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(
                                        dev.isOn ? 'Đang bật' : 'Tắt',
                                        style: TextStyle(
                                          color: dev.isOn
                                              ? (isDark ? const Color(0xFF34D399) : Colors.teal)
                                              : Colors.grey,
                                          fontSize: 11,
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ),
                                  );
                                }).toList(),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildDateCard({
    required bool isDark,
    required String title,
    required DateTime date,
    required IconData icon,
    bool isHighlight = false,
  }) {
    final cardBg = isHighlight
        ? (isDark ? const Color(0xFF312E81).withValues(alpha: 0.4) : const Color(0xFFEEF2FF))
        : (isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC));
    final borderColor = isHighlight
        ? (isDark ? const Color(0xFF4338CA) : const Color(0xFFC7D2FE))
        : (isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0));

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        children: [
          Icon(
            icon,
            size: 20,
            color: isHighlight
                ? (isDark ? const Color(0xFFA5B4FC) : const Color(0xFF4F46E5))
                : Colors.grey,
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? Colors.grey.shade400 : Colors.grey,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                '${date.day}/${date.month}/${date.year}',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  color: isHighlight
                      ? (isDark ? const Color(0xFFA5B4FC) : const Color(0xFF4F46E5))
                      : (isDark ? Colors.white : const Color(0xFF1E293B)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
