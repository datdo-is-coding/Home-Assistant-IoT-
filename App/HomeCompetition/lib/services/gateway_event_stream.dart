import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Model representing a single parsed SSE event from Gateway.
class GatewayEvent {
  final String? id;
  final String name;
  final Map<String, dynamic> data;
  final int? revision;

  const GatewayEvent({
    this.id,
    required this.name,
    required this.data,
    this.revision,
  });

  @override
  String toString() => 'GatewayEvent(id: $id, name: $name, revision: $revision, data: $data)';

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is GatewayEvent &&
        other.id == id &&
        other.name == name &&
        other.revision == revision &&
        mapEquals(other.data, data);
  }

  @override
  int get hashCode => Object.hash(id, name, revision);
}

class _StreamingStringSink implements Sink<String> {
  final void Function(String chunk) onChunk;
  _StreamingStringSink(this.onChunk);

  @override
  void add(String chunk) => onChunk(chunk);

  @override
  void close() {}
}

/// Robust chunked UTF-8 SSE line and event parser.
class SseParser {
  final void Function(GatewayEvent event) onEvent;
  final void Function()? onKeepAlive;

  final StringBuffer _lineBuf = StringBuffer();
  late final ByteConversionSink _sink;

  String? _currentId;
  String? _currentEvent;
  String? _currentData;

  SseParser({
    required this.onEvent,
    this.onKeepAlive,
  }) {
    final stringSink = _StreamingStringSink(_processChunk);
    _sink = const Utf8Decoder(allowMalformed: true).startChunkedConversion(stringSink);
  }

  void feedChunk(List<int> bytes) {
    _sink.add(bytes);
  }

  void feedString(String text) {
    _processChunk(text);
  }

  void _processChunk(String text) {
    _lineBuf.write(text);
    final full = _lineBuf.toString();
    int start = 0;
    for (int i = 0; i < full.length; i++) {
      final c = full.codeUnitAt(i);
      if (c == 10) {
        // \n
        final line = (i > start && full.codeUnitAt(i - 1) == 13)
            ? full.substring(start, i - 1)
            : full.substring(start, i);
        _handleLine(line);
        start = i + 1;
      } else if (c == 13) {
        // \r
        if (i + 1 < full.length) {
          if (full.codeUnitAt(i + 1) == 10) {
            // will be handled by LF at i + 1
            continue;
          } else {
            final line = full.substring(start, i);
            _handleLine(line);
            start = i + 1;
          }
        } else {
          // \r at the very end of chunk, wait for next char
          break;
        }
      }
    }
    if (start > 0) {
      final remaining = full.substring(start);
      _lineBuf.clear();
      _lineBuf.write(remaining);
    }
  }

  void _handleLine(String line) {
    if (line.isEmpty) {
      _dispatch();
      return;
    }
    if (line.startsWith(':')) {
      onKeepAlive?.call();
      return;
    }
    final colon = line.indexOf(':');
    String field;
    String value;
    if (colon == -1) {
      field = line;
      value = '';
    } else {
      field = line.substring(0, colon);
      value = line.substring(colon + 1);
      if (value.startsWith(' ')) {
        value = value.substring(1);
      }
    }

    switch (field) {
      case 'event':
        _currentEvent = value;
        break;
      case 'id':
        _currentId = value;
        break;
      case 'data':
        _currentData = _currentData == null ? value : '$_currentData\n$value';
        break;
    }
  }

