import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/notifiers.dart';

class CustomSearchAutocomplete extends StatefulWidget {
  const CustomSearchAutocomplete({super.key});

  static const List<Map<String, String>> searchData = [
    {
      'title': 'Phòng Khách',
      'category': 'Khu Vực • 4 Thiết Bị Active',
      'pageIndex': '0',
      'icon': 'meeting_room_outlined',
    },
    {
      'title': 'Phòng Ngủ Master',
      'category': 'Khu Vực • 3 Thiết Bị Active',
      'pageIndex': '0',
      'icon': 'bed_outlined',
    },
    {
      'title': 'Nhà Bếp & Phòng Ăn',
      'category': 'Khu Vực • 2 Thiết Bị Active',
      'pageIndex': '0',
      'icon': 'kitchen_outlined',
    },
    {
      'title': 'Báo Cáo Điện Năng',
      'category': 'Thống Kê • Tiêu Thụ KWh',
      'pageIndex': '1',
      'icon': 'bar_chart_rounded',
    },
    {
      'title': 'Thông Tin Tài Khoản',
      'category': 'Hồ Sơ • Gói Bảo Trì Pro',
      'pageIndex': '2',
      'icon': 'person_rounded',
    },
    {
      'title': 'Trung Tâm Cảnh Báo',
      'category': 'Thông Báo • 27 Sự Cố',
      'pageIndex': '3',
      'icon': 'notifications_active_rounded',
    },
    {
      'title': 'Đăng Ký Nâng Cấp',
      'category': 'Hỗ Trợ • Khảo Sát Tận Nơi',
      'pageIndex': '4',
      'icon': 'support_agent_rounded',
    },
    {
      'title': 'Cài Đặt Cấu Hình',
      'category': 'Hệ Thống • MQTT & Dark Mode',
      'pageIndex': '5',
      'icon': 'settings_rounded',
    },
  ];

  @override
  State<CustomSearchAutocomplete> createState() =>
      _CustomSearchAutocompleteState();
}

class _CustomSearchAutocompleteState extends State<CustomSearchAutocomplete> {
  bool _isExpanded = false;
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  final LayerLink _layerLink = LayerLink();
  OverlayEntry? _overlayEntry;

  List<Map<String, String>> _filteredResults = [];

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(() {
      if (!_focusNode.hasFocus && _controller.text.trim().isEmpty) {
        setState(() {
          _isExpanded = false;
        });
        _hideOverlay();
      }
    });

