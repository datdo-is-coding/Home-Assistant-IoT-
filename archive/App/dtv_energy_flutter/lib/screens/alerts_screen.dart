import 'dart:async';
import 'package:flutter/material.dart';
import '../services/energy_service.dart';
import '../services/theme_service.dart';
import '../widgets/liquid_glass_card.dart';

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
    final theme = ThemeService().currentTheme;
    return Scaffold(
      backgroundColor: theme.bg,
      appBar: AppBar(
        backgroundColor: theme.surface.withOpacity(0.9),
        elevation: 0,
        title: Row(children: [
          Icon(Icons.notifications_active_rounded, color: theme.primary, size: 20),
          const SizedBox(width: 8),
          Text('CẢNH BÁO & GỢI Ý',
              style: TextStyle(color: theme.primary, fontWeight: FontWeight.bold, fontSize: 15, letterSpacing: 1)),
        ]),
        actions: [
          IconButton(icon: Icon(Icons.refresh_rounded, color: theme.primary), onPressed: _fetchAlerts),
        ],
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator(color: theme.primary))
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
            color: const Color(0xFF10B981).withOpacity(0.12),
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.check_circle_outline_rounded, color: Color(0xFF10B981), size: 56),
        ),
        const SizedBox(height: 20),
        const Text("Hệ thống hoạt động an toàn!",
            style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        const Text("Không có cảnh báo bất thường nào từ ESP32-S3.",
            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12.5)),
      ]),
    );
  }

  Widget _alertTile(dynamic alert) {
    final level = alert['level'] ?? 'info';
    Color color;
    IconData iconData;
    switch (level) {
      case 'critical':
        color = const Color(0xFFEF4444);
        iconData = Icons.error_rounded;
        break;
      case 'warning':
        color = const Color(0xFFF59E0B);
        iconData = Icons.warning_amber_rounded;
        break;
      case 'tip':
        color = const Color(0xFF10B981);
        iconData = Icons.lightbulb_outline_rounded;
        break;
      default:
        color = const Color(0xFF06B6D4);
        iconData = Icons.info_outline_rounded;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      child: LiquidGlassCard(
        padding: const EdgeInsets.all(14),
        borderColor: color.withOpacity(0.35),
        glowColor: color.withOpacity(0.08),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(iconData, color: color, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(alert['title'] ?? '',
                      style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 13.5)),
                  const SizedBox(height: 4),
                  Text(alert['message'] ?? '',
                      style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 12, height: 1.35)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
