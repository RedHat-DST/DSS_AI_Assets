"""Local configuration for Red Hat Shadowbot Sales Assistant."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config.json"
DEFAULT_PROFILE = PROJECT_ROOT / "profiles" / "default"
DEFAULT_SESSION_FILE = PROJECT_ROOT / "session.json"

DEFAULTS = {
    "start_url": "https://shadowbot.io.redhat.com/agents/sales-assistant",
    "langgraph_api_url": "https://api.enterprise.redhat.com/sales-assistant",
    "assistant_id": "sales_assistant_v2",
    "sso_base_url": "https://auth.redhat.com/auth",
    "sso_realm": "EmployeeIDP",
    "sso_client_id": "shadowbot-ui",
    "cdp_port": 9225,
    "login_timeout_seconds": 600,
    "run_timeout_seconds": 300,
}


@dataclass
class ShadowbotConfig:
    start_url: str
    langgraph_api_url: str
    assistant_id: str
    sso_base_url: str
    sso_realm: str
    sso_client_id: str
    cdp_port: int
    login_timeout_seconds: int
    run_timeout_seconds: int
    profile: Path
    session_file: Path

    @property
    def token_url(self) -> str:
        return (
            f"{self.sso_base_url.rstrip('/')}/realms/{self.sso_realm}"
            "/protocol/openid-connect/token"
        )

    @property
    def userinfo_url(self) -> str:
        return (
            f"{self.sso_base_url.rstrip('/')}/realms/{self.sso_realm}"
            "/protocol/openid-connect/userinfo"
        )

    @property
    def issuer(self) -> str:
        return f"{self.sso_base_url.rstrip('/')}/realms/{self.sso_realm}"


def load_config() -> ShadowbotConfig:
    data = dict(DEFAULTS)
    if DEFAULT_CONFIG_FILE.exists():
        try:
            loaded = json.loads(DEFAULT_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if v is not None})
        except Exception:
            pass

    start_url = os.environ.get("SHADOWBOT_START_URL") or data["start_url"]
    api_url = os.environ.get("SHADOWBOT_LANGGRAPH_API_URL") or data["langgraph_api_url"]
    assistant = os.environ.get("SHADOWBOT_ASSISTANT_ID") or data["assistant_id"]
    sso_base = os.environ.get("SHADOWBOT_SSO_BASE_URL") or data["sso_base_url"]
    realm = os.environ.get("SHADOWBOT_SSO_REALM") or data["sso_realm"]
    client_id = os.environ.get("SHADOWBOT_SSO_CLIENT_ID") or data["sso_client_id"]
    port = int(os.environ.get("SHADOWBOT_CDP_PORT") or data["cdp_port"])
    login_timeout = int(os.environ.get("SHADOWBOT_LOGIN_TIMEOUT") or data["login_timeout_seconds"])
    run_timeout = int(os.environ.get("SHADOWBOT_RUN_TIMEOUT") or data["run_timeout_seconds"])
    profile = Path(os.environ.get("SHADOWBOT_PROFILE") or DEFAULT_PROFILE).expanduser().resolve()
    session_file = Path(
        os.environ.get("SHADOWBOT_SESSION_FILE") or DEFAULT_SESSION_FILE
    ).expanduser().resolve()

    return ShadowbotConfig(
        start_url=start_url,
        langgraph_api_url=api_url.rstrip("/"),
        assistant_id=assistant,
        sso_base_url=sso_base.rstrip("/"),
        sso_realm=realm,
        sso_client_id=client_id,
        cdp_port=port,
        login_timeout_seconds=login_timeout,
        run_timeout_seconds=run_timeout,
        profile=profile,
        session_file=session_file,
    )
