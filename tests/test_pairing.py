"""Pairing a device with a one-time code."""

from __future__ import annotations

import pytest

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized

from custom_components.kid_panel.const import DOMAIN
from custom_components.kid_panel.pairing import FAILURE_LIMIT, PairingCodes

from .conftest import KEY


async def _code(hass: HomeAssistant, panel, user) -> str:
    result = await hass.services.async_call(
        DOMAIN, "create_pairing_code", {"panel": panel.entry_id},
        blocking=True, return_response=True, context=Context(user_id=user.id),
    )
    return result["code"]


async def _pair(client, code):
    return await client.post("/kid_panel/pair/api", json={"code": code})


async def test_code_pairs_once(hass: HomeAssistant, panel, hass_admin_user, hass_client_no_auth) -> None:
    code = await _code(hass, panel, hass_admin_user)
    assert len(code) == 6 and code.isdigit()
    client = await hass_client_no_auth()
    resp = await _pair(client, code)
    assert resp.status == 200
    assert await resp.json() == {"path": f"/kid_panel/{KEY}", "title": "Alex"}
    assert "noindex" in resp.headers["X-Robots-Tag"]
    # Used up
    assert (await _pair(client, code)).status == 403


async def test_new_code_replaces_old(hass: HomeAssistant, panel, hass_admin_user, hass_client_no_auth) -> None:
    first = await _code(hass, panel, hass_admin_user)
    second = await _code(hass, panel, hass_admin_user)
    client = await hass_client_no_auth()
    if first != second:
        assert (await _pair(client, first)).status == 403
    assert (await _pair(client, second)).status == 200


async def test_creating_codes_is_admin_only(hass: HomeAssistant, panel, hass_read_only_user) -> None:
    with pytest.raises(Unauthorized):
        await _code(hass, panel, hass_read_only_user)


async def test_bad_requests(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    for body in ({"code": "12345"}, {"code": "abcdef"}, {"code": 123456}, {}, ["123456"]):
        assert (await client.post("/kid_panel/pair/api", json=body)).status == 400
    # The page is served, and "pair" is never mistaken for a panel key
    page = await client.get("/kid_panel/pair")
    assert page.status == 200
    assert "Enter pairing code" in await page.text()
    assert "default-src 'none'" in page.headers["Content-Security-Policy"]


async def test_expired_code(hass: HomeAssistant, panel) -> None:
    now = [1000.0]
    codes = PairingCodes(clock=lambda: now[0])
    code = codes.create(panel.entry_id)
    now[0] += 601
    assert codes.redeem(code) is None


def test_lockout_after_wrong_codes() -> None:
    now = [0.0]
    codes = PairingCodes(clock=lambda: now[0])
    good = codes.create("entry")
    for i in range(FAILURE_LIMIT):
        bad = f"{(int(good) + 1 + i) % 1_000_000:06d}"
        assert codes.redeem(bad) is None
    # Locked: even the right code is refused, and it was withdrawn
    assert codes.locked
    assert codes.redeem(good) is None
    now[0] += 601
    assert not codes.locked
    assert codes.redeem(good) is None
