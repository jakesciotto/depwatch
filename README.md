# depwatch

Watches a list of GitHub repos for dependency changes and writes one markdown
note per week into a git-backed vault. A local model summarises each change.
Findings that can break your code get a second read that names the affected
files and decides whether you need to act.

It replaces the habit of opening Dependabot, ten changelogs and `git log` on a
Monday morning with one note that already says what changed and what matters.

```markdown
---
type: dependency-digest
week: 2026-W37
generated: 2026-09-14T07:00:00-04:00
repos: 12
findings:
  advisories: 1
  landed: 2
  releases: 5
skipped: 1
---

# Dependencies 2026-W37

## Advisories

- [ ] [easton-duels](https://github.com/acme/easton-duels): hono < 4.6.2, [GHSA-aaaa-bbbb-cccc](https://github.com/advisories/GHSA-aaaa-bbbb-cccc) (high), fixed in 4.6.2. Path traversal in static middleware. Breakage: server/src/app.ts:12 mounts the affected middleware. [tier:: backlog]

## easton-duels

### Landed
- 2026-09-10 `a1b2c3d`: [drizzle-orm 0.36.1 -> 0.38.0](https://github.com/acme/easton-duels/commit/a1b2c3d4e5f6) (minor). Adds relational query v2.
- 2026-09-11 `b2c3d4e`: [left-pad added at 1.3.0](https://github.com/acme/easton-duels/commit/b2c3d4e5f6a7) (minor).

### Upstream
- [ ] [vitest 3.2.0 -> 4.0.0](https://github.com/vitest-dev/vitest/releases/tag/v4.0.0) (major). Drops the vi.mocked overload. Breakage: three test files use the removed overload. [tier:: backlog]
- [react-router 7.1.0 -> 7.2.0](https://github.com/remix-run/react-router/releases/tag/v7.2.0) (minor). Adds data strategies.
- Patches: @types/node, typescript (2).

## portfolio

### Upstream
- [next 16.2.6 -> 17.0.0](https://github.com/vercel/next.js/releases/tag/v17.0.0) (major). No import sites found.

## recall

- fetch failed: git fetch failed: could not read from remote
```

Checkbox lines are actionable. The `[tier:: backlog]` field is an Obsidian
Dataview key, so a task query in the vault picks them up. In any other markdown
viewer it is inert text.

## What it watches

Each run syncs every repo in the allowlist with a partial clone
(`--filter=blob:none`), parses the direct dependencies, and collects findings
from three feeds.

| Feed | Source | What counts as a finding |
|---|---|---|
| Upstream | npm and PyPI registries, then the upstream repo's GitHub releases | The latest published version is newer than the version the repo pins. Classified as patch, minor or major. Release notes between the two versions are attached. |
| Landed | `git log --first-parent` since the head recorded by the last run | A commit changed a manifest and a dependency version moved, appeared or disappeared. Base image tags in Dockerfiles count. |
| Advisories | GitHub GraphQL `vulnerabilityAlerts` | An open Dependabot alert the previous runs did not report. |

Manifests it reads: `package.json` with `package-lock.json` or `pnpm-lock.yaml`
(workspaces included), `pyproject.toml` with `uv.lock`, `requirements.txt`, and
`FROM` lines in Dockerfiles. Locked versions win over ranges when a lockfile is
present.

The first run against a repo records its head and reports no landed changes.
A finding is reported once. Releases are keyed by target version and advisories
by GHSA permalink, so a package that keeps shipping shows up again only when a
newer version exists.

## How a finding is judged

Two tiers, chosen for cost. Tier one runs on everything. Tier two runs only
where it can change a decision.

1. **Tier one** sends every finding except patch releases to an OpenAI-compatible endpoint
   and asks for a two-sentence summary and a risk grade. This is meant for a
   local model. If the endpoint is down, the note falls back to the first line
   of the release notes or advisory and says so.
2. **Import site search** greps each repo for `import` and `require` of the
   package, capped at 20 hits. A major release of a package nothing imports is
   listed with "No import sites found" and is not actionable.
3. **Tier two** runs for major releases and high or critical advisories that
   have import sites. It receives the import sites plus the release notes and
   returns `breakage` and `actionable` as structured output. With
   `provider = "anthropic"` it uses the Claude API through `messages.parse`
   with a Pydantic schema. With `provider = "local"` it uses JSON mode on the
   same kind of endpoint as tier one. A per-run cap bounds the spend.

