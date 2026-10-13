"""Pairing: a short, one-time code that hands a device its panel's address.

A panel's address carries a 43-character key, which is no fun to type on a
watch. An admin creates a 6-digit code for a panel (an admin-only action); the
device sends it to `/kid_panel/pair/api` within ten minutes and gets the
panel's address back. A code works once. Wrong codes count as failed logins
(so Home Assistant's IP banning applies when it's enabled), and after a run of
them every outstanding code is withdrawn and pairing pauses for a while.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
import secrets
import time

from aiohttp import web

from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.ban import process_wrong_login
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_KEY, DOMAIN, URL_BASE

CODE_LIFETIME = 600.0
CODE_DIGITS = 6
FAILURE_LIMIT = 10
FAILURE_WINDOW = 600.0
LOCKOUT = 600.0

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet, noimageindex, noai, noimageai",
}


@dataclass
class _Code:
    entry_id: str
    expires: float


class PairingCodes:
    """Outstanding codes, at most one per panel, and the failure count."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._codes: dict[str, _Code] = {}
        self._failures: deque[float] = deque()
        self._locked_until = 0.0

    def create(self, entry_id: str) -> str:
        """Return a fresh code for a panel, replacing any it had."""
        self._prune()
        self._codes = {c: v for c, v in self._codes.items() if v.entry_id != entry_id}
        while True:
            code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
            if code not in self._codes:
                break
        self._codes[code] = _Code(entry_id, self._clock() + CODE_LIFETIME)
        return code

    def redeem(self, code: str) -> str | None:
        """Return the panel a code belongs to and use it up, or None."""
        now = self._clock()
        self._prune()
        if now < self._locked_until:
            return None
        found = None
        for candidate, value in self._codes.items():
            if secrets.compare_digest(candidate.encode(), code.encode()):
                found = candidate, value
        if found is None:
            self._fail(now)
            return None
        del self._codes[found[0]]
        return found[1].entry_id

    @property
    def locked(self) -> bool:
        return self._clock() < self._locked_until

    def _fail(self, now: float) -> None:
        self._failures.append(now)
        while self._failures and now - self._failures[0] > FAILURE_WINDOW:
            self._failures.popleft()
        if len(self._failures) >= FAILURE_LIMIT:
            self._codes.clear()
            self._failures.clear()
            self._locked_until = now + LOCKOUT

    def _prune(self) -> None:
        now = self._clock()
        self._codes = {c: v for c, v in self._codes.items() if v.expires > now}


def pairing_codes(hass: HomeAssistant) -> PairingCodes:
    """The one PairingCodes for this Home Assistant run."""
    return hass.data.setdefault(f"{DOMAIN}_pairing", PairingCodes())


def notify_code(hass: HomeAssistant, title: str, entry_id: str, code: str) -> None:
    """Show the code to admins in Home Assistant's notifications."""
    persistent_notification.async_create(
        hass,
        f"Pairing code for **{title}**: **{code}**\n\nValid for 10 minutes, once. "
        f"Enter it in the watch app, or open `{URL_BASE}/pair` on the device.",
        title="Kid Panel pairing code",
        notification_id=f"{DOMAIN}_pairing_{entry_id}",
    )


class PairPageView(HomeAssistantView):
    """A page where a device's browser enters a code."""

    url = URL_BASE + "/pair"
    name = "api:kid_panel:pair_page"
    requires_auth = False
    cors_allowed = False

    def __init__(self, hass: HomeAssistant, page: Path) -> None:
        self.hass = hass
        self._page = page

    async def get(self, request: web.Request) -> web.Response:
        page = await self.hass.async_add_executor_job(self._page.read_text, "utf-8")
        nonce = secrets.token_urlsafe(16)
        headers = {
            **_SECURITY_HEADERS,
            "Content-Security-Policy": (
                "default-src 'none'; "
                f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
        }
        return web.Response(
            text=page.replace("__NONCE__", nonce),
            content_type="text/html",
            charset="utf-8",
            headers=headers,
        )


class PairApiView(HomeAssistantView):
    """Trade a code for a panel's address."""

    url = URL_BASE + "/pair/api"
    name = "api:kid_panel:pair_api"
    requires_auth = False
    cors_allowed = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        def reply(data: dict, status: int) -> web.Response:
            return web.json_response(data, status=status, headers=_SECURITY_HEADERS)

        if request.content_length is None or request.content_length > 256:
            return reply({"error": "bad_request"}, HTTPStatus.BAD_REQUEST)
        try:
            body = await request.json()
        except ValueError:
            return reply({"error": "bad_request"}, HTTPStatus.BAD_REQUEST)
        code = body.get("code") if isinstance(body, dict) else None
        if not isinstance(code, str) or len(code) != CODE_DIGITS or not code.isdigit():
            return reply({"error": "bad_request"}, HTTPStatus.BAD_REQUEST)

        codes = pairing_codes(self.hass)
        if codes.locked:
            return reply({"error": "locked"}, HTTPStatus.TOO_MANY_REQUESTS)
        entry_id = codes.redeem(code)
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            await process_wrong_login(request)
            return reply({"error": "invalid_code"}, HTTPStatus.FORBIDDEN)

        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_pairing_{entry.entry_id}")
        return reply(
            {"path": f"{URL_BASE}/{entry.data[CONF_ACCESS_KEY]}", "title": entry.title},
            HTTPStatus.OK,
        )
