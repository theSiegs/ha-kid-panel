"""Config and options flow for Kid Panel."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_ACCESS_KEY,
    CONF_CONTROL_ENTITIES,
    CONF_DISPLAY_NAMES,
    CONF_REGENERATE_KEY,
    CONF_REMOTE_ENTITY,
    CONF_VIEW_ENTITIES,
    CONTROL_DOMAINS,
    DOMAIN,
    URL_BASE,
)


def new_access_key() -> str:
    """Return a fresh, unguessable panel key."""
    return secrets.token_urlsafe(32)


def parse_display_names(text: str) -> dict[str, str]:
    """Parse `entity_id: Name` lines; anything malformed is ignored."""
    names: dict[str, str] = {}
    for line in (text or "").splitlines():
        entity_id, sep, name = line.partition(":")
        entity_id, name = entity_id.strip(), name.strip()
        if sep and "." in entity_id and name:
            names[entity_id] = name[:60]
    return names


class KidPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the panel; its entities are chosen under Configure."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_ACCESS_KEY: new_access_key()},
                options={
                    CONF_CONTROL_ENTITIES: [],
                    CONF_VIEW_ENTITIES: [],
                    CONF_DISPLAY_NAMES: "",
                },
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return KidPanelOptionsFlow()


class KidPanelOptionsFlow(OptionsFlow):
    """Choose what the panel shows and controls."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the panel's entities, names and key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            controls = user_input.get(CONF_CONTROL_ENTITIES, [])
            if any(e.split(".", 1)[0] not in CONTROL_DOMAINS for e in controls):
                errors[CONF_CONTROL_ENTITIES] = "unsupported_domain"
            else:
                if user_input.pop(CONF_REGENERATE_KEY, False):
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={
                            **self.config_entry.data,
                            CONF_ACCESS_KEY: new_access_key(),
                        },
                    )
                return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        suggested: dict[str, Any] = {
            CONF_CONTROL_ENTITIES: options.get(CONF_CONTROL_ENTITIES, []),
            CONF_VIEW_ENTITIES: options.get(CONF_VIEW_ENTITIES, []),
            CONF_DISPLAY_NAMES: options.get(CONF_DISPLAY_NAMES, ""),
        }
        if options.get(CONF_REMOTE_ENTITY):
            suggested[CONF_REMOTE_ENTITY] = options[CONF_REMOTE_ENTITY]

        schema = vol.Schema(
            {
                vol.Optional(CONF_CONTROL_ENTITIES): EntitySelector(
                    EntitySelectorConfig(domain=list(CONTROL_DOMAINS), multiple=True)
                ),
                vol.Optional(CONF_VIEW_ENTITIES): EntitySelector(
                    EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_REMOTE_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="remote")
                ),
                vol.Optional(CONF_DISPLAY_NAMES): TextSelector(
                    TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_REGENERATE_KEY, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders={"url": self._panel_url()},
        )

    def _panel_url(self) -> str:
        """Return the panel's address, external first."""
        path = f"{URL_BASE}/{self.config_entry.data[CONF_ACCESS_KEY]}"
        try:
            base = get_url(self.hass, prefer_external=True)
        except NoURLAvailableError:
            return path
        return f"{base}{path}"
