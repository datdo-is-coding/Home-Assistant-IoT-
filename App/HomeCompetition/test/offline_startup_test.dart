import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:home_competition/app/home_competition_app.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/services/gateway_cache_service.dart';

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  group('Offline Startup & Snapshot Cache Tests', () {
    testWidgets(
        'F4: Cold start offline opens cached shell immediately without 10s network spinner timeout',
        (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);

      final capturedTime = DateTime(2026, 10, 19, 14, 30);
      final cacheService = GatewayCacheService(debounceDuration: Duration.zero);
      final snapshot = CachedSnapshot(
        scope: const SessionScope(
          gatewayUrl: 'http://gateway:8000',
          userId: 'admin',
          generation: 1,
        ),
        revision: 1,
        capturedAt: capturedTime,
        user: {'id': 'admin', 'role': 'admin', 'fullname': 'Quản Trị Viên'},
        nodes: {
          'AB1': {
            'name': 'Công tắc phòng khách',
            'status': 'online',
            'room': 'phong_khach',
            'relay_state': [1, 0],
            'channels': {
              'ch1': {'name': 'Đèn trần', 'device_type': 'light'},
              'ch2': {'name': 'Quạt trần', 'device_type': 'fan'},
            }
          }
        },
        pending: {},
      );

      // Pre-seed storage
      SharedPreferences.setMockInitialValues({
        'gateway_server_url': 'http://gateway:8000',
        'gw_last_user_http://gateway:8000': 'admin',
        'gw_snapshot_http://gateway:8000::admin': jsonEncode(snapshot.toJson()),
      });

      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('sic/session'),
        (call) async => call.method == 'read'
            ? jsonEncode({
                'url': 'http://gateway:8000',
                'token': 'saved_token',
                'user': {'id': 'admin', 'role': 'admin'}
              })
            : null,
      );
      addTearDown(() => tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(const MethodChannel('sic/session'), null));

      // Network mock throws error (offline)
      final client = GatewayClient(
        cacheService: cacheService,
        client: MockClient((req) async {
          throw http.ClientException('Network offline / unreachable');
        }),
      );
      addTearDown(client.dispose);

      await tester.pumpWidget(ProviderScope(
        overrides: [gatewayClientProvider.overrideWith((ref) => client)],
        child: const HomeCompetitionApp(),
      ));

      // UI renders shell immediately without blocking on 10s network timeout
      await tester.pumpAndSettle();

      // Zero-wait check: NO spinner blocking the user!
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.text('My Home'), findsOneWidget);
      expect(find.text('Nhà'), findsOneWidget);

      // Verify cached devices rendered from snapshot
      expect(find.text('Đèn trần'), findsWidgets);
      expect(find.text('Quạt trần'), findsWidgets);

      // Verify client offline state and truthful indicators
      expect(client.authenticated, isTrue);
      expect(client.connected, isFalse);
      expect(client.isStale, isTrue);
      expect(client.updatedAt, capturedTime);

      // Truthful indicators: 0 devices online (TUYỆT ĐỐI KHÔNG hiện trạng thái online giả)
      expect(find.text('2 thiết bị · 0 trực tuyến'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });

    test('Corrupted cache recovery automatically cleans up corrupted entries without crashing',
        () async {
      SharedPreferences.setMockInitialValues({
        'gw_snapshot_http://gateway:8000::user1': '{corrupted json not valid!',
      });

      final cacheService = GatewayCacheService(debounceDuration: Duration.zero);
      final loaded =
          await cacheService.loadSnapshot('http://gateway:8000', 'user1');

      // Should return null gracefully instead of throwing
      expect(loaded, isNull);

      // Corrupted entry should be removed from SharedPreferences
      final prefs = await SharedPreferences.getInstance();
      expect(
          prefs.getString('gw_snapshot_http://gateway:8000::user1'), isNull);
    });

    test('Logout clears cache scope from local storage', () async {
      final cacheService = GatewayCacheService(debounceDuration: Duration.zero);
      final snapshot = CachedSnapshot(
        scope: const SessionScope(
          gatewayUrl: 'http://gateway:8000',
          userId: 'user1',
          generation: 1,
        ),
        capturedAt: DateTime.now(),
        nodes: {'AB1': {}},
      );

      SharedPreferences.setMockInitialValues({});
      await cacheService.saveSnapshot(snapshot, immediate: true);

      // Verify saved
      var cached =
          await cacheService.loadSnapshot('http://gateway:8000', 'user1');
      expect(cached, isNotNull);

      // Client logout
      final client = GatewayClient(
        persistSession: true,
        cacheService: cacheService,
        client: MockClient((req) async {
          if (req.url.path == '/api/auth/me') {
            return http.Response(
                '{"authenticated":true,"user":{"id":"user1"}}', 200);
          }
          if (req.url.path == '/api/auth/logout') {
            return http.Response('{"success":true}', 200);
          }
          return http.Response('{}', 200);
        }),
      );
      addTearDown(client.dispose);

      await client.loginWithKey(url: 'http://gateway:8000', key: 'tok');
      expect(client.currentUserId, 'user1');

      await client.logout();

      // Verify scope was cleared from cache
      cached = await cacheService.loadSnapshot('http://gateway:8000', 'user1');
      expect(cached, isNull);
    });

    test('Debounced snapshot saving writes to disk after debounce delay',
        () async {
      SharedPreferences.setMockInitialValues({});
      final cacheService = GatewayCacheService(
        debounceDuration: const Duration(milliseconds: 50),
      );
      addTearDown(cacheService.dispose);

      final snapshot = CachedSnapshot(
        scope: const SessionScope(
          gatewayUrl: 'http://gateway:8000',
          userId: 'user1',
          generation: 1,
        ),
        capturedAt: DateTime.now(),
        nodes: {'AB1': {'relay_state': [1, 0]}},
      );

      await cacheService.saveSnapshot(snapshot);

      // In-memory returns immediately
      final inMem =
          await cacheService.loadSnapshot('http://gateway:8000', 'user1');
      expect(inMem, isNotNull);

      // But SharedPreferences disk hasn't flushed yet
      var prefs = await SharedPreferences.getInstance();
      expect(
          prefs.getString('gw_snapshot_http://gateway:8000::user1'), isNull);

      // Wait for debounce timer
      await Future<void>.delayed(const Duration(milliseconds: 70));

      prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('gw_snapshot_http://gateway:8000::user1'),
          isNotNull);
    });
  });
}
