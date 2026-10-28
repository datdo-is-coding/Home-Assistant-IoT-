import 'package:flutter/material.dart';

class AlertCenterCard extends StatefulWidget {
  const AlertCenterCard({super.key});

  @override
  State<AlertCenterCard> createState() => _AlertCenterCardState();
}

class _AlertCenterCardState extends State<AlertCenterCard> {
  String selectedFilter = 'ALL';

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              'Trung Tâm Cảnh Báo Sự Cố',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: isDark ? Colors.white : const Color(0xFF1E293B),
              ),
            ),
            TextButton.icon(
              onPressed: () {},
              icon: Icon(
                Icons.done_all,
                size: 18,
                color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade700,
              ),
              label: Text(
                'Đã xử lý tất cả',
                style: TextStyle(
                  color: isDark ? const Color(0xFF60A5FA) : Colors.blue.shade700,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            _buildFilterChip('ALL', 'Tất cả', isDark),
            const SizedBox(width: 8),
            _buildFilterChip('HIGH', '🔴 Nguy hiểm', isDark),
            const SizedBox(width: 8),
            _buildFilterChip('MEDIUM', '🟠 Cảnh báo', isDark),
            const SizedBox(width: 8),
            _buildFilterChip('RESOLVED', '🟢 Đã xử lý', isDark),
          ],
        ),
        const SizedBox(height: 20),
        Expanded(
          child: Center(
            child: Text(
              'Danh sách cảnh báo chưa có sự cố mới nào.',
              style: TextStyle(
                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                fontSize: 14,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFilterChip(String key, String label, bool isDark) {
    final isSelected = selectedFilter == key;

    final selectedBg = isDark ? const Color(0xFF2563EB) : Colors.blue.shade600;
    final unselectedBg = isDark ? const Color(0xFF1E293B) : Colors.grey.shade100;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade300;

    return FilterChip(
      selected: isSelected,
      label: Text(
        label,
        style: TextStyle(
          color: isSelected
              ? Colors.white
              : (isDark ? Colors.grey.shade300 : Colors.black87),
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
        ),
      ),
      selectedColor: selectedBg,
      backgroundColor: unselectedBg,
      checkmarkColor: Colors.white,
      side: BorderSide(
        color: isSelected ? selectedBg : borderColor,
      ),
      onSelected: (bool selected) {
        setState(() {
          selectedFilter = key;
        });
      },
    );
  }
}
