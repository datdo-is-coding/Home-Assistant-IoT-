import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../services/google_assistant_service.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final GoogleAssistantService _assistantService = GoogleAssistantService();

  double _voltage = 220.5;
  double _current = 1.25;
  double _power = 265.4;
  double _energy = 12.45;
  bool _isOnline = true;
  String _assistantSpeech = "Hệ thống sẵn sàng nghe lệnh Google Assistant...";
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _startTelemetryStream();
  }

  void _startTelemetryStream() {
    _timer = Timer.periodic(const Duration(seconds: 1), (t) async {
      try {
        final res = await http.get(Uri.parse('http://192.168.1.11/api/status')).timeout(const Duration(seconds: 1));
        if (res.statusCode == 200) {
          final data = jsonDecode(res.body);
          setState(() {
            _voltage = (data['voltage'] as num).toDouble();
            _current = (data['current'] as num).toDouble();
            _power = (data['power'] as num).toDouble();
            _energy = (data['energy'] as num).toDouble();
            _isOnline = true;
          });
        }
      } catch (_) {
        // Fallback for simulation
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _triggerGoogleAssistant(String intent) async {
    final result = await _assistantService.processVoiceIntent(intent);
    setState(() {
      _assistantSpeech = result['speech_response'] ?? "";
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('⚡ DTV ENERGY SMART HUB', style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold)),
        elevation: 4,
        actions: [
          Container(
            margin: const EdgeInsets.only(right: 16),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: _isOnline ? Colors.green.withOpacity(0.2) : Colors.red.withOpacity(0.2),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: _isOnline ? Colors.green : Colors.red),
            ),
            child: Row(
              children: [
                Icon(Icons.wifi, color: _isOnline ? Colors.green : Colors.red, size: 16),
                const SizedBox(width: 6),
                Text(_isOnline ? "CH 11 ONLINE" : "OFFLINE", style: TextStyle(color: _isOnline ? Colors.green : Colors.red, fontSize: 12, fontWeight: FontWeight.bold)),
              ],
            ),
          )
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 🎙️ GOOGLE ASSISTANT VOICE ASSISTANT BANNER
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Color(0xFF1E1B4B), Color(0xFF312E81)]),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF6366F1)),
                boxShadow: [BoxShadow(color: const Color(0xFF6366F1).withOpacity(0.3), blurRadius: 10)],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.mic, color: Color(0xFF818CF8), size: 28),
                      const SizedBox(width: 10),
                      const Text("GOOGLE ASSISTANT VOICE AI", style: TextStyle(color: Color(0xFFA5B4FC), fontWeight: FontWeight.bold, fontSize: 16)),
                      const Spacer(),
                      Container(
                        width: 12, height: 12,
                        decoration: const BoxDecoration(color: Colors.greenAccent, shape: BoxShape.circle),
                      )
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(_assistantSpeech, style: const TextStyle(color: Colors.white, fontSize: 14, fontStyle: FontStyle.italic)),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF4F46E5)),
                        onPressed: () => _triggerGoogleAssistant("query_voltage"),
                        icon: const Icon(Icons.bolt, color: Colors.amber),
                        label: const Text("Hỏi Điện Áp"),
                      ),
                      const SizedBox(width: 10),
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF4F46E5)),
                        onPressed: () => _triggerGoogleAssistant("query_power"),
                        icon: const Icon(Icons.speed, color: Colors.cyanAccent),
                        label: const Text("Hỏi Công Suất"),
                      ),
                    ],
                  )
                ],
              ),
            ),
            const SizedBox(height: 20),

            // ⚡ POWER TELEMETRY CARDS
            const Text("LIVE POWER METRICS (PZEM-004T)", style: TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, letterSpacing: 1.2)),
            const SizedBox(height: 12),

            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 1.4,
              children: [
                _buildMetricCard("VOLTAGE", "${_voltage.toStringAsFixed(1)} V", Icons.electric_meter, Colors.cyan),
                _buildMetricCard("CURRENT", "${_current.toStringAsFixed(2)} A", Icons.compress, Colors.amber),
                _buildMetricCard("ACTIVE POWER", "${_power.toStringAsFixed(1)} W", Icons.flash_on, Colors.orangeAccent),
                _buildMetricCard("ACCUMULATED ENERGY", "${_energy.toStringAsFixed(2)} kWh", Icons.battery_charging_full, Colors.greenAccent),
              ],
            ),
            const SizedBox(height: 20),

            // 🎙️ ESP32-S3 VOICE MASTER HARDWARE CARD
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF334155)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.memory, color: Color(0xFF38BDF8)),
                      const SizedBox(width: 10),
                      const Text("ESP32-S3 N16R8 VOICE MASTER", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(color: Colors.green.withOpacity(0.2), borderRadius: BorderRadius.circular(6)),
                        child: const Text("WS2812 RGB: OK", style: TextStyle(color: Colors.green, fontSize: 11, fontWeight: FontWeight.bold)),
                      )
                    ],
                  ),
                  const SizedBox(height: 12),
                  const Text("Wake Word Model: WakeNet9 ('Hi ESP')", style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 6),
                  const Text("Microphone Hardware: INMP441 MEMS I2S (GPIO 47, 10, 21)", style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                ],
              ),
            )
          ],
        ),
      ),
    );
  }

  Widget _buildMetricCard(String title, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity(0.3)),
        boxShadow: [BoxShadow(color: color.withOpacity(0.1), blurRadius: 8)],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 20),
              const SizedBox(width: 8),
              Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11, fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 10),
          Text(value, style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
