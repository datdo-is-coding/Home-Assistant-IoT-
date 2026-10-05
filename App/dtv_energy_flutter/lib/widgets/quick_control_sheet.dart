import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../core/theme/app_theme.dart';
import '../models/device.dart';

class QuickControlSheet extends StatefulWidget {
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
  State<QuickControlSheet> createState() => _QuickControlSheetState();
}

class _QuickControlSheetState extends State<QuickControlSheet> {
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
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final colors = theme.extension<AppColors>() ?? (isDark ? AppColors.dark : AppColors.light);

    final Color accentColor = switch (widget.device.type) {
      DeviceType.light => colors.lightAccent,
      DeviceType.fan => colors.fanAccent,
      DeviceType.socket => colors.socketAccent,
      DeviceType.airConditioner => colors.climateAccent,
      _ => colors.socketAccent,
    };

    return Container(
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF161B26) : Colors.white,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
        border: Border(top: BorderSide(color: colors.cardBorder, width: 1)),
      ),
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Drag handle
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF334155) : const Color(0xFFCBD5E1),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),

          // Header: Name, Room, Close Button
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: _isOn && widget.device.online
                      ? accentColor.withValues(alpha: isDark ? 0.24 : 0.16)
                      : (isDark ? const Color(0xFF1F2532) : const Color(0xFFF1F5F9)),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  widget.device.iconData,
                  color: _isOn && widget.device.online ? accentColor : colors.cardBorder,
                  size: 22,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.device.name,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${widget.device.roomId} · ${_isOn ? "Đang bật" : "Đã tắt"}',
                      style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              IconButton(
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close_rounded),
                style: IconButton.styleFrom(
                  backgroundColor: isDark ? const Color(0xFF1F2532) : const Color(0xFFF1F5F9),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          // Hero Vertical Pill Slider only for dimmable devices
          if (widget.device.metadata['can_dim'] == true) ...[
            Container(
              height: 200,
              width: 100,
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF12151D) : const Color(0xFFF1F5F9),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: colors.cardBorder),
              ),
              clipBehavior: Clip.antiAlias,
              child: Stack(
                alignment: Alignment.bottomCenter,
                children: [
                  // Animated fill representing slider level
                  FractionallySizedBox(
                    heightFactor: _isOn ? (_currentValue / 100.0).clamp(0.05, 1.0) : 0.0,
                    widthFactor: 1.0,
                    child: Container(
                      decoration: BoxDecoration(
                        color: accentColor.withValues(alpha: isDark ? 0.85 : 0.90),
                        borderRadius: const BorderRadius.vertical(bottom: Radius.circular(24)),
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

            // Quick Preset Buttons (25%, 50%, 75%, 100%)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [25, 50, 75, 100].map((preset) {
                final isSelected = _currentValue.toInt() == preset;
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: ActionChip(
                    label: Text('$preset%'),
                    labelStyle: TextStyle(
                      fontSize: 12,
                      fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      color: isSelected ? Colors.white : theme.colorScheme.onSurface,
                    ),
                    backgroundColor: isSelected
                        ? accentColor
                        : (isDark ? const Color(0xFF1E2532) : const Color(0xFFF1F5F9)),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    side: BorderSide.none,
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      setState(() {
                        _currentValue = preset.toDouble();
                        _isOn = true;
                      });
                      widget.onValueChanged(preset.toDouble());
                    },
                  ),
                );
              }).toList(),
            ),
          ] else ...[
            // For Smart Socket or AC: Show telemetry & power button
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E2532) : const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  Column(
                    children: [
                      const Text('Trạng thái', style: TextStyle(fontSize: 12, color: Colors.grey)),
                      const SizedBox(height: 4),
                      Text(_isOn ? 'Đang bật' : 'Đã tắt', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    ],
                  ),
                  Column(
                    children: [
                      const Text('Công suất tức thời', style: TextStyle(fontSize: 12, color: Colors.grey)),
                      const SizedBox(height: 4),
                      Text('${widget.device.value.toStringAsFixed(1)} W', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    ],
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 24),

          // Secondary Actions / Settings Row
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: Icon(_isOn ? Icons.power_settings_new_rounded : Icons.power_rounded),
                  label: Text(_isOn ? 'Tắt thiết bị' : 'Bật thiết bị'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  ),
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    final next = !_isOn;
                    setState(() => _isOn = next);
                    widget.onToggle(next);
                  },
                ),
              ),
              if (widget.onMoreSettings != null) ...[
                const SizedBox(width: 12),
                FilledButton.tonalIcon(
                  icon: const Icon(Icons.settings_outlined, size: 18),
                  label: const Text('Cài đặt'),
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  ),
                  onPressed: widget.onMoreSettings,
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
