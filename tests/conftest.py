"""Fixtures for Kid Panel tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.kid_panel.const import (
    CONF_ACCESS_KEY,
    CONF_CONTROL_ENTITIES,
    CONF_DISPLAY_NAMES,
    CONF_REMOTE_ENTITY,
    CONF_VIEW_ENTITIES,
    DOMAIN,
)

KEY = "k" * 43


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load integrations from custom_components."""
    return


@pytest.fixture
async def panel(hass: HomeAssistant) -> MockConfigEntry:
    """A loaded panel with a fixed key and a typical set of entities."""
    hass.states.async_set(
        "light.bedroom", "on",
        {"friendly_name": "Bedroom", "brightness": 128,
         "supported_color_modes": ["brightness"], "secret_attr": "x"},
    )
    hass.states.async_set("switch.lamp", "off", {"friendly_name": "Lamp"})
    hass.states.async_set(
        "media_player.speaker", "playing",
        {"friendly_name": "Speaker", "volume_level": 0.3, "media_title": "Song",
         "entity_picture": "/api/media_player_proxy/x?token=secret"},
    )
    hass.states.async_set(
        "sensor.screen_time", "160.2",
        {"friendly_name": "Screen time", "unit_of_measurement": "min",
         "device_class": "duration", "child_id": "123",
         "apps": [{"name": "Chat", "minutes": 60.2, "package": "com.x"}]},
    )
    hass.states.async_set("switch.bedtime", "on", {"friendly_name": "Bedtime"})
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Front"})
    hass.states.async_set("remote.tv", "on", {"friendly_name": "TV"})

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alex",
        data={CONF_ACCESS_KEY: KEY},
        options={
            CONF_CONTROL_ENTITIES: ["light.bedroom", "switch.lamp", "media_player.speaker"],
            CONF_VIEW_ENTITIES: ["sensor.screen_time", "switch.bedtime"],
            CONF_REMOTE_ENTITY: "remote.tv",
            CONF_DISPLAY_NAMES: "sensor.screen_time: Screen time today\nbad line",
        },
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, "http", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
