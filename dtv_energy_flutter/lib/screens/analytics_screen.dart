import 'dart:async';
import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';
import '../services/energy_service.dart';
import '../services/theme_service.dart';
import '../widgets/liquid_glass_card.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  final EnergyService _service = EnergyService();
  List<dynamic> _analytics = [];
  Map<String, dynamic> _weather = {};
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _fetchData();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _fetchData());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _fetchData() async {
    final analytics = await _service.fetchAnalytics();
    final weather = await _service.fetchWeather();
    if (mounted) setState(() { _analytics = analytics; _weather = weather; });
  }

  double _getMax(String key) {
    if (_analytics.isEmpty) return 1.0;
    return _analytics.map((d) => EnergyService.parseDouble(d[key])).reduce(max);
  }

  double _getAvg(String key) {
    if (_analytics.isEmpty) return 0.0;
    final sum = _analytics.map((d) => EnergyService.parseDouble(d[key])).reduce((a, b) => a + b);
    return sum / _analytics.length;
  }

  double _getMin(String key) {
    if (_analytics.isEmpty) return 0.0;
    return _analytics.map((d) => EnergyService.parseDouble(d[key])).reduce(min);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: const Text('📊 PHÂN TÍCH NĂNG LƯỢNG',
            style: TextStyle(color: Color(0xFF38BDF8), fontWeight: FontWeight.bold, fontSize: 16)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, color: Color(0xFF38BDF8)), onPressed: _fetchData),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _fetchData,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // === WEATHER CARD ===
              _buildWeatherCard(),
              const SizedBox(height: 16),

              // === POWER CHART ===
              _buildChartCard("⚡ CÔNG SUẤT (W)", "power", const Color(0xFFF97316)),
              const SizedBox(height: 14),

              // === VOLTAGE CHART ===
              _buildChartCard("🔌 ĐIỆN ÁP (V)", "voltage", const Color(0xFF06B6D4)),
              const SizedBox(height: 14),

              // === CURRENT CHART ===
              _buildChartCard("📊 DÒNG ĐIỆN (A)", "current", const Color(0xFFF59E0B)),
              const SizedBox(height: 14),

              // === STATS ===
              _buildStatsGrid(),
              const SizedBox(height: 14),

              // === SAMPLE INFO ===
              Text("📈 ${_analytics.length} / 60 mẫu (polling mỗi 5s)",
                  style: const TextStyle(color: Color(0xFF64748B), fontSize: 11)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWeatherCard() {
    final theme = ThemeService().currentTheme;
    final temp = EnergyService.parseDouble(_weather['temp'], 32.0);
    final humidity = EnergyService.parseInt(_weather['humidity'], 70);
    final desc = _weather['description'] ?? 'trời nắng';
    final city = _weather['city'] ?? 'Hà Nội';
    final suggestion = _weather['suggestion'] ?? '';
    final windSpeed = EnergyService.parseDouble(_weather['wind_speed'], 3.0);

    return LiquidGlassCard(
      borderColor: const Color(0xFFFBBF24).withOpacity(0.3),
      glowColor: const Color(0xFFFBBF24).withOpacity(0.08),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.wb_sunny_rounded, color: Color(0xFFFBBF24), size: 26),
          const SizedBox(width: 10),
          Text("THỜI TIẾT $city".toUpperCase(),
              style: const TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11.5, letterSpacing: 1)),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Text("${temp.toStringAsFixed(0)}°C",
              style: const TextStyle(color: Colors.white, fontSize: 36, fontWeight: FontWeight.bold, fontFeatures: [FontFeature.tabularFigures()])),
          const SizedBox(width: 16),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(desc, style: TextStyle(color: theme.primary, fontSize: 14, fontWeight: FontWeight.w600)),
            Text("Độ ẩm: $humidity% · Gió: ${windSpeed.toStringAsFixed(1)} m/s",
                style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
          ])),
        ]),
        if (suggestion.isNotEmpty) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: theme.surface.withOpacity(0.6),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(children: [
              const Icon(Icons.lightbulb_outline_rounded, color: Color(0xFF38BDF8), size: 16),
              const SizedBox(width: 8),
              Expanded(child: Text(suggestion,
                  style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 11.5, fontStyle: FontStyle.italic))),
            ]),
          ),
        ],
      ]),
    );
  }

  Widget _buildChartCard(String title, String key, Color color) {
    return LiquidGlassCard(
      borderColor: color.withOpacity(0.3),
      glowColor: color.withOpacity(0.08),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11.5, letterSpacing: 0.5)),
          if (_analytics.isNotEmpty)
            Text("Avg: ${_getAvg(key).toStringAsFixed(1)} · Max: ${_getMax(key).toStringAsFixed(1)}",
                style: TextStyle(color: color, fontSize: 10.5, fontWeight: FontWeight.bold, fontFeatures: const [FontFeature.tabularFigures()])),
        ]),
        const SizedBox(height: 10),
        SizedBox(
          height: 80,
          child: _analytics.isEmpty
              ? const Center(child: Text("Đang thu thập dữ liệu...", style: TextStyle(color: Color(0xFF64748B), fontSize: 12)))
              : CustomPaint(
                  size: const Size(double.infinity, 80),
                  painter: _ChartPainter(_analytics, key, color),
                ),
        ),
      ]),
    );
  }

  Widget _buildStatsGrid() {
    return GridView.count(
      crossAxisCount: 2, shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 10, mainAxisSpacing: 10, childAspectRatio: 2.0,
      children: [
        _statCard("Avg Power", "${_getAvg('power').toStringAsFixed(1)} W", const Color(0xFFF97316)),
        _statCard("Max Power", "${_getMax('power').toStringAsFixed(1)} W", const Color(0xFFEF4444)),
        _statCard("Avg Voltage", "${_getAvg('voltage').toStringAsFixed(1)} V", const Color(0xFF06B6D4)),
        _statCard("Min Voltage", "${_getMin('voltage').toStringAsFixed(1)} V", const Color(0xFFF59E0B)),
      ],
    );
  }

  Widget _statCard(String label, String value, Color color) {
    return LiquidGlassCard(
      padding: const EdgeInsets.all(10),
      borderRadius: 14,
      borderColor: color.withOpacity(0.25),
      glowColor: color.withOpacity(0.06),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
        Text(label, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Text(value, style: TextStyle(color: color, fontSize: 15, fontWeight: FontWeight.bold, fontFeatures: const [FontFeature.tabularFigures()])),
      ]),
    );
  }
}

