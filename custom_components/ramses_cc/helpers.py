#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

import logging
from typing import Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.entity_registry import EntityRegistry, async_get

from .const import DOMAIN as PLATFORM

OLD_PLATFORM = "evohome_cc" if PLATFORM == "ramses_cc" else "ramses_cc"

_LOGGER = logging.getLogger(__name__)


@callback
def migrate_to_ramses_rf(hass: HomeAssistant, domain: str, unique_id: str):
    """Migrate an entity to the ramses_rf platform (from evohome_rf)."""

    registry: EntityRegistry = async_get(hass)

    if entity_id := registry.async_get_entity_id(domain, OLD_PLATFORM, unique_id):

        if hass.states.get(entity_id).state == STATE_UNAVAILABLE:  # HACK
            hass.states.get(entity_id).state = STATE_UNKNOWN

        try:
            registry.async_update_entity_platform(entity_id, PLATFORM)
        except ValueError as exc:
            _LOGGER.error(f"migrating {entity_id} ({unique_id}) to {PLATFORM} failed: {exc}")
        else:
            _LOGGER.warning(f"migrating {entity_id} ({unique_id}) to {PLATFORM}: success")

    # if (
    #     state := hass.states.get(entity_id)
    # ) is not None and state.state != STATE_UNKNOWN:
    #     raise ValueError("Only entities that haven't been loaded can be migrated")
