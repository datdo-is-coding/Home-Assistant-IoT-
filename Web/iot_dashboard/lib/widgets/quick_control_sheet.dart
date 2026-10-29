import 'dart:ui' show ImageFilter;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/smart_home_providers.dart';
import '../core/theme/app_theme.dart';
import '../models/device.dart';
import 'soft_3d_decorations.dart';

class QuickControlSheet extends ConsumerStatefulWidget {
  final Device device;
  final ValueChanged<bool> onToggle;
  final ValueChanged<double> onValueChanged;
  final VoidCallback? onMoreSettings;

  const QuickControlSheet({
    super.key,
    required this.device,
    required this.onToggle,
    required this.onValueChanged,
    this.onMoreSettings,
  });

  static Future<void> show(
    BuildContext context, {
    required Device device,
    required ValueChanged<bool> onToggle,
    required ValueChanged<double> onValueChanged,
    VoidCallback? onMoreSettings,
  }) {
    return showModalBottomSheet(
      context: context,
      useRootNavigator: true,
      useSafeArea: true,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => QuickControlSheet(
        device: device,
        onToggle: onToggle,
        onValueChanged: onValueChanged,
        onMoreSettings: onMoreSettings,
      ),
    );
  }

  @override
  ConsumerState<QuickControlSheet> createState() => _QuickControlSheetState();
}

class _QuickControlSheetState extends ConsumerState<QuickControlSheet> {
  late double _currentValue;
  late bool _isOn;

  @override
  void initState() {
    super.initState();
    _currentValue = widget.device.value;
    _isOn = widget.device.isOn;
  }

