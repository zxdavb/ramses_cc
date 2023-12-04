"""Helpers for RAMSES integration."""
from __future__ import annotations

import logging

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN as PLATFORM

OLD_PLATFORM = "evohome_cc" if PLATFORM == "ramses_cc" else "ramses_cc"

_LOGGER = logging.getLogger(__name__)


@callback
def migrate_to_ramses_rf(hass: HomeAssistant, domain: str, unique_id: str):
    """Migrate an entity to the ramses_rf platform (from evohome_rf)."""

    entity_registry = er.async_get(hass)

    if entity_id := entity_registry.async_get_entity_id(
        domain, OLD_PLATFORM, unique_id
    ):
        if (entity := hass.states.get(entity_id)) and entity.state == STATE_UNAVAILABLE:
            hass.states.get(entity_id).state = STATE_UNKNOWN  # HACK

        try:
            entity_registry.async_update_entity_platform(entity_id, PLATFORM)
        except ValueError as exc:
            _LOGGER.error(
                "Migrating %s (%s) to %s failed: %s",
                entity_id,
                unique_id,
                PLATFORM,
                exc,
            )
        else:
            _LOGGER.warning(
                "Migrating %s (%s) to %s: success", entity_id, unique_id, PLATFORM
            )

    # if (
    #     state := hass.states.get(entity_id)
    # ) is not None and state.state != STATE_UNKNOWN:
    #     raise ValueError("Only entities that haven't been loaded can be migrated")
