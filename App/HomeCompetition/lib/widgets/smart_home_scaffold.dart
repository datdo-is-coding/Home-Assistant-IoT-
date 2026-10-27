import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/smart_home_providers.dart';
import 'package:go_router/go_router.dart';

class SmartHomeScaffold extends ConsumerWidget {
  final StatefulNavigationShell navigationShell;

  const SmartHomeScaffold({
    super.key,
    required this.navigationShell,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final client = ref.read(gatewayClientProvider);
    ref.watch(gatewayClientProvider
        .select((c) => (c.usesFirebase, c.connected, c.error)));
    return Column(children: [
      if (client.usesFirebase)
        SafeArea(
            bottom: false,
            child: Material(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                child: Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Row(children: [
                      Expanded(
                          child: Text(
                              client.error ??
                                  (client.connected
                                      ? 'Firebase · trạng thái lưu trên cloud, chưa xác nhận tải'
                                      : 'Đang chờ kết nối và dữ liệu Firebase'),
                              style: Theme.of(context).textTheme.bodySmall)),
                      if (client.error != null)
                        TextButton(
                            onPressed: client.refresh,
                            child: const Text('Thử lại')),
                      IconButton(
                          tooltip: 'Điện năng & Cảnh báo',
                          onPressed: () => context.go('/energy'),
                          icon: const Icon(Icons.analytics_outlined)),
                    ])))),
      Expanded(child: LayoutBuilder(
        builder: (context, constraints) {
          final isWideScreen = constraints.maxWidth >= 720;

          if (isWideScreen) {
            return Scaffold(
              body: Row(
                children: [
                  NavigationRail(
                    selectedIndex: navigationShell.currentIndex,
                    onDestinationSelected: (index) => _onTap(context, index),
                    labelType: NavigationRailLabelType.all,
                    leading: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Icon(
                        Icons.home_rounded,
                        size: 28,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                    destinations: const [
                      NavigationRailDestination(
                        icon: Icon(Icons.home_outlined),
                        selectedIcon: Icon(Icons.home_rounded),
                        label: Text('Nhà'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.devices_other_outlined),
                        selectedIcon: Icon(Icons.devices_other_rounded),
                        label: Text('Thiết bị'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.bar_chart_outlined),
                        selectedIcon: Icon(Icons.bar_chart_rounded),
                        label: Text('Điện năng'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.bolt_outlined),
                        selectedIcon: Icon(Icons.bolt_rounded),
                        label: Text('Kịch bản'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Icons.settings_outlined),
                        selectedIcon: Icon(Icons.settings_rounded),
                        label: Text('Cài đặt'),
                      ),
                    ],
                  ),
                  const VerticalDivider(thickness: 1, width: 1),
                  Expanded(child: navigationShell),
                ],
              ),
            );
          }

          return Scaffold(
            body: navigationShell,
            bottomNavigationBar: NavigationBar(
              selectedIndex: navigationShell.currentIndex,
              onDestinationSelected: (index) => _onTap(context, index),
              destinations: const [
                NavigationDestination(
                  icon: Icon(Icons.home_outlined),
                  selectedIcon: Icon(Icons.home_rounded),
                  label: 'Nhà',
                ),
                NavigationDestination(
                  icon: Icon(Icons.devices_other_outlined),
                  selectedIcon: Icon(Icons.devices_other_rounded),
                  label: 'Thiết bị',
                ),
                NavigationDestination(
                  icon: Icon(Icons.bar_chart_outlined),
                  selectedIcon: Icon(Icons.bar_chart_rounded),
                  label: 'Điện năng',
                ),
                NavigationDestination(
                  icon: Icon(Icons.bolt_outlined),
                  selectedIcon: Icon(Icons.bolt_rounded),
                  label: 'Kịch bản',
                ),
                NavigationDestination(
                  icon: Icon(Icons.settings_outlined),
                  selectedIcon: Icon(Icons.settings_rounded),
                  label: 'Cài đặt',
                ),
              ],
            ),
          );
        },
      )),
    ]);
  }

  void _onTap(BuildContext context, int index) {
    navigationShell.goBranch(
      index,
      initialLocation: index == navigationShell.currentIndex,
    );
  }
}
