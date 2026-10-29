import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'flagship_backdrop.dart';
import 'progressive_blur.dart';

class SmartHomeScaffold extends StatelessWidget {
  final StatefulNavigationShell navigationShell;

  const SmartHomeScaffold({super.key, required this.navigationShell});

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 720) {
            return Scaffold(
                body: Row(children: [
              NavigationRail(
                selectedIconTheme: IconThemeData(
                    color: Theme.of(context).colorScheme.onSurface),
                unselectedIconTheme: IconThemeData(
                    color: Theme.of(context).colorScheme.onSurfaceVariant),
                selectedIndex: navigationShell.currentIndex,
                onDestinationSelected: _onTap,
                labelType: NavigationRailLabelType.all,
                destinations: const [
                  NavigationRailDestination(
                      icon: Icon(Icons.home_outlined),
                      selectedIcon: Icon(Icons.home_rounded),
                      label: Text('Nhà')),
                  NavigationRailDestination(
                      icon: Icon(Icons.devices_other_outlined),
                      selectedIcon: Icon(Icons.devices_other_rounded),
                      label: Text('Thiết bị')),
                  NavigationRailDestination(
                      icon: Icon(Icons.bar_chart_outlined),
                      selectedIcon: Icon(Icons.bar_chart_rounded),
                      label: Text('Điện năng')),
                  NavigationRailDestination(
                      icon: Icon(Icons.bolt_outlined),
                      selectedIcon: Icon(Icons.bolt_rounded),
                      label: Text('Kịch bản')),
                  NavigationRailDestination(
                      icon: Icon(Icons.settings_outlined),
                      selectedIcon: Icon(Icons.settings_rounded),
                      label: Text('Cài đặt')),
                ],
              ),
              const VerticalDivider(thickness: 1, width: 1),
              Expanded(child: FlagshipBackdrop(child: navigationShell)),
            ]));
          }
          return Scaffold(
            extendBody: true,
            body: FlagshipBackdrop(child: navigationShell),
            bottomNavigationBar: SafeArea(
              top: false,
              minimum: const EdgeInsets.fromLTRB(14, 8, 14, 12),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(30),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF0B211B).withValues(alpha: 0.12),
                      blurRadius: 28,
                      offset: const Offset(0, 10),
                      spreadRadius: -8,
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(30),
                  child: Stack(children: [
                    Positioned.fill(
                      child: ProgressiveBlur(
                        tint: Theme.of(context).colorScheme.surface,
                      ),
                    ),
                    Positioned.fill(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(30),
                          border: Border.all(
                            color: Colors.white.withValues(
                              alpha: Theme.of(context).brightness ==
                                      Brightness.dark
                                  ? 0.14
                                  : 0.8,
                            ),
                          ),
                        ),
                      ),
                    ),
                    MediaQuery.removePadding(
                      context: context,
                      removeTop: true,
                      removeBottom: true,
                      child: NavigationBar(
                        backgroundColor: Colors.transparent,
                        height: 72,
                        elevation: 0,
                        selectedIndex: navigationShell.currentIndex,
                        onDestinationSelected: _onTap,
                        destinations: const [
                          NavigationDestination(
                              icon: Icon(Icons.home_outlined),
                              selectedIcon: Icon(Icons.home_rounded),
                              label: 'Nhà'),
                          NavigationDestination(
                              icon: Icon(Icons.devices_other_outlined),
                              selectedIcon: Icon(Icons.devices_other_rounded),
                              label: 'Thiết bị'),
                          NavigationDestination(
                              icon: Icon(Icons.bar_chart_outlined),
                              selectedIcon: Icon(Icons.bar_chart_rounded),
                              label: 'Điện năng'),
                          NavigationDestination(
                              icon: Icon(Icons.bolt_outlined),
                              selectedIcon: Icon(Icons.bolt_rounded),
                              label: 'Kịch bản'),
                          NavigationDestination(
                              icon: Icon(Icons.settings_outlined),
                              selectedIcon: Icon(Icons.settings_rounded),
                              label: 'Cài đặt'),
                        ],
                      ),
                    ),
                  ]),
                ),
              ),
            ),
          );
        },
      );

  void _onTap(int index) => navigationShell.goBranch(index,
      initialLocation: index == navigationShell.currentIndex);
}
