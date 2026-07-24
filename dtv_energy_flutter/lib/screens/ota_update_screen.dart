import 'package:flutter/material.dart';

class OTAUpdateScreen extends StatefulWidget {
  const OTAUpdateScreen({super.key});

  @override
  State<OTAUpdateScreen> createState() => _OTAUpdateScreenState();
}

class _OTAUpdateScreenState extends State<OTAUpdateScreen> {
  String _selectedTarget = "ESP32-S3 Voice Master (192.168.1.11)";
  double _uploadProgress = 0.0;
  bool _isUploading = false;
  String _statusMessage = "Chọn file firmware (.bin) để nạp không dây qua sóng Wi-Fi.";

  void _simulateOTAUpload() async {
    setState(() {
      _isUploading = true;
      _uploadProgress = 0.0;
      _statusMessage = "Đang nạp file firmware.bin không dây tới $_selectedTarget...";
    });

    for (int i = 1; i <= 100; i += 10) {
      await Future.delayed(const Duration(milliseconds: 200));
      setState(() {
        _uploadProgress = i / 100.0;
      });
    }

    setState(() {
      _isUploading = false;
      _statusMessage = "✅ Nạp OTA thành công 100%! Thiết bị đang reboot...";
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text("🚀 WEB OTA FIRMWARE MANAGEMENT", style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold)),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF38BDF8).withOpacity(0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text("CHỌN THIẾT BỊ NẠP FIRMWARE KHÔNG DÂY", style: TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold)),
                  const SizedBox(height: 10),
                  DropdownButton<String>(
                    value: _selectedTarget,
                    isExpanded: true,
                    dropdownColor: const Color(0xFF1E293B),
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                    items: const [
                      DropdownMenuItem(value: "ESP32-S3 Voice Master (192.168.1.11)", child: Text("ESP32-S3 Voice Master (192.168.1.11)")),
                      DropdownMenuItem(value: "ESP32 WROOM Energy Slave (192.168.1.12)", child: Text("ESP32 WROOM Energy Slave (192.168.1.12)")),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _selectedTarget = val);
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.all(24),
              width: double.infinity,
              decoration: BoxDecoration(
                color: const Color(0xFF0F172A),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF0284C7), width: 2),
              ),
              child: Column(
                children: [
                  const Icon(Icons.cloud_upload, size: 48, color: Color(0xFF38BDF8)),
                  const SizedBox(height: 12),
                  Text(_statusMessage, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white, fontSize: 14)),
                  const SizedBox(height: 20),
                  if (_isUploading) ...[
                    LinearProgressIndicator(value: _uploadProgress, backgroundColor: Colors.grey[800], color: Colors.cyanAccent),
                    const SizedBox(height: 8),
                    Text("${(_uploadProgress * 100).toInt()}%", style: const TextStyle(color: Colors.cyanAccent, fontWeight: FontWeight.bold)),
                  ],
                  const SizedBox(height: 16),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF0284C7),
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                    ),
                    onPressed: _isUploading ? null : _simulateOTAUpload,
                    icon: const Icon(Icons.upload_file),
                    label: const Text("Tải File firmware.bin & Nạp OTA", style: TextStyle(fontWeight: FontWeight.bold)),
                  )
                ],
              ),
            )
          ],
        ),
      ),
    );
  }
}
