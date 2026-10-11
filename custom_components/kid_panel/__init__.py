"""Kid Panel: a login-free control page limited to chosen entities.

Each config entry is one panel, reached at `/kid_panel/<access key>`. The
person using it never holds a Home Assistant credential; the panel's server
side decides what they may see and do, so nothing outside the entry's options
is reachable through it.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .services import async_register_services
from .views import async_register_views

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the panel's HTTP views and actions once, for every entry to share."""
    async_register_views(hass)
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a panel. Its views look entries up by key on every request."""
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a panel; an unloaded entry no longer answers its key."""
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload so a changed key or option takes effect at once."""
    await hass.config_entries.async_reload(entry.entry_id)
