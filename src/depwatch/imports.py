import re
from pathlib import Path

CAP = 20
_SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "build"}
_JS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}


def _pattern(package: str, ecosystem: str) -> re.Pattern | None:
    if ecosystem == "npm":
        p = re.escape(package)
        return re.compile(rf"""(?:from\s*|import\s*\(?\s*|require\s*\(\s*)['"]{p}(?:/[^'"]*)?['"]""")
    if ecosystem == "pypi":
        mod = re.escape(package.replace("-", "_"))
        return re.compile(rf"^\s*(?:import\s+{mod}|from\s+{mod})(?=$|[.\s,])")
    return None


def find(checkout: Path, package: str, ecosystem: str) -> list[tuple[str, int, str]]:
    pat = _pattern(package, ecosystem)
    if pat is None:
        return []
    suffixes = _JS if ecosystem == "npm" else {".py"}
    hits: list[tuple[str, int, str]] = []
    for p in sorted(checkout.rglob("*")):
        rel = p.relative_to(checkout)
        if any(part in _SKIP for part in rel.parts) or p.suffix not in suffixes or not p.is_file():
            continue
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if pat.search(line):
                hits.append((rel.as_posix(), i, line.strip()))
                if len(hits) >= CAP:
                    return hits
    return hits