  void _dispatch() {
    if (_currentEvent == null && _currentData == null && _currentId == null) {
      return;
    }
    Map<String, dynamic> data = {};
    if (_currentData != null && _currentData!.isNotEmpty) {
      try {
        final decoded = jsonDecode(_currentData!);
        if (decoded is Map<String, dynamic>) {
          data = decoded;
        } else if (decoded is Map) {
          data = Map<String, dynamic>.from(decoded);
        } else {
          data = {'value': decoded};
        }
      } catch (_) {
        data = {'raw': _currentData};
      }
    }

    int? rev;
    if (data.containsKey('revision')) {
      final r = data['revision'];
      if (r is int) {
        rev = r;
      } else if (r is num) {
        rev = r.toInt();
      } else if (r is String) {
        rev = int.tryParse(r);
      }
    }
    if (rev == null && _currentId != null) {
      rev = int.tryParse(_currentId!);
    }

    final event = GatewayEvent(
      id: _currentId,
      name: _currentEvent ?? 'message',
      data: data,
      revision: rev,
    );

    _currentId = null;
    _currentEvent = null;
    _currentData = null;

    onEvent(event);
  }

  void reset() {
    _lineBuf.clear();
    _currentId = null;
    _currentEvent = null;
    _currentData = null;
  }
}

/// Service managing persistent SSE connection to Gateway with gap detection,
/// exponential backoff reconnection, lifecycle awareness, and telemetry coalescing.
class GatewayEventStream {
  final String Function() gatewayUrl;
  final String Function() tokenProvider;
  final void Function(GatewayEvent event) onEvent;
  final void Function(dynamic error)? onError;
  final void Function()? onGapDetected;
  final void Function()? onConnected;
  final void Function()? onDisconnected;
  final Duration telemetryThrottle;
  final http.Client Function()? httpClientFactory;
  final bool closeClientOnDisconnect;

  int? _lastRevision;
  int _reconnectAttempts = 0;
  bool _isConnected = false;
  bool _isPaused = false;
  bool _isClosed = false;

  Timer? _reconnectTimer;
  http.Client? _activeClient;
  StreamSubscription? _streamSub;

  final Map<String, DateTime> _lastTelemetryEmitted = {};
  final Map<String, GatewayEvent> _pendingTelemetry = {};
  final Map<String, Timer> _telemetryTimers = {};

  late final SseParser _parser;

  GatewayEventStream({
    required this.gatewayUrl,
    required this.tokenProvider,
    required this.onEvent,
    this.onError,
    this.onGapDetected,
    this.onConnected,
    this.onDisconnected,
    this.telemetryThrottle = const Duration(milliseconds: 250),
    this.httpClientFactory,
    this.closeClientOnDisconnect = true,
  }) {
    _parser = SseParser(
      onEvent: _onRawEvent,
      onKeepAlive: () {
        // Keepalive received
      },
    );
  }

  bool get isConnected => _isConnected;
  bool get isPaused => _isPaused;
  bool get isClosed => _isClosed;
  int? get lastRevision => _lastRevision;
  int get reconnectAttempts => _reconnectAttempts;

  void feedChunk(List<int> bytes) => _parser.feedChunk(bytes);
  void feedString(String text) => _parser.feedString(text);

  void _onRawEvent(GatewayEvent event) {
    final rev = event.revision;
    if (rev != null) {
      if (_lastRevision != null && rev > _lastRevision! + 1) {
        onGapDetected?.call();
      }
      _lastRevision = (_lastRevision == null) ? rev : max(_lastRevision!, rev);
    }
    _dispatchOrCoalesce(event);
  }

  void _dispatchOrCoalesce(GatewayEvent event) {
    if (event.name != 'node_telemetry') {
      onEvent(event);
      return;
    }

    final nodeId = (event.data['node_id'] ?? event.data['device_id'] ?? 'default').toString();
    final now = DateTime.now();
    final lastEmitted = _lastTelemetryEmitted[nodeId];

    if (lastEmitted == null || now.difference(lastEmitted) >= telemetryThrottle) {
      _telemetryTimers[nodeId]?.cancel();
      _telemetryTimers.remove(nodeId);
      _pendingTelemetry.remove(nodeId);
      _lastTelemetryEmitted[nodeId] = now;
      onEvent(event);
    } else {
      _pendingTelemetry[nodeId] = event;
      if (_telemetryTimers[nodeId] == null) {
        final waitDuration = telemetryThrottle - now.difference(lastEmitted);
        _telemetryTimers[nodeId] = Timer(
          waitDuration > Duration.zero ? waitDuration : Duration.zero,
          () {
            _telemetryTimers.remove(nodeId);
            final pending = _pendingTelemetry.remove(nodeId);
            if (pending != null && !_isClosed && !_isPaused) {
              _lastTelemetryEmitted[nodeId] = DateTime.now();
              onEvent(pending);
            }
          },
        );
      }
    }
  }

