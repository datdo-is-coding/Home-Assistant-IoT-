import 'dart:async';
import 'dart:io';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

enum AppUpdatePhase {
  idle,
  checking,
  current,
  available,
  downloading,
  ready,
  permissionRequired,
  installing,
  failed,
}

class AppRelease {
  const AppRelease(this.version, this.code, this.size, this.sha256, this.url);
  final String version, sha256;
  final int code, size;
  final Uri url;

  static AppRelease parse(Object? value) {
    if (value is! Map ||
        value['schema'] != 1 ||
        value['package'] != 'com.dtv.homeassistant.dtv_home_assistant' ||
        value['version_code'] is! int ||
        (value['version_code'] as int) <= 0 ||
        value['size'] is! int ||
        (value['size'] as int) < 1024 ||
        (value['size'] as int) > 120 * 1024 * 1024 ||
        !RegExp(r'^\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.]+)?$')
            .hasMatch('${value['version']}') ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch('${value['sha256']}')) {
      throw const FormatException('Thông tin bản cập nhật không hợp lệ.');
    }
    final url = Uri.tryParse('${value['url']}');
    if (url == null || !allowedSource(url)) {
      throw const FormatException('Nguồn tải bản cập nhật không hợp lệ.');
    }
    return AppRelease(value['version'] as String, value['version_code'] as int,
        value['size'] as int, value['sha256'] as String, url);
  }

  static bool allowedSource(Uri uri) {
    if (uri.scheme != 'https' ||
        uri.userInfo.isNotEmpty ||
        uri.hasFragment ||
        uri.port != 443) return false;
    if (uri.host == 'github.com') {
      return uri.path.startsWith(
          '/datdo-is-coding/Home-Assistant-IoT-/releases/download/');
    }
    if (uri.host == 'home-companion-fed2e.web.app' ||
        uri.host == 'home-companion-fed2e.firebaseapp.com') return true;
    return uri.host == 'firebasestorage.googleapis.com' &&
        uri.path
            .startsWith('/v0/b/home-companion-fed2e.firebasestorage.app/o/');
  }
}

class AppUpdateService extends ChangeNotifier {
  AppUpdateService(
      {Future<Object?> Function()? loadRelease,
      http.Client? client,
      MethodChannel? channel,
      bool? enabled})
      : _loadRelease = loadRelease ?? _firebaseRelease,
        _http = client ?? http.Client(),
        _channel = channel ?? const MethodChannel('homecompetition/updates'),
        enabled = enabled ??
            (!kIsWeb && defaultTargetPlatform == TargetPlatform.android);

  static Future<Object?> _firebaseRelease() async =>
      (await FirebaseDatabase.instance
              .ref('app_releases/android/stable')
              .get()
              .timeout(const Duration(seconds: 12)))
          .value;

  final Future<Object?> Function() _loadRelease;
  final http.Client _http;
  final MethodChannel _channel;
  final bool enabled;
  AppUpdatePhase phase = AppUpdatePhase.idle;
  AppRelease? release;
  String installedVersion = '', error = '';
  int installedCode = 0, received = 0;
  String? _directory, _apkPath;
  DateTime? _lastCheck;
  bool _closed = false;
  bool get busy =>
      phase == AppUpdatePhase.checking ||
      phase == AppUpdatePhase.downloading ||
      phase == AppUpdatePhase.installing;
  bool get canInstall => _apkPath != null;
  double? get progress => release == null ? null : received / release!.size;
  void _notify() {
    if (!_closed) notifyListeners();
  }

  Future<void> check({bool force = false}) async {
    if (!enabled || _closed || busy) return;
    if (!force &&
        _lastCheck != null &&
        DateTime.now().difference(_lastCheck!) < const Duration(hours: 1))
      return;
    phase = AppUpdatePhase.checking;
    error = '';
    _notify();
    try {
      final info = await _channel.invokeMapMethod<String, dynamic>('info');
      if (info == null)
        throw const FormatException('Chưa đọc được phiên bản ứng dụng.');
      installedVersion = info['version'] as String;
      installedCode = info['versionCode'] as int;
      _directory = info['directory'] as String;
      final data = await _loadRelease();
      if (_closed) return;
      _lastCheck = DateTime.now();
      release = data == null ? null : AppRelease.parse(data);
      if (release == null || release!.code <= installedCode) {
        release = null;
        _apkPath = null;
        phase = AppUpdatePhase.current;
        _notify();
        return;
      }
      final file = File('$_directory/HomeCompetition-${release!.code}.apk');
      if (await file.exists()) {
        try {
          await _validate(file);
          if (_closed) return;
          _apkPath = file.path;
          received = release!.size;
          phase = AppUpdatePhase.ready;
          _notify();
          return;
        } catch (_) {
          await file.delete();
        }
      }
      phase = AppUpdatePhase.available;
      _notify();
      if (info['unmetered'] == true) await download();
    } catch (e) {
      _fail(e);
    }
  }

