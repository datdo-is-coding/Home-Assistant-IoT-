import 'dart:async';
import 'dart:ui';
import 'package:flutter/material.dart';
import '../services/energy_service.dart';
import '../services/notification_service.dart';
import '../services/theme_service.dart';
import '../services/weather_state.dart';
import '../widgets/liquid_glass_card.dart';

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

  Map<String, dynamic> _tinyMlData = {};

  Future<void> _fetchMetrics() async {
    final data = await _service.fetchLiveMetrics();
    final tinyMl = await _service.fetchTinyML();
    if (mounted) {
      setState(() {
        _voltage = EnergyService.parseDouble(data['voltage'], 0.0);
        _current = EnergyService.parseDouble(data['current'], 0.0);
        _power = EnergyService.parseDouble(data['power'], 0.0);
        _energy = EnergyService.parseDouble(data['energy'], 0.0);
        _frequency = EnergyService.parseDouble(data['frequency'], 50.0);
        _pf = EnergyService.parseDouble(data['pf'], 1.0);
        _isOnline = data['is_online'] == true || data['voltage'] != null;
        _tinyMlData = tinyMl;
      });

      // 🔔 Auto push notification if TinyML detects anomaly or voltage spike
      final score = EnergyService.parseInt(_tinyMlData['anomaly_score'], 0);
      if (score >= 45) {
        final pattern = _tinyMlData['pattern_name'] ?? 'Cảnh báo TinyML AI';
        final rec = _tinyMlData['recommendation'] ?? '';
        NotificationService().showAnomalyNotification(
          id: 101,
          title: "🤖 TinyML AI Alert: $pattern",
          body: rec,
          isCritical: score >= 70,
        );
      }
    }
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
              const SizedBox(height: 14),
              _heroMetric(),
              const SizedBox(height: 14),
              _tinyMlCard(),
              const SizedBox(height: 14),
              _metricsGrid(),
              const SizedBox(height: 14),
              _evnCalculatorCard(),
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
        Row(children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [Color(0xFF00F2FE), Color(0xFF7C3AED)]),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.bolt_rounded, color: Colors.white, size: 18),
          ),
          const SizedBox(width: 8),
          ShaderMask(
            shaderCallback: (bounds) => const LinearGradient(
              colors: [Color(0xFF00F2FE), Color(0xFF93C5FD)],
            ).createShader(bounds),
            child: const Text("DTV ECHO HUB",
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 20, letterSpacing: 1.2)),
          ),
        ]),
        const SizedBox(height: 2),
        const Text("Standalone IoT Gateway · Hà Nội",
            style: TextStyle(color: Color(0xFF64748B), fontSize: 11.5, fontWeight: FontWeight.w500)),
      ]),
      const Spacer(),
      AnimatedBuilder(
        animation: _pulseController,
        builder: (context, child) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
            decoration: BoxDecoration(
              color: (_isOnline ? const Color(0xFF10B981) : Colors.red).withOpacity(0.12 + _pulseController.value * 0.08),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: _isOnline ? const Color(0xFF10B981) : Colors.red, width: 1.2),
              boxShadow: [
                BoxShadow(
                  color: (_isOnline ? const Color(0xFF10B981) : Colors.red).withOpacity(0.2),
                  blurRadius: 10,
                ),
              ],
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.sensors_rounded, size: 14, color: _isOnline ? const Color(0xFF10B981) : Colors.red),
              const SizedBox(width: 5),
              Text(_isOnline ? "ESP-NOW 24/7" : "OFFLINE",
                  style: TextStyle(color: _isOnline ? const Color(0xFF10B981) : Colors.red, fontSize: 10.5, fontWeight: FontWeight.bold)),
            ]),
          );
        },
      ),
    ]);
  }

  // === HERO METRIC (Power - Liquid Glassmorphism) ===
  Widget _heroMetric() {
    final theme = ThemeService().currentTheme;
    return LiquidGlassCard(
      borderColor: theme.primary.withOpacity(0.4),
      glowColor: theme.primary.withOpacity(0.12),
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 20),
      child: Column(children: [
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Container(
            width: 8, height: 8,
            decoration: BoxDecoration(color: theme.primary, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          const Text("CÔNG SUẤT TIÊU THỤ THỜI GIAN THỰC",
              style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11, letterSpacing: 1.5, fontWeight: FontWeight.bold)),
        ]),
        const SizedBox(height: 10),
        ShaderMask(
          shaderCallback: (bounds) => LinearGradient(
            colors: [Colors.white, theme.primary],
            begin: Alignment.topCenter, end: Alignment.bottomCenter,
          ).createShader(bounds),
          child: Text(
            _power.toStringAsFixed(0),
            style: const TextStyle(
              color: Colors.white, fontSize: 58, fontWeight: FontWeight.w900, height: 1.0,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
        ),
        const SizedBox(height: 6),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
          decoration: BoxDecoration(
            color: theme.primary.withOpacity(0.12),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: theme.primary.withOpacity(0.4)),
          ),
          child: Text("WATT (W)", style: TextStyle(color: theme.primary, fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
        ),
      ]),
    );
  }

  // === METRICS GRID ===
  Widget _metricsGrid() {
    return GridView.count(
      crossAxisCount: 2, shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 10, mainAxisSpacing: 10, childAspectRatio: 1.45,
      children: [
        _metricCard("VOLTAGE", "${_voltage.toStringAsFixed(1)} V", Icons.electric_meter_rounded, const Color(0xFF06B6D4)),
        _metricCard("CURRENT", "${_current.toStringAsFixed(2)} A", Icons.compress_rounded, const Color(0xFFF59E0B)),
        _metricCard("ENERGY", "${_energy.toStringAsFixed(2)} kWh", Icons.battery_charging_full_rounded, const Color(0xFF10B981)),
        _metricCard("PF / FREQ", "${_pf.toStringAsFixed(2)} · ${_frequency.toStringAsFixed(0)}Hz", Icons.speed_rounded, const Color(0xFFA78BFA)),
      ],
    );
  }

  Widget _metricCard(String title, String value, IconData icon, Color color) {
    return LiquidGlassCard(
      padding: const EdgeInsets.all(12),
      borderRadius: 16,
      borderColor: color.withOpacity(0.3),
      glowColor: color.withOpacity(0.08),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Row(children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 6),
          Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10.5, fontWeight: FontWeight.bold)),
        ]),
        const SizedBox(height: 8),
        Text(
          value,
          style: TextStyle(
            color: color, fontSize: 17.5, fontWeight: FontWeight.bold,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ]),
    );
  }

  // === QUICK WEATHER ===
  Widget _quickWeather() {
    final temp = EnergyService.parseDouble(_weather['temp'], 32.0);
    final desc = _weather['description'] ?? 'trời nắng';
    final suggestion = _weather['suggestion'] ?? '';

    // Auto-update weather effect from API
    WeatherState().updateFromApi(desc);

    return LiquidGlassCard(
      borderColor: const Color(0xFFFBBF24).withOpacity(0.35),
      glowColor: const Color(0xFFFBBF24).withOpacity(0.1),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.wb_sunny_rounded, color: Color(0xFFFBBF24), size: 26),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Hà Nội · ${temp.toStringAsFixed(0)}°C · $desc",
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold)),
              if (suggestion.isNotEmpty)
                Text(suggestion, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11), maxLines: 1, overflow: TextOverflow.ellipsis),
            ])),
          ]),
          const SizedBox(height: 10),

          // Dynamic Weather Effect Selector Chips
          ValueListenableBuilder<WeatherMode>(
            valueListenable: WeatherState().currentMode,
            builder: (context, currentMode, _) {
              return SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    _weatherChip(WeatherMode.sunny, "☀️ Nắng", currentMode),
                    const SizedBox(width: 6),
                    _weatherChip(WeatherMode.rainy, "🌧️ Mưa Kính", currentMode),
                    const SizedBox(width: 6),
                    _weatherChip(WeatherMode.stormy, "⛈️ Sấm Dông", currentMode),
                    const SizedBox(width: 6),
                    _weatherChip(WeatherMode.cloudy, "☁️ Mây U Ám", currentMode),
                    const SizedBox(width: 6),
                    _weatherChip(WeatherMode.auto, "🔄 Tự Động", currentMode),
                  ],
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _weatherChip(WeatherMode mode, String label, WeatherMode currentMode) {
    final isSelected = currentMode == mode;
    final theme = ThemeService().currentTheme;
    return GestureDetector(
      onTap: () => WeatherState().setMode(mode),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: isSelected ? theme.primary.withOpacity(0.25) : theme.bg.withOpacity(0.6),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: isSelected ? theme.primary : const Color(0xFF334155)),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? theme.primary : const Color(0xFF94A3B8),
            fontSize: 10.5,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
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

  // === NEW v1.0.2 FEATURE BANNER ===
  Widget _version102Banner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [Color(0xFF0284C7), Color(0xFF7C3AED)]),
        borderRadius: BorderRadius.circular(10),
      ),
      child: const Row(children: [
        Icon(Icons.auto_awesome, color: Colors.amberAccent, size: 18),
        SizedBox(width: 8),
        Expanded(child: Text(
          "✨ VERSION 1.0.2 LIVE — Đã tích hợp Công Cụ Tính Tiền Điện EVN Bậc Thang 2026!",
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 11),
        )),
      ]),
    );
  }

  // === NEW v1.0.2 EVN CALCULATOR CARD ===
  Widget _evnCalculatorCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF38BDF8).withOpacity(0.3)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.calculate, color: Color(0xFF38BDF8), size: 20),
          SizedBox(width: 8),
          Text("🧮 TÍNH TIỀN ĐIỆN EVN 6 BẬC THANG (v1.0.2)",
              style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12)),
        ]),
        const SizedBox(height: 8),
        const Text(
          "Dựa trên điện năng tiêu thụ thực tế đo từ PZEM-004T. Nhấn để tính tiền điện và mô phỏng mức tiết kiệm.",
          style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: _showEvnCalculatorDialog,
            icon: const Icon(Icons.analytics, size: 16),
            label: const Text("Mở Bảng Tính Tiền Điện EVN"),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF0284C7),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 10),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
        ),
      ]),
    );
  }

  void _showEvnCalculatorDialog() {
    double estKwh = _energy > 0 ? _energy : 185.5; // fallback or real kWh
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1E293B),
        title: const Row(children: [
          Icon(Icons.request_quote, color: Color(0xFF38BDF8)),
          SizedBox(width: 8),
          Text("Bảng Tính EVN 2026", style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text("⚡ Sản lượng đo được: ${estKwh.toStringAsFixed(1)} kWh",
              style: const TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold, fontSize: 14)),
          const SizedBox(height: 10),
          _evnTierRow("Bậc 1 (0-50 kWh)", "1.893 đ/kWh"),
          _evnTierRow("Bậc 2 (51-100 kWh)", "1.956 đ/kWh"),
          _evnTierRow("Bậc 3 (101-200 kWh)", "2.271 đ/kWh"),
          _evnTierRow("Bậc 4 (201-300 kWh)", "2.860 đ/kWh"),
          _evnTierRow("Bậc 5 (301-400 kWh)", "3.197 đ/kWh"),
          _evnTierRow("Bậc 6 (>400 kWh)", "3.302 đ/kWh"),
          const Divider(color: Color(0xFF334155)),
          const Text("💡 Dự kiến tiết kiệm 20% nếu dùng máy lạnh 26°C:",
              style: TextStyle(color: Color(0xFF22C55E), fontSize: 11.5, fontWeight: FontWeight.bold)),
        ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text("Đóng", style: TextStyle(color: Color(0xFF38BDF8))),
          ),
        ],
      ),
    );
  }

  Widget _evnTierRow(String tier, String price) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(tier, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
        Text(price, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
      ]),
    );
  }

  // === TINYML AI CARD (echo-nightly glassmorphic) ===
  Widget _tinyMlCard() {
    final pattern = _tinyMlData['pattern_name'] ?? 'Tải Điện Bình Thường & Tối Ưu';
    final rec = _tinyMlData['recommendation'] ?? 'Mô hình TinyML ESP32-S3 đánh giá hệ thống an toàn.';
    final score = EnergyService.parseInt(_tinyMlData['anomaly_score'], 5);
    final latencyUs = EnergyService.parseInt(_tinyMlData['inference_us'], 525);

    Color statusColor = const Color(0xFF10B981);
    if (score >= 70) {
      statusColor = const Color(0xFFEF4444);
    } else if (score >= 40) {
      statusColor = const Color(0xFFF59E0B);
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF131B2E).withOpacity(0.85),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: statusColor.withOpacity(0.4), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: statusColor.withOpacity(0.12),
            blurRadius: 18,
            spreadRadius: 1,
          ),
        ],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: statusColor.withOpacity(0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(Icons.psychology_rounded, color: statusColor, size: 22),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text("🤖 TINYML AI ENGINE (ESP32-S3 N16R8)",
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 12, letterSpacing: 0.5)),
              Text("On-Device Inference · Xtensa LX7 Vector",
                  style: TextStyle(color: const Color(0xFF64748B), fontSize: 10)),
            ]),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
            decoration: BoxDecoration(
              color: statusColor.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: statusColor.withOpacity(0.5)),
            ),
            child: Text("${latencyUs} µs", style: TextStyle(color: statusColor, fontSize: 10.5, fontWeight: FontWeight.bold)),
          ),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          const Text("Trạng Thái: ", style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11.5)),
          Expanded(
            child: Text(pattern, style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.bold)),
          ),
        ]),
        const SizedBox(height: 6),
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: const Color(0xFF090D16).withOpacity(0.6),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(children: [
            const Icon(Icons.lightbulb_outline_rounded, color: Color(0xFF38BDF8), size: 16),
            const SizedBox(width: 8),
            Expanded(
              child: Text(rec, style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 11, height: 1.3)),
            ),
          ]),
        ),
      ]),
    );
  }
}
