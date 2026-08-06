import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Central, typed accessor for mobile-app environment variables.
/// Mirrors apps/web/src/config/env.ts and app/core/config.py so all three
/// clients read configuration the same way.
class EnvConfig {
  EnvConfig._();

  static String get apiBaseUrl =>
      dotenv.env['API_BASE_URL'] ?? 'http://10.0.2.2:8000';

  static String get environment => dotenv.env['ENVIRONMENT'] ?? 'development';

  static bool get isProduction => environment == 'production';
}
