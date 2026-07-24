import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  final FlutterLocalNotificationsPlugin _notificationsPlugin = FlutterLocalNotificationsPlugin();
  bool _isInitialized = false;
  int _lastNotificationTime = 0;

  Future<void> init() async {
    if (_isInitialized) return;

    const AndroidInitializationSettings initializationSettingsAndroid =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const InitializationSettings initializationSettings = InitializationSettings(
      android: initializationSettingsAndroid,
    );

    await _notificationsPlugin.initialize(
      initializationSettings,
      onDidReceiveNotificationResponse: (NotificationResponse details) {
        // Handle notification click if needed
      },
    );

    _isInitialized = true;
  }

  Future<void> showAnomalyNotification({
    required int id,
    required String title,
    required String body,
    bool isCritical = false,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _lastNotificationTime < 15000) return; // Prevent spamming within 15 seconds
    _lastNotificationTime = now;

    AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
      isCritical ? 'critical_alerts_channel' : 'energy_insights_channel',
      isCritical ? '🚨 Cảnh Báo An Toàn Điện' : '💡 Lời Nhắc Tiết Kiệm Điện EVN',
      channelDescription: 'Thông báo đẩy từ máy chủ ESP32-S3 TinyML AI',
      importance: isCritical ? Importance.max : Importance.defaultImportance,
      priority: isCritical ? Priority.high : Priority.defaultPriority,
      color: isCritical ? Color(0xFFEF4444) : Color(0xFF38BDF8),
      playSound: true,
      enableVibration: true,
    );

    NotificationDetails notificationDetails = NotificationDetails(android: androidDetails);

    await _notificationsPlugin.show(
      id,
      title,
      body,
      notificationDetails,
    );
  }
}