  static Duration calculateBackoffDelay(int attempt, {bool withJitter = false, Random? random}) {
    final baseSec = min(2 * (1 << attempt), 30);
    final jitterMs = withJitter ? (random ?? Random()).nextInt(501) : 0;
    return Duration(seconds: baseSec, milliseconds: jitterMs);
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    if (_isClosed || _isPaused) return;
    final delay = calculateBackoffDelay(_reconnectAttempts, withJitter: true);
    _reconnectAttempts++;
    _reconnectTimer = Timer(delay, () {
      if (!_isClosed && !_isPaused) {
        connect();
      }
    });
  }

  Future<void> connect() async {
    if (_isClosed || _isPaused) return;
    final url = gatewayUrl();
    final token = tokenProvider();
    if (url.isEmpty || token.isEmpty) return;

    _disconnectStream();

    try {
      final client = httpClientFactory != null ? httpClientFactory!() : http.Client();
      _activeClient = client;

      final request = http.Request('GET', Uri.parse('$url/api/events'))
        ..headers['Accept'] = 'text/event-stream'
        ..headers['Cache-Control'] = 'no-cache'
        ..headers['Authorization'] = 'Bearer $token';

      final response = await client.send(request);
      if (_isClosed || _isPaused) {
        if (closeClientOnDisconnect) client.close();
        return;
      }
      final contentType = response.headers['content-type'] ?? '';
      if (response.statusCode == 200 && (contentType.isEmpty || contentType.contains('text/event-stream'))) {
        _isConnected = true;
        _reconnectAttempts = 0;
        onConnected?.call();
        _streamSub = response.stream.listen(
          (chunk) {
            _parser.feedChunk(chunk);
          },
          onError: (err) {
            _handleDisconnect(err);
          },
          onDone: () {
            _handleDisconnect(null);
          },
          cancelOnError: true,
        );
      } else {
        _handleDisconnect(
          'HTTP ${response.statusCode} (content-type: $contentType)',
          reconnect: response.statusCode >= 500,
        );
      }
    } catch (e) {
      _handleDisconnect(e);
    }
  }

  void _handleDisconnect(dynamic error, {bool reconnect = true}) {
    if (_isConnected) {
      _isConnected = false;
      onDisconnected?.call();
    }
    if (error != null) {
      onError?.call(error);
    }
    _disconnectStream();
    if (reconnect && !_isClosed && !_isPaused) {
      _scheduleReconnect();
    }
  }

  void _disconnectStream() {
    _streamSub?.cancel();
    _streamSub = null;
    if (closeClientOnDisconnect) _activeClient?.close();
    _activeClient = null;
  }

  void pause() {
    _isPaused = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    for (final t in _telemetryTimers.values) {
      t.cancel();
    }
    _telemetryTimers.clear();
    _pendingTelemetry.clear();
    if (_isConnected) {
      _isConnected = false;
      onDisconnected?.call();
    }
    _disconnectStream();
  }

  void resume() {
    if (!_isPaused && !_isClosed) return;
    _isPaused = false;
    _reconnectAttempts = 0;
    connect();
    onGapDetected?.call();
  }

  void dispose() {
    _isClosed = true;
    _reconnectTimer?.cancel();
    for (final t in _telemetryTimers.values) {
      t.cancel();
    }
    _telemetryTimers.clear();
    _pendingTelemetry.clear();
    if (_isConnected) {
      _isConnected = false;
      onDisconnected?.call();
    }
    _disconnectStream();
  }
}
