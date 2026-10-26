import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/model/device_model.dart';
import 'package:iot_dashboard/data/model/room_model.dart';

/// Class quản lý và tính toán dữ liệu công suất thiết bị IoT dùng chung
/// cho toàn bộ các biểu đồ (Charts) và thẻ thống kê (Cards) trong ứng dụng.
class DevicePowerManager {
  // Singleton Pattern
  static final DevicePowerManager _instance = DevicePowerManager._internal();
  factory DevicePowerManager() => _instance;
  DevicePowerManager._internal();

  // Giá điện trung bình (VND / kWh)
  static const double defaultPricePerKwh = 2500.0;

  /// Danh sách dữ liệu phòng và thiết bị mẫu chuẩn hệ thống
  final List<RoomModel> rooms = [
    RoomModel(
      id: 'e1',
      name: 'Phòng ngủ',
      devices: [
        DeviceModel(
          id: 'd1',
          name: 'Đèn trần',
          icon: 'lightbulb',
          isOn: true,
          powerWatts: 15,
          color: const Color(0xFF3B82F6),
          hourlyKwh: const [
            0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01,
            0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.03, 0.03, 0.03, 0.02, 0.01, 0.01
          ],
        ),
        DeviceModel(
          id: 'd2',
          name: 'Điều hòa',
          icon: 'ac_unit',
          isOn: false,
          powerWatts: 750,
          color: const Color(0xFF06B6D4),
          hourlyKwh: const [
            0.55, 0.50, 0.45, 0.40, 0.35, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.45,
            0.65, 0.70, 0.55, 0.00, 0.00, 0.00, 0.00, 0.60, 0.75, 0.70, 0.65, 0.60
          ],
        ),
      ],
    ),
    RoomModel(
      id: 'e2',
      name: 'Phòng khách',
      devices: [
        DeviceModel(
          id: 'd3',
          name: 'Đèn chùm',
          icon: 'light',
          isOn: true,
          powerWatts: 40,
          color: const Color(0xFFF59E0B),
          hourlyKwh: const [
            0.03, 0.02, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00,
            0.00, 0.00, 0.00, 0.00, 0.00, 0.04, 0.08, 0.08, 0.08, 0.06, 0.04, 0.03
          ],
        ),
        DeviceModel(
          id: 'd4',
          name: 'Quạt trần',
          icon: 'fan',
          isOn: true,
          powerWatts: 55,
          color: const Color(0xFF10B981),
          hourlyKwh: const [
            0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.05, 0.05, 0.04, 0.04, 0.04, 0.05,
            0.05, 0.05, 0.05, 0.04, 0.04, 0.05, 0.05, 0.05, 0.05, 0.05, 0.04, 0.04
          ],
        ),
        DeviceModel(
          id: 'd5',
          name: 'Tivi',
          icon: 'tv',
          isOn: false,
          powerWatts: 120,
          color: const Color(0xFF8B5CF6),
          hourlyKwh: const [
            0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00,
            0.12, 0.12, 0.00, 0.00, 0.00, 0.00, 0.15, 0.24, 0.24, 0.12, 0.00, 0.00
          ],
        ),
      ],
    ),
    RoomModel(
      id: 'e3',
      name: 'Phòng bếp',
      devices: [
        DeviceModel(
          id: 'd6',
          name: 'Bếp từ',
          icon: 'soup_kitchen',
          isOn: false,
          powerWatts: 2000,
          color: const Color(0xFFEF4444),
          hourlyKwh: const [
            0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.20, 0.00, 0.00, 0.00, 0.80,
            1.20, 0.30, 0.00, 0.00, 0.00, 0.50, 1.50, 1.10, 0.20, 0.00, 0.00, 0.00
          ],
        ),
        DeviceModel(
          id: 'd7',
          name: 'Tủ lạnh',
          icon: 'kitchen',
          isOn: true,
          powerWatts: 150,
          color: const Color(0xFFEC4899),
          hourlyKwh: const [
            0.12, 0.11, 0.10, 0.10, 0.11, 0.12, 0.14, 0.15, 0.15, 0.14, 0.14, 0.15,
            0.16, 0.16, 0.15, 0.14, 0.14, 0.15, 0.16, 0.17, 0.16, 0.15, 0.13, 0.12
          ],
        ),
      ],
    ),
  ];

