#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for climate entities.
"""
import logging
from datetime import datetime as dt
from typing import Any, Dict, Optional

from homeassistant.components.fan import DOMAIN as PLATFORM
from homeassistant.components.fan import FanEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import EvoZoneBase
from .const import (
    ATTR_SETPOINT,
    BROKER,
    DATA,
    DOMAIN,
    SERVICE,
    UNIQUE_ID,
    SystemMode,
    ZoneMode,
)
from .schema import (
    CLIMATE_SERVICES,
    CONF_MODE,
    CONF_SYSTEM_MODE,
    SVC_RESET_SYSTEM_MODE,
    SVC_SET_SYSTEM_MODE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create the HVAC devices, if any."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    new_entities = [
        RamsesFan(hass.data[DOMAIN][BROKER], device)
        for device in discovery_info.get("devices", [])
        if hasattr(device, "fan_rate")
    ]

    if new_entities:
        async_add_entities(new_entities)

    if broker.services.get(PLATFORM):
        return
    broker.services[PLATFORM] = True


class RamsesFan(EvoZoneBase, FanEntity):
    """Base for a Honeywell TCS Zone."""

    def __init__(self, broker, device) -> None:
        """Initialize a Zone."""
        _LOGGER.info("Found a Fan: %r", device)
        super().__init__(broker, device)

        self._unique_id = device.id
        self._icon = "mdi:fan"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "zone_idx": self._device.idx,
            "heating_type": self._device.heating_type,
            "mode": self._device.mode,
            "config": self._device.config,
            **super().extra_state_attributes,
        }
