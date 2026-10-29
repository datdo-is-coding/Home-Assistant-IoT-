import 'package:iot_dashboard/data/model/user_model.dart';

class AuthValidator {
  /// Validate thông tin đăng nhập
  static String? validateSignIn({
    required String email,
    required String password,
  }) {
    if (email.isEmpty || password.isEmpty) {
      return 'Vui lòng nhập đầy đủ Email và Mật khẩu!';
    }
    if (!email.contains('@')) {
      return 'Email không đúng định dạng (cần có ký tự @)!';
    }
    return null;
  }

  /// Validate thông tin đăng ký
  static String? validateSignUp({
    required String name,
    required String email,
    required String password,
    required bool isAgreed,
  }) {
    if (name.isEmpty || email.isEmpty || password.isEmpty) {
      return 'Vui lòng nhập đầy đủ thông tin!';
    }
    if (!email.contains('@')) {
      return 'Email không đúng định dạng (cần có ký tự @)!';
    }
    if (password.length < 6) {
      return 'Mật khẩu phải có ít nhất 6 ký tự!';
    }
    if (!isAgreed) {
      return 'Vui lòng đồng ý với Điều khoản và Chính sách bảo mật!';
    }
    return null;
  }

  /// Tạo dữ liệu tài khoản khi đăng nhập thành công
  static UserModel createSignInUserData({
    required String email,
    required String password,
  }) {
    final displayName = email.split('@').first.toUpperCase();

    return UserModel(
      id: 'usr_001',
      name: displayName,
      email: email,
      phone: '0987 654 321',
      address: '123 Đường Công Nghệ, Q. Bình Thạnh, TP.HCM',
      password: password,
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
            RoomDeviceInfo(
              deviceName: 'Đèn trần',
              powerWatts: '15W',
              isOn: true,
            ),
            RoomDeviceInfo(
              deviceName: 'Điều hòa',
              powerWatts: '750W',
              isOn: false,
            ),
          ],
          'Phòng khách': [
            RoomDeviceInfo(
              deviceName: 'Đèn chùm',
              powerWatts: '40W',
              isOn: true,
            ),
            RoomDeviceInfo(
              deviceName: 'Quạt trần',
              powerWatts: '55W',
              isOn: true,
            ),
            RoomDeviceInfo(
              deviceName: 'Tivi',
              powerWatts: '120W',
              isOn: false,
            ),
          ],
          'Phòng bếp': [
            RoomDeviceInfo(
              deviceName: 'Bếp từ',
              powerWatts: '2000W',
              isOn: false,
            ),
            RoomDeviceInfo(
              deviceName: 'Tủ lạnh',
              powerWatts: '150W',
              isOn: true,
            ),
          ],
        },
      ),
    );
  }

  /// Tạo dữ liệu tài khoản mới khi đăng ký thành công
  static UserModel createSignUpUserData({
    required String name,
    required String email,
    required String password,
  }) {
    final timestamp = DateTime.now().millisecondsSinceEpoch.toString();
    final userId = 'usr_${timestamp.length > 6 ? timestamp.substring(timestamp.length - 6) : timestamp}';

    return UserModel(
      id: userId,
      name: name,
      email: email,
      phone: 'Chưa cập nhật',
      address: 'Chưa cập nhật',
      password: password,
      avatarUrl: 'https://i.pravatar.cc/150?img=12',
      package: MaintenancePackageModel(
        packageName: 'Gói Bảo Trì 12 Tháng (Mới tạo)',
        durationMonths: 12,
        registrationDate: DateTime.now(),
        expiryDate: DateTime.now().add(const Duration(days: 365)),
        totalRooms: 3,
        totalDevices: 7,
        roomDevicesDetails: {
          'Phòng ngủ': [
            RoomDeviceInfo(
              deviceName: 'Đèn trần',
              powerWatts: '15W',
              isOn: true,
            ),
            RoomDeviceInfo(
              deviceName: 'Điều hòa',
              powerWatts: '750W',
              isOn: false,
            ),
          ],
          'Phòng khách': [
            RoomDeviceInfo(
              deviceName: 'Đèn chùm',
              powerWatts: '40W',
              isOn: true,
            ),
            RoomDeviceInfo(
              deviceName: 'Quạt trần',
              powerWatts: '55W',
              isOn: true,
            ),
            RoomDeviceInfo(
              deviceName: 'Tivi',
              powerWatts: '120W',
              isOn: false,
            ),
          ],
          'Phòng bếp': [
            RoomDeviceInfo(
              deviceName: 'Bếp từ',
              powerWatts: '2000W',
              isOn: false,
            ),
            RoomDeviceInfo(
              deviceName: 'Tủ lạnh',
              powerWatts: '150W',
              isOn: true,
            ),
          ],
        },
      ),
    );
  }
}
