import 'dart:async';
import 'package:flutter/services.dart';

enum ProvisioningStep {
  connectingAp,
  handshake,
  sendingConfig,
  verifying,
  completed,
  failed,
}

extension ProvisioningStepExt on ProvisioningStep {
  String get wireName {
    switch (this) {
      case ProvisioningStep.connectingAp:
        return 'CONNECTING_AP';
      case ProvisioningStep.handshake:
        return 'HANDSHAKE';
      case ProvisioningStep.sendingConfig:
        return 'SENDING_CONFIG';
      case ProvisioningStep.verifying:
        return 'VERIFYING';
      case ProvisioningStep.completed:
        return 'COMPLETED';
      case ProvisioningStep.failed:
        return 'FAILED';
    }
  }
}

class ProvisioningProgressEvent {
  final ProvisioningStep step;
  final String message;
  final DateTime timestamp;
  final Object? error;

  ProvisioningProgressEvent({
    required this.step,
    required this.message,
    DateTime? timestamp,
    this.error,
  }) : timestamp = timestamp ?? DateTime.now();

  String get stepName => step.wireName;

  @override
  String toString() => 'ProvisioningProgressEvent($stepName: $message)';
}

abstract class ProvisioningException implements Exception {
  final String code;
  final String message;
  const ProvisioningException(this.code, this.message);

  @override
  String toString() => 'ProvisioningException($code): $message';
}

class SetupNetworkTimeoutException extends ProvisioningException {
  const SetupNetworkTimeoutException([String message = 'Hết thời gian kết nối SoftAP của SubBox'])
      : super('SETUP_NETWORK_TIMEOUT', message);
}

class ProofRejectedException extends ProvisioningException {
  const ProofRejectedException([String message = 'Mã thiết lập (POP) không đúng hoặc bị từ chối'])
      : super('PROOF_REJECTED', message);
}

class WifiDisconnectedException extends ProvisioningException {
  const WifiDisconnectedException([String message = 'Mất kết nối Wi-Fi trong quá trình cài đặt'])
      : super('WIFI_DISCONNECTED', message);
}

class PermissionDeniedException extends ProvisioningException {
  const PermissionDeniedException([String message = 'Không có quyền thay đổi trạng thái mạng'])
      : super('PERMISSION_DENIED', message);
}

class ProvisioningFailedException extends ProvisioningException {
  const ProvisioningFailedException([String message = 'Cấu hình thiết bị thất bại'])
      : super('PROVISIONING_FAILED', message);
}

class SubBoxProvisionRequest {
  final String ssid;
  final String password;
  final String gatewayHost;
  final int gatewayPort;
  final String pop;
  final String roomName;
  final int roomType;

  const SubBoxProvisionRequest({
    required this.ssid,
    required this.password,
    required this.gatewayHost,
    this.gatewayPort = 8883,
    required this.pop,
    this.roomName = 'Phòng khách',
    this.roomType = 1,
  });

  Map<String, dynamic> toMap() => {
    'ssid': ssid,
    'password': password,
    'gateway_host': gatewayHost,
    'gateway_port': gatewayPort,
    'pop': pop,
    'room_name': roomName,
    'room_type': roomType,
  };
}

class SubBoxProvisionResult {
  final String status;
  final String ssid;
  final String gatewayHost;
  final String roomName;
  final Map<String, dynamic> raw;

  const SubBoxProvisionResult({
    required this.status,
    required this.ssid,
    required this.gatewayHost,
    required this.roomName,
    required this.raw,
  });

  factory SubBoxProvisionResult.fromMap(Map<String, dynamic> map) {
    return SubBoxProvisionResult(
      status: map['status'] as String? ?? 'SUCCESS',
      ssid: map['ssid'] as String? ?? '',
      gatewayHost: map['gateway_host'] as String? ?? '',
      roomName: map['room_name'] as String? ?? '',
      raw: map,
    );
  }
}

