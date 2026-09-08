---
type: dependency-digest
week: 2026-W37
generated: 2026-09-14T07:00:00-04:00
repos: 12
findings:
  advisories: 1
  landed: 2
  releases: 4
skipped: 1
---

# Dependencies 2026-W37

## Advisories

- [ ] [easton-duels](https://github.com/jakesciotto/easton-duels): hono < 4.6.2, [GHSA-aaaa-bbbb-cccc](https://github.com/advisories/GHSA-aaaa-bbbb-cccc) (high), fixed in 4.6.2. Path traversal in static middleware. Breakage: server/src/app.ts:12 mounts the affected middleware. [tier:: backlog]

## easton-duels

### Landed
- 2026-09-10 `a1b2c3d`: [drizzle-orm 0.36.1 -> 0.38.0](https://github.com/jakesciotto/easton-duels/commit/a1b2c3d4e5f6) (minor). Adds relational query v2.
- 2026-09-11 `b2c3d4e`: [left-pad added at 1.3.0](https://github.com/jakesciotto/easton-duels/commit/b2c3d4e5f6a7) (minor).

### Upstream
- [ ] [vitest 3.2.0 -> 4.0.0](https://github.com/vitest-dev/vitest/releases/tag/v4.0.0) (major). Drops the vi.mocked overload. Breakage: three test files use the removed overload. [tier:: backlog]
- [react-router 7.1.0 -> 7.2.0](https://github.com/remix-run/react-router/releases/tag/v7.2.0) (minor). Adds data strategies.
- Patches: @types/node, typescript (2).

## portfolio

### Upstream
- [next 16.2.6 -> 17.0.0](https://github.com/vercel/next.js/releases/tag/v17.0.0) (major). No import sites found.

## recall

- fetch failed: git fetch failed: could not read from remote
