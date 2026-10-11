"""Admin-only action that delivers a panel's address to a device.

The address carries the panel's key, so the key travels straight from Home
Assistant to the chosen notify service and is never shown to the caller.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.service import async_register_admin_service

from .const import CONF_ACCESS_KEY, DOMAIN, URL_BASE

SERVICE_SEND_LINK = "send_link"
ATTR_PANEL = "panel"
ATTR_NOTIFY_SERVICE = "notify_service"

SEND_LINK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PANEL): cv.string,
        vol.Required(ATTR_NOTIFY_SERVICE): cv.string,
    }
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the panel's actions."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_LINK):
        return

    async def send_link(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_PANEL])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Unknown kid panel")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("That panel is not loaded")

        notify_service = call.data[ATTR_NOTIFY_SERVICE].removeprefix("notify.")
        if not hass.services.has_service("notify", notify_service):
            raise ServiceValidationError(f"No notify.{notify_service} action")

        try:
            base = get_url(hass, prefer_external=True)
        except NoURLAvailableError as err:
            raise ServiceValidationError("Home Assistant has no URL to link to") from err
        url = f"{base}{URL_BASE}/{entry.data[CONF_ACCESS_KEY]}"

        await hass.services.async_call(
            "notify",
            notify_service,
            {
                "title": f"{entry.title}'s panel",
                "message": (
                    "Tap to open it, then use your browser's menu and choose "
                    f"Add to Home screen.\n{url}"
                ),
                "data": {"clickAction": url, "url": url},
            },
            blocking=True,
        )

    async_register_admin_service(
        hass, DOMAIN, SERVICE_SEND_LINK, send_link, schema=SEND_LINK_SCHEMA
    )
