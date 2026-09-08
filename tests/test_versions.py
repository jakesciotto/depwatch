import pytest

from depwatch import versions as v


@pytest.mark.parametrize("text,expected", [
    ("1.2.3", (1, 2, 3)),
    ("v1.2.3", (1, 2, 3)),
    ("^1.2.3", (1, 2, 3)),
    ("1.2.3-beta.1", (1, 2, 3)),
    ("2024.1", (2024, 1)),
    ("3", (3,)),
    ("latest", None),
    ("", None),
])
def test_parse(text, expected):
    assert v.parse(text) == expected


@pytest.mark.parametrize("cur,latest,expected", [
    ("1.2.3", "1.2.4", "patch"),
    ("1.2.3", "1.3.0", "minor"),
    ("1.2.3", "2.0.0", "major"),
    ("1.2.3", "1.2.3", None),
    ("1.2.4", "1.2.3", None),
    ("0.36.1", "0.38.0", "minor"),
    ("0.36.1", "0.36.2", "patch"),
    ("3", "4", "major"),
    ("1.2", "1.2.1", "patch"),
    ("x", "1.0.0", None),
])
def test_gap(cur, latest, expected):
    assert v.gap(cur, latest) == expected


@pytest.mark.parametrize("spec,expected", [
    ("^1.2.3", "1.2.3"),
    ("~1.2.3", "1.2.3"),
    (">=3.1", "3.1"),
    (">=3.1,<4", "3.1"),
    ("~=2.0", "2.0"),
    ("==1.4.0", "1.4.0"),
    ("1.2.3", "1.2.3"),
    ("1.x", "1"),
    ("*", None),
    ("workspace:*", None),
    ("latest", None),
])
def test_floor(spec, expected):
    assert v.floor(spec) == expected


def test_newer():
    assert v.newer("1.10.0", "1.9.0")
    assert not v.newer("1.9.0", "1.10.0")
    assert not v.newer("x", "1.0.0")