class _ChartPainter extends CustomPainter {
  final List<dynamic> data;
  final String key;
  final Color color;
  _ChartPainter(this.data, this.key, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    if (data.isEmpty) return;
    final values = data.map((d) => EnergyService.parseDouble(d[key])).toList();
    final maxVal = values.reduce(max);
    final minVal = values.reduce(min);
    final range = maxVal - minVal;
    final yScale = range > 0 ? (size.height - 10) / range : 1.0;
    final xStep = data.length > 1 ? size.width / (data.length - 1) : size.width;

    final linePaint = Paint()
      ..color = color
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final fillPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [color.withOpacity(0.3), color.withOpacity(0.0)],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));

    final path = Path();
    final fillPath = Path();

    for (int i = 0; i < values.length; i++) {
      final x = i * xStep;
      final y = size.height - 5 - ((values[i] - minVal) * yScale);
      if (i == 0) {
        path.moveTo(x, y);
        fillPath.moveTo(x, size.height);
        fillPath.lineTo(x, y);
      } else {
        path.lineTo(x, y);
        fillPath.lineTo(x, y);
      }
    }
    fillPath.lineTo((values.length - 1) * xStep, size.height);
    fillPath.close();

    canvas.drawPath(fillPath, fillPaint);
    canvas.drawPath(path, linePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
