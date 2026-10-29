import '../widgets/flagship_backdrop.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/firebase_auth_service.dart';
import '../services/firebase_home_client.dart';

class FirebaseLoginScreen extends StatefulWidget {
  const FirebaseLoginScreen({super.key, required this.client});
  final FirebaseHomeClient client;
  @override
  State<FirebaseLoginScreen> createState() => _FirebaseLoginScreenState();
}

class _FirebaseLoginScreenState extends State<FirebaseLoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _form = GlobalKey<FormState>();
  bool _register = false, _busy = false, _obscure = true;
  String? _message;

  Future<void> _submit({bool google = false, bool reset = false}) async {
    if (!google && !reset && !_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      if (google) {
        await AuthService().signInWithGoogle();
      } else if (reset) {
        await widget.client.auth
            .sendPasswordResetEmail(email: _email.text.trim());
        if (mounted)
          setState(() => _message =
              'Đã gửi yêu cầu đặt lại mật khẩu. Kiểm tra email của bạn.');
      } else if (_register) {
        await widget.client.auth.createUserWithEmailAndPassword(
            email: _email.text.trim(), password: _password.text);
      } else {
        await widget.client
            .login(url: '', username: _email.text, password: _password.text);
      }
    } on FirebaseAuthException catch (e) {
      debugPrint(
          '[AUTH] provider=${google ? "google" : "password"} code=${e.code}');
      if (mounted)
        setState(() => _message = switch (e.code) {
              'invalid-credential' ||
              'wrong-password' ||
              'user-not-found' =>
                'Email hoặc mật khẩu không đúng.',
              'email-already-in-use' => 'Email đã có tài khoản.',
              'weak-password' => 'Mật khẩu cần ít nhất 6 ký tự.',
              'invalid-email' => 'Email không hợp lệ.',
              'too-many-requests' => 'Vui lòng chờ rồi thử lại.',
              'operation-not-allowed' =>
                'Phương thức ${google ? "Google" : "Email/Password"} chưa được bật trên Firebase (operation-not-allowed).',
              _ => 'Không đăng nhập được. Kiểm tra kết nối và thử lại.',
            });
    } on PlatformException catch (e) {
      final apiCode = RegExp(r'ApiException:\s*(\d+)')
          .firstMatch(e.message ?? '')
          ?.group(1);
      debugPrint(
          '[AUTH] provider=${google ? "google" : "password"} platform=${e.code} api=${apiCode ?? "unknown"}');
      if (mounted)
        setState(() => _message = apiCode == '10'
            ? 'Google từ chối cấu hình ứng dụng (mã 10). Cần kiểm tra SHA-1 của bản cài trong Firebase.'
            : 'Đăng nhập thất bại (${e.code}${apiCode == null ? "" : "/$apiCode"}).');
    } catch (e) {
      debugPrint('[AUTH] unexpected=${e.runtimeType}');
      if (mounted)
        setState(() => _message =
            'Không đăng nhập được. Kiểm tra cấu hình Firebase và thử lại.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FlagshipBackdrop(
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: SafeArea(
              child: Center(
                  child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Form(
                  key: _form,
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Icon(Icons.home_rounded, size: 64),
                        const SizedBox(height: 16),
                        Text('HomeCompetition',
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.headlineMedium),
                        const SizedBox(height: 8),
                        Text(
                            _register
                                ? 'Tạo tài khoản mới'
                                : 'Đăng nhập để xem ngôi nhà của bạn',
                            textAlign: TextAlign.center),
                        const SizedBox(height: 24),
                        TextFormField(
                            controller: _email,
                            enabled: !_busy,
                            keyboardType: TextInputType.emailAddress,
                            autofillHints: const [AutofillHints.email],
                            decoration:
                                const InputDecoration(labelText: 'Email'),
                            validator: (v) =>
                                v != null && v.trim().contains('@')
                                    ? null
                                    : 'Nhập email hợp lệ'),
                        const SizedBox(height: 16),
                        TextFormField(
                            controller: _password,
                            enabled: !_busy,
                            obscureText: _obscure,
                            autofillHints: [
                              _register
                                  ? AutofillHints.newPassword
                                  : AutofillHints.password
                            ],
                            decoration: InputDecoration(
                                labelText: 'Mật khẩu',
                                suffixIcon: IconButton(
                                    tooltip: _obscure
                                        ? 'Hiện mật khẩu'
                                        : 'Ẩn mật khẩu',
                                    onPressed: () =>
                                        setState(() => _obscure = !_obscure),
                                    icon: Icon(_obscure
                                        ? Icons.visibility
                                        : Icons.visibility_off))),
                            validator: (v) => v != null && v.length >= 6
                                ? null
                                : 'Nhập mật khẩu ít nhất 6 ký tự'),
                        const SizedBox(height: 16),
                        if (_message != null)
                          Padding(
                              padding: const EdgeInsets.only(bottom: 16),
                              child: Text(_message!, semanticsLabel: _message)),
                        FilledButton(
                            onPressed: _busy ? null : () => _submit(),
                            child: Text(_busy
                                ? 'Đang xử lý…'
                                : _register
                                    ? 'Đăng ký'
                                    : 'Đăng nhập')),
                        const SizedBox(height: 12),
                        OutlinedButton(
                            onPressed:
                                _busy ? null : () => _submit(google: true),
                            child: const Text('Tiếp tục với Google')),
                        const SizedBox(height: 12),
                        FilledButton.tonalIcon(
                            onPressed: _busy ? null : () => widget.client.enterGuestMode(),
                            icon: const Icon(Icons.rocket_launch_rounded, size: 18),
                            label: const Text('Truy cập nhanh (Chế độ Khách / Xem thử ngay)')),
                        TextButton(
                            onPressed:
                                _busy ? null : () => _submit(reset: true),
                            child: const Text('Quên mật khẩu')),
                        TextButton(
                            onPressed: _busy
                                ? null
                                : () => setState(() {
                                      _register = !_register;
                                      _message = null;
                                    }),
                            child: Text(_register
                                ? 'Đã có tài khoản? Đăng nhập'
                                : 'Chưa có tài khoản? Đăng ký')),
                      ]),
                )),
          ))),
        ),
      );
}
