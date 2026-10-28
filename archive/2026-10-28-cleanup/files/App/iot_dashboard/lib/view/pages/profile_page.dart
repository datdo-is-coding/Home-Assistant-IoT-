import 'package:flutter/material.dart';
import 'package:iot_dashboard/data/model/user_model.dart';
import 'package:iot_dashboard/data/notifiers.dart';
import 'package:iot_dashboard/view/widgets/profile/user_maintenance_package_card.dart';
import 'package:iot_dashboard/view/widgets/profile/user_profile_card.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: ValueListenableBuilder<UserModel>(
        valueListenable: currentUserNotifier,
        builder: (context, user, child) {
          return Padding(
            padding: const EdgeInsets.all(24.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // CỘT 1: THÔNG TIN CÁ NHÂN KHÁCH HÀNG (45% Chiều rộng)
                Expanded(
                  flex: 45,
                  child: UserProfileCard(user: user),
                ),

                const SizedBox(width: 24),

                // CỘT 2: GÓI BẢO TRÌ ĐANG SỬ DỤNG (55% Chiều rộng)
                Expanded(
                  flex: 55,
                  child: UserMaintenancePackageCard(package: user.package),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
