# Architecture Documentation

- `system-context.md` — C4-style system context diagram (Module 1 scope).
- `container-diagram.md` — containers/services and how they talk to each other.
- `request-lifecycle.md` — sequence diagram for a single request through
  the stack, including the health-check flow shipped in Module 1.
- `repo-structure.md` — annotated monorepo folder layout.

All diagrams are authored in [Mermaid](https://mermaid.js.org/) so they
render directly on GitHub with no build step. Keep diagrams in sync with
reality as part of the PR that changes the architecture — a stale diagram
is worse than no diagram.
