# depwatch

Watches GitHub repos for dependency changes and writes one markdown note per
week into a git-backed vault. Three feeds: upstream releases on npm and PyPI,
manifest changes that landed in the repo, and open Dependabot advisories. A
local model summarises each change. Major releases and serious advisories of
packages the repo imports get a second read that names the affected files.

```markdown
## Advisories

- [ ] [easton-duels](https://github.com/acme/easton-duels): hono < 4.6.2, [GHSA-aaaa-bbbb-cccc](https://github.com/advisories/GHSA-aaaa-bbbb-cccc) (high), fixed in 4.6.2. Path traversal in static middleware. Breakage: server/src/app.ts:12 mounts the affected middleware. [tier:: backlog]

## easton-duels

### Landed
- 2026-09-10 `a1b2c3d`: [drizzle-orm 0.36.1 -> 0.38.0](https://github.com/acme/easton-duels/commit/a1b2c3d4e5f6) (minor). Adds relational query v2.

### Upstream
- [ ] [vitest 3.2.0 -> 4.0.0](https://github.com/vitest-dev/vitest/releases/tag/v4.0.0) (major). Drops the vi.mocked overload. Breakage: three test files use the removed overload. [tier:: backlog]
- Patches: @types/node, typescript (2).
```

Checkbox lines are actionable. `[tier:: backlog]` is an Obsidian Dataview
field and plain text anywhere else.

## Run

```bash
uv sync
cp config.example.toml config.toml      # edit it, every key is documented
export GITHUB_TOKEN=$(gh auth token)
uv run depwatch digest --dry-run
uv run depwatch digest
```

Or copy `.env.example` to `.env` and `docker compose up -d --build`.
`depwatch serve` runs the digest on Monday at 07:00 and an advisory-only pass
on the other days.

`GITHUB_TOKEN` needs read on the watched repos, Dependabot alerts read, and
contents write on the vault repo. `ANTHROPIC_API_KEY` is only needed with
`provider = "anthropic"`. `NTFY_TOPIC` is optional and gets failure pings.

## Tests

```bash
uv run pytest
```

MIT.
