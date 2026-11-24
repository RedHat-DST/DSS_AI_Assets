"""SSO session for Red Hat Shadowbot (Sales Assistant).

Unlike Gmail/Drive (OAuth refresh tokens), Shadowbot sits behind associate
SSO and FreeOTP. Sessions expire. Auth therefore:

1. Opens (or reconnects to) a persistent Chrome window
2. Lets you complete SSO + FreeOTP in that window
3. Harvests the Keycloak access token (network Authorization header or
   localStorage oidc user)
4. Leaves Chrome running so the next login is faster
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from .chrome import (
    HARVEST_JS,
    connect_over_cdp,
    disconnect_leave_chrome,
    log,
    looks_logged_in,
    pick_best_page_sync,
    spawn_chrome_cdp,
)
from .config import ShadowbotConfig, load_config
from .langgraph import (
    LangGraphClient,
    SessionExpired,
    decode_jwt_claims,
    probe_identity,
    refresh_access_token,
)

AUTH_INSTRUCTIONS = (
    "Red Hat associate login required for Shadowbot (Sales Assistant).\n\n"
    "A Chrome window is open. Sign in with your Red Hat associate account "
    "(SSO at auth.redhat.com — same as other internal apps) and enter your "
    "FreeOTP code. Wait until Sales Assistant loads "
    "(shadowbot.io.redhat.com/agents/sales-assistant), not the IdP page.\n\n"
    "This MCP uses your associate session. Never paste your associate "
    "password or OTP into chat.\n\n"
    "Then call shadowbot_auth again. Chrome stays open so later FreeOTP "
    "prompts are faster when Shadowbot kicks you out."
)


class AuthRequired(RuntimeError):
    """Raised when the agent/user must complete SSO + FreeOTP."""

    def __init__(self, message: str = AUTH_INSTRUCTIONS):
        super().__init__(message)


class ShadowbotAuth:
    def __init__(self, config: Optional[ShadowbotConfig] = None):
        self.config = config or load_config()
        self._session: dict | None = None
        self._client: LangGraphClient | None = None

    def session_path(self):
        return self.config.session_file

    def load_session(self) -> dict | None:
        path = self.session_path()
        if not path.exists():
            self._session = None
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._session = None
            return None
        if not isinstance(data, dict) or not data.get("access_token"):
            self._session = None
            return None
        self._session = data
        return data

    def save_session(self, session: dict) -> None:
        path = self.session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(session, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except Exception:
            pass
        self._session = session
        self._client = None

    def clear_client(self) -> None:
        self._client = None

    async def probe_saved_session(self) -> dict | None:
        session = self.load_session()
        if not session:
            return None
        token = session.get("access_token")
        if not token:
            return None
        try:
            identity = await probe_identity(token, self.config.userinfo_url)
        except SessionExpired:
            refresh = session.get("refresh_token")
            if not refresh:
                return None
            try:
                refreshed = await refresh_access_token(
                    refresh, self.config.token_url, self.config.sso_client_id
                )
            except SessionExpired:
                return None
            session["access_token"] = refreshed["access_token"]
            if refreshed.get("refresh_token"):
                session["refresh_token"] = refreshed["refresh_token"]
            session["token_type"] = refreshed.get("token_type") or "Bearer"
            identity = await probe_identity(session["access_token"], self.config.userinfo_url)
        except Exception as e:
            log(f"Session probe failed: {e}")
            return None
        session.update(identity)
        session["checked_at"] = datetime.now(timezone.utc).isoformat()
        self.save_session(session)
        return session

    def _on_api_request(self, request, sink: list[dict]) -> None:
        url = (request.url or "").lower()
        if "api.enterprise.redhat.com" not in url and "auth.redhat.com" not in url:
            return
        headers = {str(k).lower(): v for k, v in (request.headers or {}).items()}
        auth = headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            if token and token.count(".") == 2:
                sink.append({"access_token": token, "source": "network", "url": request.url})

    async def _collect_storage_tokens(self, context) -> list[dict]:
        found: list[dict] = []
        for page in list(context.pages):
            try:
                url = page.url or ""
            except Exception:
                url = ""
            if "shadowbot" not in url.lower() and "redhat.com" not in url.lower():
                continue
            try:
                data = await page.evaluate(HARVEST_JS)
            except Exception as e:
                log(f"Token harvest skipped for {url}: {e}")
                continue
            for row in (data or {}).get("tokens") or []:
                if row.get("access_token"):
                    found.append(row)
        return found

    def _dedupe(self, rows: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for row in rows:
            token = row.get("access_token")
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(row)
        return out

    async def _probe_candidates(self, candidates: list[dict]) -> dict:
        last_err: Exception | None = None
        for cand in candidates:
            token = cand.get("access_token")
            if not token:
                continue
            try:
                identity = await probe_identity(token, self.config.userinfo_url)
            except SessionExpired as e:
                last_err = e
                continue
            except Exception as e:
                last_err = e
                continue
            return {**cand, **identity}
        if last_err:
            raise last_err
        raise AuthRequired()

    async def harvest_from_chrome(self, *, navigate: bool, wait: bool) -> dict:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "playwright is not installed. From shadowbot-assistant run:\n"
                "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n"
                "  .venv/bin/playwright install chromium"
            ) from e

        spawn_chrome_cdp(self.config.profile, self.config.cdp_port)
        browser = None
        live: list[dict] = []
        async with async_playwright() as p:
            try:
                browser, context, page = await connect_over_cdp(p, self.config.cdp_port)
                context.on("request", lambda req: self._on_api_request(req, live))
                if navigate:
                    log(f"Opening Shadowbot -> {self.config.start_url}")
                    try:
                        await page.goto(
                            self.config.start_url,
                            wait_until="domcontentloaded",
                            timeout=120_000,
                        )
                    except Exception as e:
                        log(f"Initial goto warning: {e} (complete login in Chrome)")
                    await page.wait_for_timeout(1500)

                logged_in = await looks_logged_in(page)
                if not logged_in and wait:
                    logged_in = await self._wait_for_login(context, page)
                    page = pick_best_page_sync(list(context.pages)) or page

                if not logged_in and not live:
                    raise AuthRequired()

                try:
                    await page.reload(wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(3500)
                except Exception as e:
                    log(f"Reload to capture live token: {e}")
                    await page.wait_for_timeout(2000)

                stored = await self._collect_storage_tokens(context)
                if not live and not stored:
                    for _ in range(8):
                        await asyncio.sleep(1.5)
                        stored = await self._collect_storage_tokens(context)
                        if live or stored:
                            break

                candidates = self._dedupe(live + stored)
                log(f"Harvest candidates: live={len(live)} storage={len(stored)} unique={len(candidates)}")
                if not candidates:
                    raise AuthRequired(
                        "Logged into Shadowbot but no Keycloak access token was captured. "
                        "Wait until Sales Assistant finishes loading, then call shadowbot_auth again."
                    )

                try:
                    probed = await self._probe_candidates(candidates)
                except SessionExpired as e:
                    raise AuthRequired(
                        "Shadowbot is open in Chrome, but the harvested session was rejected "
                        f"({e}). Call shadowbot_auth with force=true after finishing SSO.\n\n"
                        + AUTH_INSTRUCTIONS
                    ) from e

                page_url = ""
                try:
                    page_url = page.url or ""
                except Exception:
                    pass
                claims = decode_jwt_claims(probed["access_token"])
                session = {
                    "access_token": probed["access_token"],
                    "refresh_token": probed.get("refresh_token"),
                    "token_type": "Bearer",
                    "page_url": page_url,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "email": probed.get("email") or claims.get("email"),
                    "name": probed.get("name") or claims.get("name"),
                    "preferred_username": probed.get("preferred_username")
                    or claims.get("preferred_username"),
                    "sub": probed.get("sub") or claims.get("sub"),
                    "source": probed.get("source"),
                    "langgraph_api_url": self.config.langgraph_api_url,
                    "assistant_id": self.config.assistant_id,
                    "ok": True,
                }
                self.save_session(session)
                log(f"Harvested Shadowbot session for {session.get('email') or session.get('name')}")
                return session
            finally:
                if browser is not None:
                    await disconnect_leave_chrome(browser)

    async def _wait_for_login(self, context, page) -> bool:
        timeout = self.config.login_timeout_seconds
        ready_path = self.config.profile / "user_ready"
        log("=" * 60)
        log("ACTION REQUIRED — RED HAT ASSOCIATE SSO + FreeOTP")
        log("1. In the Chrome window, sign in with your Red Hat associate account.")
        log("2. Enter your FreeOTP code (same token as other Red Hat apps).")
        log("3. Wait until Sales Assistant is visible (shadowbot.io.redhat.com).")
        log(f"   Auto-detect timeout: {timeout}s")
        log(f"   Or create this file to continue: {ready_path}")
        log("=" * 60)

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            page = pick_best_page_sync(list(context.pages)) or page
            try:
                if await looks_logged_in(page):
                    log(f"Login detected -> {page.url}")
                    return True
            except Exception:
                pass
            if ready_path.exists():
                try:
                    ready_path.unlink()
                except Exception:
                    pass
                log("Ready sentinel seen — harvesting session.")
                return True
            await asyncio.sleep(2)
        return False

    async def authenticate(self, *, force_login: bool = False, wait: bool = False) -> dict:
        """Return a valid session, opening Chrome / waiting for SSO as needed."""
        if not force_login:
            session = await self.probe_saved_session()
            if session:
                return session
            try:
                return await self.harvest_from_chrome(navigate=True, wait=False)
            except AuthRequired:
                if not wait:
                    raise
            except Exception as e:
                log(f"Harvest without wait failed: {e}")
                if not wait:
                    raise AuthRequired(f"{AUTH_INSTRUCTIONS}\n\nDetails: {e}") from e

        return await self.harvest_from_chrome(navigate=True, wait=True)

    async def ensure_client(self) -> LangGraphClient:
        session = await self.authenticate(wait=False)
        if self._client is None:
            self._client = LangGraphClient(
                token=session["access_token"],
                api_url=session.get("langgraph_api_url") or self.config.langgraph_api_url,
                assistant_id=session.get("assistant_id") or self.config.assistant_id,
                timeout=self.config.run_timeout_seconds,
                config=self.config,
            )
        return self._client

    def status_dict(self) -> dict:
        session = self.load_session() or {}
        return {
            "authenticated": bool(session.get("access_token")),
            "email": session.get("email"),
            "name": session.get("name"),
            "preferred_username": session.get("preferred_username"),
            "assistant_id": session.get("assistant_id") or self.config.assistant_id,
            "langgraph_api_url": session.get("langgraph_api_url") or self.config.langgraph_api_url,
            "thread_id": session.get("thread_id"),
            "captured_at": session.get("captured_at"),
            "checked_at": session.get("checked_at"),
            "chrome_cdp_alive": _cdp_status(self.config.cdp_port),
            "cdp_port": self.config.cdp_port,
        }


def _cdp_status(port: int) -> bool:
    from .chrome import cdp_alive

    return cdp_alive(port)


_default_auth: Optional[ShadowbotAuth] = None


def get_auth() -> ShadowbotAuth:
    global _default_auth
    if _default_auth is None:
        _default_auth = ShadowbotAuth()
    return _default_auth
