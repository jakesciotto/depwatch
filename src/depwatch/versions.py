import re
from typing import Literal

Gap = Literal["patch", "minor", "major"]

_NUM = re.compile(r"^v?(\d+(?:\.\d+)*)")
_FLOOR = re.compile(r"^(?:\^|~=|~|>=|==|>)?\s*v?(\d+(?:\.\d+)*)")


def parse(text: str) -> tuple[int, ...] | None:
    m = _NUM.match(text.strip().lstrip("^~>=<! "))
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def _pad(t: tuple[int, ...], n: int) -> tuple[int, ...]:
    return t + (0,) * (n - len(t))


def newer(a: str, b: str) -> bool:
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return False
    n = max(len(pa), len(pb))
    return _pad(pa, n) > _pad(pb, n)


def gap(current: str, latest: str) -> Gap | None:
    pc, pl = parse(current), parse(latest)
    if pc is None or pl is None:
        return None
    n = max(len(pc), len(pl), 3)
    pc, pl = _pad(pc, n), _pad(pl, n)
    if pl <= pc:
        return None
    if pl[0] != pc[0]:
        return "major"
    if pl[1] != pc[1]:
        return "minor"
    return "patch"


def floor(spec: str) -> str | None:
    first = spec.split(",")[0].split("||")[0].strip()
    m = _FLOOR.match(first)
    if not m:
        return None
    return m.group(1)
