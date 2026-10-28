import 'package:flutter/material.dart';

class SlidingOverlayCard extends StatelessWidget {
  final Animation<double> animation;
  final double cardWidth;
  final bool isSignIn;
  final VoidCallback onToggleMode;

  const SlidingOverlayCard({
    super.key,
    required this.animation,
    required this.cardWidth,
    required this.isSignIn,
    required this.onToggleMode,
  });

  @override
  Widget build(BuildContext context) {
    final halfWidth = cardWidth / 2;

    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        return Positioned(
          left: (1 - animation.value) * halfWidth,
          top: 0,
          bottom: 0,
          width: halfWidth,
          child: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [Color(0xFF6366F1), Color(0xFF4F46E5)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32.0),
                child: isSignIn
                    ? _buildOverlaySignInContent()
                    : _buildOverlaySignUpContent(),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildOverlaySignInContent() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.rocket_launch_rounded, size: 64, color: Colors.white),
        const SizedBox(height: 24),
        const Text(
          'Bạn là người mới?',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
        const SizedBox(height: 12),
        const Text(
          'Tạo không gian làm việc, quản lý các dự án và lưu giữ mọi ý tưởng của bạn.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white70, height: 1.5),
        ),
        const SizedBox(height: 32),
        OutlinedButton(
          style: OutlinedButton.styleFrom(
            side: const BorderSide(color: Colors.white, width: 1.5),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          ),
          onPressed: onToggleMode,
          child: const Text(
            'Tạo tài khoản',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          ),
        ),
      ],
    );
  }

  Widget _buildOverlaySignUpContent() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.lock_open_rounded, size: 64, color: Colors.white),
        const SizedBox(height: 24),
        const Text(
          'Đã có tài khoản?',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: Colors.white,
          ),
        ),
        const SizedBox(height: 12),
        const Text(
          'Đăng nhập và tiếp tục công việc của bạn.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white70, height: 1.5),
        ),
        const SizedBox(height: 32),
        OutlinedButton(
          style: OutlinedButton.styleFrom(
            side: const BorderSide(color: Colors.white, width: 1.5),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          ),
          onPressed: onToggleMode,
          child: const Text(
            'Quay lại Đăng nhập',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          ),
        ),
      ],
    );
  }
}
