"""HTTP views for Kid Panel.

Every view is unauthenticated by Home Assistant's standard: the access key in
the path is the credential. Everything a request may reach is decided here,
from the entry's options, never from the request:

- the page and its state list only the entry's control, view and remote
  entities, with a fixed set of attributes each;
- an action must name one of the entry's control entities (or its remote) and
  one of the actions in `ACTIONS` for that entity's domain, and the service
  data is built here, never copied from the request;
- view entities are read-only: no action accepts them.
"""

from __future__ import annotations

from collections import deque
import html
from http import HTTPStatus
import json
import logging
from pathlib import Path
import secrets
import time
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.ban import process_wrong_login
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME, STATE_UNAVAILABLE
from homeassistant.core import Context, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError

from .config_flow import parse_display_names
from .pairing import PairApiView, PairPageView
from .const import (
    ACTIONS,
    CONF_ACCESS_KEY,
    CONF_CONTROL_ENTITIES,
    CONF_DISPLAY_NAMES,
    CONF_REMOTE_ENTITY,
    CONF_VIEW_ENTITIES,
    CONTROL_DOMAINS,
    DOMAIN,
    MAX_APPS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    REMOTE_COMMANDS,
    URL_BASE,
)

_LOGGER = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"
_VIEWS_REGISTERED = f"{DOMAIN}_views_registered"
_MAX_BODY = 1024

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet, noimageindex, noai, noimageai",
}


@callback
def async_register_views(hass: HomeAssistant) -> None:
    """Register the views once per Home Assistant run."""
    if hass.data.get(_VIEWS_REGISTERED):
        return
    hass.data[_VIEWS_REGISTERED] = True
    limiter = _RateLimiter()
    # Pairing first: its fixed paths must win over the panel's /kid_panel/<key>
    for view in (
        PairPageView(hass, _STATIC / "pair.html"),
        PairApiView(hass),
        PanelPageView(hass, limiter),
        PanelManifestView(hass, limiter),
        PanelIconView(hass, limiter),
        PanelStateView(hass, limiter),
        PanelActionView(hass, limiter),
    ):
        hass.http.register_view(view)


