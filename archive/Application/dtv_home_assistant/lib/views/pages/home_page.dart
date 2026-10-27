import 'package:flutter/material.dart';
import 'package:dtv_home_assistant/views/widgets/consumption_chart.dart';
import 'package:dtv_home_assistant/data/services/realtime_energy_service.dart';

class DeviceItem {
  final String id;
  final String name;
  final IconData icon;
  int watt;
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
    RealtimeEnergyService.instance.deviceDataNotifier.addListener(_onDeviceDataUpdated);
  }

  @override
  void dispose() {
    RealtimeEnergyService.instance.deviceDataNotifier.removeListener(_onDeviceDataUpdated);
    super.dispose();
  }

  void _onDeviceDataUpdated() {
    final data = RealtimeEnergyService.instance.deviceDataNotifier.value;
    if (data == null || !mounted) return;
    setState(() {
      final lr = rooms.firstWhere((r) => r.id == 'living_room');
      if (data.channels.containsKey('ch1')) {
        final ch1 = data.channels['ch1']!;
        final light = lr.devices.firstWhere((d) => d.id == 'lr_light');
        light.isOn = ch1.state;
        light.watt = ch1.power.round();
      }
      if (data.channels.containsKey('ch2')) {
        final ch2 = data.channels['ch2']!;
        final fan = lr.devices.firstWhere((d) => d.id == 'lr_fan');
        fan.isOn = ch2.state;
        fan.watt = ch2.power.round();
      }
    });
  }

  void _toggleDevice(DeviceItem device, bool val) {
    setState(() {
      device.isOn = val;
    });
    if (device.id == 'lr_light') {
      RealtimeEnergyService.instance.setChannelState('ch1', val);
    } else if (device.id == 'lr_fan') {
      RealtimeEnergyService.instance.setChannelState('ch2', val);
    }
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

  Widget _buildActionBoxTelemetryCard(ActionBoxData? data) {
    final isOnline = data != null && data.online;
    return Container(
      margin: const EdgeInsets.only(top: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.15),
            blurRadius: 15,
            offset: const Offset(0, 6),
          ),
        ],
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
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isOnline ? const Color(0xFF10B981) : const Color(0xFFEF4444),
                      boxShadow: isOnline
                          ? [
                              BoxShadow(
                                color: const Color(0xFF10B981).withValues(alpha: 0.6),
                                blurRadius: 6,
                                spreadRadius: 2,
                              ),
                            ]
                          : null,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    data?.name ?? 'Action Box (ESP32-S3)',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: isOnline
                      ? const Color(0xFF10B981).withValues(alpha: 0.2)
                      : Colors.white.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: isOnline ? const Color(0xFF10B981) : Colors.white24,
                    width: 0.8,
                  ),
                ),
                child: Text(
                  isOnline ? 'ONLINE' : 'OFFLINE',
                  style: TextStyle(
                    color: isOnline ? const Color(0xFF34D399) : Colors.white60,
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.5,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _buildMetricItem(
                  icon: Icons.electric_bolt_rounded,
                  label: 'Điện áp',
                  value: '${data?.voltage.toStringAsFixed(1) ?? "--"} V',
                  color: const Color(0xFFFBBF24),
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  icon: Icons.speed_rounded,
                  label: 'Dòng điện',
                  value: '${data?.totalCurrent.toStringAsFixed(2) ?? "--"} A',
                  color: const Color(0xFF38BDF8),
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  icon: Icons.power_rounded,
                  label: 'Công suất',
                  value: '${data?.totalPower.toStringAsFixed(1) ?? "--"} W',
                  color: const Color(0xFFA78BFA),
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  icon: Icons.timelapse_rounded,
                  label: 'Điện năng',
                  value: '${data?.totalEnergyKwh.toStringAsFixed(3) ?? "--"} kWh',
                  color: const Color(0xFF34D399),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetricItem({
    required IconData icon,
    required String label,
    required String value,
    required Color color,
  }) {
    return Column(
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.6),
            fontSize: 10,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.bold,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final currentRoom = rooms.firstWhere(
      (r) => r.id == selectedRoomId,
      orElse: () => rooms.first,
    );

    return ValueListenableBuilder<ActionBoxData?>(
      valueListenable: RealtimeEnergyService.instance.deviceDataNotifier,
      builder: (context, actionBoxData, _) {
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(
                height: 360,
                child: ConsumptionChart(showDropdown: false, initialMode: 'hourly'),
              ),
              _buildActionBoxTelemetryCard(actionBoxData),
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
                        _toggleDevice(device, !device.isOn);
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
                                    _toggleDevice(device, val);
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
  },
);
  }
}