class DeviceProvisioningService {
  final MethodChannel _channel;
  final StreamController<ProvisioningProgressEvent> _eventsController =
      StreamController<ProvisioningProgressEvent>.broadcast(sync: true);

  DeviceProvisioningService({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel('sic/provisioning');

  Stream<ProvisioningProgressEvent> get provisioningEvents =>
      _eventsController.stream;

  void dispose() {
    _eventsController.close();
  }

  void _emit(ProvisioningStep step, String message, {Object? error}) {
    if (!_eventsController.isClosed) {
      _eventsController.add(ProvisioningProgressEvent(
        step: step,
        message: message,
        error: error,
      ));
    }
  }

  ProvisioningException mapPlatformException(PlatformException e) {
    switch (e.code) {
      case 'SETUP_NETWORK_TIMEOUT':
        return SetupNetworkTimeoutException(e.message ?? 'Hết thời gian kết nối mạng setup');
      case 'PROOF_REJECTED':
        return ProofRejectedException(e.message ?? 'Mã xác thực bị từ chối');
      case 'WIFI_DISCONNECTED':
        return WifiDisconnectedException(e.message ?? 'Mất kết nối Wi-Fi');
      case 'PERMISSION_DENIED':
        return PermissionDeniedException(e.message ?? 'Quyền bị từ chối');
      case 'PROVISIONING_FAILED':
      default:
        return ProvisioningFailedException(e.message ?? 'Cấu hình thất bại');
    }
  }

  Future<void> connectSetupNetwork(String ssid, String password) async {
    _emit(ProvisioningStep.connectingAp, 'Đang kết nối tới SoftAP $ssid...');
    try {
      await _channel.invokeMethod<bool>('connectSetupNetwork', {
        'ssid': ssid,
        'password': password,
      });
      _emit(ProvisioningStep.connectingAp, 'Đã kết nối SoftAP $ssid');
    } on PlatformException catch (e) {
      final ex = mapPlatformException(e);
      _emit(ProvisioningStep.failed, ex.message, error: ex);
      throw ex;
    } catch (e) {
      final ex = ProvisioningFailedException(e.toString());
      _emit(ProvisioningStep.failed, ex.message, error: ex);
      throw ex;
    }
  }

  Future<Map<String, dynamic>> provisionSubBox({
    required String ssid,
    required String password,
    required String gatewayHost,
    int gatewayPort = 8883,
    required String pop,
    String roomName = 'Phòng khách',
    int roomType = 1,
  }) async {
    try {
      _emit(ProvisioningStep.handshake, 'Đang thiết lập phiên bảo mật với SubBox...');
      _emit(ProvisioningStep.sendingConfig, 'Đang gửi cấu hình Wi-Fi và Gateway...');

      final rawResult = await _channel.invokeMapMethod<String, dynamic>('provisionSubBox', {
        'ssid': ssid,
        'password': password,
        'gateway_host': gatewayHost,
        'gateway_port': gatewayPort,
        'pop': pop,
        'room_name': roomName,
        'room_type': roomType,
      });

      _emit(ProvisioningStep.verifying, 'Đang xác nhận cấu hình thiết bị...');
      final result = rawResult != null
          ? Map<String, dynamic>.from(rawResult)
          : <String, dynamic>{'status': 'SUCCESS'};
      _emit(ProvisioningStep.completed, 'Cấu hình SubBox thành công!');
      return result;
    } on PlatformException catch (e) {
      final ex = mapPlatformException(e);
      _emit(ProvisioningStep.failed, ex.message, error: ex);
      throw ex;
    } catch (e) {
      final ex = ProvisioningFailedException(e.toString());
      _emit(ProvisioningStep.failed, ex.message, error: ex);
      throw ex;
    }
  }

  Future<void> cancelProvisioning() async {
    try {
      await _channel.invokeMethod<void>('cancelProvisioning');
    } on PlatformException catch (e) {
      throw mapPlatformException(e);
    }
  }
}
