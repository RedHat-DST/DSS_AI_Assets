"""Local configuration for LinkedIn Sales Navigator."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import importlib.util

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config.json"
DEFAULT_PROFILE = PROJECT_ROOT / "profiles" / "default"
DEFAULT_SESSION_FILE = PROJECT_ROOT / "session.json"

_MCP_CHROME = importlib.util.spec_from_file_location(
    "mcp_chrome_shared",
    Path.home() / "mcps" / "mcp-chrome" / "shared.py",
)
_mcp_chrome_mod = importlib.util.module_from_spec(_MCP_CHROME)
assert _MCP_CHROME.loader is not None
_MCP_CHROME.loader.exec_module(_mcp_chrome_mod)

DEFAULTS = {
    "start_url": "https://www.linkedin.com/login",
    "sales_url": "https://www.linkedin.com/sales/homepage",
    "cdp_port": _mcp_chrome_mod.DEFAULT_CDP_PORT,
    "login_timeout_seconds": 600,
    "page_size": 25,
}


@dataclass
class SalesNavConfig:
    start_url: str
    sales_url: str
    cdp_port: int
    login_timeout_seconds: int
    page_size: int
    profile: Path
    session_file: Path


def load_config() -> SalesNavConfig:
    data = dict(DEFAULTS)
    if DEFAULT_CONFIG_FILE.exists():
        try:
            loaded = json.loads(DEFAULT_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if v is not None})
        except Exception:
            pass

    start_url = os.environ.get("SALESNAV_START_URL") or data["start_url"]
    sales_url = os.environ.get("SALESNAV_SALES_URL") or data["sales_url"]
    port = _mcp_chrome_mod.resolve_cdp_port("SALESNAV_CDP_PORT", data.get("cdp_port"))
    timeout = int(os.environ.get("SALESNAV_LOGIN_TIMEOUT") or data["login_timeout_seconds"])
    page_size = int(os.environ.get("SALESNAV_PAGE_SIZE") or data["page_size"])
    profile = _mcp_chrome_mod.resolve_profile("SALESNAV_PROFILE", data.get("profile"))
    session_file = Path(os.environ.get("SALESNAV_SESSION_FILE") or DEFAULT_SESSION_FILE).expanduser().resolve()

    return SalesNavConfig(
        start_url=start_url,
        sales_url=sales_url.rstrip("/"),
        cdp_port=port,
        login_timeout_seconds=timeout,
        page_size=page_size,
        profile=profile,
        session_file=session_file,
    )