    _controller.addListener(() {
      final query = _controller.text.toLowerCase().trim();
      if (query.isNotEmpty) {
        final matches = CustomSearchAutocomplete.searchData.where((item) {
          final title = item['title']!.toLowerCase();
          final category = item['category']!.toLowerCase();
          return title.contains(query) || category.contains(query);
        }).toList();

        setState(() {
          _filteredResults = matches;
        });

        _showOverlay();
      } else {
        setState(() {
          _filteredResults = [];
        });
        _hideOverlay();
      }
    });
  }

  @override
  void dispose() {
    _hideOverlay();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _showOverlay() {
    _overlayEntry?.remove();
    _overlayEntry = _createOverlayEntry();
    Overlay.of(context).insert(_overlayEntry!);
  }

  void _hideOverlay() {
    _overlayEntry?.remove();
    _overlayEntry = null;
  }

  void _toggleExpand() {
    setState(() {
      _isExpanded = !_isExpanded;
      if (_isExpanded) {
        _focusNode.requestFocus();
      } else {
        _focusNode.unfocus();
        _controller.clear();
        _hideOverlay();
      }
    });
  }

  void _selectResult(Map<String, String> item) {
    final pageIndex = int.parse(item['pageIndex']!);
    selectedPageNotifier.value = pageIndex;
    _controller.clear();
    _focusNode.unfocus();
    setState(() {
      _isExpanded = false;
    });
    _hideOverlay();

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã chuyển tới: ${item['title']}'),
        backgroundColor: const Color(0xFF38BDF8),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  OverlayEntry _createOverlayEntry() {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return OverlayEntry(
      builder: (context) => Positioned(
        width: 360,
        child: CompositedTransformFollower(
          link: _layerLink,
          showWhenUnlinked: false,
          offset: const Offset(0, 52),
          child: Material(
            color: Colors.transparent,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                child: Container(
                  constraints: const BoxConstraints(maxHeight: 280),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xE6161B22) // rgba(22, 27, 34, 0.9)
                        : Colors.white.withValues(alpha: 0.92),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: isDark
                          ? const Color(0x3338BDF8)
                          : const Color(0x6638BDF8),
                      width: 1.5,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF38BDF8).withValues(alpha: 0.2),
                        blurRadius: 20,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: _filteredResults.isEmpty
                      ? const Padding(
                          padding: EdgeInsets.all(16.0),
                          child: Center(
                            child: Text(
                              "Không tìm thấy kết quả phù hợp",
                              style: TextStyle(
                                color: Colors.grey,
                                fontSize: 13,
                              ),
                            ),
                          ),
                        )
                      : ListView.separated(
                          padding: EdgeInsets.zero,
                          shrinkWrap: true,
                          itemCount: _filteredResults.length,
                          separatorBuilder: (context, index) =>
                              const SizedBox(height: 6),
                          itemBuilder: (context, index) {
                            final item = _filteredResults[index];
                            return _MovieSearchResultCard(
                              item: item,
                              isDark: isDark,
                              onTap: () => _selectResult(item),
                            );
                          },
                        ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    const cyanAccent = Color(0xFF38BDF8);

    final boxBg = isDark
        ? const Color(0xCC161B22) // rgba(22, 27, 34, 0.8)
        : Colors.white.withValues(alpha: 0.85);

    final borderColor = _isExpanded
        ? cyanAccent
        : (isDark ? Colors.white.withValues(alpha: 0.1) : Colors.grey.shade300);

    return CompositedTransformTarget(
      link: _layerLink,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 400),
        curve: const Cubic(0.2, 1.0, 0.36, 1.0),
        width: _isExpanded ? 340 : 44,
        height: 44,
        decoration: BoxDecoration(
          color: boxBg,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: borderColor, width: _isExpanded ? 1.8 : 1),
          boxShadow: [
            BoxShadow(
              color: _isExpanded
                  ? cyanAccent.withValues(alpha: 0.3)
                  : Colors.black.withValues(alpha: isDark ? 0.4 : 0.08),
              blurRadius: _isExpanded ? 20 : 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: [
            // SEARCH ICON BUTTON (Tap to Expand / Collapse)
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: _toggleExpand,
                borderRadius: BorderRadius.circular(22),
                child: Container(
                  width: 42,
                  height: 42,
                  alignment: Alignment.center,
                  child: const Icon(
                    Icons.search_rounded,
                    color: cyanAccent,
                    size: 22,
                  ),
                ),
              ),
            ),

            // SEARCH INPUT FIELD (Shown when expanded)
            if (_isExpanded) ...[
              Expanded(
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  style: TextStyle(
                    fontSize: 14,
                    color: isDark ? const Color(0xFFF8FAFC) : const Color(0xFF0F172A),
                  ),
                  decoration: const InputDecoration(
                    hintText: "Search devices, rooms, pages...",
                    hintStyle: TextStyle(
                      fontSize: 13,
                      color: Color(0xFF64748B),
                    ),
                    border: InputBorder.none,
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
              if (_controller.text.isNotEmpty)
                IconButton(
                  icon: const Icon(Icons.close_rounded, size: 18),
                  color: Colors.grey,
                  onPressed: () {
                    _controller.clear();
                  },
                )
              else
                Container(
                  margin: const EdgeInsets.only(right: 12),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: cyanAccent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Text(
                    "ready",
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: cyanAccent,
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

/// AESTHETIC SEARCH RESULT CARD (Movie Card Style matching HTML Template)
class _MovieSearchResultCard extends StatefulWidget {
  final Map<String, String> item;
  final bool isDark;
  final VoidCallback onTap;

  const _MovieSearchResultCard({
    required this.item,
    required this.isDark,
    required this.onTap,
  });

  @override
  State<_MovieSearchResultCard> createState() => _MovieSearchResultCardState();
}

class _MovieSearchResultCardState extends State<_MovieSearchResultCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    const cyanAccent = Color(0xFF38BDF8);

    final cardBg = widget.isDark
        ? (_isHovered ? const Color(0xFF1E293B) : const Color(0xFF161B22))
        : (_isHovered ? Colors.grey.shade100 : Colors.grey.shade50);

    final borderColor = _isHovered
        ? cyanAccent.withValues(alpha: 0.5)
        : (widget.isDark ? Colors.white.withValues(alpha: 0.08) : Colors.grey.shade300);

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: cardBg,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: borderColor, width: 1),
            boxShadow: _isHovered
                ? [
                    BoxShadow(
                      color: cyanAccent.withValues(alpha: 0.15),
                      blurRadius: 10,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: cyanAccent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  color: cyanAccent,
                  size: 18,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.item['title']!,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: widget.isDark
                            ? const Color(0xFFE2E8F0)
                            : const Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      widget.item['category']!,
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF64748B),
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.arrow_forward_ios_rounded,
                size: 14,
                color: Color(0xFF64748B),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
