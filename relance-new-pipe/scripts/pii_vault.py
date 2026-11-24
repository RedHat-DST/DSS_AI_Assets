#!/usr/bin/env python3
"""Collect / Mask / Rehydrate helpers for agent skills (RGPD-minded).

The LLM should reason on tokens like [EMAIL_1]. Real values stay in a
short-lived local vault JSON and are rehydrated only at tool execution
(Gmail draft create, SF field update).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Currency / ACV-style amounts (avoid masking years like 2026)
AMOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:€|\$|USD|EUR)\s?\d[\d\s.,]*|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b"
)


class PiiVault:
    def __init__(self) -> None:
        self.map: dict[str, str] = {}  # token -> raw
        self._rev: dict[str, str] = {}  # normalized raw -> token
        self._counts: dict[str, int] = {}

    def _next(self, kind: str) -> str:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return f"[{kind}_{self._counts[kind]}]"

    def mask_value(self, kind: str, value: str | None) -> str:
        if value is None:
            return ""
        raw = str(value).strip()
        if not raw:
            return ""
        key = f"{kind}:{raw.lower()}" if kind == "EMAIL" else f"{kind}:{raw}"
        if key in self._rev:
            return self._rev[key]
        tok = self._next(kind)
        self.map[tok] = raw
        self._rev[key] = tok
        return tok

    def mask_emails_in_text(self, text: str) -> str:
        if not text:
            return text

        def repl(m: re.Match[str]) -> str:
            return self.mask_value("EMAIL", m.group(0))

        return EMAIL_RE.sub(repl, text)

    def mask_amounts_in_text(self, text: str) -> str:
        if not text:
            return text

        def repl(m: re.Match[str]) -> str:
            return self.mask_value("ACV", m.group(0))

        return AMOUNT_RE.sub(repl, text)

    def mask_text(self, text: str, *, amounts: bool = False) -> str:
        out = self.mask_emails_in_text(text)
        if amounts:
            out = self.mask_amounts_in_text(out)
        return out

    def rehydrate(self, text: str) -> str:
        if not text:
            return text
        out = text
        # Longer tokens first so [EMAIL_10] before [EMAIL_1]
        for tok in sorted(self.map.keys(), key=len, reverse=True):
            out = out.replace(tok, self.map[tok])
        return out

    def rehydrate_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.rehydrate(obj)
        if isinstance(obj, list):
            return [self.rehydrate_obj(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.rehydrate_obj(v) for k, v in obj.items()}
        return obj

    def mask_record(
        self,
        row: dict[str, Any],
        field_kinds: dict[str, str],
        *,
        text_fields: list[str] | None = None,
        mask_amounts_in: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a copy with selected fields replaced by tokens."""
        out = dict(row)
        for field, kind in field_kinds.items():
            if field in out and out[field] not in (None, ""):
                out[field] = self.mask_value(kind, str(out[field]))
        for field in text_fields or []:
            if field in out and isinstance(out[field], str):
                out[field] = self.mask_text(
                    out[field], amounts=field in (mask_amounts_in or [])
                )
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"map": self.map, "counts": self._counts}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PiiVault":
        v = cls()
        v.map = dict(data.get("map") or {})
        v._counts = dict(data.get("counts") or {})
        for tok, raw in v.map.items():
            kind = tok.strip("[]").rsplit("_", 1)[0]
            key = f"{kind}:{raw.lower()}" if kind == "EMAIL" else f"{kind}:{raw}"
            v._rev[key] = tok
        return v

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "PiiVault":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def scrub_followup_drafted(drafted: list[dict[str, Any]], vault: PiiVault) -> list[dict[str, Any]]:
    """Mask contact fields for agent-visible / chat-safe results."""
    masked: list[dict[str, Any]] = []
    for item in drafted:
        m = dict(item)
        if m.get("to"):
            m["to"] = vault.mask_value("EMAIL", str(m["to"]))
        if m.get("cc"):
            # cc may be comma-separated
            parts = [p.strip() for p in str(m["cc"]).split(",") if p.strip()]
            m["cc"] = ", ".join(vault.mask_value("EMAIL", p) for p in parts)
        if m.get("subject"):
            m["subject"] = vault.mask_emails_in_text(str(m["subject"]))
        # Keep account / stage / ids — needed for reasoning; no personal emails
        masked.append(m)
    return masked


def main() -> int:
    p = argparse.ArgumentParser(description="Mask or rehydrate text/JSON via a PII vault")
    p.add_argument("action", choices=["mask", "rehydrate", "mask-json", "rehydrate-json"])
    p.add_argument("--vault", type=Path, required=True)
    p.add_argument("--in", dest="infile", type=Path, required=True)
    p.add_argument("--out", dest="outfile", type=Path, required=True)
    p.add_argument("--amounts", action="store_true", help="Also mask ACV-like amounts")
    args = p.parse_args()

    vault = PiiVault.load(args.vault) if args.vault.exists() else PiiVault()
    raw = args.infile.read_text(encoding="utf-8")

    if args.action == "mask":
        out = vault.mask_text(raw, amounts=args.amounts)
        vault.save(args.vault)
    elif args.action == "rehydrate":
        out = vault.rehydrate(raw)
    elif args.action == "mask-json":
        data = json.loads(raw)
        # Best-effort: stringify → mask emails → parse back only for strings via walk
        def walk(o: Any) -> Any:
            if isinstance(o, str):
                return vault.mask_text(o, amounts=args.amounts)
            if isinstance(o, list):
                return [walk(x) for x in o]
            if isinstance(o, dict):
                return {k: walk(v) for k, v in o.items()}
            return o

        out = json.dumps(walk(data), indent=2, ensure_ascii=False)
        vault.save(args.vault)
    else:
        data = json.loads(raw)
        out = json.dumps(vault.rehydrate_obj(data), indent=2, ensure_ascii=False)

    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    args.outfile.write_text(out, encoding="utf-8")
    print(f"Wrote {args.outfile} (vault tokens: {len(vault.map)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
