from pathlib import Path

from depwatch import imports


def test_npm_import_forms(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.ts").write_text("import { Hono } from 'hono'\nimport x from 'hono/cors'\nconst y = require(\"hono\")\nimport 'honoke'\n")
    (tmp_path / "src/b.js").write_text("import('hono')\n")
    (tmp_path / "node_modules/hono/index.js").parent.mkdir(parents=True)
    (tmp_path / "node_modules/hono/index.js").write_text("import 'hono'\n")
    assert imports.find(tmp_path, "hono", "npm") == [
        ("src/a.ts", 1, "import { Hono } from 'hono'"), ("src/a.ts", 2, "import x from 'hono/cors'"),
        ("src/a.ts", 3, 'const y = require("hono")'), ("src/b.js", 1, "import('hono')")]


def test_scoped_npm_package(tmp_path: Path):
    (tmp_path / "a.tsx").write_text('import { z } from "@scope/pkg";\n')
    assert imports.find(tmp_path, "@scope/pkg", "npm") == [("a.tsx", 1, 'import { z } from "@scope/pkg";')]


def test_python_forms(tmp_path: Path):
    (tmp_path / "m.py").write_text("import psycopg\nfrom psycopg.rows import dict_row\nimport psycopg_pool\nfrom psycopg import sql\n")
    assert [l for _, l, _ in imports.find(tmp_path, "psycopg", "pypi")] == [1, 2, 4]


def test_python_dashed_name(tmp_path: Path):
    (tmp_path / "m.py").write_text("import python_dateutil\n")
    assert len(imports.find(tmp_path, "python-dateutil", "pypi")) == 1


def test_cap_and_docker(tmp_path: Path):
    (tmp_path / "big.ts").write_text("import 'x'\n" * 30)
    assert len(imports.find(tmp_path, "x", "npm")) == 20
    assert imports.find(tmp_path, "node", "docker") == []


def test_results_sorted_by_path_before_walk_order(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "z.ts").write_text("import 'x'\n")
    (tmp_path / "src/a.ts").write_text("import 'x'\n")
    assert imports.find(tmp_path, "x", "npm") == [("src/a.ts", 1, "import 'x'"), ("z.ts", 1, "import 'x'")]


def test_cap_keeps_lowest_paths(tmp_path: Path):
    (tmp_path / "z.ts").write_text("import 'x'\n" * 30)
    (tmp_path / "a.ts").write_text("import 'x'\n")
    results = imports.find(tmp_path, "x", "npm")
    assert len(results) == 20
    assert results[0][0] == "a.ts"
