#!/usr/bin/env python3
"""Rehydrate a masked Gmail draft payload before MCP/API create.

Reads masked JSON (to/cc/subject/body with [EMAIL_n] / [ACCT_n] tokens) + vault,
writes cleartext JSON for the tool executor only — never paste cleartext in chat.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pii_vault import PiiVault


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, required=True)
    ap.add_argument("--in", dest="infile", type=Path, required=True)
    ap.add_argument("--out", dest="outfile", type=Path, required=True)
    args = ap.parse_args()

    vault = PiiVault.load(args.vault)
    data = json.loads(args.infile.read_text(encoding="utf-8"))
    clear = vault.rehydrate_obj(data)
    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    args.outfile.write_text(json.dumps(clear, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rehydrated → {args.outfile} (do not paste in chat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
