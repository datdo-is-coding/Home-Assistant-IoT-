import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/theme/app_theme.dart';
import '../providers/smart_home_providers.dart';
import '../screens/login_screen.dart';
import '../services/gateway_client.dart';
import 'app_router.dart';

class SmartHomeApp extends ConsumerStatefulWidget {
  const SmartHomeApp({super.key});

  @override
  ConsumerState<SmartHomeApp> createState() => _SmartHomeAppState();
}

class _SmartHomeAppState extends ConsumerState<SmartHomeApp>
    with WidgetsBindingObserver {
  static const _useMock = bool.fromEnvironment('USE_MOCK_DATA');
  late final GatewayClient _client;
  Timer? _timer;
  bool _ready = _useMock;

  @override
  void initState() {
    super.initState();
    _client = ref.read(gatewayClientProvider);
    WidgetsBinding.instance.addObserver(this);
    if (!_useMock) _restore();
  }

  Future<void> _restore() async {
    try {
      await _client.restore();
    } catch (_) {
      _client.error = 'Không thể khôi phục phiên. Vui lòng đăng nhập lại.';
    }
    if (!mounted) return;
    setState(() => _ready = true);
    if (WidgetsBinding.instance.lifecycleState == null ||
        WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
      _startPolling();
    }
  }

  void _startPolling() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _client.refresh());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _timer?.cancel();
    if (!_useMock && _ready && state == AppLifecycleState.resumed) {
      _client.refresh();
      _startPolling();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);
    final client = ref.watch(gatewayClientProvider);

    if (!_ready || (!_useMock && !client.authenticated)) {
      return MaterialApp(
        title: 'Smart Home IoT',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: themeMode,
        home: !_ready
            ? const Scaffold(body: Center(child: CircularProgressIndicator()))
            : LoginScreen(client: client),
      );
    }

    return MaterialApp.router(
      title: 'Smart Home IoT',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: themeMode,
      routerConfig: appRouter,
    );
  }
}
