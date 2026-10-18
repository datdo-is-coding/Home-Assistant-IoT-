import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../features/home/home_screen.dart';
import '../features/devices/devices_screen.dart';
import '../features/devices/device_detail_screen.dart';
import '../features/rooms/room_detail_screen.dart';
import '../features/actionbox/action_box_detail_screen.dart';
import '../features/actionbox/add_device_flow.dart';
import '../features/automation/automation_screen.dart';
import '../features/voice/voice_screen.dart';
import '../features/settings/settings_screen.dart';
import '../widgets/smart_home_scaffold.dart';

final GlobalKey<NavigatorState> _rootNavigatorKey = GlobalKey<NavigatorState>();

final appRouter = GoRouter(
  navigatorKey: _rootNavigatorKey,
  initialLocation: '/home',
  routes: [

    GoRoute(
      path: '/actionbox/add-device',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (context, state) => const AddDeviceFlowScreen(),
    ),
    GoRoute(
      path: '/voice',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (context, state) => const VoiceScreen(),
    ),
    GoRoute(
      path: '/devices/:deviceId',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (context, state) {
        final deviceId = state.pathParameters['deviceId'] ?? '';
        return FeatureDeviceDetailScreen(deviceId: deviceId);
      },
    ),
    GoRoute(
      path: '/rooms/:roomId',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (context, state) {
        final roomId = state.pathParameters['roomId'] ?? '';
        return RoomDetailScreen(roomId: roomId);
      },
    ),
    GoRoute(
      path: '/actionbox/:actionBoxId',
      parentNavigatorKey: _rootNavigatorKey,
      builder: (context, state) {
        final actionBoxId = state.pathParameters['actionBoxId'] ?? '';
        return FeatureActionBoxDetailScreen(actionBoxId: actionBoxId);
      },
    ),

    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) {
        return SmartHomeScaffold(navigationShell: navigationShell);
      },
      branches: [

        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/home',
              builder: (context, state) => const FeatureHomeScreen(),
            ),
          ],
        ),

        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/devices',
              builder: (context, state) => const FeatureDevicesScreen(),
            ),
          ],
        ),

        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/automation',
              builder: (context, state) => const AutomationScreen(),
            ),
          ],
        ),

        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/settings',
              builder: (context, state) => const SettingsScreen(),
            ),
          ],
        ),
      ],
    ),
  ],
);
