import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';

class AuthService {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  final GoogleSignIn _googleSignIn = GoogleSignIn();

  /// Stream lắng nghe thay đổi trạng thái đăng nhập
  Stream<User?> get authStateChanges => _auth.authStateChanges();

  /// Lấy thông tin user hiện tại
  User? get currentUser => _auth.currentUser;

  /// Đăng ký tài khoản với Email và Mật khẩu
  Future<UserCredential?> signUpWithEmail({
    required String email,
    required String password,
  }) async {
    try {
      return await _auth.createUserWithEmailAndPassword(
        email: email.trim(),
        password: password,
      );
    } on FirebaseAuthException catch (e) {
      throw Exception(_handleAuthException(e));
    } catch (e) {
      throw Exception('Đã xảy ra lỗi không xác định: $e');
    }
  }

  /// Đăng nhập với Email và Mật khẩu
  Future<UserCredential?> signInWithEmail({
    required String email,
    required String password,
  }) async {
    try {
      return await _auth.signInWithEmailAndPassword(
        email: email.trim(),
        password: password,
      );
    } on FirebaseAuthException catch (e) {
      throw Exception(_handleAuthException(e));
    } catch (e) {
      throw Exception('Đã xảy ra lỗi không xác định: $e');
    }
  }

  /// Đăng nhập với tài khoản Google
  Future<UserCredential?> signInWithGoogle() async {
    try {
      if (kIsWeb) {
        GoogleAuthProvider authProvider = GoogleAuthProvider();
        return await _auth.signInWithPopup(authProvider);
      } else {
        final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
        if (googleUser == null) return null; // Người dùng hủy thao tác

        final GoogleSignInAuthentication googleAuth =
            await googleUser.authentication;
        final AuthCredential credential = GoogleAuthProvider.credential(
          accessToken: googleAuth.accessToken,
          idToken: googleAuth.idToken,
        );

        return await _auth.signInWithCredential(credential);
      }
    } catch (e) {
      throw Exception('Đăng nhập Google thất bại: $e');
    }
  }

  /// Đăng xuất tài khoản
  Future<void> signOut() async {
    if (!kIsWeb) {
      try {
        await _googleSignIn.signOut();
      } catch (_) {}
    }
    await _auth.signOut();
  }

  /// Lấy JWT ID Token (gửi cho Backend Flask nếu cần)
  Future<String?> getIdToken() async {
    return await _auth.currentUser?.getIdToken();
  }

  /// Xử lý thông báo lỗi FirebaseAuth theo định dạng tiếng Việt dễ hiểu
  String _handleAuthException(FirebaseAuthException e) {
    switch (e.code) {
      case 'user-not-found':
        return 'Tài khoản không tồn tại.';
      case 'wrong-password':
      case 'invalid-credential':
        return 'Email hoặc mật khẩu không chính xác.';
      case 'email-already-in-use':
        return 'Email này đã được đăng ký tài khoản khác.';
      case 'weak-password':
        return 'Mật khẩu quá yếu (tối thiểu 6 ký tự).';
      case 'invalid-email':
        return 'Địa chỉ email không hợp lệ.';
      case 'network-request-failed':
        return 'Lỗi kết nối mạng, vui lòng kiểm tra lại Internet.';
      case 'too-many-requests':
        return 'Quá nhiều yêu cầu thất bại. Vui lòng thử lại sau.';
      case 'operation-not-allowed':
        return 'Phương thức đăng nhập này chưa được bật trên Firebase Console (tab Authentication > Sign-in method). Bạn có thể bấm "Truy cập nhanh (Chế độ Khách / Xem thử)" ở bên dưới để vào ngay!';
      default:
        if (e.message != null && e.message!.contains('sign-in provider is disabled')) {
          return 'Phương thức đăng nhập này chưa được kích hoạt trên Firebase Console. Hãy bật Email/Password hoặc Google trong Auth > Sign-in method, hoặc nhấn "Truy cập nhanh (Chế độ Khách)" bên dưới để vào ngay.';
        }
        return 'Lỗi xác thực: ${e.message ?? e.code}';
    }
  }
}