The judge fails closed. A high or critical advisory with import sites is
actionable no matter what tier two says. A finding that qualified for tier two
but did not get a read, because the cap was hit or the model was unavailable,
is marked actionable with a note saying why.

## Publishing

The note goes to `<folder>/<ISO week>.md` in the vault repo. depwatch clones
the vault the same way it clones watched repos, writes the file, commits with
the configured identity, and pushes to the default branch. A rejected push
triggers a fresh sync and a rebuild from the current file content, up to three
times, so a concurrent edit to the vault does not lose the digest.

A second digest in the same week appends a "Digest re-run" section instead of
replacing the note. State moves only after the push succeeds.

## Schedule

`depwatch serve` runs two jobs in the configured timezone.

| Job | When | Feeds | Writes |
|---|---|---|---|
| digest | Monday 07:00 | upstream, landed, advisories | The week's note |
| advisory | Tuesday to Sunday 07:00 | advisories | An "Advisory <date>" section, only when there is a new alert or a repo failed to sync |

A failed run posts to an [ntfy](https://ntfy.sh) topic when `NTFY_TOPIC` is set.

## Run it

Local, with [uv](https://docs.astral.sh/uv/) and git on the path:

```bash
uv sync
cp config.example.toml config.toml   # edit the vault, endpoints and allowlist
export GITHUB_TOKEN=$(gh auth token)
uv run depwatch digest --dry-run     # prints the note, publishes and records nothing
uv run depwatch digest               # publishes once
uv run pytest
```

As a container:

```bash
cp config.example.toml config.toml
cp .env.example .env                 # GITHUB_TOKEN, optional ANTHROPIC_API_KEY and NTFY_TOPIC
docker compose up -d --build
docker compose exec depwatch depwatch digest --dry-run
docker compose exec depwatch depwatch digest
```

`compose.yaml` mounts `config.toml` read-only and keeps clones and the SQLite
state in `./data`. The container runs as uid 1000 so that directory stays owned
by the host user. Change `user:` in `compose.yaml` if your uid differs.

## Configuration

`config.toml` holds everything that is not a secret. Secrets come from the
environment, or from `.env` under compose.

| Key | Meaning |
|---|---|
| `vault.repo` | `owner/name` of the repo that receives notes |
| `vault.folder` | Folder inside that repo, one note per ISO week |
| `vault.timezone` | Scheduler and timestamps. Default `UTC` |
| `vault.committer_name`, `vault.committer_email` | Identity on digest commits |
| `llm.tier1.base_url`, `llm.tier1.model` | OpenAI-compatible endpoint for summaries |
| `llm.tier2.provider` | `local` or `anthropic` |
| `llm.tier2.base_url`, `llm.tier2.model` | Endpoint and model for breakage reads. `base_url` defaults to tier one's |
| `llm.tier2.max_calls_per_run` | Cap on tier two calls per run. Default 10 |
| `repos.allowlist` | Repos to watch, `owner/name` |

| Variable | Meaning |
|---|---|
| `GITHUB_TOKEN` | Read on the watched repos, Dependabot alerts read, and contents write on the vault repo |
| `ANTHROPIC_API_KEY` | Required when tier two provider is `anthropic` |
| `NTFY_TOPIC` | Optional. Failure notifications |
| `DEPWATCH_DATA_DIR` | Clones and state. Default `data` |

The token never reaches the command line. Git authenticates through an
`GIT_ASKPASS` helper, and the token is scrubbed from any git error before it is
logged.

## Limits

- Registries: npm and PyPI. Docker base images appear in the landed feed only.
- Versions compare by numeric prefix. A pre-release suffix is ignored, so `4.0.0-rc.1` counts as `4.0.0`. Calendar versions compare as numbers, so a year bump reads as a major.
- Import search is a regex over source files, not an AST. Dynamic imports by string and re-exports through a local barrel file are missed.
- Release notes are read from the upstream repo's GitHub releases only, capped at 4000 characters. Packages that publish changelogs elsewhere get a bare version line.
- Dependabot alerts require Dependabot to be enabled on each watched repo.
- Both LLM tiers are best effort. Their absence is visible in the note, never silent.

## Development

```bash
uv run pytest
```

The renderer is tested against golden fixtures in `tests/fixtures/notes`. The
vault and repo layers run against real git repos created in a temp directory,
including the push race. GitHub, registry and model calls are stubbed at the
HTTP client.

## License

MIT.
