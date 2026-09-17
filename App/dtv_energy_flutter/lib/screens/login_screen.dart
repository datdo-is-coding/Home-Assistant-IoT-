import 'package:flutter/material.dart';
import '../services/energy_service.dart';
import '../services/theme_service.dart';
import '../main.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _serverController = TextEditingController();
  final _userController = TextEditingController();
  final _passController = TextEditingController();
  final _apiKeyController = TextEditingController();

  bool _isApiKeyMode = false;
  bool _rememberMe = true;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    final service = EnergyService();
    _serverController.text = service.serverUrl;
    _userController.text = service.username.isNotEmpty ? service.username : 'admin';
    _apiKeyController.text = service.apiKey;
    if (service.apiKey.isNotEmpty && service.username.isEmpty) {
      _isApiKeyMode = true;
    }
  }

  @override
  void dispose() {
    _serverController.dispose();
    _userController.dispose();
    _passController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }

  Future<void> _handleLogin() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final service = EnergyService();
    final serverUrl = _serverController.text.trim();
    if (serverUrl.isNotEmpty) {
      await service.setServerUrl(serverUrl);
    }

    if (_isApiKeyMode) {
      final key = _apiKeyController.text.trim();
      if (key.isEmpty) {
        setState(() {
          _isLoading = false;
          _errorMessage = 'Vui lòng nhập API Key';
        });
        return;
      }
      await service.saveApiKey(key);
      final ok = await service.checkSession();
      if (ok) {
        if (!mounted) return;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const MainTabNavigator()),
        );
      } else {
        setState(() {
          _isLoading = false;
          _errorMessage = 'API Key không hợp lệ hoặc không thể kết nối tới Gateway';
        });
      }
    } else {
      final u = _userController.text.trim();
      final p = _passController.text;
      if (u.isEmpty || p.isEmpty) {
        setState(() {
          _isLoading = false;
          _errorMessage = 'Vui lòng nhập tên đăng nhập và mật khẩu';
        });
        return;
      }

      final res = await service.login(u, p);
      if (res['success'] == true) {
        if (!mounted) return;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const MainTabNavigator()),
        );
      } else {
        setState(() {
          _isLoading = false;
          _errorMessage = res['error'] ?? 'Đăng nhập thất bại';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = ThemeService().currentTheme;

    return Scaffold(
      backgroundColor: const Color(0xFF07090E),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Brand Logo & Glow
                Container(
                  width: 72,
                  height: 72,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF00F2FE), Color(0xFF8B5CF6)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF00F2FE).withOpacity(0.35),
                        blurRadius: 28,
                        spreadRadius: 2,
                      ),
                    ],
                  ),
                  child: const Center(
                    child: Icon(Icons.hub_rounded, size: 38, color: Colors.white),
                  ),
                ),
                const SizedBox(height: 18),

                const Text(
                  'AETHERIA OS',
                  style: TextStyle(
                    fontFamily: 'Outfit',
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Spatial Smart Home Intelligence',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: Color(0xFF94A3B8),
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: 32),

                // Glassmorphism Card
                Container(
                  padding: const EdgeInsets.all(22),
                  decoration: BoxDecoration(
                    color: const Color(0xFF0E131F).withOpacity(0.85),
                    borderRadius: BorderRadius.circular(22),
                    border: Border.all(
                      color: Colors.white.withOpacity(0.09),
                      width: 1.2,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.4),
                        blurRadius: 24,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Mode Selector (Account vs API Key)
                      Container(
                        padding: const EdgeInsets.all(4),
                        decoration: BoxDecoration(
                          color: Colors.black.withOpacity(0.3),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.white.withOpacity(0.06)),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: GestureDetector(
                                onTap: () => setState(() => _isApiKeyMode = false),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(vertical: 8),
                                  decoration: BoxDecoration(
                                    color: !_isApiKeyMode ? const Color(0xFF00F2FE).withOpacity(0.18) : Colors.transparent,
                                    borderRadius: BorderRadius.circular(9),
                                    border: !_isApiKeyMode ? Border.all(color: const Color(0xFF00F2FE).withOpacity(0.4)) : null,
                                  ),
                                  child: Text(
                                    'Tài Khoản',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: !_isApiKeyMode ? Colors.white : const Color(0xFF94A3B8),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                            Expanded(
                              child: GestureDetector(
                                onTap: () => setState(() => _isApiKeyMode = true),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(vertical: 8),
                                  decoration: BoxDecoration(
                                    color: _isApiKeyMode ? const Color(0xFF8B5CF6).withOpacity(0.18) : Colors.transparent,
                                    borderRadius: BorderRadius.circular(9),
                                    border: _isApiKeyMode ? Border.all(color: const Color(0xFF8B5CF6).withOpacity(0.4)) : null,
                                  ),
                                  child: Text(
                                    'API Key',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: _isApiKeyMode ? Colors.white : const Color(0xFF94A3B8),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 18),

                      // Gateway URL
                      const Text(
                        'ĐỊA CHỈ GATEWAY',
                        style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF64748B),
                          letterSpacing: 1.2,
                        ),
                      ),
                      const SizedBox(height: 6),
                      _buildTextField(
                        controller: _serverController,
                        hint: 'http://192.168.11.29:8000',
                        icon: Icons.dns_rounded,
                      ),
                      const SizedBox(height: 14),

                      if (!_isApiKeyMode) ...[
                        // Username
                        const Text(
                          'TÊN ĐĂNG NHẬP',
                          style: TextStyle(
                            fontSize: 10.5,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF64748B),
                            letterSpacing: 1.2,
                          ),
                        ),
                        const SizedBox(height: 6),
                        _buildTextField(
                          controller: _userController,
                          hint: 'admin',
                          icon: Icons.person_rounded,
                        ),
                        const SizedBox(height: 14),

                        // Password
                        const Text(
                          'MẬT KHẨU',
                          style: TextStyle(
                            fontSize: 10.5,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF64748B),
                            letterSpacing: 1.2,
                          ),
                        ),
                        const SizedBox(height: 6),
                        _buildTextField(
                          controller: _passController,
                          hint: '••••••••',
                          icon: Icons.lock_rounded,
                          isPassword: true,
                        ),
                      ] else ...[
                        // API Key Input
                        const Text(
                          'AETHERIA API KEY',
                          style: TextStyle(
                            fontSize: 10.5,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF64748B),
                            letterSpacing: 1.2,
                          ),
                        ),
                        const SizedBox(height: 6),
                        _buildTextField(
                          controller: _apiKeyController,
                          hint: 'aeth_xxxxxxxxxxxxxxxxxxxx',
                          icon: Icons.vpn_key_rounded,
                        ),
                      ],

                      // Error message if any
                      if (_errorMessage != null) ...[
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: Colors.red.withOpacity(0.12),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: Colors.red.withOpacity(0.3)),
                          ),
                          child: Row(
                            children: [
                              const Icon(Icons.error_outline, size: 16, color: Colors.redAccent),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  _errorMessage!,
                                  style: const TextStyle(fontSize: 12, color: Colors.redAccent),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],

                      const SizedBox(height: 14),

                      // Remember Me
                      Row(
                        children: [
                          SizedBox(
                            width: 24,
                            height: 24,
                            child: Checkbox(
                              value: _rememberMe,
                              onChanged: (v) => setState(() => _rememberMe = v ?? true),
                              activeColor: const Color(0xFF00F2FE),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Text(
                            'Tự động lưu API Key & Đăng nhập các lần sau',
                            style: TextStyle(fontSize: 11.5, color: Color(0xFF94A3B8)),
                          ),
                        ],
                      ),
                      const SizedBox(height: 20),

                      // Submit Button
                      SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: ElevatedButton(
                          onPressed: _isLoading ? null : _handleLogin,
                          style: ElevatedButton.styleFrom(
                            padding: EdgeInsets.zero,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                          ),
                          child: Ink(
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                colors: [Color(0xFF00F2FE), Color(0xFF8B5CF6)],
                              ),
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: Center(
                              child: _isLoading
                                  ? const SizedBox(
                                      width: 20,
                                      height: 20,
                                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                    )
                                  : const Text(
                                      'Vào Hệ Thống Aetheria',
                                      style: TextStyle(
                                        fontSize: 14.5,
                                        fontWeight: FontWeight.w700,
                                        color: Colors.white,
                                      ),
                                    ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 24),
                // Footer
                const Text(
                  'Tài khoản mặc định: admin / admin123\nAPI Key được mã hóa và bảo vệ trong bộ nhớ máy',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11, color: Color(0xFF64748B), height: 1.4),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String hint,
    required IconData icon,
    bool isPassword = false,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.25),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: TextField(
        controller: controller,
        obscureText: isPassword,
        style: const TextStyle(fontSize: 13, color: Colors.white),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.25)),
          prefixIcon: Icon(icon, size: 18, color: const Color(0xFF00F2FE)),
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        ),
      ),
    );
  }
}
