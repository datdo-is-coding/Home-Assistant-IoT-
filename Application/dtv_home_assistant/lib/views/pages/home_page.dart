import 'package:flutter/material.dart';
import 'package:dtv_home_assistant/views/widgets/consumption_chart.dart';

class DeviceItem {
  final String id;
  final String name;
  final IconData icon;
  final int watt;
  bool isOn;

  DeviceItem({
    required this.id,
    required this.name,
    required this.icon,
    required this.watt,
    this.isOn = false,
  });
}

class RoomItem {
  final String id;
  final String name;
  final List<DeviceItem> devices;

  RoomItem({required this.id, required this.name, required this.devices});
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late String selectedRoomId;

  final List<RoomItem> rooms = [
    RoomItem(
      id: 'living_room',
      name: 'Phòng Khách',
      devices: [
        DeviceItem(
          id: 'lr_light',
          name: 'Đèn trần',
          icon: Icons.lightbulb_rounded,
          watt: 45,
          isOn: true,
        ),
        DeviceItem(
          id: 'lr_ac',
          name: 'Điều hòa',
          icon: Icons.ac_unit_rounded,
          watt: 1200,
          isOn: true,
        ),
        DeviceItem(
          id: 'lr_tv',
          name: 'Smart TV',
          icon: Icons.tv_rounded,
          watt: 120,
          isOn: false,
        ),
        DeviceItem(
          id: 'lr_fan',
          name: 'Quạt trần',
          icon: Icons.air_rounded,
          watt: 60,
          isOn: true,
        ),
      ],
    ),
    RoomItem(
      id: 'bedroom',
      name: 'Phòng Ngủ',
      devices: [
        DeviceItem(
          id: 'br_light',
          name: 'Đèn ngủ',
          icon: Icons.bedtime_rounded,
          watt: 15,
          isOn: true,
        ),
        DeviceItem(
          id: 'br_ac',
          name: 'Điều hòa',
          icon: Icons.ac_unit_rounded,
          watt: 900,
          isOn: false,
        ),
        DeviceItem(
          id: 'br_purifier',
          name: 'Máy lọc không khí',
          icon: Icons.air_rounded,
          watt: 30,
          isOn: true,
        ),
      ],
    ),
    RoomItem(
      id: 'kitchen',
      name: 'Phòng Bếp',
      devices: [
        DeviceItem(
          id: 'kt_fridge',
          name: 'Tủ lạnh',
          icon: Icons.kitchen_rounded,
          watt: 150,
          isOn: true,
        ),
        DeviceItem(
          id: 'kt_light',
          name: 'Đèn bếp',
          icon: Icons.lightbulb_outline_rounded,
          watt: 30,
          isOn: false,
        ),
        DeviceItem(
          id: 'kt_microwave',
          name: 'Lò vi sóng',
          icon: Icons.microwave_rounded,
          watt: 800,
          isOn: false,
        ),
      ],
    ),
  ];

  @override
  void initState() {
    super.initState();
    selectedRoomId = rooms.first.id;
  }

  IconData _getRoomIcon(String roomName) {
    if (roomName.contains('Khách')) return Icons.weekend_rounded;
    if (roomName.contains('Ngủ')) return Icons.bed_rounded;
    if (roomName.contains('Bếp')) return Icons.soup_kitchen_rounded;
    return Icons.meeting_room_rounded;
  }

  int _calculateTotalWatts(RoomItem room) {
    return room.devices
        .where((d) => d.isOn)
        .fold(0, (sum, device) => sum + device.watt);
  }

  @override
  Widget build(BuildContext context) {
    final currentRoom = rooms.firstWhere(
      (r) => r.id == selectedRoomId,
      orElse: () => rooms.first,
    );

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(
            height: 360,
            child: ConsumptionChart(showDropdown: false, initialMode: 'hourly'),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 20,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 1. BỘ CHỌN PHÒNG VÀ THỐNG KÊ TỔNG QUAN
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF1F5F9),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.grey.shade300),
                      ),
                      child: DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          value: selectedRoomId,
                          icon: const Icon(
                            Icons.keyboard_arrow_down_rounded,
                            color: Color(0xFF475569),
                          ),
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF1E293B),
                          ),
                          items: rooms.map((room) {
                            return DropdownMenuItem<String>(
                              value: room.id,
                              child: Row(
                                children: [
                                  Icon(
                                    _getRoomIcon(room.name),
                                    size: 20,
                                    color: const Color(0xFF6366F1),
                                  ),
                                  const SizedBox(width: 10),
                                  Text(room.name),
                                ],
                              ),
                            );
                          }).toList(),
                          onChanged: (String? newValue) {
                            if (newValue != null) {
                              setState(() {
                                selectedRoomId = newValue;
                              });
                            }
                          },
                        ),
                      ),
                    ),

                    // Thống kê nhanh tổng công suất tiêu thụ trong phòng
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEEF2FF),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFFC7D2FE)),
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.electric_bolt_rounded,
                            size: 16,
                            color: Color(0xFF4F46E5),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            '${_calculateTotalWatts(currentRoom)} W',
                            style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.bold,
                              color: Color(0xFF4338CA),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 20),

                // 2. TIÊU ĐỀ & SỐ LƯỢNG THIẾT BỊ
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Danh sách thiết bị (${currentRoom.devices.length})',
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF64748B),
                      ),
                    ),
                    Text(
                      '${currentRoom.devices.where((d) => d.isOn).length} đang hoạt động',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Color(0xFF047857),
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 16),

                // 3. GRID HIỂN THỊ CÁC THIẾT BỊ CẦN ĐIỀU KHIỂN
                GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: currentRoom.devices.length,
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    childAspectRatio: 1.35,
                  ),
                  itemBuilder: (context, index) {
                    final device = currentRoom.devices[index];
                    return GestureDetector(
                      onTap: () {
                        setState(() {
                          device.isOn = !device.isOn;
                        });
                      },
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: device.isOn
                              ? const Color(0xFFEEF2FF)
                              : const Color(0xFFF8FAFC),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: device.isOn
                                ? const Color(0xFFC7D2FE)
                                : Colors.grey.shade200,
                            width: 1.5,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(8),
                                  decoration: BoxDecoration(
                                    color: device.isOn
                                        ? const Color(0xFF6366F1)
                                        : Colors.grey.shade300,
                                    shape: BoxShape.circle,
                                  ),
                                  child: Icon(
                                    device.icon,
                                    size: 20,
                                    color: device.isOn
                                        ? Colors.white
                                        : Colors.grey.shade600,
                                  ),
                                ),
                                Switch.adaptive(
                                  value: device.isOn,
                                  activeThumbColor: const Color(0xFF6366F1),
                                  onChanged: (val) {
                                    setState(() {
                                      device.isOn = val;
                                    });
                                  },
                                ),
                              ],
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  device.name,
                                  style: TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.bold,
                                    color: device.isOn
                                        ? const Color(0xFF1E293B)
                                        : const Color(0xFF64748B),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  '${device.watt} W',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w500,
                                    color: device.isOn
                                        ? const Color(0xFF4F46E5)
                                        : Colors.grey.shade500,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
