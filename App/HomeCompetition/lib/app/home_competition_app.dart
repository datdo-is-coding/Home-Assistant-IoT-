import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/theme/app_theme.dart';
import '../providers/smart_home_providers.dart';
import '../screens/login_screen.dart';
import '../screens/firebase_login_screen.dart';
import '../services/firebase_home_client.dart';
import '../services/gateway_client.dart';
import '../services/app_update_service.dart';
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
  late final AppUpdateService _updates;
  final _messenger = GlobalKey<ScaffoldMessengerState>();
  int? _announcedUpdate;
  Timer? _timer;
  bool _ready = _useMock;

  @override
  void initState() {
    super.initState();
    _client = ref.read(gatewayClientProvider);
    _updates = ref.read(appUpdateProvider)..addListener(_onUpdate);
    WidgetsBinding.instance.addObserver(this);
    if (!_useMock) _restore();
  }

  void _onUpdate() {
    if (!mounted ||
        !_ready ||
        !_client.authenticated ||
        _updates.phase != AppUpdatePhase.ready ||
        _updates.release?.code == _announcedUpdate ||
        WidgetsBinding.instance.lifecycleState == AppLifecycleState.paused)
      return;
    final messenger = _messenger.currentState;
    if (messenger == null) return;
    _announcedUpdate = _updates.release!.code;
    messenger.showSnackBar(SnackBar(
      content: Text('Bản ${_updates.release!.version} đã sẵn sàng'),
      action: SnackBarAction(label: 'Cài đặt', onPressed: _updates.install),
    ));
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
      if (_client.usesFirebase) unawaited(_updates.check());
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
      if (_client.usesFirebase) {
        _updates.resume();
        unawaited(_updates.check());
      }
      _startPolling();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _updates.removeListener(_onUpdate);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);
    final session = ref.watch(gatewayClientProvider
        .select((c) => (c.authenticated, c.currentUserId)));
    final authenticated = session.$1;

    ref.listen<bool>(gatewayClientProvider.select((c) => c.authenticated),
        (previous, next) {
      if (next && _ready && _client.usesFirebase) unawaited(_updates.check());
    });

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
        scaffoldMessengerKey: _messenger,
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
      scaffoldMessengerKey: _messenger,
      title: 'HomeCompetition',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: themeMode,
      routerConfig: appRouter,
    );
  }
}
