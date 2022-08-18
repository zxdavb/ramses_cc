#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by HVAC.

Provides support for fan entities.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesEntity
from .const import BROKER, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create the Climate entities for CH/DHW (heat) & HVAC."""

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]
    new_entities = []

    for fan in [f for f in discovery_info.get("fans", [])]:
        new_entities.append(RamsesFan(broker, fan))

    if new_entities:
        async_add_entities(new_entities)


class RamsesFan(RamsesEntity, FanEntity):
    """Base for a Honeywell HVAC unit (Fan, HRU, MVHR, PIV, etc)."""

    # Entity attrs...
    _attr_icon = "mdi:fan"

    # Fan attrs....
    _attr_preset_modes: list[str] = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_supported_features: int = (
        FanEntityFeature.PRESET_MODE | FanEntityFeature.SET_SPEED
    )

    def __init__(self, broker, device) -> None:
        """Initialize a HVAC system."""
        _LOGGER.info("Found a HVAC system: %r", device)

        super().__init__(broker, device)

        self._unique_id = device.id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().extra_state_attributes,
        }

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._device.id

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return FAN_AUTO
