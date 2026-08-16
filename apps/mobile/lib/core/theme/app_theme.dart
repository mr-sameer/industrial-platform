import 'package:flutter/material.dart';

/// Minimal placeholder theme. A full design system arrives with the first
/// business-feature module; Module 1 only needs enough styling to render
/// the health-check screen legibly.
class AppTheme {
  AppTheme._();

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1A3C34)),
      );
}
