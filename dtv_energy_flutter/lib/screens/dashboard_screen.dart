import 'dart:async';
import 'package:flutter/material.dart';
import '../services/energy_service.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> with SingleTickerProviderStateMixin {
  final EnergyService _service = EnergyService();

  double _voltage = 0, _current = 0, _power = 0, _energy = 0;
  double _frequency = 50.0, _pf = 1.0;
  bool _isOnline = false;
  List<dynamic> _alerts = [];
  Map<String, dynamic> _weather = {};

  Timer? _fastTimer;
  Timer? _slowTimer;
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    _fetchAll();
    _fastTimer = Timer.periodic(const Duration(seconds: 2), (_) => _fetchMetrics());
    _slowTimer = Timer.periodic(const Duration(seconds: 15), (_) => _fetchSlow());
  }

  @override
  void dispose() {
    _fastTimer?.cancel();
    _slowTimer?.cancel();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _fetchAll() async {
    await Future.wait([_fetchMetrics(), _fetchSlow()]);
  }

  Future<void> _fetchMetrics() async {
    final data = await _service.fetchLiveMetrics();
    if (mounted) setState(() {
      _voltage = (data['voltage'] as num?)?.toDouble() ?? 0;
      _current = (data['current'] as num?)?.toDouble() ?? 0;
      _power = (data['power'] as num?)?.toDouble() ?? 0;
      _energy = (data['energy'] as num?)?.toDouble() ?? 0;
      _frequency = (data['frequency'] as num?)?.toDouble() ?? 50.0;
      _pf = (data['pf'] as num?)?.toDouble() ?? 1.0;
      _isOnline = data['is_online'] == true;
    });
  }

  Future<void> _fetchSlow() async {
    final alerts = await _service.fetchAlerts();
    final weather = await _service.fetchWeather();
    if (mounted) setState(() { _alerts = alerts; _weather = weather; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _fetchAll,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              _header(),
              const SizedBox(height: 16),
              _heroMetric(),
              const SizedBox(height: 14),
              _metricsGrid(),
              const SizedBox(height: 14),
              _quickWeather(),
              const SizedBox(height: 14),
              _quickAlerts(),
            ]),
          ),
        ),
      ),
    );
  }

  // === HEADER ===
  Widget _header() {
    return Row(children: [
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text("⚡ DTV ENERGY",
            style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold, fontSize: 20, letterSpacing: 1)),
        Text("Smart Hub · Hà Nội",
            style: TextStyle(color: const Color(0xFF64748B), fontSize: 12)),
      ]),
      const Spacer(),
      AnimatedBuilder(
        animation: _pulseController,
        builder: (context, child) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: (_isOnline ? Colors.green : Colors.red).withOpacity(0.08 + _pulseController.value * 0.08),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: _isOnline ? Colors.green : Colors.red, width: 1.2),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.sensors, size: 14, color: _isOnline ? Colors.green : Colors.red),
              const SizedBox(width: 5),
              Text(_isOnline ? "ESP-NOW LIVE" : "OFFLINE",
                  style: TextStyle(color: _isOnline ? Colors.green : Colors.red, fontSize: 10, fontWeight: FontWeight.bold)),
            ]),
          );
        },
      ),
    ]);
  }

  // === HERO METRIC (Power) ===
  Widget _heroMetric() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            const Color(0xFF0284C7).withOpacity(0.2),
            const Color(0xFF1E293B),
          ],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF38BDF8).withOpacity(0.3)),
      ),
      child: Column(children: [
        const Text("ACTIVE POWER", style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12, letterSpacing: 2, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text("${_power.toStringAsFixed(0)}", style: const TextStyle(color: Colors.white, fontSize: 52, fontWeight: FontWeight.bold)),
        const Text("WATTS", style: TextStyle(color: Color(0xFF38BDF8), fontSize: 14, letterSpacing: 3)),
      ]),
    );
  }

  // === METRICS GRID ===
  Widget _metricsGrid() {
    return GridView.count(
      crossAxisCount: 2, shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 10, mainAxisSpacing: 10, childAspectRatio: 1.5,
      children: [
        _metricCard("VOLTAGE", "${_voltage.toStringAsFixed(1)} V", Icons.electric_meter, const Color(0xFF06B6D4)),
        _metricCard("CURRENT", "${_current.toStringAsFixed(2)} A", Icons.compress, const Color(0xFFF59E0B)),
        _metricCard("ENERGY", "${_energy.toStringAsFixed(2)} kWh", Icons.battery_charging_full, const Color(0xFF22C55E)),
        _metricCard("PF / FREQ", "${_pf.toStringAsFixed(2)} · ${_frequency.toStringAsFixed(0)}Hz", Icons.speed, const Color(0xFFA78BFA)),
      ],
    );
  }

  Widget _metricCard(String title, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.25)),
        boxShadow: [BoxShadow(color: color.withOpacity(0.05), blurRadius: 10)],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Row(children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 6),
          Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10, fontWeight: FontWeight.bold)),
        ]),
        const SizedBox(height: 8),
        Text(value, style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.bold)),
      ]),
    );
  }

  // === QUICK WEATHER ===
  Widget _quickWeather() {
    final temp = (_weather['temp'] as num?)?.toDouble() ?? 32.0;
    final desc = _weather['description'] ?? 'trời nắng';
    final suggestion = _weather['suggestion'] ?? '';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF1E3A5F), Color(0xFF0F172A)],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF38BDF8).withOpacity(0.2)),
      ),
      child: Row(children: [
        const Icon(Icons.wb_sunny, color: Color(0xFFFBBF24), size: 28),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text("Hà Nội · ${temp.toStringAsFixed(0)}°C · $desc",
              style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
          if (suggestion.isNotEmpty)
            Text(suggestion, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11), maxLines: 1, overflow: TextOverflow.ellipsis),
        ])),
      ]),
    );
  }

  // === QUICK ALERTS ===
  Widget _quickAlerts() {
    if (_alerts.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFF22C55E).withOpacity(0.06),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color(0xFF22C55E).withOpacity(0.3)),
        ),
        child: const Row(children: [
          Icon(Icons.check_circle, color: Color(0xFF22C55E), size: 18),
          SizedBox(width: 8),
          Text("Hệ thống bình thường. Không có cảnh báo.",
              style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
        ]),
      );
    }

    final criticals = _alerts.where((a) => a['level'] == 'critical' || a['level'] == 'warning').toList();
    return Column(children: [
      for (int i = 0; i < criticals.length && i < 2; i++)
        Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: (criticals[i]['level'] == 'critical' ? Colors.red : Colors.orange).withOpacity(0.06),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: (criticals[i]['level'] == 'critical' ? Colors.red : Colors.orange).withOpacity(0.3)),
          ),
          child: Row(children: [
            Text(criticals[i]['icon'] ?? '⚠️', style: const TextStyle(fontSize: 18)),
            const SizedBox(width: 8),
            Expanded(child: Text(criticals[i]['title'] ?? '',
                style: TextStyle(
                  color: criticals[i]['level'] == 'critical' ? Colors.redAccent : Colors.orangeAccent,
                  fontSize: 12, fontWeight: FontWeight.bold),
                maxLines: 1, overflow: TextOverflow.ellipsis)),
          ]),
        ),
    ]);
  }
}
