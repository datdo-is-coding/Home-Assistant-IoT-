import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:ota_update/ota_update.dart';
import '../services/energy_service.dart';

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
  String _currentAppVersion = "1.0.1";
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text("🚀 QUẢN LÝ NẠP OTA FIRMWARE",
            style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold, fontSize: 16)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

          // ── SECTION 1: ANDROID APP SELF-OTA ──────────
          _section("📱 1. CẬP NHẬT APP ANDROID (APP SELF-OTA)", child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.android, color: Color(0xFF22C55E), size: 28),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text("Phiên bản hiện tại: v$_currentAppVersion",
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
                  Text("Bản mới trên Server: v$_serverAppVersion",
                      style: TextStyle(
                        color: _serverAppVersion != _currentAppVersion ? const Color(0xFF38BDF8) : const Color(0xFF94A3B8),
                        fontWeight: FontWeight.w600, fontSize: 12,
                      )),
                ])),
                ElevatedButton.icon(
                  onPressed: _isCheckingApp ? null : _checkAppVersion,
                  icon: _isCheckingApp
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.refresh, size: 16),
                  label: const Text("Kiểm tra"),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1E293B),
                    foregroundColor: const Color(0xFF38BDF8),
                    side: const BorderSide(color: Color(0xFF38BDF8)),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  ),
                ),
              ]),
              if (_appChangelog.isNotEmpty) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF0F172A),
                    borderRadius: BorderRadius.circular(8),
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
                  backgroundColor: const Color(0xFF0F172A),
                  color: const Color(0xFF22C55E),
                  minHeight: 6,
                ),
              ],
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _isAppUpdating ? null : _triggerAndroidAppSelfUpdate,
                  icon: const Icon(Icons.system_update, size: 18),
                  label: Text(_isAppUpdating ? "Đang tải APK ($_appProgressPercentage%)..." : "📥 Tải & Nạp OTA App Android Tự Động"),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF22C55E),
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
            ],
          )),
          const SizedBox(height: 20),

          // ── SECTION 2: HARDWARE FIRMWARE OTA ────────
          _section("⚡ 2. CHỌN THIẾT BỊ PHẦN CỨNG NẠP FIRMWARE", child: Column(children: [
            DropdownButton<int>(
              value: _selectedTargetIndex,
              isExpanded: true,
              dropdownColor: const Color(0xFF1E293B),
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
              items: [
                DropdownMenuItem(value: 0, child: Text("🎙️ Node 1: ESP32-S3 ($_s3Ip)")),
                DropdownMenuItem(value: 1, child: Text("⚡ Node 2: WROOM ($_wroomIp)")),
                const DropdownMenuItem(value: 2, child: Text("🌐 IP tùy chỉnh...")),
              ],
              onChanged: (v) { if (v != null) setState(() => _selectedTargetIndex = v); },
            ),
            if (_selectedTargetIndex == 2) ...[
              const SizedBox(height: 8),
              TextField(
                controller: _customIpController,
                style: const TextStyle(color: Colors.white),
                decoration: InputDecoration(
                  hintText: "192.168.11.x", hintStyle: const TextStyle(color: Color(0xFF64748B)),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF334155))),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF38BDF8))),
                  filled: true, fillColor: const Color(0xFF0F172A),
                ),
              ),
            ],
          ])),
          const SizedBox(height: 14),

          // ── SECTION 3: FILE .BIN ────────────────────
          _section("📁 3. CHỌN FILE FIRMWARE (.BIN)",
            borderColor: _selectedFile != null ? const Color(0xFF22C55E).withOpacity(0.5) : null,
            child: Row(children: [
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(_selectedFile?.name ?? "Chưa chọn file",
                    style: TextStyle(color: _selectedFile != null ? const Color(0xFF22C55E) : Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
                if (_selectedFile != null)
                  Text("${(_selectedFile!.size / 1024).toStringAsFixed(1)} KB",
                      style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
              ])),
              ElevatedButton.icon(
                onPressed: _isUploading ? null : _pickFirmwareFile,
                icon: const Icon(Icons.folder_open, size: 16),
                label: const Text("Chọn File"),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF0284C7), foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 18),

          // ── UPLOAD AREA ─────────────────────────────
          Container(
            padding: const EdgeInsets.all(20), width: double.infinity,
            decoration: BoxDecoration(
              color: const Color(0xFF0F172A), borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: _isSuccess ? const Color(0xFF22C55E) : _isUploading ? const Color(0xFF38BDF8) : const Color(0xFF334155),
                width: 2,
              ),
            ),
            child: Column(children: [
              Icon(
                _isSuccess ? Icons.check_circle_outline : _isUploading ? Icons.cloud_upload : Icons.sd_storage_outlined,
                size: 44,
                color: _isSuccess ? const Color(0xFF22C55E) : _isUploading ? const Color(0xFF38BDF8) : const Color(0xFF64748B),
              ),
              const SizedBox(height: 10),
              Text(_statusMessage, textAlign: TextAlign.center,
                  style: TextStyle(color: _isSuccess ? const Color(0xFF22C55E) : _statusMessage.contains("❌") ? Colors.redAccent : Colors.white, fontSize: 13, height: 1.4)),
              if (_isUploading) ...[
                const SizedBox(height: 14),
                LinearProgressIndicator(value: _uploadProgress, backgroundColor: const Color(0xFF1E293B), color: const Color(0xFF38BDF8), minHeight: 6),
                const SizedBox(height: 6),
                Text("${(_uploadProgress * 100).toInt()}%", style: const TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold)),
              ],
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _isUploading ? null : _startOtaUpload,
                  icon: const Icon(Icons.upload_file),
                  label: Text(_isUploading ? "Đang truyền..." : "🚀 Nạp Firmware OTA (.bin)"),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _isUploading ? const Color(0xFF334155) : const Color(0xFF0284C7),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ),
            ]),
          ),
        ]),
      ),
    );
  }

  Widget _section(String title, {required Widget child, Color? borderColor}) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B), borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor ?? const Color(0xFF334155)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11, letterSpacing: 1)),
        const SizedBox(height: 10),
        child,
      ]),
    );
  }
}
