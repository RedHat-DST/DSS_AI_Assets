#!/usr/bin/env python3
"""Enrich territory account JSON with RHSC Sales Group, Global Sales Group, and revenue."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SALESCLOUD_ROOT = PROJECT_ROOT.parent / "salescloud-assistant"
ENRICH_SCRIPT = SALESCLOUD_ROOT / "scripts" / "enrich_territory_accounts.py"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--accounts",
        default=str(PROJECT_ROOT / "output/nl_core_territory2_accounts.json"),
    )
    parser.add_argument("--output", default=None, help="Defaults to --accounts (in-place)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--delay", type=float, default=0.12)
    args = parser.parse_args()

    python = SALESCLOUD_ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)

    cmd = [
        str(python),
        str(ENRICH_SCRIPT),
        args.accounts,
        "--concurrency",
        str(args.concurrency),
        "--delay",
        str(args.delay),
    ]
    if args.output:
        cmd.extend(["--output", args.output])
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
