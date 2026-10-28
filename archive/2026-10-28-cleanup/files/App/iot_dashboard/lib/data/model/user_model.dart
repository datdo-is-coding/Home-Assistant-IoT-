class RoomDeviceInfo {
  final String deviceName;
  final String powerWatts;
  final bool isOn;

  RoomDeviceInfo({
    required this.deviceName,
    required this.powerWatts,
    required this.isOn,
  });
}

class MaintenancePackageModel {
  final String packageName;
  final int durationMonths;
  final DateTime registrationDate;
  final DateTime expiryDate;
  final int totalRooms;
  final int totalDevices;
  final Map<String, List<RoomDeviceInfo>> roomDevicesDetails;

  MaintenancePackageModel({
    required this.packageName,
    required this.durationMonths,
    required this.registrationDate,
    required this.expiryDate,
    required this.totalRooms,
    required this.totalDevices,
    required this.roomDevicesDetails,
  });
}

class UserModel {
  String id;
  String name;
  String email;
  String phone;
  String address;
  String password;
  String avatarUrl;
  MaintenancePackageModel package;

  UserModel({
    required this.id,
    required this.name,
    required this.email,
    required this.phone,
    required this.address,
    required this.password,
    required this.avatarUrl,
    required this.package,
  });
}
