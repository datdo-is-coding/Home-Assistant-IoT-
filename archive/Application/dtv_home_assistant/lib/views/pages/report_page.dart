import 'package:dtv_home_assistant/views/widgets/consumption_chart.dart';
import 'package:flutter/material.dart';

class ReportPage extends StatelessWidget {
  const ReportPage({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(
            height: 380,
            child: ConsumptionChart(showDropdown: true, initialMode: 'hourly'),
          ),
          const SizedBox(height: 16),
          // 2. Card Tổng quan thống kê chi tiết báo cáo
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 20,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(
                      Icons.analytics_rounded,
                      color: Color(0xFF6366F1),
                      size: 22,
                    ),
                    SizedBox(width: 8),
                    Text(
                      'Thống Kê Chi Tiết',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1E293B),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: _buildReportStatCard(
                        title: 'Trung bình/Ngày',
                        value: '22.4 kWh',
                        icon: Icons.speed_rounded,
                        color: const Color(0xFF3B82F6),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildReportStatCard(
                        title: 'Giờ Cao Điểm',
                        value: '18:00 - 20:00',
                        icon: Icons.access_time_filled_rounded,
                        color: const Color(0xFFF97316),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildReportStatCard(
                        title: 'Ước tính tiền điện',
                        value: '1.250.000 đ',
                        icon: Icons.payments_rounded,
                        color: const Color(0xFF10B981),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildReportStatCard(
                        title: 'Hiệu suất năng lượng',
                        value: '-12% so với tháng trước',
                        icon: Icons.trending_down_rounded,
                        color: const Color(0xFF8B5CF6),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildReportStatCard({
    required String title,
    required String value,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: color),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: Colors.grey.shade700,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.bold,
              color: color,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
