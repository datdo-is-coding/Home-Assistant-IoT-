import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:dtv_energy_flutter/services/gateway_client.dart';

void main() {
  test('SSE disconnect and resume preserve REST requests on the real HTTP client', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final client = GatewayClient(persistSession: false);
    addTearDown(() async {
      client.dispose();
      await server.close(force: true);
    });
    server.listen((request) async {
      if (request.uri.path == '/api/events') {
        request.response.headers.contentType = ContentType('text', 'event-stream');
        request.response.write(': connected\n\n');
        await request.response.flush();
        return;
      }
      request.response.headers.contentType = ContentType.json;
      request.response.write(request.uri.path == '/api/auth/me'
          ? '{"authenticated":true,"user":{"role":"admin"}}'
          : '{"nodes":{},"pending":{}}');
      await request.response.close();
    });
    Future<void> waitForEvents() async {
      for (var i = 0; i < 100 && !client.isSseConnected; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      expect(client.isSseConnected, isTrue);
    }
    await client.loginWithKey(url: 'http://127.0.0.1:${server.port}', key: 'test');
    await waitForEvents();
    client.eventStream!.pause();
    await client.refresh();
    expect(client.connected, isTrue, reason: client.error);
    client.eventStream!.resume();
    await waitForEvents();
    await client.refresh();
    expect(client.connected, isTrue, reason: client.error);
  });
}
