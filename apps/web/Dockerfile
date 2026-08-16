# syntax=docker/dockerfile:1.7

# ---- Base ----
FROM node:20.11-bookworm-slim AS base
RUN corepack enable && corepack prepare pnpm@9.7.0 --activate
WORKDIR /repo

# ---- Dependencies (cached layer) ----
FROM base AS deps
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY packages/shared-types/package.json packages/shared-types/
COPY packages/ui/package.json packages/ui/
COPY packages/eslint-config/package.json packages/eslint-config/
COPY packages/tsconfig/package.json packages/tsconfig/
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter web...

# ---- Build ----
FROM base AS build
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/packages ./packages
COPY --from=deps /repo/apps/web/node_modules ./apps/web/node_modules
COPY . .
# NEXT_PUBLIC_* variables are inlined into the client bundle at build
# time by webpack — setting this only in docker-compose.yml's runtime
# `environment:` block (as this project previously did) has no effect
# on the already-built client JS, causing the browser to call a
# different API origin than what CSP's connect-src (set server-side, at
# request time, in middleware.ts) allows. Confirmed via real
# production-build browser testing — see
# docs/adr/0031-csp-blocked-hydration.md.
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN pnpm --filter web... build

# ---- Runtime ----
FROM node:20.11-bookworm-slim AS runner
ENV NODE_ENV=production
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

# `output: "standalone"` in next.config.mjs produces a minimal server bundle
COPY --from=build --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=nextjs:nodejs /repo/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 3000
ENV PORT=3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "apps/web/server.js"]
