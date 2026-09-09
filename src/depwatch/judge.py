import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import anthropic
import httpx
from pydantic import BaseModel

from . import imports
from .models import Finding

TIER1_SYSTEM = ('You summarise dependency changes for a software engineer. Reply with JSON only: '
                '{"summary": "<at most two sentences>", "risk": "low"|"medium"|"high"}.')
TIER2_SYSTEM = ("You review a dependency change against the code that uses it. Name the affected files and "
                "lines in plain sentences. Set actionable true when the engineer must change code or upgrade "
                "to stay safe.")
CAP_NOTE = "not analysed: run cap reached"
log = logging.getLogger("depwatch")
_RISKS = {"low", "medium", "high"}


class Breakage(BaseModel):
    breakage: str
    actionable: bool


def _header(f: Finding) -> str:
    return (f"Repo: {f.repo}\nPackage: {f.package} ({f.ecosystem})\n"
            f"Change: {f.kind} {f.current} -> {f.target} ({f.severity})\n\n")


class Tier1:
    def __init__(self, client: httpx.Client, base_url: str, model: str):
        self.client, self.base_url, self.model = client, base_url.rstrip("/"), model
        self.available = True

    def annotate(self, f: Finding) -> None:
        if not self.available:
            return
        body = {"model": self.model, "temperature": 0, "max_tokens": 300,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": TIER1_SYSTEM},
                             {"role": "user", "content": _header(f) + f.raw}]}
        try:
            r = self.client.post(f"{self.base_url}/chat/completions", json=body, timeout=120)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except httpx.TransportError:
            self.available = False
            return
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            return
        summary, risk = data.get("summary"), data.get("risk")
        if isinstance(summary, str) and risk in _RISKS:
            f.summary, f.risk = summary.strip(), risk


class Tier2:
    def __init__(self, client: anthropic.Anthropic, model: str, max_calls: int):
        self.client, self.model, self.max_calls = client, model, max_calls
        self.calls = 0
        self.available = True

    def read(self, f: Finding) -> None:
        if not self.available:
            return
        sites = "\n".join(f"{p}:{n}: {t}" for p, n, t in f.import_sites)
        content = _header(f) + f"Import sites:\n{sites}\n\nRelease notes or advisory:\n{f.raw}"
        try:
            self.calls += 1
            r = self.client.messages.parse(model=self.model, max_tokens=2000, system=TIER2_SYSTEM,
                                            messages=[{"role": "user", "content": content}],
                                            output_format=Breakage)
        except Exception as e:
            if isinstance(e, (anthropic.APIConnectionError, anthropic.AuthenticationError, TypeError)):
                self.available = False
            log.warning("tier two read for %s: %s", f.package, type(e).__name__)
            return
        parsed = r.parsed_output
        if parsed is not None:
            f.breakage, f.actionable = parsed.breakage.strip(), parsed.actionable


class LocalTier2:
    def __init__(self, client: httpx.Client, base_url: str, model: str, max_calls: int):
        self.client, self.base_url, self.model, self.max_calls = client, base_url.rstrip("/"), model, max_calls
        self.calls = 0
        self.available = True

    def read(self, f: Finding) -> None:
        if not self.available:
            return
        sites = "\n".join(f"{p}:{n}: {t}" for p, n, t in f.import_sites)
        content = _header(f) + f"Import sites:\n{sites}\n\nRelease notes or advisory:\n{f.raw}"
        system = TIER2_SYSTEM + ' Reply with JSON only in the form {"breakage": "<sentences>", "actionable": true|false}.'
        body = {"model": self.model, "temperature": 0, "max_tokens": 4000,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        self.calls += 1
        try:
            r = self.client.post(f"{self.base_url}/chat/completions", json=body, timeout=600)
            r.raise_for_status()
            choice = r.json()["choices"][0]
        except httpx.TransportError:
            self.available = False
            return
        except Exception as e:
            log.warning("local tier two read for %s: %s", f.package, type(e).__name__)
            return
        raw = choice.get("message", {}).get("content")
        if choice.get("finish_reason") == "length" or not isinstance(raw, str) or not raw:
            log.warning("tier two truncated for %s", f.package)
            return
        try:
            parsed = Breakage.model_validate(json.loads(raw))
        except Exception as e:
            log.warning("local tier two read for %s: %s", f.package, type(e).__name__)
            return
        f.breakage, f.actionable = parsed.breakage.strip(), parsed.actionable


TierTwo = Tier2 | LocalTier2


@dataclass(frozen=True)
class JudgeReport:
    tier1_available: bool
    tier2_available: bool
    tier2_capped: int


def run(findings: list[Finding], checkout_for: Callable[[str], Path | None], tier1: Tier1, tier2: TierTwo) -> JudgeReport:
    for f in findings:
        if f.kind in ("release", "advisory"):
            checkout = checkout_for(f.repo)
            if checkout is not None:
                f.import_sites = imports.find(checkout, f.package, f.ecosystem)
        if f.kind == "release" and f.severity == "patch":
            continue
        tier1.annotate(f)
    capped = 0
    for f in findings:
        if not f.qualifies_for_tier2:
            continue
        if tier2.calls >= tier2.max_calls:
            f.breakage = CAP_NOTE
            capped += 1
            continue
        tier2.read(f)
    for f in findings:
        if f.kind == "advisory" and f.severity in ("high", "critical"):
            f.actionable = True
        elif f.qualifies_for_tier2 and (f.breakage is None or f.breakage == CAP_NOTE):
            f.actionable = True
    return JudgeReport(tier1.available, tier2.available, capped)
