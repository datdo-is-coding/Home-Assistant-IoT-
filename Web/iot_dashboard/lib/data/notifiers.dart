import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/model/user_model.dart';

ValueNotifier<int> selectedPageNotifier = ValueNotifier(0);
ValueNotifier<bool> isSidebarOpenNotifier = ValueNotifier(true);
ValueNotifier<bool> isLampOnNotifier = ValueNotifier(false);
ValueNotifier<bool> isFanOnNotifier = ValueNotifier(false);
ValueNotifier<bool> isAwayModeNotifier = ValueNotifier(false);
ValueNotifier<bool> isDarkModeNotifier = ValueNotifier(true);
ValueNotifier<bool> isGuestModeNotifier = ValueNotifier(false);
ValueNotifier<UserModel> currentUserNotifier = ValueNotifier<UserModel>(
  UserModel(
    id: 'usr_001',
    name: 'Phạm Vinh',
    email: 'phamvinh@example.com',
    phone: '0987 654 321',
    address: '123 Đường Công Nghệ, Q. Bình Thạnh, TP.HCM',
    password: 'password123',
    avatarUrl: 'https://i.pravatar.cc/150?img=68',
    package: MaintenancePackageModel(
      packageName: 'Gói Bảo Trì Cao Cấp 12 Tháng',
      durationMonths: 12,
      registrationDate: DateTime(2026, 1, 15),
      expiryDate: DateTime(2027, 1, 15),
      totalRooms: 3,
      totalDevices: 7,
      roomDevicesDetails: {
        'Phòng ngủ': [
          RoomDeviceInfo(deviceName: 'Đèn trần', powerWatts: '15W', isOn: true),
          RoomDeviceInfo(
            deviceName: 'Điều hòa',
            powerWatts: '750W',
            isOn: false,
          ),
        ],
        'Phòng khách': [
          RoomDeviceInfo(deviceName: 'Đèn chùm', powerWatts: '40W', isOn: true),
          RoomDeviceInfo(
            deviceName: 'Quạt trần',
            powerWatts: '55W',
            isOn: true,
          ),
          RoomDeviceInfo(deviceName: 'Tivi', powerWatts: '120W', isOn: false),
        ],
        'Phòng bếp': [
          RoomDeviceInfo(
            deviceName: 'Bếp từ',
            powerWatts: '2000W',
            isOn: false,
          ),
          RoomDeviceInfo(deviceName: 'Tủ lạnh', powerWatts: '150W', isOn: true),
        ],
      },
    ),
  ),
);
