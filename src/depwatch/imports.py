import os
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
    for dirpath, dirnames, filenames in os.walk(checkout):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP)
        for name in sorted(filenames):
            p = Path(dirpath, name)
            if p.suffix not in suffixes:
                continue
            rel = p.relative_to(checkout)
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