class _RateLimiter:
    """Sliding-window request cap per panel."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def allow(self, entry_id: str) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(entry_id, deque())
        while hits and now - hits[0] > RATE_LIMIT_WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_REQUESTS:
            return False
        hits.append(now)
        return True


def _json(data: Any, status: int = HTTPStatus.OK) -> web.Response:
    return web.json_response(data, status=status, headers=_SECURITY_HEADERS)


class _PanelView(HomeAssistantView):
    """Resolve the access key to a loaded entry before anything else."""

    requires_auth = False
    cors_allowed = False

    def __init__(self, hass: HomeAssistant, limiter: _RateLimiter) -> None:
        self.hass = hass
        self._limiter = limiter

    async def _entry(self, request: web.Request, key: str) -> ConfigEntry:
        """Return the entry for `key`, or raise a response.

        A wrong key is reported to Home Assistant's login-attempt tracking,
        so repeated guessing is banned like a bad password when IP banning is
        enabled. Every loaded entry is compared in constant time.
        """
        found: ConfigEntry | None = None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.state is not ConfigEntryState.LOADED:
                continue
            if secrets.compare_digest(
                entry.data[CONF_ACCESS_KEY].encode(), key.encode()
            ):
                found = entry
        if found is None:
            await process_wrong_login(request)
            raise web.HTTPNotFound(headers=_SECURITY_HEADERS)
        if not self._limiter.allow(found.entry_id):
            raise web.HTTPTooManyRequests(headers=_SECURITY_HEADERS)
        return found


class PanelPageView(_PanelView):
    """The panel itself."""

    url = URL_BASE + "/{key}"
    name = "api:kid_panel:page"

    async def get(self, request: web.Request, key: str) -> web.Response:
        entry = await self._entry(request, key)
        page = await self.hass.async_add_executor_job(
            (_STATIC / "panel.html").read_text, "utf-8"
        )
        nonce = secrets.token_urlsafe(16)
        base = f"{URL_BASE}/{key}"
        page = (
            page.replace("__TITLE__", html.escape(entry.title))
            .replace("__NONCE__", nonce)
            .replace("__BASE__", base)
        )
        headers = {
            **_SECURITY_HEADERS,
            "Content-Security-Policy": (
                "default-src 'none'; "
                f"script-src 'nonce-{nonce}'; "
                f"style-src 'nonce-{nonce}'; "
                "connect-src 'self'; img-src 'self'; manifest-src 'self'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
        }
        return web.Response(
            text=page, content_type="text/html", charset="utf-8", headers=headers
        )


class PanelManifestView(_PanelView):
    """Web app manifest, so the page installs to a home screen."""

    url = URL_BASE + "/{key}/manifest.webmanifest"
    name = "api:kid_panel:manifest"

    async def get(self, request: web.Request, key: str) -> web.Response:
        entry = await self._entry(request, key)
        base = f"{URL_BASE}/{key}"
        manifest = {
            "name": entry.title,
            "short_name": entry.title[:12],
            "start_url": base,
            "scope": base,
            "display": "standalone",
            "background_color": "#0e1116",
            "theme_color": "#0e1116",
            "icons": [
                {"src": f"{base}/icon-{size}.png", "sizes": f"{size}x{size}",
                 "type": "image/png", "purpose": "any maskable"}
                for size in (192, 512)
            ],
        }
        return web.Response(
            text=json.dumps(manifest),
            content_type="application/manifest+json",
            headers=_SECURITY_HEADERS,
        )


class PanelIconView(_PanelView):
    """Home-screen icon."""

    url = URL_BASE + "/{key}/icon-{size:192|512}.png"
    name = "api:kid_panel:icon"

    async def get(self, request: web.Request, key: str, size: str) -> web.Response:
        await self._entry(request, key)
        body = await self.hass.async_add_executor_job(
            (_STATIC / f"icon-{size}.png").read_bytes
        )
        return web.Response(
            body=body, content_type="image/png", headers=_SECURITY_HEADERS
        )


class PanelStateView(_PanelView):
    """Current state of everything on the panel, and nothing else."""

    url = URL_BASE + "/{key}/api/state"
    name = "api:kid_panel:state"

    async def get(self, request: web.Request, key: str) -> web.Response:
        entry = await self._entry(request, key)
        return _json(build_state(self.hass, entry))


class PanelActionView(_PanelView):
    """Perform one allowed action on one allowed entity."""

    url = URL_BASE + "/{key}/api/action"
    name = "api:kid_panel:action"

    async def post(self, request: web.Request, key: str) -> web.Response:
        entry = await self._entry(request, key)
        if request.content_length is None or request.content_length > _MAX_BODY:
            return _json({"error": "bad_request"}, HTTPStatus.BAD_REQUEST)
        try:
            body = await request.json()
        except ValueError:
            return _json({"error": "bad_request"}, HTTPStatus.BAD_REQUEST)
        if not isinstance(body, dict):
            return _json({"error": "bad_request"}, HTTPStatus.BAD_REQUEST)

        call = resolve_action(entry, body)
        if call is None:
            _LOGGER.warning(
                "Panel %s refused action %r on %r",
                entry.title,
                str(body.get("action"))[:40],
                str(body.get("entity_id"))[:80],
            )
            return _json({"error": "not_allowed"}, HTTPStatus.FORBIDDEN)

        domain, service, data = call
        try:
            await self.hass.services.async_call(
                domain, service, data, blocking=True, context=Context()
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.debug("Panel %s action failed: %s", entry.title, err)
            return _json({"error": "failed"}, HTTPStatus.BAD_GATEWAY)
        return _json({"ok": True})


def resolve_action(
    entry: ConfigEntry, body: dict[str, Any]
) -> tuple[str, str, dict[str, Any]] | None:
    """Turn a request into a service call, or None if it is not allowed."""
    entity_id = body.get("entity_id")
    action = body.get("action")
    value = body.get("value")
    if not isinstance(entity_id, str) or not isinstance(action, str):
        return None

    options = entry.options
    remote = options.get(CONF_REMOTE_ENTITY)
    if remote and entity_id == remote:
        if action != "command" or not isinstance(value, str):
            return None
        if value not in REMOTE_COMMANDS:
            return None
        return "remote", "send_command", {ATTR_ENTITY_ID: remote, "command": value}

    if entity_id not in options.get(CONF_CONTROL_ENTITIES, []):
        return None
    domain = entity_id.split(".", 1)[0]
    if domain not in CONTROL_DOMAINS:
        return None
    service = ACTIONS.get(domain, {}).get(action)
    if service is None:
        return None

    data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
    if action == "brightness":
        pct = _number(value, 0, 100)
        if pct is None:
            return None
        data["brightness_pct"] = int(pct)
    elif action == "volume_set":
        level = _number(value, 0, 1)
        if level is None:
            return None
        data["volume_level"] = round(level, 2)
    elif action == "position":
        position = _number(value, 0, 100)
        if position is None:
            return None
        data["position"] = int(position)
    elif action == "mute":
        if not isinstance(value, bool):
            return None
        data["is_volume_muted"] = value
    return domain, service, data


def _number(value: Any, low: float, high: float) -> float | None:
    """Return value as a float clamped to [low, high], or None if not numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    return float(min(max(value, low), high))


