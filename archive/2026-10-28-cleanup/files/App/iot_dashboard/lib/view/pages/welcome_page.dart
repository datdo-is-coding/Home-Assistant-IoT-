import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/welcome/auth_validator.dart';
import 'package:iot_dashboard/view/widgets/welcome/sliding_overlay_card.dart';
import 'package:iot_dashboard/view/widgets_tree.dart';

class WelcomePage extends StatefulWidget {
  const WelcomePage({super.key});

  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  bool isSignIn = true;
  bool isAgreed = false;
  bool isPasswordObscured = true;
  bool isLoading = false;

  // Controllers cho Sign In
  final TextEditingController signInEmailController = TextEditingController();
  final TextEditingController signInPasswordController =
      TextEditingController();

  // Controllers cho Sign Up
  final TextEditingController signUpNameController = TextEditingController();
  final TextEditingController signUpEmailController = TextEditingController();
  final TextEditingController signUpPasswordController =
      TextEditingController();

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _animation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOutCubic,
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    signInEmailController.dispose();
    signInPasswordController.dispose();
    signUpNameController.dispose();
    signUpEmailController.dispose();
    signUpPasswordController.dispose();
    super.dispose();
  }

  void _toggleMode() {
    setState(() {
      isSignIn = !isSignIn;
      if (isSignIn) {
        _controller.reverse();
      } else {
        _controller.forward();
      }
    });
  }

  // Xử lý đăng nhập (Sử dụng AuthValidator)
  Future<void> _handleSignIn() async {
    final email = signInEmailController.text.trim();
    final password = signInPasswordController.text.trim();

    final errorMsg = AuthValidator.validateSignIn(
      email: email,
      password: password,
    );

    if (errorMsg != null) {
      _showSnackBar(errorMsg);
      return;
    }

    setState(() => isLoading = true);

    // Mô phỏng gọi API đăng nhập
    await Future.delayed(const Duration(seconds: 1));

    if (!mounted) return;

    // Cập nhật thông tin User thông qua AuthValidator
    currentUserNotifier.value = AuthValidator.createSignInUserData(
      email: email,
      password: password,
    );

    setState(() => isLoading = false);

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (context) => const WidgetsTree()),
    );
  }

  // Xử lý đăng ký (Sử dụng AuthValidator)
  Future<void> _handleSignUp() async {
    final name = signUpNameController.text.trim();
    final email = signUpEmailController.text.trim();
    final password = signUpPasswordController.text.trim();

    final errorMsg = AuthValidator.validateSignUp(
      name: name,
      email: email,
      password: password,
      isAgreed: isAgreed,
    );

    if (errorMsg != null) {
      _showSnackBar(errorMsg);
      return;
    }

    setState(() => isLoading = true);

    await Future.delayed(const Duration(seconds: 1));

    if (!mounted) return;

    // Cập nhật tài khoản mới tạo thông qua AuthValidator
    currentUserNotifier.value = AuthValidator.createSignUpUserData(
      name: name,
      email: email,
      password: password,
    );

    setState(() => isLoading = false);

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (context) => const WidgetsTree()),
    );
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Colors.redAccent,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;

    // Scale kích thước vừa vặn và cân đối hoàn hảo theo khung hình thiết bị
    final cardWidth = (size.width * 0.85).clamp(750.0, 1150.0);
    final cardHeight = (size.height * 0.82).clamp(560.0, 750.0);

    return Scaffold(
      backgroundColor: const Color(0xFFF3F4F9),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Container(
                width: cardWidth,
                height: cardHeight,
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.08),
                      blurRadius: 35,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: Stack(
                    children: [
                      // 1. CÁC FORM NHẬP LIỆU (Nằm ở lớp dưới)
                      Row(
                        children: [
                          // Form Sign In (Bên trái)
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 36.0,
                              ),
                              child: _buildSignInForm(),
                            ),
                          ),
                          // Form Sign Up (Bên phải)
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 36.0,
                              ),
                              child: _buildSignUpForm(),
                            ),
                          ),
                        ],
                      ),

                      // 2. TẤM THẺ MÀU TÍM TRƯỢT QUA LẠI (Thành phần widget riêng SlidingOverlayCard)
                      SlidingOverlayCard(
                        animation: _animation,
                        cardWidth: cardWidth,
                        isSignIn: isSignIn,
                        onToggleMode: _toggleMode,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  // Giao diện Form Sign In
  Widget _buildSignInForm() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Chào mừng trở lại',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: Color(0xFF1E293B),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Đăng nhập để tiếp tục truy cập tài khoản của bạn.',
          style: TextStyle(color: Colors.grey),
        ),
        const SizedBox(height: 32),
        _buildTextField(
          controller: signInEmailController,
          label: 'Email',
          hint: 'ban@congty.com',
          icon: Icons.email_outlined,
        ),
        const SizedBox(height: 16),
        _buildTextField(
          controller: signInPasswordController,
          label: 'Mật khẩu',
          hint: '••••••••',
          icon: Icons.lock_outline,
          isPassword: true,
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            onPressed: () {
              _showSnackBar('Chức năng Quên mật khẩu đang phát triển!');
            },
            child: const Text(
              'Quên mật khẩu?',
              style: TextStyle(color: Color(0xFF6366F1)),
            ),
          ),
        ),
        const SizedBox(height: 20),
        _buildPrimaryButton(
          text: 'Đăng nhập',
          onPressed: _handleSignIn,
        ),
        const SizedBox(height: 24),
        _buildSocialButtons(),
      ],
    );
  }

  // Giao diện Form Sign Up
  Widget _buildSignUpForm() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Tạo tài khoản mới',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: Color(0xFF1E293B),
          ),
        ),
        const SizedBox(height: 24),
        _buildTextField(
          controller: signUpNameController,
          label: 'Họ và tên',
          hint: 'Nguyễn Văn A',
          icon: Icons.person_outline,
        ),
        const SizedBox(height: 16),
        _buildTextField(
          controller: signUpEmailController,
          label: 'Email',
          hint: 'ban@congty.com',
          icon: Icons.email_outlined,
        ),
        const SizedBox(height: 16),
        _buildTextField(
          controller: signUpPasswordController,
          label: 'Mật khẩu',
          hint: 'Ít nhất 6 ký tự',
          icon: Icons.lock_outline,
          isPassword: true,
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Checkbox(
              value: isAgreed,
              activeColor: const Color(0xFF6366F1),
              onChanged: (val) => setState(() => isAgreed = val ?? false),
            ),
            const Expanded(
              child: Text(
                'Tôi đồng ý với Điều khoản và Chính sách bảo mật',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        _buildPrimaryButton(
          text: 'Tạo tài khoản',
          onPressed: _handleSignUp,
        ),
      ],
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required String hint,
    required IconData icon,
    bool isPassword = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 13,
            color: Color(0xFF475569),
          ),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: controller,
          obscureText: isPassword ? isPasswordObscured : false,
          decoration: InputDecoration(
            hintText: hint,
            prefixIcon: Icon(icon, color: Colors.grey, size: 20),
            suffixIcon: isPassword
                ? IconButton(
                    icon: Icon(
                      isPasswordObscured
                          ? Icons.visibility_off
                          : Icons.visibility,
                      color: Colors.grey,
                      size: 20,
                    ),
                    onPressed: () => setState(
                      () => isPasswordObscured = !isPasswordObscured,
                    ),
                  )
                : null,
            filled: true,
            fillColor: const Color(0xFFF8FAFC),
            contentPadding: const EdgeInsets.symmetric(
              vertical: 14,
              horizontal: 16,
            ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPrimaryButton({
    required String text,
    required VoidCallback onPressed,
  }) {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: ElevatedButton(
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF4F46E5),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          elevation: 0,
        ),
        onPressed: isLoading ? null : onPressed,
        child: isLoading
            ? const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  color: Colors.white,
                  strokeWidth: 2.5,
                ),
              )
            : Text(
                text,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
      ),
    );
  }

  Widget _buildSocialButtons() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildSocialIcon(Icons.g_mobiledata, 'Google'),
        const SizedBox(width: 16),
        _buildSocialIcon(Icons.code, 'GitHub'),
      ],
    );
  }

  Widget _buildSocialIcon(IconData icon, String label) {
    return OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        side: const BorderSide(color: Color(0xFFE2E8F0)),
      ),
      onPressed: () {
        _showSnackBar('Đăng nhập bằng $label đang được tích hợp!');
      },
      icon: Icon(icon, size: 20, color: Colors.black87),
      label: Text(
        label,
        style: const TextStyle(color: Colors.black87, fontSize: 13),
      ),
    );
  }
}