  Future<http.StreamedResponse> _open(Uri uri) async {
    for (var redirects = 0; redirects <= 5; redirects++) {
      final request = http.Request('GET', uri)..followRedirects = false;
      final response =
          await _http.send(request).timeout(const Duration(seconds: 20));
      if (response.statusCode >= 300 && response.statusCode < 400) {
        final location = response.headers['location'];
        await response.stream.listen((_) {}).cancel();
        if (location == null) break;
        final next = uri.resolve(location);
        final githubAsset = next.scheme == 'https' &&
            next.port == 443 &&
            next.userInfo.isEmpty &&
            !next.hasFragment &&
            next.host == 'release-assets.githubusercontent.com' &&
            release!.url.host == 'github.com';
        if (!AppRelease.allowedSource(next) && !githubAsset) break;
        uri = next;
      } else {
        return response;
      }
    }
    throw const FormatException('Đường dẫn tải bản cập nhật không hợp lệ.');
  }

  Future<void> _validate(File file) => _channel.invokeMethod<void>('validate', {
        'path': file.path,
        'versionCode': release!.code,
        'size': release!.size,
        'sha256': release!.sha256,
      });

  Future<void> download() async {
    if (_closed || release == null || busy || _directory == null) return;
    phase = AppUpdatePhase.downloading;
    error = '';
    received = 0;
    _apkPath = null;
    _notify();
    final file = File('$_directory/HomeCompetition-${release!.code}.apk');
    final part = File('${file.path}.part');
    IOSink? sink;
    try {
      final response = await _open(release!.url);
      if (response.statusCode != 200 ||
          (response.contentLength != null &&
              response.contentLength != release!.size)) {
        await response.stream.listen((_) {}).cancel();
        throw const FormatException('Máy chủ chưa cung cấp đúng gói cập nhật.');
      }
      sink = part.openWrite();
      var lastNotify = DateTime.now();
      await for (final chunk
          in response.stream.timeout(const Duration(seconds: 30))) {
        if (_closed) throw const FormatException('Đã dừng tải bản cập nhật.');
        received += chunk.length;
        if (received > release!.size)
          throw const FormatException('Kích thước gói cập nhật không khớp.');
        sink.add(chunk);
        if (DateTime.now().difference(lastNotify).inMilliseconds >= 200) {
          lastNotify = DateTime.now();
          _notify();
        }
      }
      await sink.flush();
      await sink.close();
      sink = null;
      if (received != release!.size)
        throw const FormatException('Gói cập nhật tải chưa đầy đủ.');
      await part.rename(file.path);
      await _validate(file);
      if (_closed) return;
      _apkPath = file.path;
      phase = AppUpdatePhase.ready;
      _notify();
    } catch (e) {
      await sink?.close();
      if (await part.exists()) await part.delete();
      if (await file.exists()) await file.delete();
      _fail(e);
    }
  }

  Future<void> install() async {
    if (_closed || !canInstall || busy) return;
    phase = AppUpdatePhase.installing;
    error = '';
    _notify();
    try {
      final result = await _channel.invokeMethod<String>('install', {
        'path': _apkPath,
        'versionCode': release!.code,
        'size': release!.size,
        'sha256': release!.sha256,
      });
      if (_closed) return;
      if (result == 'permission_required')
        phase = AppUpdatePhase.permissionRequired;
      _notify();
    } catch (e) {
      _fail(e);
    }
  }

  void resume() {
    if (phase == AppUpdatePhase.installing ||
        phase == AppUpdatePhase.permissionRequired) {
      phase = AppUpdatePhase.ready;
      _notify();
    }
  }

  void _fail(Object e) {
    if (_closed) return;
    error = e is FormatException
        ? e.message
        : e is PlatformException
            ? (e.message ?? 'Chưa xác minh được gói cập nhật.')
            : 'Chưa kiểm tra hoặc tải được bản mới. Bạn vẫn dùng ứng dụng bình thường.';
    phase = AppUpdatePhase.failed;
    _notify();
  }

  @override
  void dispose() {
    _closed = true;
    _http.close();
    super.dispose();
  }
}
