import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_competition/providers/smart_home_providers.dart';
import 'package:home_competition/services/app_update_service.dart';
import 'package:home_competition/widgets/app_update_tile.dart';

class _ReadyUpdate extends AppUpdateService {
  _ReadyUpdate() : super(enabled: false) {
    phase = AppUpdatePhase.ready;
    installedVersion = '1.7.0';
    release = AppRelease(
        '1.7.1',
        44,
        1024,
        'a' * 64,
        Uri.parse(
            'https://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/app-v1.7.1/HomeCompetition.apk'));
  }
  bool requestedInstall = false;
  @override
  bool get canInstall => true;
  @override
  Future<void> install() async {
    requestedInstall = true;
  }
}

void main() {
  testWidgets('the settings update sheet installs the verified ready release',
      (tester) async {
    final update = _ReadyUpdate();
    await tester.pumpWidget(ProviderScope(overrides: [
      appUpdateProvider.overrideWith((_) => update),
    ], child: const MaterialApp(home: Scaffold(body: AppUpdateTile()))));
    expect(find.text('Bản 1.7.1 đã sẵn sàng'), findsOneWidget);
    await tester.tap(find.byKey(const Key('app_update_tile')));
    await tester.pumpAndSettle();
    expect(find.text('Đang dùng 1.7.0'), findsOneWidget);
    await tester.tap(find.text('Cài đặt'));
    expect(update.requestedInstall, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
