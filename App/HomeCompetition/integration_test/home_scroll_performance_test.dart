import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:home_competition/app/home_competition_app.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/gateway_client.dart';
import 'package:home_competition/widgets/device_card.dart';

class PerformanceClient extends GatewayClient {
  PerformanceClient() : super(persistSession: false) {
    user = {'id': 'synthetic-performance', 'role': 'user'};
    serverUrl = 'https://performance.invalid';
    connected = true;
    update(0);
  }
  @override
  bool get authenticated => true;
  @override
  bool get usesFirebase => true;
  @override
  Future<void> restoreLocalSession() async {}
  @override
  Future<void> revalidateSession() async {}
  @override
  Future<void> refresh() async {}
  @override
  Future<Map<String, dynamic>> relay(
          String nodeId, String channel, bool on) async =>
      throw StateError(
          'Physical control is forbidden in the performance fixture');

  void update(int tick) {
    final now = DateTime.now().millisecondsSinceEpoch / 1000;
    nodes = {
      for (var box = 0; box < 40; box++)
        'box_$box': {
          'name': 'Bộ điều khiển $box',
          'status': 'online',
          'room': 'room_${box % 4}',
          'relay_state': [true, false, true],
          'channels': {
            for (var channel = 1; channel <= 3; channel++)
              'ch$channel': {
                'name': 'Thiết bị $box/$channel',
                'device_type': 'light',
                'telemetry': {
                  'valid': true,
                  'received_at': now,
                  'current_ma': 100 + tick % 10,
                  'voltage_v': 220,
                  'power_w': 20 + tick % 10
                },
              }
          },
        }
    };
    notifyListeners();
  }
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('120-channel scrolling with 5Hz updates', (tester) async {
    final client = PerformanceClient();
    await tester.pumpWidget(ProviderScope(overrides: [
      gatewayClientProvider.overrideWith((ref) => client),
    ], child: const HomeCompetitionApp()));
    await tester.pumpAndSettle();
    expect(find.byType(DeviceCard), findsWidgets);
    expect(client.nodes.length, 40);
    final scroll = find.byType(CustomScrollView).first;
    expect(scroll, findsOneWidget);
    // Warm up both directions before recording steady-state frames.
    await tester.fling(scroll, const Offset(0, -900), 1800);
    await tester.pumpAndSettle();
    await tester.fling(scroll, const Offset(0, 900), 1800);
    await tester.pumpAndSettle();
    var tick = 0;
    final updates = Timer.periodic(
        const Duration(milliseconds: 200), (_) => client.update(++tick));
    try {
      final timings = <FrameTiming>[];
      void record(List<FrameTiming> frames) => timings.addAll(frames);
      binding.addTimingsCallback(record);
      try {
        for (var i = 0; i < 8; i++) {
          await tester.fling(scroll, const Offset(0, -700), 2200);
          await tester.pump(const Duration(milliseconds: 500));
          await tester.fling(scroll, const Offset(0, 700), 2200);
          await tester.pump(const Duration(milliseconds: 500));
        }
        updates.cancel();
        await Future<void>.delayed(const Duration(seconds: 1));
      } finally {
        binding.removeTimingsCallback(record);
      }
      expect(timings.length, greaterThan(20));
      Map<String, Object> summarize(List<double> values) {
        values.sort();
        double percentile(double p) =>
            values[((values.length - 1) * p).round()];
        return {
          'count': values.length,
          'p50_ms': percentile(0.5),
          'p95_ms': percentile(0.95),
          'p99_ms': percentile(0.99),
          'over_8ms': values.where((v) => v > 8.333).length,
          'over_16ms': values.where((v) => v > 16.667).length
        };
      }

      binding.reportData = {
        'scroll_120_channels_5hz': {
          'build': summarize(timings
              .map((f) => f.buildDuration.inMicroseconds / 1000)
              .toList()),
          'raster': summarize(timings
              .map((f) => f.rasterDuration.inMicroseconds / 1000)
              .toList()),
          'updates': tick,
        }
      };
      expect(tick, greaterThan(0));
      expect(tester.takeException(), isNull);
    } finally {
      updates.cancel();
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });
}
