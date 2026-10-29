import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/smart_home_providers.dart';
import '../services/app_update_service.dart';

String _updateStatus(AppUpdateService update) => switch (update.phase) {
      AppUpdatePhase.idle => 'Kiểm tra phiên bản mới',
      AppUpdatePhase.checking => 'Đang kiểm tra bản mới…',
      AppUpdatePhase.current => 'Chưa có bản cập nhật mới',
      AppUpdatePhase.available => 'Có bản ${update.release!.version}',
      AppUpdatePhase.downloading =>
        'Đang tải ${((update.progress ?? 0) * 100).round()}%',
      AppUpdatePhase.ready => 'Bản ${update.release!.version} đã sẵn sàng',
      AppUpdatePhase.permissionRequired =>
        'Cho phép HomeCompetition cài ứng dụng, rồi bấm Cài đặt.',
      AppUpdatePhase.installing =>
        'Đang chờ xác nhận trong trình cài đặt Android',
      AppUpdatePhase.failed => update.error,
    };

class AppUpdateTile extends ConsumerWidget {
  const AppUpdateTile({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final update = ref.watch(appUpdateProvider);
    return ListTile(
      key: const Key('app_update_tile'),
      leading: const Icon(Icons.system_update_rounded),
      title: const Text('Cập nhật ứng dụng',
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      subtitle: Text(_updateStatus(update),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 12)),
      trailing: update.busy
          ? SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(
                  strokeWidth: 2,
                  value: update.phase == AppUpdatePhase.downloading
                      ? update.progress
                      : null))
          : const Icon(Icons.chevron_right_rounded),
      onTap: () {
        update.check();
        showModalBottomSheet<void>(
          context: context,
          useRootNavigator: true,
          showDragHandle: true,
          isScrollControlled: true,
          builder: (_) => const _AppUpdateSheet(),
        );
      },
    );
  }
}

class _AppUpdateSheet extends ConsumerWidget {
  const _AppUpdateSheet();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final update = ref.watch(appUpdateProvider);
    return SafeArea(
        child: Padding(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
      child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('HomeCompetition',
                style: Theme.of(context).textTheme.titleLarge),
            if (update.installedVersion.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text('Đang dùng ${update.installedVersion}'),
            ],
            const SizedBox(height: 18),
            Text(_updateStatus(update)),
            if (update.phase == AppUpdatePhase.downloading) ...[
              const SizedBox(height: 12),
              LinearProgressIndicator(value: update.progress),
            ],
            const SizedBox(height: 18),
            const Text('Bản cập nhật giữ dữ liệu và tài khoản đang đăng nhập.',
                style: TextStyle(fontSize: 12)),
            const SizedBox(height: 16),
            Row(children: [
              TextButton(
                  onPressed:
                      update.busy ? null : () => update.check(force: true),
                  child: const Text('Kiểm tra lại')),
              const Spacer(),
              if (update.release != null)
                FilledButton(
                    onPressed: update.busy
                        ? null
                        : update.canInstall
                            ? update.install
                            : update.download,
                    child: Text(update.canInstall ? 'Cài đặt' : 'Tải bản mới')),
            ]),
          ]),
    ));
  }
}
