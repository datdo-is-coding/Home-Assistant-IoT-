import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'core_client.dart';

class CoreProvisionInfo {
  final String factoryId, radioMac, challenge;
  final bool isSubBox;
  CoreProvisionInfo._(
      this.factoryId, this.radioMac, this.challenge, this.isSubBox);
  factory CoreProvisionInfo.parse(Uint8List bytes) {
    if (bytes.length != 49 ||
        ascii.decode(bytes.sublist(0, 4), allowInvalid: true) != 'HCI1' ||
        ![1, 2].contains(bytes[4])) {
      throw const CoreException(
          'invalid_identity', 'Box trả thông tin provisioning không hợp lệ.');
    }
    String hex(List<int> data) =>
        data.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return CoreProvisionInfo._('HC-${hex(bytes.sublist(5, 11)).toUpperCase()}',
        hex(bytes.sublist(11, 17)), hex(bytes.sublist(17)), bytes[4] == 1);
  }
}

class CoreProvisioning {
  static const channel = MethodChannel('home_competition/provisioning');
  static bool get supported => Platform.isAndroid;
  static Future<void> wifiSettings() =>
      channel.invokeMethod<void>('wifiSettings');
  static Future<Uint8List> exchange(
      String pop, String endpoint, Uint8List payload) async {
    if (!supported)
      throw const CoreException(
          'unsupported', 'Secure provisioning hiện hỗ trợ Android.');
    try {
      final result = await channel.invokeMethod<Uint8List>('exchange', {
        'pop': pop,
        'endpoint': endpoint,
        'payload': payload
      }).timeout(const Duration(seconds: 20));
      if (result == null)
        throw const CoreException('invalid_response', 'Box không trả dữ liệu.');
      return result;
    } on PlatformException {
      throw const CoreException('provisioning_failed',
          'Không xác thực được Box. Kiểm tra SoftAP, setup code và cửa sổ ghép nối vật lý.');
    } on TimeoutException {
      throw const CoreException('timeout',
          'Box chưa phản hồi. Kết quả lưu cấu hình chưa xác định; kiểm tra trạng thái trên Gateway.');
    }
  }

  static Uint8List decodeHex(String value) {
    if (value.length.isOdd || !RegExp(r'^[0-9a-fA-F]+$').hasMatch(value))
      throw const CoreException(
          'invalid_packet', 'Gateway trả gói cấu hình không hợp lệ.');
    return Uint8List.fromList([
      for (int i = 0; i < value.length; i += 2)
        int.parse(value.substring(i, i + 2), radix: 16)
    ]);
  }
}
