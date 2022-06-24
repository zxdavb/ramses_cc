#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for climate entities.
"""
import logging
from typing import Any, Dict

from homeassistant.components.fan import DOMAIN as PLATFORM
from homeassistant.components.fan import FanEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import EvoZoneBase
from .const import BROKER, DOMAIN
from .helpers import migrate_to_ramses_rf

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create the HVAC devices, if any."""

    def entity_factory(entity_class, broker, device):
        migrate_to_ramses_rf(hass, "fan", f"{device.id}")
        return entity_class(broker, device)

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    new_entities = [
        entity_factory(RamsesFan, broker, device)
        for device in discovery_info.get("devices", [])
        if hasattr(device, "fan_rate")
    ]

    if new_entities:
        async_add_entities(new_entities)

    if broker._services.get(PLATFORM):
        return
    broker._services[PLATFORM] = True


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
