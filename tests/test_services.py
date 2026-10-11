"""The send-link action."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized

from custom_components.kid_panel.const import DOMAIN

from .conftest import KEY


async def test_send_link_delivers_url(hass: HomeAssistant, panel, hass_admin_user) -> None:
    hass.config.external_url = "https://home.example.com"
    sent = async_mock_service(hass, "notify", "mobile_app_alex_phone")
    await hass.services.async_call(
        DOMAIN, "send_link",
        {"panel": panel.entry_id, "notify_service": "notify.mobile_app_alex_phone"},
        blocking=True, context=Context(user_id=hass_admin_user.id),
    )
    url = f"https://home.example.com/kid_panel/{KEY}"
    assert sent[0].data["data"] == {"clickAction": url, "url": url}
    assert url in sent[0].data["message"]


async def test_send_link_is_admin_only(hass: HomeAssistant, panel, hass_read_only_user) -> None:
    sent = async_mock_service(hass, "notify", "mobile_app_alex_phone")
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, "send_link",
            {"panel": panel.entry_id, "notify_service": "mobile_app_alex_phone"},
            blocking=True, context=Context(user_id=hass_read_only_user.id),
        )
    assert not sent


async def test_send_link_rejects_bad_targets(hass: HomeAssistant, panel) -> None:
    for data in (
        {"panel": "not-an-entry", "notify_service": "notify"},
        {"panel": panel.entry_id, "notify_service": "no_such_service"},
    ):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "send_link", data, blocking=True)
