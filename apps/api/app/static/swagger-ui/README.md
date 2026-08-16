# Vendored Swagger UI assets

`swagger-ui-bundle.js`, `swagger-ui.css`, `favicon-32x32.png` — fetched
from the `swagger-ui-dist@5.32.12` npm package
(https://www.npmjs.com/package/swagger-ui-dist), vendored here so
`/docs` never depends on an external CDN (`cdn.jsdelivr.net`) at
runtime. See `docs/adr/0034-self-hosted-api-docs.md`.

**Not the `swagger-ui-bundle` PyPI package** (removed — its latest
release, 1.1.0, bundles Swagger UI 4.15.5, which predates proper
OpenAPI 3.1 support; this FastAPI app generates `openapi: "3.1.0"`
documents, which 4.x's Swagger UI rejects outright with "The provided
definition does not specify a valid version field" — confirmed via
real browser testing, not assumed). License in `LICENSE`, same file as
ships in the npm package.

To update: `npm pack swagger-ui-dist@<version>`, extract, replace these
files with the new package's equivalents.
