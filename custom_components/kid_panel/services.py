"""Admin-only actions that get a panel's address onto a device.

send_link delivers the address itself: it carries the panel's key, so the key
travels straight from Home Assistant to the chosen notify service and is never
shown to the caller. create_pairing_code makes a short one-time code instead,
which the device trades for the address (see pairing.py).
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.service import async_register_admin_service

from .const import CONF_ACCESS_KEY, DOMAIN, URL_BASE
from .pairing import CODE_LIFETIME, notify_code, pairing_codes

SERVICE_SEND_LINK = "send_link"
SERVICE_CREATE_PAIRING_CODE = "create_pairing_code"
ATTR_PANEL = "panel"
ATTR_NOTIFY_SERVICE = "notify_service"

SEND_LINK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PANEL): cv.string,
        vol.Required(ATTR_NOTIFY_SERVICE): cv.string,
    }
)
PAIRING_SCHEMA = vol.Schema({vol.Required(ATTR_PANEL): cv.string})


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the panel's actions."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_LINK):
        return

    def loaded_panel(call: ServiceCall):
        entry = hass.config_entries.async_get_entry(call.data[ATTR_PANEL])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Unknown kid panel")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("That panel is not loaded")
        return entry

    async def send_link(call: ServiceCall) -> None:
        entry = loaded_panel(call)

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

    async def create_pairing_code(call: ServiceCall) -> ServiceResponse:
        entry = loaded_panel(call)
        code = pairing_codes(hass).create(entry.entry_id)
        notify_code(hass, entry.title, entry.entry_id, code)
        return {"code": code, "valid_for_seconds": int(CODE_LIFETIME)}

    async_register_admin_service(
        hass, DOMAIN, SERVICE_SEND_LINK, send_link, schema=SEND_LINK_SCHEMA
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CREATE_PAIRING_CODE,
        create_pairing_code,
        schema=PAIRING_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
