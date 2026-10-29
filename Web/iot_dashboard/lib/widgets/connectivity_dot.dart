import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

class ConnectivityDot extends StatelessWidget {
  const ConnectivityDot({super.key, required this.online});

  final bool online;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.extension<AppColors>() ?? AppColors.light;
    final label = online ? 'Trực tuyến' : 'Ngoại tuyến';
    return Semantics(
      label: label,
      child: Tooltip(
        message: label,
        excludeFromSemantics: true,
        child: Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: online
                ? colors.online
                : theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.45),
          ),
        ),
      ),
    );
  }
}
