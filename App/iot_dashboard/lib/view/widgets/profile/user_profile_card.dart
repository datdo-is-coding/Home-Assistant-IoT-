import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/model/user_model.dart';
import 'package:iot_dashboard/data/notifiers.dart';

class UserProfileCard extends StatefulWidget {
  final UserModel user;

  const UserProfileCard({super.key, required this.user});

  @override
  State<UserProfileCard> createState() => _UserProfileCardState();
}

class _UserProfileCardState extends State<UserProfileCard> {
  bool isPasswordVisible = false;

  void _showSingleFieldEditDialog({
    required String fieldTitle,
    required String currentValue,
    required IconData icon,
    bool isPassword = false,
    required Function(String newValue) onSave,
  }) {
    final controller = TextEditingController(text: currentValue);
    bool obscure = isPassword;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              backgroundColor: isDark ? const Color(0xFF1E293B) : Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              title: Row(
                children: [
                  Icon(icon, color: const Color(0xFF818CF8)),
                  const SizedBox(width: 8),
                  Text(
                    'Cập nhật $fieldTitle',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                      color: isDark ? Colors.white : const Color(0xFF1E293B),
                    ),
                  ),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: controller,
                    obscureText: obscure,
                    style: TextStyle(
                      color: isDark ? Colors.white : const Color(0xFF1E293B),
                    ),
                    decoration: InputDecoration(
                      labelText: fieldTitle,
                      labelStyle: TextStyle(
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade700,
                      ),
                      prefixIcon: Icon(
                        icon,
                        color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                      suffixIcon: isPassword
                          ? IconButton(
                              icon: Icon(
                                obscure
                                    ? Icons.visibility_off
                                    : Icons.visibility,
                                color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                              ),
                              onPressed: () {
                                setDialogState(() {
                                  obscure = !obscure;
                                });
                              },
                            )
                          : null,
                      border: const OutlineInputBorder(),
                    ),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: Text(
                    'Hủy',
                    style: TextStyle(
                      color: isDark ? Colors.grey.shade400 : Colors.grey.shade700,
                    ),
                  ),
                ),
                ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF4F46E5),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  onPressed: () {
                    final newValue = controller.text.trim();
                    if (newValue.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('$fieldTitle không được để trống!'),
                          backgroundColor: Colors.redAccent,
                        ),
                      );
                      return;
                    }
                    onSave(newValue);
                    Navigator.pop(context);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Cập nhật $fieldTitle thành công!'),
                        backgroundColor: Colors.green,
                      ),
                    );
                  },
                  child: const Text(
                    'Lưu',
                    style: TextStyle(color: Colors.white),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }

  void _updateUser(void Function(UserModel u) action) {
    final current = currentUserNotifier.value;
    action(current);
    currentUserNotifier.value = UserModel(
      id: current.id,
      name: current.name,
      email: current.email,
      phone: current.phone,
      address: current.address,
      password: current.password,
      avatarUrl: current.avatarUrl,
      package: current.package,
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.user;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardBg = isDark ? const Color(0xFF1E293B) : Colors.white;
    final borderColor = isDark ? const Color(0xFF334155) : Colors.grey.shade200;

    return Card(
      margin: EdgeInsets.zero,
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: borderColor),
      ),
      color: cardBg,
      child: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: constraints.maxHeight - 48,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(
                        Icons.person,
                        color: Color(0xFF818CF8),
                        size: 24,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        'Thông Tin Cá Nhân',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : const Color(0xFF1E293B),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  // Avatar & Mã Khách hàng
                  Center(
                    child: Column(
                      children: [
                        Stack(
                          children: [
                            CircleAvatar(
                              radius: 44,
                              backgroundImage: NetworkImage(user.avatarUrl),
                            ),
                            Positioned(
                              bottom: 0,
                              right: 0,
                              child: InkWell(
                                onTap: () {
                                  _showSingleFieldEditDialog(
                                    fieldTitle: 'URL Ảnh Đại Diện (Avatar)',
                                    currentValue: user.avatarUrl,
                                    icon: Icons.image_outlined,
                                    onSave: (val) {
                                      _updateUser((u) => u.avatarUrl = val);
                                    },
                                  );
                                },
                                child: Container(
                                  padding: const EdgeInsets.all(6),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF4F46E5),
                                    shape: BoxShape.circle,
                                    border: Border.all(
                                      color: cardBg,
                                      width: 2,
                                    ),
                                  ),
                                  child: const Icon(
                                    Icons.camera_alt,
                                    size: 14,
                                    color: Colors.white,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: isDark
                                ? const Color(0xFF312E81).withValues(alpha: 0.5)
                                : const Color(0xFFEEF2FF),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            'Mã KH: ${user.id}',
                            style: TextStyle(
                              color: isDark ? const Color(0xFFA5B4FC) : const Color(0xFF4F46E5),
                              fontWeight: FontWeight.bold,
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),
                  Divider(color: borderColor),
                  const SizedBox(height: 8),

                  // Các dòng thông tin chỉnh sửa
                  _buildEditableFieldRow(
                    isDark: isDark,
                    icon: Icons.person_outline,
                    label: 'Họ và tên',
                    value: user.name,
                    onEdit: () {
                      _showSingleFieldEditDialog(
                        fieldTitle: 'Họ và tên',
                        currentValue: user.name,
                        icon: Icons.person_outline,
                        onSave: (val) {
                          _updateUser((u) => u.name = val);
                        },
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  _buildEditableFieldRow(
                    isDark: isDark,
                    icon: Icons.email_outlined,
                    label: 'Email',
                    value: user.email,
                    onEdit: () {
                      _showSingleFieldEditDialog(
                        fieldTitle: 'Email',
                        currentValue: user.email,
                        icon: Icons.email_outlined,
                        onSave: (val) {
                          _updateUser((u) => u.email = val);
                        },
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  _buildEditableFieldRow(
                    isDark: isDark,
                    icon: Icons.phone_outlined,
                    label: 'Số điện thoại',
                    value: user.phone,
                    onEdit: () {
                      _showSingleFieldEditDialog(
                        fieldTitle: 'Số điện thoại',
                        currentValue: user.phone,
                        icon: Icons.phone_outlined,
                        onSave: (val) {
                          _updateUser((u) => u.phone = val);
                        },
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  _buildEditableFieldRow(
                    isDark: isDark,
                    icon: Icons.location_on_outlined,
                    label: 'Địa chỉ',
                    value: user.address,
                    onEdit: () {
                      _showSingleFieldEditDialog(
                        fieldTitle: 'Địa chỉ',
                        currentValue: user.address,
                        icon: Icons.location_on_outlined,
                        onSave: (val) {
                          _updateUser((u) => u.address = val);
                        },
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  _buildEditableFieldRow(
                    isDark: isDark,
                    icon: Icons.lock_outline,
                    label: 'Mật khẩu',
                    value: isPasswordVisible ? user.password : '••••••••',
                    trailingWidget: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: Icon(
                            isPasswordVisible
                                ? Icons.visibility_off
                                : Icons.visibility,
                            size: 18,
                            color: isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                          ),
                          onPressed: () {
                            setState(() {
                              isPasswordVisible = !isPasswordVisible;
                            });
                          },
                        ),
                        IconButton(
                          icon: Icon(
                            Icons.edit,
                            size: 18,
                            color: isDark ? const Color(0xFF818CF8) : const Color(0xFF4F46E5),
                          ),
                          onPressed: () {
                            _showSingleFieldEditDialog(
                              fieldTitle: 'Mật khẩu',
                              currentValue: user.password,
                              icon: Icons.lock_outline,
                              isPassword: true,
                              onSave: (val) {
                                _updateUser((u) => u.password = val);
                              },
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildEditableFieldRow({
    required bool isDark,
    required IconData icon,
    required String label,
    required String value,
    VoidCallback? onEdit,
    Widget? trailingWidget,
  }) {
    final itemBg = isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC);
    final borderColor = isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: itemBg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        children: [
          Icon(
            icon,
            color: isDark ? Colors.grey.shade400 : const Color(0xFF64748B),
            size: 20,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: isDark ? Colors.grey.shade400 : Colors.grey,
                    fontSize: 11,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                  ),
                ),
              ],
            ),
          ),
          trailingWidget ??
              IconButton(
                icon: Icon(
                  Icons.edit,
                  size: 18,
                  color: isDark ? const Color(0xFF818CF8) : const Color(0xFF4F46E5),
                ),
                onPressed: onEdit,
              ),
        ],
      ),
    );
  }
}
