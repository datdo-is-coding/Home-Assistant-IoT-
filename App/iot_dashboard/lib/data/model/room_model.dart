import 'device_model.dart';

class RoomModel {
  final String id; // Mã phòng (ví dụ: 'e1', 'e2')
  final String name; // Tên phòng (ví dụ: 'Phòng khách')
  final List<DeviceModel> devices; // Danh sách các thiết bị thuộc phòng này

  RoomModel({required this.id, required this.name, required this.devices});
}
