import 'package:flutter/material.dart';
import 'package:dtv_home_assistant/data/notifiers.dart';
import 'package:dtv_home_assistant/views/pages/home_page.dart';
import 'package:dtv_home_assistant/views/pages/alert_page.dart';
import 'package:dtv_home_assistant/views/pages/setting_page.dart';
import 'package:dtv_home_assistant/views/pages/report_page.dart';

import 'widgets/navbar_widget.dart';

List<Widget> pages = [HomePage(), ReportPage(), AlertPage()];

class WidgetTree extends StatelessWidget {
  const WidgetTree({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text(
          "HOME COMPANION",
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2.0,
            fontSize: 20,
          ),
        ),
        centerTitle: false,
        actions: [
          ValueListenableBuilder(
            valueListenable: selectedPageNotifier,
            builder: (context, value, child) {
              if (value == 2) {
                return Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.settings),
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (context) {
                              return const SettingPage(title: "Cài đặt");
                            },
                          ),
                        );
                      },
                    ),
                  ],
                );
              }
              return const SizedBox.shrink();
            },
          ),
        ],
      ),

      body: ValueListenableBuilder(
        valueListenable: selectedPageNotifier,
        builder: (context, value, child) {
          return pages.elementAt(value);
        },
      ),
      bottomNavigationBar: const NavBarWidget(),
    );
  }
}
