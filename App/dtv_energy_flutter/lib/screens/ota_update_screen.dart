import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:ota_update/ota_update.dart';
import '../services/energy_service.dart';
import '../services/theme_service.dart';
import '../widgets/liquid_glass_card.dart';

class OTAUpdateScreen extends StatefulWidget {
  const OTAUpdateScreen({super.key});

  @override
  State<OTAUpdateScreen> createState() => _OTAUpdateScreenState();
}

class _OTAUpdateScreenState extends State<OTAUpdateScreen> {
  final EnergyService _service = EnergyService();

  // Hardware OTA state
  String _s3Ip = "192.168.11.181";
  String _wroomIp = "192.168.11.182";
  int _selectedTargetIndex = 0;
  final TextEditingController _customIpController = TextEditingController();
  PlatformFile? _selectedFile;
  double _uploadProgress = 0.0;
  bool _isUploading = false;
  String _statusMessage = "Vui lòng chọn file firmware (.bin) từ bộ nhớ để nạp OTA.";
  bool _isSuccess = false;

  // Android App OTA state
  String _currentAppVersion = "1.0.10";
  String _serverAppVersion = "1.0.0";
  String _serverApkUrl = "";
  String _appChangelog = "";
  bool _isCheckingApp = false;
  bool _isAppUpdating = false;
  int _appProgressPercentage = 0;
  String _appStatusMessage = "Nhấn nút để kiểm tra bản cập nhật mới cho App Android.";

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    final config = await _service.fetchConfig();
    final appVer = await _service.fetchAppVersion();
    if (mounted) {
      setState(() {
        _s3Ip = config['esp_s3_ip'] ?? _s3Ip;
        _wroomIp = config['esp_wroom_ip'] ?? _wroomIp;
        _serverAppVersion = appVer['version'] ?? "1.0.0";
        _serverApkUrl = appVer['apk_url'] ?? "";
        _appChangelog = appVer['changelog'] ?? "";
      });
    }
  }

  // ── HARDWARE OTA LOGIC ────────────────────────────────

  String get _targetIp {
    if (_selectedTargetIndex == 0) return _s3Ip;
    if (_selectedTargetIndex == 1) return _wroomIp;
    return _customIpController.text.trim();
  }

  String get _targetName {
    if (_selectedTargetIndex == 0) return "ESP32-S3 Voice Master ($_s3Ip)";
    if (_selectedTargetIndex == 1) return "ESP32 WROOM Energy Slave ($_wroomIp)";
    return "Tùy chỉnh: ${_customIpController.text.trim()}";
  }

  Future<void> _pickFirmwareFile() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['bin'],
        withData: true,
      );
      if (result != null && result.files.isNotEmpty) {
        setState(() {
          _selectedFile = result.files.first;
          _statusMessage = "Đã chọn: ${_selectedFile!.name} (${(_selectedFile!.size / 1024).toStringAsFixed(1)} KB)";
          _isSuccess = false;
        });
      }
    } catch (e) {
      setState(() => _statusMessage = "⚠️ Lỗi chọn file: $e");
    }
  }

  Future<void> _startOtaUpload() async {
    if (_selectedFile == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ Chọn file .bin trước!'), backgroundColor: Colors.orange),
      );
      return;
    }
    if (_targetIp.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ Nhập IP thiết bị đích!'), backgroundColor: Colors.orange),
      );
      return;
    }

    setState(() {
      _isUploading = true;
      _uploadProgress = 0.1;
      _statusMessage = "🚀 Đang gửi ${_selectedFile!.name} tới $_targetName...";
      _isSuccess = false;
    });

    final ok = await _service.uploadOtaFirmware(
      targetIp: _targetIp,
      file: _selectedFile!,
      isS3Master: _selectedTargetIndex == 0,
      onProgress: (p) { if (mounted) setState(() => _uploadProgress = p); },
    );

    if (mounted) setState(() {
      _isUploading = false;
      if (ok) {
        _uploadProgress = 1.0;
        _isSuccess = true;
        _statusMessage = "✅ NẠP FIRMWARE OTA THÀNH CÔNG!\nThiết bị đang khởi động lại...";
      } else {
        _statusMessage = "❌ THẤT BẠI! Kiểm tra IP và kết nối Wi-Fi.";
      }
    });
  }

  // ── APP SELF-OTA LOGIC ────────────────────────────────

  Future<void> _checkAppVersion() async {
    setState(() => _isCheckingApp = true);
    final appVer = await _service.fetchAppVersion();
    if (mounted) {
      setState(() {
        _isCheckingApp = false;
        _serverAppVersion = appVer['version'] ?? "1.0.0";
        _serverApkUrl = appVer['apk_url'];
        _appChangelog = appVer['changelog'] ?? "";
        if (_serverAppVersion != _currentAppVersion) {
          _appStatusMessage = "🎉 Có bản cập nhật App mới v$_serverAppVersion!";
        } else {
          _appStatusMessage = "✅ App Android đang ở phiên bản mới nhất (v$_currentAppVersion).";
        }
      });
    }
  }

  void _triggerAndroidAppSelfUpdate() {
    setState(() {
      _isAppUpdating = true;
      _appProgressPercentage = 0;
      _appStatusMessage = "📥 Đang tải file APK mới nhất từ Rust Server...";
    });

    try {
      final stream = _service.triggerAppOtaUpdate(customApkUrl: _serverApkUrl);
      if (stream == null) {
        setState(() {
          _isAppUpdating = false;
          _appStatusMessage = "❌ Không thể khởi động OTA cho App.";
        });
        return;
      }

      stream.listen(
        (OtaEvent event) {
          if (mounted) {
            setState(() {
              switch (event.status) {
                case OtaStatus.DOWNLOADING:
                  _appProgressPercentage = int.tryParse(event.value ?? '0') ?? 0;
                  _appStatusMessage = "📥 Đang tải APK: $_appProgressPercentage%";
                  break;
                case OtaStatus.INSTALLING:
                  _appProgressPercentage = 100;
                  _appStatusMessage = "🚀 Đang mở Trình Cài Đặt Android...";
                  _isAppUpdating = false;
                  break;
                case OtaStatus.ALREADY_RUNNING_ERROR:
                  _appStatusMessage = "⚠️ Tiến trình OTA đang chạy dở.";
                  _isAppUpdating = false;
                  break;
                case OtaStatus.PERMISSION_NOT_GRANTED_ERROR:
                  _appStatusMessage = "❌ Chưa cấp quyền cài ứng dụng từ nguồn ngoài!";
                  _isAppUpdating = false;
                  break;
                default:
                  _appStatusMessage = "❌ Lỗi nạp OTA App: ${event.status}";
                  _isAppUpdating = false;
              }
            });
          }
        },
        onError: (err) {
          if (mounted) {
            setState(() {
              _isAppUpdating = false;
              _appStatusMessage = "❌ Lỗi tải APK: $err";
            });
          }
        },
      );
    } catch (e) {
      setState(() {
        _isAppUpdating = false;
        _appStatusMessage = "❌ Lỗi: $e";
      });
    }
  }

  Widget _targetChip(int index, String label, String ip) {
    final theme = ThemeService().currentTheme;
    bool isSelected = _selectedTargetIndex == index;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _selectedTargetIndex = index),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? theme.primary.withOpacity(0.2) : theme.bg,
            border: Border.all(color: isSelected ? theme.primary : const Color(0xFF334155)),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Column(children: [
            Text(label, style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
            Text(ip, style: TextStyle(color: const Color(0xFF94A3B8), fontSize: 10)),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = ThemeService().currentTheme;
    return Scaffold(
      backgroundColor: theme.bg,
      appBar: AppBar(
        backgroundColor: theme.surface.withOpacity(0.9),
        elevation: 0,
        title: Row(children: [
          Icon(Icons.system_update_rounded, color: theme.primary, size: 20),
          const SizedBox(width: 8),
          Text("QUẢN LÝ NẠP OTA FIRMWARE",
              style: TextStyle(color: theme.primary, fontWeight: FontWeight.bold, fontSize: 15, letterSpacing: 1)),
        ]),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

          // ── SECTION 1: ANDROID APP SELF-OTA ──────────
          _section("📱 1. CẬP NHẬT APP ANDROID (APP SELF-OTA)", child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.android_rounded, color: Color(0xFF10B981), size: 28),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text("Phiên bản hiện tại: v$_currentAppVersion",
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
                  Text("Bản mới trên Server: v$_serverAppVersion",
                      style: TextStyle(
                        color: _serverAppVersion != _currentAppVersion ? theme.primary : const Color(0xFF94A3B8),
                        fontWeight: FontWeight.w600, fontSize: 12,
                      )),
                ])),
                ElevatedButton.icon(
                  onPressed: _isCheckingApp ? null : _checkAppVersion,
                  icon: _isCheckingApp
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : Icon(Icons.refresh_rounded, size: 16, color: theme.primary),
                  label: Text("Kiểm tra", style: TextStyle(color: theme.primary, fontSize: 12, fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.surface,
                    side: BorderSide(color: theme.primary.withOpacity(0.5)),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ]),
              if (_appChangelog.isNotEmpty) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: theme.bg.withOpacity(0.6),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(_appChangelog, style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 11.5, height: 1.3)),
                ),
              ],
              const SizedBox(height: 10),
              Text(_appStatusMessage, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
              if (_isAppUpdating) ...[
                const SizedBox(height: 10),
                LinearProgressIndicator(
                  value: _appProgressPercentage / 100.0,
                  backgroundColor: theme.bg,
                  color: const Color(0xFF10B981),
                  minHeight: 6,
                ),
              ],
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: (_isAppUpdating || _serverAppVersion == _currentAppVersion)
                      ? null
                      : _triggerAndroidAppSelfUpdate,
                  icon: const Icon(Icons.cloud_download_rounded, size: 18),
                  label: Text(
                    _serverAppVersion != _currentAppVersion
                        ? "📥 Tải & Nạp OTA App Android Tự Động (v$_serverAppVersion)"
                        : "App Đang Ở Phiên Bản Mới Nhất",
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.primary,
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
            ],
          )),
          const SizedBox(height: 16),

          // ── SECTION 2: HARDWARE FIRMWARE OTA ──────────
          _section("⚡ 2. NẠP FIRMWARE OTA PHẦN CỨNG (ESP32)", child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [

              // Target Node selector
              const Text("CHỌN THIẾT BỊ NẠP:",
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1)),
              const SizedBox(height: 6),
              Row(children: [
                _targetChip(0, "🎙️ ESP32-S3 Master", _s3Ip),
                const SizedBox(width: 8),
                _targetChip(1, "⚡ WROOM Slave", _wroomIp),
              ]),
              const SizedBox(height: 8),
              // Pick file button & selected file info
              Row(children: [
                ElevatedButton.icon(
                  onPressed: _isUploading ? null : _pickFirmwareFile,
                  icon: const Icon(Icons.folder_open_rounded, size: 16),
                  label: const Text("Chọn file .bin"),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.surface,
                    foregroundColor: theme.primary,
                    side: BorderSide(color: theme.primary.withOpacity(0.5)),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _selectedFile != null ? "${_selectedFile!.name} (${(_selectedFile!.size / 1024).toStringAsFixed(1)} KB)" : "Chưa chọn file",
                    style: TextStyle(
                      color: _selectedFile != null ? const Color(0xFF10B981) : const Color(0xFF64748B),
                      fontSize: 12, fontWeight: _selectedFile != null ? FontWeight.bold : FontWeight.normal,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ]),
              const SizedBox(height: 12),

              // Progress bar
              if (_isUploading) ...[
                LinearProgressIndicator(
                  value: _uploadProgress,
                  backgroundColor: theme.bg,
                  color: theme.primary,
                  minHeight: 8,
                ),
                const SizedBox(height: 8),
              ],

              // Status message box
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _isSuccess
                      ? const Color(0xFF10B981).withOpacity(0.12)
                      : theme.bg.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: _isSuccess ? const Color(0xFF10B981) : const Color(0xFF334155),
                  ),
                ),
                child: Text(
                  _statusMessage,
                  style: TextStyle(
                    color: _isSuccess ? const Color(0xFF10B981) : const Color(0xFFCBD5E1),
                    fontSize: 11.5, height: 1.3,
                  ),
                ),
              ),
              const SizedBox(height: 14),

              // Start Upload Button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: (_isUploading || _selectedFile == null) ? null : _startOtaUpload,
                  icon: _isUploading
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.cloud_upload_rounded),
                  label: Text(_isUploading ? "ĐANG NẠP OTA..." : "🚀 NẠP FIRMWARE OTA (.BIN)"),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.secondary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
            ],
          )),
        ]),
      ),
    );
  }

  Widget _section(String title, {required Widget child, Color? borderColor}) {
    return LiquidGlassCard(
      borderColor: borderColor,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11, letterSpacing: 1)),
        const SizedBox(height: 10),
        child,
      ]),
    );
  }
}
