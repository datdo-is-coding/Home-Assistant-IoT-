import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/widgets/progressive_blur.dart';

void main() {
  testWidgets('frosted edge passes taps to the controls underneath',
      (tester) async {
    var taps = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: SizedBox(
        width: 280,
        height: 96,
        child: Stack(children: [
          Positioned.fill(
              child: FilledButton(
            onPressed: () => taps++,
            child: const Text('Điều khiển'),
          )),
          const Positioned.fill(child: ProgressiveBlur(tint: Colors.white)),
        ]),
      )),
    ));
    await tester.tap(find.text('Điều khiển'));
    await tester.pumpAndSettle();
    expect(taps, 1);
    expect(find.byType(BackdropFilter), findsNWidgets(3));
    expect(tester.takeException(), isNull);
  });

  for (final contrast in [false, true]) {
    testWidgets(
        'reduced effects use an opaque readable edge: contrast=$contrast',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
          home: MediaQuery(
        data: MediaQueryData(
          disableAnimations: !contrast,
          highContrast: contrast,
        ),
        child: const SizedBox(
          width: 280,
          height: 96,
          child: ProgressiveBlur(tint: Colors.white),
        ),
      )));
      expect(find.byType(BackdropFilter), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }
}
