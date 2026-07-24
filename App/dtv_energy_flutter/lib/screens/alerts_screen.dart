import 'dart:async';
import 'package:flutter/material.dart';
import '../services/energy_service.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  final EnergyService _service = EnergyService();
  List<dynamic> _alerts = [];
  bool _isLoading = true;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _fetchAlerts();
    _timer = Timer.periodic(const Duration(seconds: 8), (_) => _fetchAlerts());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _fetchAlerts() async {
    final alerts = await _service.fetchAlerts();
    if (mounted) setState(() { _alerts = alerts; _isLoading = false; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('🚨 CẢNH BÁO & GỢI Ý',
            style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold, fontSize: 16)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, color: Color(0xFF38BDF8)), onPressed: _fetchAlerts),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF38BDF8)))
          : _alerts.isEmpty
              ? _emptyState()
              : RefreshIndicator(
                  onRefresh: _fetchAlerts,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(14),
                    itemCount: _alerts.length,
                    itemBuilder: (context, index) => _alertTile(_alerts[index]),
                  ),
                ),
    );
  }

  Widget _emptyState() {
    return Center(
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: const Color(0xFF22C55E).withOpacity(0.1),
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.check_circle_outline, color: Color(0xFF22C55E), size: 56),
        ),
        const SizedBox(height: 20),
        const Text("Hệ thống hoạt động bình thường!",
            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        const Text("Không có cảnh báo nào. Mọi thông số đều ổn định.",
            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
      ]),
    );
  }

  Widget _alertTile(dynamic alert) {
    final level = alert['level'] ?? 'info';
    Color color;
    IconData iconData;
    switch (level) {
      case 'critical':
        color = Colors.redAccent;
        iconData = Icons.error;
        break;
      case 'warning':
        color = Colors.orangeAccent;
        iconData = Icons.warning_amber;
        break;
      case 'tip':
        color = const Color(0xFF22C55E);
        iconData = Icons.lightbulb_outline;
        break;
      default:
        color = const Color(0xFF38BDF8);
        iconData = Icons.info_outline;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [color.withOpacity(0.08), const Color(0xFF1E293B)],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        leading: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(alert['icon'] ?? '⚠️', style: const TextStyle(fontSize: 24)),
        ),
        title: Text(alert['title'] ?? '',
            style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 14)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(alert['message'] ?? '',
              style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 12.5, height: 1.4)),
        ),
      ),
    );
  }
}
