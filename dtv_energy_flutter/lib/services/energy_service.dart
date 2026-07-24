import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:file_picker/file_picker.dart';
import 'package:ota_update/ota_update.dart';

/// Singleton service — ALL data flows through Rust Core Server.
/// Flutter NEVER calls ESP32 directly for data (only for OTA uploads).
class EnergyService {
  static const String _serverUrlKey = 'rust_server_url';
  static const String _defaultServerUrl = 'http://192.168.1.100:8080';

  String _serverUrl = _defaultServerUrl;

  static final EnergyService _instance = EnergyService._internal();
  factory EnergyService() => _instance;
  EnergyService._internal();

  String get serverUrl => _serverUrl;

  // ── Init ──────────────────────────────────────────────

  Future<void> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _serverUrl = prefs.getString(_serverUrlKey) ?? _defaultServerUrl;
  }

  Future<void> setServerUrl(String url) async {
    _serverUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_serverUrlKey, url);
  }

  // ── UNIFIED DATA (all from Rust Server) ───────────────

  /// Live metrics: voltage, current, power, energy, frequency, pf, is_online
  Future<Map<String, dynamic>> fetchLiveMetrics() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/status'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return {
      "is_online": false, "voltage": 0.0, "current": 0.0, "power": 0.0,
      "energy": 0.0, "frequency": 50.0, "pf": 1.0,
    };
  }

  /// Smart alerts
  Future<List<dynamic>> fetchAlerts() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/alerts'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return [];
  }

  /// Weather Hà Nội
  Future<Map<String, dynamic>> fetchWeather() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/weather'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return {
      "city": "Hà Nội", "temp": 32.0, "humidity": 70,
      "description": "trời nắng", "suggestion": "Dùng quạt thay máy lạnh để tiết kiệm điện.",
    };
  }

  /// Chart history (60 samples)
  Future<List<dynamic>> fetchAnalytics() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/analytics'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return [];
  }

  /// Get ESP32 IPs from server config (for OTA targets)
  Future<Map<String, dynamic>> fetchConfig() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/config'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) return jsonDecode(res.body);
    } catch (_) {}
    return {"esp_s3_ip": "192.168.1.11", "esp_wroom_ip": "192.168.1.12"};
  }

  /// Update ESP32 IPs on server
  Future<bool> updateConfig({String? espS3Ip, String? espWroomIp}) async {
    try {
      final body = <String, String>{};
      if (espS3Ip != null) body['esp_s3_ip'] = espS3Ip;
      if (espWroomIp != null) body['esp_wroom_ip'] = espWroomIp;
      final res = await http.post(
        Uri.parse('$_serverUrl/api/config'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ).timeout(const Duration(seconds: 3));
      return res.statusCode == 200;
    } catch (_) {}
    return false;
  }

  // ── ANDROID APP OTA SELF-UPDATE ───────────────────────

  /// Fetch latest Android App version info from Rust Server
  Future<Map<String, dynamic>> fetchAppVersion() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/app-version'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(res.body);
        String url = data['apk_url'] ?? '';
        if (url.startsWith('/')) {
          url = '$_serverUrl$url';
        }
        data['apk_url'] = url;
        return data;
      }
    } catch (_) {}
    return {
      "version": "1.0.0",
      "build_number": 1,
      "apk_url": "$_serverUrl/downloads/app-debug.apk",
      "changelog": "Bản hiện tại",
    };
  }

  /// Download and trigger Android App self-install via OTA
  Stream<OtaEvent>? triggerAppOtaUpdate({String? customApkUrl}) {
    try {
      final url = (customApkUrl != null && customApkUrl.startsWith('http'))
          ? customApkUrl
          : '$_serverUrl/downloads/app-debug.apk';
      return OtaUpdate().execute(
        url,
        destinationFilename: 'dtv_energy_latest.apk',
      );
    } catch (_) {
      return null;
    }
  }

  // ── CONNECTION TEST ───────────────────────────────────

  Future<bool> testServerConnection() async {
    try {
      final res = await http.get(Uri.parse('$_serverUrl/api/status'))
          .timeout(const Duration(seconds: 3));
      return res.statusCode == 200;
    } catch (_) {}
    return false;
  }

  // ── OTA UPLOAD (direct to ESP device) ─────────────────

  Future<bool> uploadOtaFirmware({
    required String targetIp,
    required PlatformFile file,
    required Function(double progress) onProgress,
  }) async {
    try {
      final uri = Uri.parse('http://$targetIp/update');
      final request = http.MultipartRequest('POST', uri);

      if (file.bytes != null) {
        request.files.add(http.MultipartFile.fromBytes(
          'update', file.bytes!, filename: file.name,
        ));
      } else if (file.path != null) {
        request.files.add(await http.MultipartFile.fromPath(
          'update', file.path!, filename: file.name,
        ));
      } else {
        return false;
      }

      onProgress(0.1);
      final response = await request.send().timeout(const Duration(seconds: 120));
      onProgress(1.0);
      return response.statusCode == 200;
    } catch (_) {}
    return false;
  }
}
