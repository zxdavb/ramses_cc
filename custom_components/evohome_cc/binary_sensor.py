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
from .const import (
    ATTR_ACTUATOR,
    ATTR_BATTERY,
    ATTR_BATTERY_LEVEL,
    ATTR_WINDOW,
    BROKER,
    DEVICE_CLASS_ACTUATOR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]
    new_devices = broker.find_new_binary_sensors()
    broker.binary_sensors += new_devices

    new_entities = [
        klass(broker, device)
        for klass in (EvoActuator, EvoBattery, EvoWindow)
        for device in new_devices
        if hasattr(device, klass.STATE_ATTR)
    ]
    if new_entities:
        async_add_entities(new_entities)


class EvoBinarySensorBase(EvoDeviceBase, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    def __init__(self, broker, device) -> None:
        """Initialize the binary sensor."""
        _LOGGER.info("Found a Binary Sensor (%s), id=%s", self.STATE_ATTR, device.id)
        super().__init__(broker, device)

        self._unique_id = f"{device.id}-{self.STATE_ATTR}_state"

    @property
    def available(self) -> bool:
        """Return True if the binary sensor is available."""
        return getattr(self._device, self.STATE_ATTR) is not None

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return getattr(self._device, self.STATE_ATTR)


class EvoActuator(EvoBinarySensorBase):
    """Representation of an actuator sensor; on means active."""

    DEVICE_CLASS = DEVICE_CLASS_ACTUATOR
    STATE_ATTR = ATTR_ACTUATOR

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:valve" if self.is_on else "mdi:valve-closed"  # "mdi:valve-open"


class EvoBattery(EvoBinarySensorBase):
    """Representation of a low battery sensor; on means low."""

    DEVICE_CLASS = DEVICE_CLASS_BATTERY
    STATE_ATTR = ATTR_BATTERY

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        state = self._device.battery_state
        return {
            **super().device_state_attributes,
            ATTR_BATTERY_LEVEL: state and state.get(ATTR_BATTERY_LEVEL),
        }


class EvoWindow(EvoBinarySensorBase):
    """Representation of an open window sensor; on means open."""

    DEVICE_CLASS = DEVICE_CLASS_WINDOW
    STATE_ATTR = ATTR_WINDOW
