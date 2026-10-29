import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:iot_dashboard/core/theme/app_theme.dart';
import 'package:iot_dashboard/data/notifiers.dart';

class SidebarWidget extends StatelessWidget {
  const SidebarWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors =
        theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    // Glassmorphic surface aligned with AppColors
    final sidebarBg = isDark
        ? const Color(0xE6161B26) // rgba(22, 27, 38, 0.9)
        : Colors.white.withValues(alpha: 0.92);

    final borderColor = colors.cardBorder;

    return ValueListenableBuilder<bool>(
      valueListenable: isSidebarOpenNotifier,
      builder: (context, isOpen, child) {
        final sidebarWidth = isOpen ? 250.0 : 78.0;

        return ValueListenableBuilder<int>(
          valueListenable: selectedPageNotifier,
          builder: (context, selectedIndex, child) {
            return Padding(
              padding: const EdgeInsets.all(12.0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(24),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 350),
                    curve: const Cubic(0.4, 0.0, 0.2, 1.0),
                    width: sidebarWidth,
                    height: double.infinity,
                    padding: EdgeInsets.symmetric(
                      vertical: 20,
                      horizontal: isOpen ? 14 : 10,
                    ),
                    decoration: BoxDecoration(
                      color: sidebarBg,
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: borderColor, width: 1),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(
                            alpha: isDark ? 0.4 : 0.08,
                          ),
                          blurRadius: 30,
                          offset: const Offset(0, 10),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 1. BRAND / LOGO HEADER VÀ NÚT ĐÓNG/MỞ
                        _buildBrandHeader(context, isOpen, isDark),

                        const SizedBox(height: 20),

                        // 2. NAV LINKS LIST
                        Expanded(
                          child: SingleChildScrollView(
                            child: Column(
                              children: [
                                _SidebarNavItem(
                                  icon: Icons.grid_view_rounded,
                                  label: "Dashboard",
                                  isSelected: selectedIndex == 0,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 0,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.developer_board_rounded,
                                  label: "Thiết Bị & Bo Mạch",
                                  isSelected: selectedIndex == 1,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 1,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.bar_chart_rounded,
                                  label: "Điện Năng & Thống Kê",
                                  isSelected: selectedIndex == 2,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 2,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.bolt_rounded,
                                  label: "Kịch Bản",
                                  isSelected: selectedIndex == 3,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 3,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.record_voice_over_rounded,
                                  label: "Giọng Nói & KWS",
                                  isSelected: selectedIndex == 4,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 4,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.notifications_active_rounded,
                                  label: "Cảnh Báo",
                                  isSelected: selectedIndex == 5,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 5,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.person_rounded,
                                  label: "Hồ Sơ",
                                  isSelected: selectedIndex == 6,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 6,
                                ),
                                const SizedBox(height: 6),
                                _SidebarNavItem(
                                  icon: Icons.support_agent_rounded,
                                  label: "Hỗ Trợ & Liên Hệ",
                                  isSelected: selectedIndex == 7,
                                  isOpen: isOpen,
                                  isDark: isDark,
                                  onTap: () => selectedPageNotifier.value = 7,
                                ),
                              ],
                            ),
                          ),
                        ),

                        const SizedBox(height: 8),

                        // 3. SETTINGS LINK (CỐ ĐỊNH Ở ĐÁY)
                        _SidebarNavItem(
                          icon: Icons.settings_rounded,
                          label: "Cài Đặt",
                          isSelected: selectedIndex == 8,
                          isOpen: isOpen,
                          isDark: isDark,
                          onTap: () => selectedPageNotifier.value = 8,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildBrandHeader(BuildContext context, bool isOpen, bool isDark) {
    final toggleBg = isDark
        ? Colors.white.withValues(alpha: 0.08)
        : Colors.black.withValues(alpha: 0.05);

    final toggleBorder = isDark
        ? Colors.white.withValues(alpha: 0.12)
        : Colors.black.withValues(alpha: 0.08);

    if (!isOpen) {
      return Center(
        child: InkWell(
          onTap: () {
            isSidebarOpenNotifier.value = true;
          },
          borderRadius: BorderRadius.circular(16),
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF3B82F6), Color(0xFF2563EB)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(14),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF2563EB).withValues(alpha: 0.4),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: const Icon(
              Icons.bolt_rounded,
              color: Colors.white,
              size: 24,
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4.0),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF0F172A), Color(0xFF334155)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.2),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: const Icon(
              Icons.home_rounded,
              color: Colors.white,
              size: 22,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              "Home Companion",
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.3,
                color: isDark ? Colors.white : const Color(0xFF0F172A),
              ),
            ),
          ),
          InkWell(
            onTap: () {
              isSidebarOpenNotifier.value = !isSidebarOpenNotifier.value;
            },
            borderRadius: BorderRadius.circular(15),
            child: Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: toggleBg,
                shape: BoxShape.circle,
                border: Border.all(color: toggleBorder, width: 1),
              ),
              child: Icon(
                Icons.chevron_left_rounded,
                color: isDark ? Colors.white : const Color(0xFF1E293B),
                size: 18,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// INDIVIDUAL NAVIGATION LINK ITEM
class _SidebarNavItem extends StatefulWidget {
  final IconData icon;
  final String label;
  final bool isSelected;
  final bool isOpen;
  final bool isDark;
  final VoidCallback onTap;

  const _SidebarNavItem({
    required this.icon,
    required this.label,
    required this.isSelected,
    required this.isOpen,
    required this.isDark,
    required this.onTap,
  });

  @override
  State<_SidebarNavItem> createState() => _SidebarNavItemState();
}

class _SidebarNavItemState extends State<_SidebarNavItem> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final activeBg = widget.isDark
        ? const Color(0xFFF8FAFC)
        : const Color(0xFF0F172A);

    final activeTextColor = widget.isDark
        ? const Color(0xFF0F172A)
        : Colors.white;

    final inactiveTextColor = widget.isDark
        ? Colors.white.withValues(alpha: 0.7)
        : const Color(0xFF475569);

    final hoverBg = widget.isDark
        ? Colors.white.withValues(alpha: 0.1)
        : Colors.black.withValues(alpha: 0.05);

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: widget.isSelected
                ? activeBg
                : (_isHovered ? hoverBg : Colors.transparent),
            borderRadius: BorderRadius.circular(14),
            boxShadow: widget.isSelected
                ? [
                    BoxShadow(
                      color: widget.isDark
                          ? Colors.white.withValues(alpha: 0.15)
                          : Colors.black.withValues(alpha: 0.12),
                      blurRadius: 15,
                      offset: const Offset(0, 4),
                    ),
                  ]
                : null,
          ),
          child: Row(
            children: [
              Icon(
                widget.icon,
                size: 20,
                color: widget.isSelected ? activeTextColor : inactiveTextColor,
              ),
              if (widget.isOpen) ...[
                const SizedBox(width: 12),
                Expanded(
                  child: AnimatedOpacity(
                    duration: const Duration(milliseconds: 200),
                    opacity: widget.isOpen ? 1.0 : 0.0,
                    child: Text(
                      widget.label,
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: widget.isSelected
                            ? FontWeight.bold
                            : FontWeight.w500,
                        color: widget.isSelected
                            ? activeTextColor
                            : inactiveTextColor,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
