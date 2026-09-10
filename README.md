# depwatch

Weekly dependency digest for your GitHub repos, as one markdown note.
Upstream releases, dependency bumps that landed, and advisories from Dependabot and OSV.dev.
Lines that need action come back as checkboxes.

## Install

```bash
uv tool install git+https://github.com/jakesciotto/depwatch
```

## Use

Write `config.toml`:

```toml
[repos]
allowlist = ["you/app", "you/api"]
```

Run:

```bash
export GITHUB_TOKEN=$(gh auth token)
depwatch digest --dry-run
```

That prints the note:

```markdown
## app

### Upstream
- [ ] [vitest 3.2.0 -> 4.0.0](https://github.com/vitest-dev/vitest/releases/tag/v4.0.0) (major). Breakage read unavailable. [tier:: backlog]
- Patches: @types/node, typescript (2).
```

To get it every Monday in a git repo instead, add a vault and run the scheduler:

```toml
[vault]
repo = "you/notes"
```

```bash
depwatch serve
```

Or clone, copy `.env.example` to `.env`, and `docker compose up -d`.

Summaries and breakage reads need a model. `config.example.toml` shows the two optional sections.

MIT.
