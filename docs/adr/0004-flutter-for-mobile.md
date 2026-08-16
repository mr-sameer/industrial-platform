# 0004 — Flutter for the Mobile App

## Status
Accepted

## Context
The platform needs a single mobile codebase covering iOS and Android for
field/on-site industrial users, with UI needs that are moderate
(dashboards, forms, scanning in later modules) rather than requiring deep
platform-specific native APIs on day one.

## Decision
Flutter, targeting Dart SDK ^3.4, with a feature-first `lib/` structure
(`lib/core/` for cross-cutting concerns, `lib/features/<feature>/` per
feature) and `http` + a hand-rolled API client mirroring the same
response envelope used by web and API (see ADR-0008).

## Alternatives considered
- **React Native**: would share more code/patterns with the Next.js web
  app (both React), but Flutter's more consistent cross-platform rendering
  and widget-based UI model was judged a better fit for a
  dashboard-and-forms-heavy industrial app; revisit if team React Native
  expertise turns out to dominate.
- **Native (Swift + Kotlin, two codebases)**: rejected outright for a
  small team — doubles UI implementation and maintenance cost with no
  clear benefit at this stage.

## Consequences
- Only hand-authored Dart sources (`lib/`, `test/`, `pubspec.yaml`,
  `analysis_options.yaml`) are committed; native scaffolding
  (`android/`, `ios/`, etc.) is generated locally via `flutter create .`
  per `apps/mobile/README.md`, since that scaffolding is large,
  machine/SDK-version-specific, and not meaningfully reviewable as a diff.
- Type contracts are *duplicated* (not code-generated) across
  `packages/shared-types` (TS), `app/schemas/*.py` (Pydantic), and
  `lib/core/network/api_client.dart` (Dart) in Module 1. Revisit codegen
  (e.g. OpenAPI-generated Dart client) once the API surface stabilizes
  beyond the health check.
