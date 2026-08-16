# Vendored ReDoc bundle

`redoc.standalone.js` — fetched from the `redoc@2.5.3` npm package
(https://www.npmjs.com/package/redoc), vendored here so `/redoc` never
depends on an external CDN (`cdn.jsdelivr.net`) at runtime. See
`docs/adr/0034-self-hosted-api-docs.md` for why. License in
`redoc.standalone.js.LICENSE.txt`, same file as ships in the npm
package.

To update: `npm pack redoc@<version>`, extract, replace this file with
the new `bundles/redoc.standalone.js`.
