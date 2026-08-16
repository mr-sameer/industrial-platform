# Mobile App (Flutter)

Module 1 ships the app shell, environment config, a shared API client
matching the platform-wide response envelope, and a health-check screen.

## First-time setup

This directory contains hand-written Dart sources but **not** the
platform scaffolding (`android/`, `ios/`, `web/`, `.metadata`, etc.) that
`flutter create` normally generates, since those are large, machine-specific,
and don't belong in a hand-authored diff. Generate them once, locally:

```bash
cd apps/mobile
flutter create --org com.industrialplatform --project-name industrial_platform_mobile .
flutter pub get
cp .env.example .env   # then edit API_BASE_URL for your device/emulator
flutter run
```

`flutter create .` will not overwrite the existing `lib/`, `test/`,
`pubspec.yaml`, or `analysis_options.yaml` files here — it only fills in
the missing native platform folders.

## Commands

```bash
flutter analyze         # static analysis (flutter_lints)
flutter test            # unit/widget tests
flutter build apk       # Android release build
flutter build ios       # iOS release build (macOS + Xcode required)
```

## Notes

- `API_BASE_URL` defaults to `http://10.0.2.2:8000`, the Android emulator's
  alias for the host machine's `localhost`. iOS Simulator and physical
  devices need a different value — see `.env.example`.
- **Authentication (Module 2.5):** the app launches into `AuthGate`
  (`lib/features/auth/presentation/auth_gate.dart`), which shows a login
  screen, a loading spinner while restoring a session, or the
  authenticated home screen. Tokens are stored via `flutter_secure_storage`
  (`lib/core/storage/secure_token_storage.dart`) — Keychain on iOS,
  Keystore on Android — never in `SharedPreferences` or plain files. See
  `docs/adr/0012-web-session-strategy.md` for why mobile's approach
  (both tokens stored on-device) differs from web's BFF/cookie split, and
  `docs/adr/0014-refresh-token-and-session-model.md` for the
  rotating/revocable refresh token design both clients talk to.
- **Companies (Module 3A):** tap the building icon in the app bar to see
  your companies (`CompanyListScreen`), create a new one, view a
  dashboard, and edit settings (including delete/archive) — mirrors
  `apps/web/src/app/companies/*`. `CompanyRepository`
  (`lib/features/companies/data/company_repository.dart`) follows the
  same per-call token-read pattern as `AuthRepository`.
- **Verification & Industrial Identity (Module 3B):** from a company's
  dashboard, tap the verification (checkmark) icon to see progress
  (`VerificationDashboardScreen`), then drill into Business Information,
  Documents (upload/delete via `file_picker`), and Branding (logo/cover
  image upload) — mirrors `apps/web/src/app/companies/[id]/verification/*`.
  Note: the brief's Flutter section doesn't list a Social Links screen
  (unlike the Next.js frontend, which does) — that's intentional scope
  matching, not an oversight; see
  `docs/modules/module-3b-completion-report.md`.
- **Biometric gating is prepared but not implemented** — see the
  architecture note in `secure_token_storage.dart` for the intended
  extension point.
