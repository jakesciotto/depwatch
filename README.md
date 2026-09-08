# depwatch

Watches an allowlist of GitHub repos for upstream releases, landed manifest
changes, and Dependabot advisories. Writes a weekly digest note into the
Obsidian vault by pushing to the vault's git remote. Runs on vinelab.

## Deploy (vinelab)

1. `ssh jake@vinelab 'cd ~/github/depwatch && git pull'`
2. Write `~/github/depwatch/.env` (mode 600) with `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `NTFY_TOPIC`, `DEPWATCH_DATA_DIR=/data`.
3. `docker compose up -d --build`
4. `docker compose exec depwatch depwatch digest --dry-run` and read the output.
5. `docker compose exec depwatch depwatch digest` to publish once by hand.

The container runs as uid 1000, which is jake on vinelab, so `./data` stays owned by jake.

The compose project name is the directory name. Keep exactly one checkout on vinelab.

## Local development

```bash
uv sync
uv run pytest
GITHUB_TOKEN=$(gh auth token) uv run depwatch digest --dry-run
```
