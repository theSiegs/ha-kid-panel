"""Constants for Kid Panel."""

from __future__ import annotations

DOMAIN = "kid_panel"

CONF_ACCESS_KEY = "access_key"
CONF_CONTROL_ENTITIES = "control_entities"
CONF_VIEW_ENTITIES = "view_entities"
CONF_REMOTE_ENTITY = "remote_entity"
CONF_DISPLAY_NAMES = "display_names"
CONF_REGENERATE_KEY = "regenerate_key"

URL_BASE = "/kid_panel"

# Domains a panel may be given control of. Anything else is refused when the
# options are saved and again when a request arrives.
CONTROL_DOMAINS = (
    "cover",
    "fan",
    "input_boolean",
    "light",
    "media_player",
    "scene",
    "script",
    "switch",
)

# Panel action -> (service domain or None for the entity's own domain, service).
# Only these actions exist; a request naming anything else is refused.
ACTIONS: dict[str, dict[str, str]] = {
    "cover": {
        "open": "open_cover",
        "close": "close_cover",
        "stop": "stop_cover",
        "position": "set_cover_position",
    },
    "fan": {"toggle": "toggle"},
    "input_boolean": {"toggle": "toggle"},
    "switch": {"toggle": "toggle"},
    "light": {"toggle": "toggle", "brightness": "turn_on"},
    "media_player": {
        "play_pause": "media_play_pause",
        "next": "media_next_track",
        "previous": "media_previous_track",
        "volume_up": "volume_up",
        "volume_down": "volume_down",
        "volume_set": "volume_set",
        "mute": "volume_mute",
        "turn_on": "turn_on",
        "turn_off": "turn_off",
    },
    "scene": {"activate": "turn_on"},
    "script": {"run": "turn_on"},
}

# Remote keys the panel's d-pad may send (Android TV Remote key names).
REMOTE_COMMANDS = frozenset(
    {
        "BACK",
        "DPAD_CENTER",
        "DPAD_DOWN",
        "DPAD_LEFT",
        "DPAD_RIGHT",
        "DPAD_UP",
        "HOME",
        "MEDIA_FAST_FORWARD",
        "MEDIA_PLAY_PAUSE",
        "MEDIA_REWIND",
    }
)

# Requests allowed per panel per window, across all of its endpoints.
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW = 60.0

# Longest list read from a view entity's `apps` attribute.
MAX_APPS = 8
