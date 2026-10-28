class MaintenancePackageModel {
  final String packageName; // Tên gói: "Gói Bảo Trì 12 Tháng" hoặc "24 Tháng"
  final int durationMonths; // 12 hoặc 24 tháng
  final DateTime registrationDate; // Ngày đăng ký
  final DateTime expiryDate; // Ngày hết hạn
  final int totalRooms; // Tổng số phòng
  final int totalDevices; // Tổng số thiết bị
  final Map<String, int>
  roomDevices; // Số thiết bị từng phòng {"Phòng khách": 3, "Phòng ngủ": 2}
  MaintenancePackageModel({
    required this.packageName,
    required this.durationMonths,
    required this.registrationDate,
    required this.expiryDate,
    required this.totalRooms,
    required this.totalDevices,
    required this.roomDevices,
  });
}
