"""The panel must expose its own entities and nothing else."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant

from .conftest import KEY

BASE = f"/kid_panel/{KEY}"


async def test_wrong_key_is_not_found(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    for path in ("/kid_panel/nope", "/kid_panel/nope/api/state"):
        resp = await client.get(path)
        assert resp.status == 404
    resp = await client.post("/kid_panel/nope/api/action", json={})
    assert resp.status == 404
    assert "noindex" in resp.headers["X-Robots-Tag"]


async def test_unloaded_entry_stops_answering(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    assert (await client.get(f"{BASE}/api/state")).status == 200
    await hass.config_entries.async_unload(panel.entry_id)
    assert (await client.get(f"{BASE}/api/state")).status == 404


async def test_page_has_strict_headers(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    resp = await client.get(BASE)
    assert resp.status == 200
    text = await resp.text()
    assert "<title>Alex</title>" in text
    assert "__NONCE__" not in text and "__BASE__" not in text
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "noindex" in resp.headers["X-Robots-Tag"]
    assert '<meta name="robots" content="noindex' in text
    for path in ("manifest.webmanifest", "icon-192.png", "icon-512.png"):
        assert (await client.get(f"{BASE}/{path}")).status == 200
    assert (await client.get(f"{BASE}/icon-64.png")).status == 404


async def test_state_lists_only_panel_entities(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    data = await (await client.get(f"{BASE}/api/state")).json()
    ids = {i["entity_id"] for i in data["views"] + data["controls"]} | {data["remote"]["entity_id"]}
    assert ids == {
        "light.bedroom", "switch.lamp", "media_player.speaker",
        "sensor.screen_time", "switch.bedtime", "remote.tv",
    }
    body = str(data)
    for leaked in ("lock.front_door", "secret_attr", "token=secret", "child_id", "com.x"):
        assert leaked not in body
    screen = next(v for v in data["views"] if v["entity_id"] == "sensor.screen_time")
    assert screen["name"] == "Screen time today"
    assert screen["apps"] == [{"name": "Chat", "minutes": 60.2}]
    light = next(c for c in data["controls"] if c["entity_id"] == "light.bedroom")
    assert light["brightness_pct"] == 50 and light["dimmable"] is True


async def _post(client, body):
    return await client.post(f"{BASE}/api/action", json=body)


async def test_allowed_actions_call_services(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    toggles = async_mock_service(hass, "light", "toggle")
    turn_on = async_mock_service(hass, "light", "turn_on")
    volume = async_mock_service(hass, "media_player", "volume_set")
    send = async_mock_service(hass, "remote", "send_command")

    assert (await _post(client, {"entity_id": "light.bedroom", "action": "toggle"})).status == 200
    assert (await _post(client, {"entity_id": "light.bedroom", "action": "brightness", "value": 250})).status == 200
    assert (await _post(client, {"entity_id": "media_player.speaker", "action": "volume_set", "value": 0.456})).status == 200
    assert (await _post(client, {"entity_id": "remote.tv", "action": "command", "value": "DPAD_UP"})).status == 200

    assert toggles[0].data == {"entity_id": "light.bedroom"}
    assert turn_on[0].data == {"entity_id": "light.bedroom", "brightness_pct": 100}
    assert volume[0].data == {"entity_id": "media_player.speaker", "volume_level": 0.46}
    assert send[0].data == {"entity_id": "remote.tv", "command": "DPAD_UP"}


async def test_refused_actions(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    calls = [
        async_mock_service(hass, d, s)
        for d, s in (("switch", "toggle"), ("switch", "turn_off"), ("lock", "unlock"),
                     ("remote", "send_command"), ("light", "turn_off"), ("media_player", "play_media"))
    ]
    refused = [
        {"entity_id": "switch.bedtime", "action": "toggle"},        # view entity: read-only
        {"entity_id": "sensor.screen_time", "action": "toggle"},
        {"entity_id": "lock.front_door", "action": "toggle"},        # not on the panel
        {"entity_id": "switch.lamp", "action": "turn_off"},           # not an action for switches
        {"entity_id": "light.bedroom", "action": "brightness", "value": "50"},
        {"entity_id": "light.bedroom", "action": "brightness", "value": True},
        {"entity_id": "media_player.speaker", "action": "play_media"},
        {"entity_id": "remote.tv", "action": "command", "value": "POWER"},
        {"entity_id": "remote.tv", "action": "command", "value": ["DPAD_UP"]},
        {"entity_id": ["light.bedroom", "lock.front_door"], "action": "toggle"},
        {"entity_id": "light.bedroom"},
    ]
    for body in refused:
        resp = await _post(client, body)
        assert resp.status == 403, body
    assert (await client.post(f"{BASE}/api/action", data="not json",
                              headers={"Content-Type": "application/json"})).status == 400
    assert (await _post(client, ["light.bedroom"])).status == 400
    assert (await _post(client, {"entity_id": "x" * 2000, "action": "toggle"})).status == 400
    assert all(not c for c in calls)


async def test_extra_fields_are_not_forwarded(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    toggles = async_mock_service(hass, "light", "toggle")
    resp = await _post(client, {"entity_id": "light.bedroom", "action": "toggle",
                                "data": {"entity_id": "lock.front_door"}, "target": {"area_id": "all"}})
    assert resp.status == 200
    assert toggles[0].data == {"entity_id": "light.bedroom"}


async def test_rate_limit(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    statuses = [(await client.get(f"{BASE}/api/state")).status for _ in range(125)]
    assert statuses[:120] == [200] * 120
    assert statuses[-1] == 429
