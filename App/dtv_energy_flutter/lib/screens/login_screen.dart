import 'package:flutter/material.dart';
import '../main.dart' show gateway;
import '../services/gateway_client.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.client});
  final GatewayClient? client;
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _url = TextEditingController();
  final _username = TextEditingController();
  final _secret = TextEditingController();
  bool _keyMode = false, _obscure = true, _busy = false;
  String? _error;
  GatewayClient get service => widget.client ?? gateway;

  @override
  void initState() {
    super.initState();
    _url.text = service.serverUrl;
  }

  @override
  void dispose() {
    _url.dispose();
    _username.dispose();
    _secret.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (!_form.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_keyMode) {
        await service.loginWithKey(url: _url.text, key: _secret.text);
      } else {
        await service.login(
            url: _url.text, username: _username.text, password: _secret.text);
      }
    } catch (e) {
      if (mounted)
        setState(() => _error = e is GatewayException
            ? e.message
            : 'Không thể lưu phiên đăng nhập. Vui lòng thử lại.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
          child: Center(
              child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 430),
          child: AutofillGroup(
              child: Form(
                  key: _form,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                                color: colors.primary,
                                borderRadius: BorderRadius.circular(12)),
                            child: const Icon(Icons.home_rounded,
                                color: Colors.white, size: 30)),
                        const SizedBox(width: 12),
                        const Text('SIC Home',
                            style: TextStyle(
                                fontSize: 24, fontWeight: FontWeight.w700)),
                      ]),
                      const SizedBox(height: 36),
                      Text('Ngôi nhà của bạn',
                          style: Theme.of(context).textTheme.headlineMedium),
                      const SizedBox(height: 8),
                      Text('Kết nối Gateway',
                          style: TextStyle(
                              color: colors.onSurfaceVariant, fontSize: 16)),
                      const SizedBox(height: 28),
                      TextFormField(
                          controller: _url,
                          enabled: !_busy,
                          keyboardType: TextInputType.url,
                          autocorrect: false,
                          textInputAction: TextInputAction.next,
                          decoration: const InputDecoration(
                              labelText: 'Địa chỉ Gateway',
                              hintText: 'http://192.168.1.10:8000',
                              prefixIcon: Icon(Icons.router_outlined)),
                          validator: (value) {
                            try {
                              GatewayClient.normalizeServerUrl(value ?? '');
                              return null;
                            } catch (e) {
                              return e.toString();
                            }
                          }),
                      const SizedBox(height: 20),
                      SizedBox(
                          width: double.infinity,
                          child: SegmentedButton<bool>(
                            segments: const [
                              ButtonSegment(
                                  value: false,
                                  label: Text('Tài khoản'),
                                  icon: Icon(Icons.person_outline)),
                              ButtonSegment(
                                  value: true,
                                  label: Text('API key'),
                                  icon: Icon(Icons.key_outlined)),
                            ],
                            selected: {_keyMode},
                            onSelectionChanged: _busy
                                ? null
                                : (value) => setState(() {
                                      _keyMode = value.first;
                                      _secret.clear();
                                      _error = null;
                                    }),
                          )),
                      const SizedBox(height: 20),
                      if (!_keyMode) ...[
                        TextFormField(
                            controller: _username,
                            enabled: !_busy,
                            autofillHints: const [AutofillHints.username],
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                                labelText: 'Tên đăng nhập',
                                prefixIcon: Icon(Icons.person_outline)),
                            validator: (value) =>
                                value == null || value.trim().isEmpty
                                    ? 'Nhập tên đăng nhập'
                                    : null),
                        const SizedBox(height: 16),
                      ],
                      TextFormField(
                          controller: _secret,
                          enabled: !_busy,
                          obscureText: _obscure,
                          autocorrect: false,
                          enableSuggestions: false,
                          autofillHints:
                              _keyMode ? null : const [AutofillHints.password],
                          onFieldSubmitted: (_) => _busy ? null : _connect(),
                          decoration: InputDecoration(
                              labelText: _keyMode ? 'API key' : 'Mật khẩu',
                              prefixIcon: Icon(_keyMode
                                  ? Icons.key_outlined
                                  : Icons.lock_outline),
                              suffixIcon: IconButton(
                                  tooltip: _obscure
                                      ? 'Hiện mật khẩu'
                                      : 'Ẩn mật khẩu',
                                  icon: Icon(_obscure
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined),
                                  onPressed: () =>
                                      setState(() => _obscure = !_obscure))),
                          validator: (value) => value == null || value.isEmpty
                              ? (_keyMode ? 'Nhập API key' : 'Nhập mật khẩu')
                              : null),
                      if (_error != null)
                        Padding(
                            padding: const EdgeInsets.only(top: 16),
                            child: Semantics(
                                liveRegion: true,
                                child: Text(_error!,
                                    style: TextStyle(color: colors.error)))),
                      const SizedBox(height: 24),
                      SizedBox(
                          width: double.infinity,
                          child: FilledButton(
                              onPressed: _busy ? null : _connect,
                              child: _busy
                                  ? const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 2))
                                  : const Text('Kết nối'))),
                      const SizedBox(height: 24),
                      Row(children: [
                        Icon(Icons.wifi_rounded,
                            size: 18, color: colors.onSurfaceVariant),
                        const SizedBox(width: 8),
                        Expanded(
                            child: Text('Gateway nội bộ',
                                style:
                                    TextStyle(color: colors.onSurfaceVariant))),
                        Text('v1.1.0',
                            style: TextStyle(
                                color: colors.onSurfaceVariant, fontSize: 12)),
                      ]),
                    ],
                  ))),
        ),
      ))),
    );
  }
}