  @override
  Widget build(BuildContext context) {
    final liveDevice =
        ref.watch(deviceProvider(widget.device.id)) ?? widget.device;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ??
        (isDark ? AppColors.dark : AppColors.light);

    final Color accentColor = switch (widget.device.type) {
      DeviceType.light => colors.lightAccent,
      DeviceType.fan => colors.fanAccent,
      DeviceType.socket => colors.socketAccent,
      DeviceType.airConditioner => colors.climateAccent,
      _ => colors.socketAccent,
    };

    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(30)),
      child: BackdropFilter(
        enabled: !MediaQuery.disableAnimationsOf(context) &&
            !MediaQuery.highContrastOf(context),
        filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
        child: Container(
          decoration: Soft3DDecorations.card(
            isDark: isDark,
            radius: 30,
          ).copyWith(
              gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              theme.colorScheme.surface.withValues(alpha: 0.94),
              theme.colorScheme.surface.withValues(alpha: 0.90),
            ],
          )),
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xFF374458)
                        : const Color(0xFFCBD5E1),
                    borderRadius: BorderRadius.circular(10),
                    boxShadow: [
                      BoxShadow(
                        color:
                            Colors.black.withValues(alpha: isDark ? 0.3 : 0.05),
                        blurRadius: 2,
                        offset: const Offset(0, 1),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  Container(
                    width: 46,
                    height: 46,
                    decoration: Soft3DDecorations.iconWell(
                      isDark: isDark,
                      isActive: _isOn && widget.device.online,
                      accentColor: accentColor,
                      radius: 14,
                    ),
                    child: Icon(
                      widget.device.iconData,
                      color: _isOn && widget.device.online
                          ? accentColor
                          : (isDark
                              ? const Color(0xFF64748B)
                              : const Color(0xFF94A3B8)),
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.device.name,
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${widget.device.roomId} · ${_isOn ? "Đang bật" : "Đã tắt"}',
                          style: TextStyle(
                              fontSize: 13,
                              color: theme.colorScheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                  SoftBounce(
                    onTap: () => Navigator.pop(context),
                    pressedScale: 0.90,
                    child: Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: isDark
                              ? const [Color(0xFF242C3C), Color(0xFF161B26)]
                              : const [Color(0xFFFFFFFF), Color(0xFFEFF3F8)],
                        ),
                        border: Border.all(
                          color: isDark
                              ? const Color(0xFF2D384C)
                              : const Color(0xFFE2E8F0),
                          width: 1.0,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black
                                .withValues(alpha: isDark ? 0.35 : 0.06),
                            offset: const Offset(0, 3),
                            blurRadius: 6,
                          ),
                        ],
                      ),
                      child: const Icon(Icons.close_rounded, size: 18),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              if (widget.device.metadata['can_dim'] == true) ...[
                Container(
                  height: 200,
                  width: 100,
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xFF12151D)
                        : const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: colors.cardBorder),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    alignment: Alignment.bottomCenter,
                    children: [
                      FractionallySizedBox(
                        heightFactor: _isOn
                            ? (_currentValue / 100.0).clamp(0.05, 1.0)
                            : 0.0,
                        widthFactor: 1.0,
                        child: Container(
                          decoration: BoxDecoration(
                            color: accentColor.withValues(
                                alpha: isDark ? 0.85 : 0.90),
                            borderRadius: const BorderRadius.vertical(
                                bottom: Radius.circular(24)),
                          ),
                        ),
                      ),
                      Positioned.fill(
                        child: RotatedBox(
                          quarterTurns: 3,
                          child: SliderTheme(
                            data: SliderTheme.of(context).copyWith(
                              trackHeight: 100,
                              thumbShape: SliderComponentShape.noThumb,
                              overlayShape: SliderComponentShape.noOverlay,
                              activeTrackColor: Colors.transparent,
                              inactiveTrackColor: Colors.transparent,
                            ),
                            child: Slider(
                              value: _currentValue.clamp(0.0, 100.0),
                              min: 0.0,
                              max: 100.0,
                              onChanged: (val) {
                                HapticFeedback.selectionClick();
                                setState(() {
                                  _currentValue = val;
                                  _isOn = val > 0;
                                });
                                widget.onValueChanged(val);
                              },
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        top: 16,
                        child: Column(
                          children: [
                            Text(
                              '${_currentValue.toInt()}%',
                              style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w800,
                                color: _isOn && _currentValue > 70
                                    ? (isDark ? Colors.black : Colors.white)
                                    : theme.colorScheme.onSurface,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Mức sáng',
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.6,
                                color: _isOn && _currentValue > 70
                                    ? (isDark ? Colors.black54 : Colors.white70)
                                    : theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [25, 50, 75, 100].map((preset) {
                    final isSelected = _currentValue.toInt() == preset;
                    return Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 5),
                      child: SoftBounce(
                        onTap: () {
                          HapticFeedback.lightImpact();
                          setState(() {
                            _currentValue = preset.toDouble();
                            _isOn = true;
                          });
                          widget.onValueChanged(preset.toDouble());
                        },
                        pressedScale: 0.92,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 8),
                          decoration: Soft3DDecorations.pill(
                            isDark: isDark,
                            isSelected: isSelected,
                            accentColor: accentColor,
                            radius: 100,
                          ),
                          child: Text(
                            '$preset%',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: isSelected
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                              color: isSelected
                                  ? Colors.white
                                  : theme.colorScheme.onSurface,
                            ),
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ] else ...[
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: Soft3DDecorations.card(
                    isDark: isDark,
                    radius: 20,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      Expanded(
                          child: Column(
                        children: [
                          const Text('Trạng thái',
                              style:
                                  TextStyle(fontSize: 12, color: Colors.grey)),
                          const SizedBox(height: 4),
                          Text(_isOn ? 'Đang bật' : 'Đã tắt',
                              style: const TextStyle(
                                  fontSize: 18, fontWeight: FontWeight.bold)),
                        ],
                      )),
                      const SizedBox(width: 12),
                      Expanded(
                          child: Column(
                        children: [
                          const Text('Công suất tức thời',
                              style:
                                  TextStyle(fontSize: 12, color: Colors.grey)),
                          const SizedBox(height: 4),
                          Text(
                            () {
                              final p = liveDevice.online
                                  ? liveDevice.powerWatts
                                  : null;
                              if (p != null) return '${p.toStringAsFixed(1)} W';
                              return 'Chưa có đo';
                            }(),
                            style: const TextStyle(
                                fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                        ],
                      )),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Text(liveDevice.currentText,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w600)),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: SoftBounce(
                      onTap: () {
                        HapticFeedback.lightImpact();
                        final next = !_isOn;
                        setState(() => _isOn = next);
                        widget.onToggle(next);
                      },
                      pressedScale: 0.95,
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(18),
                          gradient: _isOn
                              ? LinearGradient(
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                  colors: [
                                    accentColor,
                                    Color.alphaBlend(
                                        Colors.black.withValues(alpha: 0.16),
                                        accentColor),
                                  ],
                                )
                              : LinearGradient(
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                  colors: isDark
                                      ? const [
                                          Color(0xFF242D3D),
                                          Color(0xFF161B26)
                                        ]
                                      : const [
                                          Color(0xFFFFFFFF),
                                          Color(0xFFEEF2F6)
                                        ],
                                ),
                          border: Border.all(
                            color: _isOn
                                ? accentColor.withValues(alpha: 0.6)
                                : (isDark
                                    ? const Color(0xFF334155)
                                    : const Color(0xFFE2E8F0)),
                            width: 1.0,
                          ),
                          boxShadow: [
                            if (_isOn) ...[
                              BoxShadow(
                                color: accentColor.withValues(
                                    alpha: isDark ? 0.45 : 0.35),
                                blurRadius: 18,
                                offset: const Offset(0, 6),
                              ),
                              BoxShadow(
                                color: accentColor.withValues(alpha: 0.20),
                                blurRadius: 6,
                                offset: const Offset(0, 2),
                              ),
                            ] else ...[
                              BoxShadow(
                                color: Colors.black
                                    .withValues(alpha: isDark ? 0.35 : 0.05),
                                blurRadius: 8,
                                offset: const Offset(0, 3),
                              ),
                              if (!isDark)
                                BoxShadow(
                                  color: Colors.white.withValues(alpha: 0.9),
                                  blurRadius: 2,
                                  offset: const Offset(0, -1),
                                ),
                            ],
                          ],
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              _isOn
                                  ? Icons.power_settings_new_rounded
                                  : Icons.power_rounded,
                              size: 20,
                              color: _isOn
                                  ? theme.colorScheme.onPrimary
                                  : theme.colorScheme.onSurface,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              _isOn ? 'Tắt' : 'Bật',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: _isOn
                                    ? theme.colorScheme.onPrimary
                                    : theme.colorScheme.onSurface,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  if (widget.onMoreSettings != null) ...[
                    const SizedBox(width: 12),
                    SoftBounce(
                      onTap: widget.onMoreSettings,
                      pressedScale: 0.93,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            vertical: 14, horizontal: 18),
                        decoration: Soft3DDecorations.card(
                          isDark: isDark,
                          radius: 18,
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.settings_outlined,
                                size: 18, color: theme.colorScheme.onSurface),
                            const SizedBox(width: 6),
                            Text(
                              'Cài đặt',
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                                color: theme.colorScheme.onSurface,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