def build_state(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return the panel's view of the house: its own entities, few fields."""
    options = entry.options
    names = parse_display_names(options.get(CONF_DISPLAY_NAMES, ""))

    def name(entity_id: str, state: State | None) -> str:
        if entity_id in names:
            return names[entity_id]
        if state is not None:
            return str(state.attributes.get(ATTR_FRIENDLY_NAME, entity_id))
        return entity_id

    views = []
    for entity_id in options.get(CONF_VIEW_ENTITIES, []):
        state = hass.states.get(entity_id)
        views.append(_view_item(entity_id, name(entity_id, state), state))

    controls = []
    for entity_id in options.get(CONF_CONTROL_ENTITIES, []):
        if entity_id.split(".", 1)[0] not in CONTROL_DOMAINS:
            continue
        state = hass.states.get(entity_id)
        controls.append(_control_item(entity_id, name(entity_id, state), state))

    remote = None
    if remote_id := options.get(CONF_REMOTE_ENTITY):
        state = hass.states.get(remote_id)
        remote = {
            "entity_id": remote_id,
            "name": name(remote_id, state),
            "available": state is not None and state.state != STATE_UNAVAILABLE,
        }

    return {"title": entry.title, "views": views, "controls": controls, "remote": remote}


def _view_item(entity_id: str, name: str, state: State | None) -> dict[str, Any]:
    item: dict[str, Any] = {"entity_id": entity_id, "name": name}
    if state is None:
        item["state"] = STATE_UNAVAILABLE
        return item
    item["state"] = state.state
    if unit := state.attributes.get("unit_of_measurement"):
        item["unit"] = str(unit)
    if device_class := state.attributes.get("device_class"):
        item["device_class"] = str(device_class)
    apps = state.attributes.get("apps")
    if isinstance(apps, list):
        item["apps"] = [
            {"name": str(app.get("name", ""))[:60], "minutes": _minutes(app)}
            for app in apps[:MAX_APPS]
            if isinstance(app, dict)
        ]
    return item


def _minutes(app: dict[str, Any]) -> float:
    value = app.get("minutes")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _control_item(entity_id: str, name: str, state: State | None) -> dict[str, Any]:
    domain = entity_id.split(".", 1)[0]
    item: dict[str, Any] = {"entity_id": entity_id, "domain": domain, "name": name}
    if state is None:
        item["state"] = STATE_UNAVAILABLE
        return item
    item["state"] = state.state
    attrs = state.attributes
    if domain == "light":
        modes = attrs.get("supported_color_modes") or []
        item["dimmable"] = any(mode != "onoff" for mode in modes)
        brightness = attrs.get("brightness")
        if isinstance(brightness, (int, float)):
            item["brightness_pct"] = round(brightness / 255 * 100)
    elif domain == "cover":
        features = attrs.get("supported_features", 0)
        item["positionable"] = bool(isinstance(features, int) and features & 4)
        position = attrs.get("current_position")
        if isinstance(position, (int, float)):
            item["position"] = int(position)
    elif domain == "media_player":
        volume = attrs.get("volume_level")
        if isinstance(volume, (int, float)):
            item["volume"] = round(float(volume), 2)
        item["muted"] = bool(attrs.get("is_volume_muted", False))
        if title := attrs.get("media_title"):
            item["media_title"] = str(title)[:80]
        if artist := attrs.get("media_artist"):
            item["media_artist"] = str(artist)[:80]
    return item