  /// Dữ liệu mảng tiêu thụ điện theo 24 giờ trong ngày (kWh)
  final List<Map<String, dynamic>> hourlyRawData = [
    {'hour': '00:00', 'kwh': 0.8, 'isPeak': false},
    {'hour': '01:00', 'kwh': 0.6, 'isPeak': false},
    {'hour': '02:00', 'kwh': 0.5, 'isPeak': false},
    {'hour': '03:00', 'kwh': 0.5, 'isPeak': false},
    {'hour': '04:00', 'kwh': 0.6, 'isPeak': false},
    {'hour': '05:00', 'kwh': 1.1, 'isPeak': false},
    {'hour': '06:00', 'kwh': 2.2, 'isPeak': false},
    {'hour': '07:00', 'kwh': 3.5, 'isPeak': false},
    {'hour': '08:00', 'kwh': 4.2, 'isPeak': false},
    {'hour': '09:00', 'kwh': 3.8, 'isPeak': false},
    {'hour': '10:00', 'kwh': 3.1, 'isPeak': false},
    {'hour': '11:00', 'kwh': 3.6, 'isPeak': false},
    {'hour': '12:00', 'kwh': 4.8, 'isPeak': false},
    {'hour': '13:00', 'kwh': 4.5, 'isPeak': true},
    {'hour': '14:00', 'kwh': 3.9, 'isPeak': false},
    {'hour': '15:00', 'kwh': 3.2, 'isPeak': false},
    {'hour': '16:00', 'kwh': 2.8, 'isPeak': false},
    {'hour': '17:00', 'kwh': 3.4, 'isPeak': false},
    {'hour': '18:00', 'kwh': 4.9, 'isPeak': true},
    {'hour': '19:00', 'kwh': 5.2, 'isPeak': true},
    {'hour': '20:00', 'kwh': 4.6, 'isPeak': true},
    {'hour': '21:00', 'kwh': 3.7, 'isPeak': false},
    {'hour': '22:00', 'kwh': 2.3, 'isPeak': false},
    {'hour': '23:00', 'kwh': 1.4, 'isPeak': false},
  ];

  // -------------------------------------------------------------------
  // 1. TÍNH TOÁN CÔNG SUẤT VÀ TRẠNG THÁI THIẾT BỊ
  // -------------------------------------------------------------------

  /// Tính tổng công suất tức thì (Watt) của các thiết bị đang BẬT
  double calculateTotalActivePowerWatts() {
    double total = 0.0;
    for (var room in rooms) {
      for (var device in room.devices) {
        if (device.isOn) {
          total += device.powerWatts;
        }
      }
    }
    return total;
  }

  /// Đếm số thiết bị đang BẬT và Tổng số thiết bị
  Map<String, int> getActiveDeviceCounts() {
    int active = 0;
    int total = 0;
    for (var room in rooms) {
      for (var device in room.devices) {
        total++;
        if (device.isOn) active++;
      }
    }
    return {'active': active, 'total': total};
  }

  // -------------------------------------------------------------------
  // 2. TÍNH TOÁN CHO BIỂU ĐỒ THEO GIỜ (HOURLY CHART)
  // -------------------------------------------------------------------

  /// Lấy danh sách tiêu thụ điện tính đến giờ hiện tại
  List<Map<String, dynamic>> getHourlyDataUntilCurrentHour() {
    final int currentHour = DateTime.now().hour;
    final validLength = (currentHour + 1).clamp(1, hourlyRawData.length);
    return hourlyRawData.sublist(0, validLength);
  }

  /// Tính tổng kWh điện tiêu thụ trong ngày tính tới giờ hiện tại
  double calculateTotalKwhToday() {
    final data = getHourlyDataUntilCurrentHour();
    return data.fold(0.0, (sum, item) => sum + (item['kwh'] as double));
  }

  /// Tính lượng điện tiêu thụ trong giờ cao điểm
  double calculatePeakHoursKwhToday() {
    final data = getHourlyDataUntilCurrentHour();
    return data
        .where((item) => item['isPeak'] == true)
        .fold(0.0, (sum, item) => sum + (item['kwh'] as double));
  }

  // -------------------------------------------------------------------
  // 3. TÍNH TOÁN CHI PHÍ & DỰ BÁO TIỀN ĐIỆN CHO CÁC THẺ (CARDS)
  // -------------------------------------------------------------------

  /// Tính tiền điện dự tính trong ngày (VND)
  double calculateEstimatedCostToday({double pricePerKwh = defaultPricePerKwh}) {
    return calculateTotalKwhToday() * pricePerKwh;
  }

  /// Tính tiền điện dự tính cả tháng (VND)
  double calculateEstimatedMonthlyCost({double pricePerKwh = defaultPricePerKwh}) {
    final kwhToday = calculateTotalKwhToday();
    final int currentHour = DateTime.now().hour + 1;
    final double avgKwhPerHour = currentHour > 0 ? kwhToday / currentHour : 0;
    final double estimatedDailyKwh = avgKwhPerHour * 24;
    return estimatedDailyKwh * 30 * pricePerKwh;
  }

  // -------------------------------------------------------------------
  // 4. TÍNH PHẦN TRĂM CÔNG SUẤT THEO PHÒNG (ROOM BREAKDOWN)
  // -------------------------------------------------------------------

  /// Tính tỷ lệ % đóng góp công suất của từng phòng
  List<Map<String, dynamic>> getRoomPowerBreakdown() {
    final double totalActivePower = calculateTotalActivePowerWatts();
    List<Map<String, dynamic>> result = [];

    for (var room in rooms) {
      double roomPower = 0.0;
      int activeDevices = 0;
      for (var dev in room.devices) {
        if (dev.isOn) {
          roomPower += dev.powerWatts;
          activeDevices++;
        }
      }

      double percentage = totalActivePower > 0
          ? (roomPower / totalActivePower) * 100
          : 0.0;

      result.add({
        'roomId': room.id,
        'roomName': room.name,
        'powerWatts': roomPower,
        'percentage': percentage,
        'activeDevices': activeDevices,
        'totalDevices': room.devices.length,
      });
    }

    return result;
  }

  /// Lấy tất cả danh sách thiết bị trong toàn bộ các phòng
  List<DeviceModel> getAllDevices() {
    return rooms.expand((room) => room.devices).toList();
  }
}
