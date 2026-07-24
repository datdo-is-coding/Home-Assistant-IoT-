import 'package:flutter/material.dart';
import '../services/energy_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final EnergyService _service = EnergyService();
  final TextEditingController _serverUrlController = TextEditingController();
  final TextEditingController _s3IpController = TextEditingController();
  final TextEditingController _wroomIpController = TextEditingController();

  bool _serverOnline = false;
  bool _espOnline = false;
  bool _isTesting = false;

  @override
  void initState() {
    super.initState();
    _serverUrlController.text = _service.serverUrl;
    _loadConfig();
  }

  @override
  void dispose() {
    _serverUrlController.dispose();
    _s3IpController.dispose();
    _wroomIpController.dispose();
    super.dispose();
  }

  Future<void> _loadConfig() async {
    setState(() => _isTesting = true);

    // Test server connection
    final online = await _service.testServerConnection();

    // Get ESP IPs from server
    String s3Ip = "192.168.1.11";
    String wroomIp = "192.168.1.12";
    bool espOnline = false;
    if (online) {
      final config = await _service.fetchConfig();
      s3Ip = config['esp_s3_ip'] ?? s3Ip;
      wroomIp = config['esp_wroom_ip'] ?? wroomIp;

      final status = await _service.fetchLiveMetrics();
      espOnline = status['is_online'] == true;
    }

    if (mounted) {
      setState(() {
        _serverOnline = online;
        _espOnline = espOnline;
        _s3IpController.text = s3Ip;
        _wroomIpController.text = wroomIp;
        _isTesting = false;
      });
    }
  }

  Future<void> _saveServerUrl() async {
    await _service.setServerUrl(_serverUrlController.text.trim());
    _loadConfig();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('✅ Đã lưu Server URL'), backgroundColor: Color(0xFF22C55E)),
      );
    }
  }

  Future<void> _saveEspIps() async {
    final ok = await _service.updateConfig(
      espS3Ip: _s3IpController.text.trim(),
      espWroomIp: _wroomIpController.text.trim(),
    );
    _loadConfig();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok ? '✅ Đã cập nhật IP trên server' : '❌ Không thể kết nối server'),
          backgroundColor: ok ? const Color(0xFF22C55E) : Colors.redAccent,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('⚙️ CÀI ĐẶT KẾT NỐI',
            style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold, fontSize: 16)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(children: [

          // ── CONNECTION DIAGRAM ─────────────────────
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF38BDF8).withOpacity(0.2)),
            ),
            child: Column(children: [
              const Text("KIẾN TRÚC KẾT NỐI",
                  style: TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11, letterSpacing: 1)),
              const SizedBox(height: 10),
              const Text(
                "📱 App  ──HTTP──►  🦀 Rust Server  ──HTTP──►  🎙️ ESP32-S3  ──ESP-NOW──►  ⚡ WROOM",
                style: TextStyle(color: Color(0xFF38BDF8), fontSize: 11, fontFamily: 'monospace'),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              const Text(
                "App chỉ giao tiếp với Rust Server.\nRust Server tự động thu thập dữ liệu từ ESP32 mỗi 5 giây.",
                style: TextStyle(color: Color(0xFF64748B), fontSize: 11),
                textAlign: TextAlign.center,
              ),
            ]),
          ),
          const SizedBox(height: 16),

          // ── RUST SERVER URL (only config app needs) ───
          _buildCard(
            icon: Icons.dns,
            title: "Rust Core Server",
            subtitle: "Trung tâm xử lý dữ liệu duy nhất",
            isConnected: _serverOnline,
            child: Column(children: [
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _serverUrlController,
                    style: const TextStyle(color: Colors.white, fontSize: 14),
                    decoration: _inputDecoration("http://192.168.1.100:8080"),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _saveServerUrl,
                  style: _btnStyle(), child: const Text("Lưu"),
                ),
              ]),
            ]),
          ),
          const SizedBox(height: 14),

          // ── ESP32 IPs (managed ON SERVER, displayed here) ───
          _buildCard(
            icon: Icons.sensors,
            title: "ESP32 Nodes (cấu hình trên server)",
            subtitle: _espOnline ? "ESP32-S3 đang nhận dữ liệu" : "Chưa nhận được dữ liệu từ ESP32",
            isConnected: _espOnline,
            child: Column(children: [
              _ipRow("🎙️ ESP32-S3 Master IP", _s3IpController),
              const SizedBox(height: 8),
              _ipRow("⚡ WROOM Slave IP", _wroomIpController),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _saveEspIps,
                  icon: const Icon(Icons.save, size: 16),
                  label: const Text("Lưu IP lên Server"),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF0284C7),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 20),

          // ── TEST BUTTON ───
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _isTesting ? null : _loadConfig,
              icon: _isTesting
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.refresh),
              label: Text(_isTesting ? "Đang kiểm tra..." : "🔄 Kiểm Tra Kết Nối"),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0284C7),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
          const SizedBox(height: 24),

          // ── SYSTEM INFO ───
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF334155)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text("📋 THÔNG TIN HỆ THỐNG",
                    style: TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11, letterSpacing: 1)),
                const SizedBox(height: 10),
                _infoRow("Wi-Fi", "SSID: XIAOMI | CH 11"),
                _infoRow("Master", "ESP32-S3 N16R8 + INMP441 + WS2812"),
                _infoRow("Slave", "ESP32 WROOM + PZEM-004T + ILI9341"),
                _infoRow("Protocol", "ESP-NOW 2-way (5s cycle)"),
                _infoRow("Server", "Rust Axum on port 8080"),
                _infoRow("Location", "Hà Nội, Việt Nam"),
              ],
            ),
          ),
        ]),
      ),
    );
  }

  Widget _buildCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool isConnected,
    required Widget child,
  }) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isConnected ? const Color(0xFF22C55E).withOpacity(0.4) : const Color(0xFFF97316).withOpacity(0.4),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, color: const Color(0xFF38BDF8), size: 20),
          const SizedBox(width: 8),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
            Text(subtitle, style: const TextStyle(color: Color(0xFF64748B), fontSize: 11)),
          ])),
          _statusDot(isConnected),
        ]),
        const SizedBox(height: 12),
        child,
      ]),
    );
  }

  Widget _ipRow(String label, TextEditingController controller) {
    return Row(children: [
      SizedBox(width: 140, child: Text(label, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12))),
      Expanded(
        child: TextField(
          controller: controller,
          style: const TextStyle(color: Colors.white, fontSize: 13),
          decoration: _inputDecoration("192.168.1.x"),
        ),
      ),
    ]);
  }

  InputDecoration _inputDecoration(String hint) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: Color(0xFF475569)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: Color(0xFF334155)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: Color(0xFF38BDF8)),
      ),
      filled: true,
      fillColor: const Color(0xFF0F172A),
      isDense: true,
    );
  }

  ButtonStyle _btnStyle() => ElevatedButton.styleFrom(
    backgroundColor: const Color(0xFF0284C7),
    foregroundColor: Colors.white,
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  );

  Widget _statusDot(bool ok) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: (ok ? Colors.green : Colors.orange).withOpacity(0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: ok ? Colors.green : Colors.orange),
      ),
      child: Text(ok ? "ONLINE" : "OFFLINE",
          style: TextStyle(color: ok ? Colors.green : Colors.orange, fontSize: 9, fontWeight: FontWeight.bold)),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(children: [
        SizedBox(width: 70, child: Text(label, style: const TextStyle(color: Color(0xFF64748B), fontSize: 11))),
        Expanded(child: Text(value, style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 11))),
      ]),
    );
  }
}
