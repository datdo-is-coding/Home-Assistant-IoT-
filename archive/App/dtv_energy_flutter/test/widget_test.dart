import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dtv_energy_flutter/main.dart';

void main() {
  testWidgets('Counter increments smoke test', (WidgetTester tester) async {

    await tester.pumpWidget(const DTVEnergyApp(hasValidSession: false));
  });
}
