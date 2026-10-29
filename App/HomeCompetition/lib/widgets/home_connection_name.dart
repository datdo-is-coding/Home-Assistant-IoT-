import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/theme/app_theme.dart';
import '../providers/smart_home_providers.dart';

class HomeConnectionName extends ConsumerWidget {
  const HomeConnectionName({super.key, this.style});

  final TextStyle? style;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final name = ref.watch(homeNameProvider);
    final state = ref.watch(gatewayClientProvider
        .select((c) => (c.connected, c.error, c.usesFirebase)));
    final theme = Theme.of(context);
    final colors = theme.extension<AppColors>() ?? AppColors.light;
    final online = state.$1 && state.$2 == null;
    final service = state.$3 ? 'Firebase' : 'Gateway';
    final status = online ? 'Đã kết nối $service' : 'Chưa kết nối $service';

    void showConnection() {
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Kết nối'),
          content: Text(state.$2 ?? status),
          actions: [
            if (!online)
              TextButton(
                onPressed: () async {
                  final client = ref.read(gatewayClientProvider);
                  Navigator.pop(dialogContext);
                  try {
                    await client.refresh();
                  } catch (e) {
                    if (context.mounted) {
                      ScaffoldMessenger.of(context)
                          .showSnackBar(SnackBar(content: Text('$e')));
                    }
                  }
                },
                child: const Text('Thử lại'),
              ),
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Đóng'),
            ),
          ],
        ),
      );
    }

    return Semantics(
      button: true,
      label: '$name, $status',
      onTap: showConnection,
      child: ExcludeSemantics(
        child: Tooltip(
          message: status,
          child: InkWell(
            onTap: showConnection,
            borderRadius: BorderRadius.circular(8),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 48),
              child: Align(
                alignment: Alignment.centerLeft,
                widthFactor: 1,
                heightFactor: 1,
                child: Text(
                  name,
                  key: const ValueKey('home-connection-name'),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: (style ?? theme.textTheme.bodySmall)?.copyWith(
                    color: online ? colors.online : colors.warning,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
