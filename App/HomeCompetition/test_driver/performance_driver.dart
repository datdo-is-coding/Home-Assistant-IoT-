import 'dart:convert';
import 'dart:io';
import 'package:integration_test/integration_test_driver.dart';

Future<void> main() => integrationDriver(responseDataCallback: (data) async {
      final path = Platform.environment['HOME_COMPETITION_PERF_OUTPUT'] ??
          '/tmp/homecompetition-performance.json';
      await File(path)
          .writeAsString(const JsonEncoder.withIndent('  ').convert(data));
    });
