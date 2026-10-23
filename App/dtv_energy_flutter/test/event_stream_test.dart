import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:dtv_energy_flutter/services/gateway_event_stream.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('M3 Task T12: GatewayEventStream & SSE Parser Tests', () {
    test('Test SSE chunk parsing: chunk split across multi-byte UTF-8 char and across lines is perfectly assembled', () {
      final events = <GatewayEvent>[];
      final parser = SseParser(
        onEvent: events.add,
      );

      // Vietnamese payload with multi-byte characters:
      // 'Đ' is 0xC4 0x90 (2 bytes)
      // 'ề' is 0xE1 0xBB 0x81 (3 bytes)
      // 'ộ' is 0xE1 0xBB 0x99 (3 bytes)
      const rawSseText =
          'id: 42\n'
          'event: relay_state\n'
          'data: {"name": "Đèn trần & Thiết bị điện", "revision": 42}\n\n';

      final fullBytes = utf8.encode(rawSseText);

      // Find the index of the first byte of 'Đ' (0xC4)
      final c4Index = fullBytes.indexOf(0xC4);
      expect(c4Index, isNonNegative);

      // Cut 1: right in the middle of 'Đ' (between 0xC4 and 0x90)
      final chunk1 = fullBytes.sublist(0, c4Index + 1); // contains 0xC4
      // Cut 2: slice through the data line
      final cutLineIndex = fullBytes.indexOf(0x0A, c4Index); // \n after data line
      final chunk2 = fullBytes.sublist(c4Index + 1, cutLineIndex + 1); // contains 0x90 ... \n
      // Cut 3: final \n to complete the SSE block
      final chunk3 = fullBytes.sublist(cutLineIndex + 1);

      parser.feedChunk(chunk1);
      expect(events.isEmpty, true, reason: 'Incomplete chunk must not trigger event dispatch');

      parser.feedChunk(chunk2);
      expect(events.isEmpty, true, reason: 'Waiting for trailing empty line');

      parser.feedChunk(chunk3);
      expect(events.length, 1, reason: 'Complete block dispatched');

      final ev = events.first;
      expect(ev.id, '42');
      expect(ev.name, 'relay_state');
      expect(ev.revision, 42);
      expect(ev.data['name'], 'Đèn trần & Thiết bị điện');
      expect(ev.data['revision'], 42);
    });

    test('Test SSE events: init, relay_state, node_status, node_telemetry, and keepalive comment', () {
      final events = <GatewayEvent>[];
      int keepAliveCount = 0;

      final parser = SseParser(
        onEvent: events.add,
        onKeepAlive: () => keepAliveCount++,
      );

      // 1. Keepalive
      parser.feedString(': keepalive\n\n');
      expect(keepAliveCount, 1);
      expect(events.isEmpty, true);

      // 2. Init event
      parser.feedString('id: 0\nevent: init\ndata: {"nodes": {"node1": {"status": "online"}}}\n\n');
      expect(events.length, 1);
      expect(events.last.name, 'init');
      expect(events.last.data['nodes']['node1']['status'], 'online');

      // 3. relay_state event
      parser.feedString('id: 1\nevent: relay_state\ndata: {"node_id": "node1", "relay_state": [1, 0], "revision": 1}\n\n');
      expect(events.length, 2);
      expect(events.last.name, 'relay_state');
      expect(events.last.revision, 1);
      expect(events.last.data['relay_state'], [1, 0]);

      // 4. node_status event
      parser.feedString('id: 2\nevent: node_status\ndata: {"node_id": "node1", "online": false, "revision": 2}\n\n');
      expect(events.length, 3);
      expect(events.last.name, 'node_status');
      expect(events.last.revision, 2);
      expect(events.last.data['online'], false);

      // 5. node_telemetry event
      parser.feedString('id: 3\nevent: node_telemetry\ndata: {"node_id": "node1", "power": 98.4, "revision": 3}\n\n');
      expect(events.length, 4);
      expect(events.last.name, 'node_telemetry');
      expect(events.last.revision, 3);
      expect(events.last.data['power'], 98.4);
    });

    test('Test Revision Gap Detection: sending revision 1 then revision 4 triggers onGapDetected', () {
      int gapDetections = 0;
      final events = <GatewayEvent>[];

      final stream = GatewayEventStream(
        gatewayUrl: () => 'http://test:8000',
        tokenProvider: () => 'mock-token',
        onEvent: events.add,
        onGapDetected: () => gapDetections++,
      );

      // Revision 1
      stream.feedString('id: 1\nevent: node_status\ndata: {"node_id": "n1", "revision": 1}\n\n');
      expect(gapDetections, 0);
      expect(stream.lastRevision, 1);

      // Revision 2
      stream.feedString('id: 2\nevent: node_status\ndata: {"node_id": "n1", "revision": 2}\n\n');
      expect(gapDetections, 0);
      expect(stream.lastRevision, 2);

      // Revision 4 (skipped revision 3!) -> GAP!
      stream.feedString('id: 4\nevent: node_status\ndata: {"node_id": "n1", "revision": 4}\n\n');
      expect(gapDetections, 1, reason: 'Gap from 2 to 4 must invoke onGapDetected');
      expect(stream.lastRevision, 4);

      // Revision 5 (contiguous again)
      stream.feedString('id: 5\nevent: node_status\ndata: {"node_id": "n1", "revision": 5}\n\n');
      expect(gapDetections, 1, reason: 'Contiguous revision must not trigger gap');
      expect(stream.lastRevision, 5);

      stream.dispose();
    });

    test('Test Telemetry Coalescing: 10 rapid telemetry events in 100ms are coalesced, while relay_state dispatches immediately', () async {
      final emittedEvents = <GatewayEvent>[];

      final stream = GatewayEventStream(
        gatewayUrl: () => 'http://test:8000',
        tokenProvider: () => 'mock-token',
        telemetryThrottle: const Duration(milliseconds: 250),
        onEvent: emittedEvents.add,
      );

      // Send 1st telemetry event at t=0
      stream.feedString('event: node_telemetry\ndata: {"node_id": "n1", "power": 10.0}\n\n');
      expect(emittedEvents.length, 1, reason: 'First telemetry event emits immediately');
      expect(emittedEvents.first.data['power'], 10.0);

      // Rapidly fire 9 more telemetry events for node "n1"
      for (int i = 2; i <= 10; i++) {
        stream.feedString('event: node_telemetry\ndata: {"node_id": "n1", "power": ${10.0 * i}}\n\n');
      }

      // In the middle, send a critical relay_state event
      stream.feedString('event: relay_state\ndata: {"node_id": "n1", "relay_state": [1, 1]}\n\n');

      // The critical relay_state event must be emitted immediately without throttle!
      expect(emittedEvents.length, 2);
      expect(emittedEvents.last.name, 'relay_state');
      expect(emittedEvents.last.data['relay_state'], [1, 1]);

      // Telemetry events 2-10 must have been coalesced (pending the 250ms window)
      // Advance time past 250ms
      await Future<void>.delayed(const Duration(milliseconds: 280));

      // After throttle period, exactly ONE coalesced telemetry event (the 10th one) is emitted
      expect(emittedEvents.length, 3);
      final finalTelemetry = emittedEvents.last;
      expect(finalTelemetry.name, 'node_telemetry');
      expect(finalTelemetry.data['power'], 100.0, reason: 'Coalescer must emit the freshest telemetry value');

      stream.dispose();
    });

    test('Test Reconnect Backoff: delay calculation follows 2s, 4s, 8s, 16s, 30s sequence', () {
      expect(GatewayEventStream.calculateBackoffDelay(0, withJitter: false), const Duration(seconds: 2));
      expect(GatewayEventStream.calculateBackoffDelay(1, withJitter: false), const Duration(seconds: 4));
      expect(GatewayEventStream.calculateBackoffDelay(2, withJitter: false), const Duration(seconds: 8));
      expect(GatewayEventStream.calculateBackoffDelay(3, withJitter: false), const Duration(seconds: 16));
      expect(GatewayEventStream.calculateBackoffDelay(4, withJitter: false), const Duration(seconds: 30));
      expect(GatewayEventStream.calculateBackoffDelay(5, withJitter: false), const Duration(seconds: 30));
      expect(GatewayEventStream.calculateBackoffDelay(10, withJitter: false), const Duration(seconds: 30));

      // With jitter: delay is within baseSec to baseSec + 500ms
      for (int i = 0; i < 5; i++) {
        final d = GatewayEventStream.calculateBackoffDelay(0, withJitter: true);
        expect(d.inMilliseconds >= 2000 && d.inMilliseconds <= 2500, true);
      }
    });

    test('Test Pause & Resume lifecycle: pause() closes connection, resume() reconnects and resyncs', () async {
      int resyncCount = 0;
      int connectCount = 0;

      final mockClient = MockClient.streaming((req, bodyStream) async {
        connectCount++;
        final controller = StreamController<List<int>>();
        return http.StreamedResponse(
          controller.stream,
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });

      final stream = GatewayEventStream(
        gatewayUrl: () => 'http://test:8000',
        tokenProvider: () => 'valid-token',
        httpClientFactory: () => mockClient,
        onEvent: (_) {},
        onGapDetected: () => resyncCount++,
      );

      await stream.connect();
      expect(stream.isConnected, true);
      expect(connectCount, 1);

      // Pause when entering background
      stream.pause();
      expect(stream.isPaused, true);
      expect(stream.isConnected, false);

      // Resume when entering foreground
      stream.resume();
      expect(stream.isPaused, false);
      expect(connectCount, 2);
      expect(resyncCount, 1, reason: 'Resuming must trigger gap/resync to fetch freshest state');

      stream.dispose();
    });
  });
}
