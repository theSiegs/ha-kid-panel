"""Config and options flow."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.kid_panel.const import (
    CONF_ACCESS_KEY,
    CONF_CONTROL_ENTITIES,
    CONF_REGENERATE_KEY,
    DOMAIN,
)

from .conftest import KEY


async def test_create_entry_gets_random_key(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Alex"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    key = result["result"].data[CONF_ACCESS_KEY]
    assert len(key) >= 40 and key != KEY


async def test_options_reject_lock(hass: HomeAssistant, panel) -> None:
    result = await hass.config_entries.options.async_init(panel.entry_id)
    assert KEY in result["description_placeholders"]["url"]
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_CONTROL_ENTITIES: ["lock.front_door"]}
        )
    assert panel.options[CONF_CONTROL_ENTITIES] == [
        "light.bedroom", "switch.lamp", "media_player.speaker"
    ]


async def test_regenerate_key(hass: HomeAssistant, panel, hass_client_no_auth) -> None:
    result = await hass.config_entries.options.async_init(panel.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CONTROL_ENTITIES: ["light.bedroom"], CONF_REGENERATE_KEY: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    new_key = panel.data[CONF_ACCESS_KEY]
    assert new_key != KEY
    assert CONF_REGENERATE_KEY not in panel.options
    client = await hass_client_no_auth()
    assert (await client.get(f"/kid_panel/{KEY}/api/state")).status == 404
    assert (await client.get(f"/kid_panel/{new_key}/api/state")).status == 200
