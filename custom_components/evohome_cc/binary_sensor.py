#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Provides support for binary sensors.
"""

import logging
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_WINDOW,
    BinarySensorEntity,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoDeviceBase
from .const import ATTR_BATTERY_LEVEL, BROKER, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor entities."""
    if discovery_info is None:
        return

    new_devices = [
        v.get(ENTITY_CLASS, EvoBinarySensor)(hass.data[DOMAIN][BROKER], device, k, **v)
        for device in discovery_info["new_devices"]
        for k, v in BINARY_SENSOR_ATTRS.items()
        if hasattr(device, k)
    ]

    if new_devices:
        async_add_entities(new_devices)


class EvoBinarySensor(EvoDeviceBase, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    def __init__(self, broker, device, state_attr, device_class=None, **kwargs) -> None:
        """Initialize a binary sensor."""
        _LOGGER.info("Found a Binary Sensor (%s), id=%s", state_attr, device.id)
        super().__init__(broker, device, state_attr, device_class)

        self._unique_id = f"{device.id}-{state_attr}_state"

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return getattr(self._device, self._state_attr)


class EvoActuator(EvoBinarySensor):
    """Representation of an actuator sensor; on means active."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:electric-switch-closed" if self.is_on else "mdi:electric-switch"


class EvoBattery(EvoBinarySensor):
    """Representation of a low battery sensor; on means low."""

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        state = self._device.battery_state
        return {
            **super().device_state_attributes,
            ATTR_BATTERY_LEVEL: state and state.get(ATTR_BATTERY_LEVEL),
        }


DEVICE_CLASS = "device_class"
ENTITY_CLASS = "entity_class"

BINARY_SENSOR_ATTRS = {
    "battery_low": {
        DEVICE_CLASS: DEVICE_CLASS_BATTERY,
        ENTITY_CLASS: EvoBattery,
    },
    "enabled": {
        ENTITY_CLASS: EvoActuator,
    },
    "window_open": {
        DEVICE_CLASS: DEVICE_CLASS_WINDOW,
    },
}
