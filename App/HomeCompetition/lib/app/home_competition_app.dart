import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/theme/app_theme.dart';
import '../providers/smart_home_providers.dart';
import '../screens/login_screen.dart';
import '../screens/firebase_login_screen.dart';
import '../services/firebase_home_client.dart';
import '../services/gateway_client.dart';
import 'app_router.dart';

class HomeCompetitionApp extends ConsumerStatefulWidget {
  const HomeCompetitionApp({super.key});

  @override
  ConsumerState<HomeCompetitionApp> createState() => _HomeCompetitionAppState();
}

class _HomeCompetitionAppState extends ConsumerState<HomeCompetitionApp>
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
      await _client.restoreLocalSession();
    } catch (_) {
      _client.error = 'Không thể khôi phục phiên. Vui lòng đăng nhập lại.';
    }
    if (!mounted) return;
    setState(() => _ready = true);

    if (_client.authenticated) {
      _client.revalidateSession().then((_) {
        if (mounted &&
            (WidgetsBinding.instance.lifecycleState == null ||
                WidgetsBinding.instance.lifecycleState ==
                    AppLifecycleState.resumed)) {
          _startPolling();
        }
      });
    }
  }

  void _startPolling() {
    _timer?.cancel();
    if (_client.usesFirebase) return;
    final interval = _client.isSseConnected
        ? const Duration(seconds: 15)
        : const Duration(seconds: 5);
    _timer = Timer.periodic(interval, (_) => _client.refresh());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _timer?.cancel();
    if (state == AppLifecycleState.paused) {
      _client.eventStream?.pause();
    } else if (!_useMock &&
        _ready &&
        state == AppLifecycleState.resumed &&
        _client.authenticated) {
      _client.eventStream?.resume();
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
    final session = ref.watch(gatewayClientProvider
        .select((c) => (c.authenticated, c.currentUserId)));
    final authenticated = session.$1;

    ref.listen<bool>(
      gatewayClientProvider.select((c) => c.isSseConnected),
      (prev, next) {
        if (prev != next && _ready && authenticated) {
          _startPolling();
        }
      },
    );

    if (!authenticated) {
      _timer?.cancel();
    }

    if (!_ready || (!_useMock && !authenticated)) {
      return MaterialApp(
        title: 'HomeCompetition',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: themeMode,
        home: !_ready
            ? const Scaffold(body: Center(child: CircularProgressIndicator()))
            : _client is FirebaseHomeClient
                ? FirebaseLoginScreen(client: _client as FirebaseHomeClient)
                : LoginScreen(client: _client),
      );
    }

    return MaterialApp.router(
      title: 'HomeCompetition',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: themeMode,
      routerConfig: appRouter,
    );
  }
}
