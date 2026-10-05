import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dtv_energy_flutter/app/smart_home_app.dart';
import 'package:dtv_energy_flutter/providers/smart_home_providers.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';

void main() {
  testWidgets('restores saved session and recovers after network loss', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    SharedPreferences.setMockInitialValues({});
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('sic/session'),
      (call) async => call.method == 'read'
          ? jsonEncode({'url': 'http://gateway:8000', 'token': 'saved-session'})
          : null,
    );
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('sic/session'), null));
    var offline = false;
    var expired = false;
    var requests = 0;
    final client = GatewayClient(client: MockClient((request) async {
      requests++;
      expectSync(request.headers['Authorization'], 'Bearer saved-session');
      if (offline) throw http.ClientException('network unavailable');
      if (expired) return http.Response('{}', 401);
      if (request.url.path == '/api/auth/me') {
        return http.Response('{"authenticated":true,"user":{"role":"admin"}}', 200);
      }
      return http.Response('{"nodes":{},"pending":{}}', 200);
    }));
    await tester.pumpWidget(ProviderScope(
      overrides: [gatewayClientProvider.overrideWith((ref) => client)],
      child: const SmartHomeApp(),
    ));
    await tester.pumpAndSettle();
    expect(client.authenticated, isTrue);
    expect(client.connected, isTrue);
    expect(find.text('My Home'), findsOneWidget);

    offline = true;
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(client.connected, isFalse);
    expect(find.text('Thử kết nối lại'), findsOneWidget);
    offline = false;
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(client.connected, isTrue);
    expect(find.text('Thêm thiết bị'), findsWidgets);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    offline = true;
    await tester.pump(const Duration(seconds: 10));
    expect(client.connected, isTrue);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(client.connected, isFalse);
    expect(client.loading, isFalse, reason: 'resume request completed');
    offline = false;
    expired = true;
    final previousRequests = requests;
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(requests, greaterThan(previousRequests), reason: 'polling resumes');
    expect(client.authenticated, isFalse, reason: '401 must clear the saved session; loading=${client.loading}, error=${client.error}');
    expect(find.text('Kết nối Gateway'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('no saved session opens login instead of a disconnected dashboard', (tester) async {
    final client = GatewayClient(persistSession: false);
    await tester.pumpWidget(ProviderScope(
      overrides: [gatewayClientProvider.overrideWith((ref) => client)],
      child: const SmartHomeApp(),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Kết nối Gateway'), findsOneWidget);
    expect(find.text('Thử kết nối lại'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
