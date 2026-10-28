import 'package:flutter/material.dart';
import 'package:iot_dashboard/view/widgets/alerts/alert_center_card.dart';

class AlertsPage extends StatelessWidget {
  const AlertsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: const Padding(
        padding: EdgeInsets.all(20.0),
        child: AlertCenterCard(),
      ),
    );
  }
}
