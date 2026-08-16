import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:industrial_platform_mobile/core/theme/app_theme.dart';

void main() {
  testWidgets('AppTheme.light builds a valid Material3 theme', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(body: Text('smoke test')),
      ),
    );
    expect(find.text('smoke test'), findsOneWidget);
  });
}
