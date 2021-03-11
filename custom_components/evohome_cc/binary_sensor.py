#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

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

from . import DOMAIN, EvoDeviceBase, new_binary_sensors
from .const import ATTR_ACTUATOR_STATE, ATTR_BATTERY_STATE, ATTR_WINDOW_STATE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]
    new_devices = new_binary_sensors(broker)
    new_entities = []

    for klass in (EvoActuator, EvoBattery, EvoWindow):
        for device in [d for d in new_devices if hasattr(d, klass.STATE_ATTR)]:
            new_entities.append(klass(broker, device))

    if new_entities:
        broker.binary_sensors += new_devices
        async_add_entities(new_entities, update_before_add=True)


class EvoBinarySensorBase(EvoDeviceBase, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the binary sensor."""
        _LOGGER.info("Found a Binary Sensor (%s), id=%s", self.STATE_ATTR, evo_device.id)

        super().__init__(evo_broker, evo_device)

        self._unique_id = f"{evo_device.id}-{self.STATE_ATTR}_state"

    @property
    def available(self) -> bool:
        """Return True if the binary sensor is available."""
        return getattr(self._evo_device, self.STATE_ATTR) is not None

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return getattr(self._evo_device, self.STATE_ATTR)

class EvoActuator(EvoBinarySensorBase):
    """Representation of an actuator sensor."""
    DEVICE_CLASS = "actuator"
    STATE_ATTR = "enabled"  # on means active


class EvoBattery(EvoBinarySensorBase):
    """Representation of a low battery sensor."""
    DEVICE_CLASS = DEVICE_CLASS_BATTERY
    STATE_ATTR = "battery_low"  #  on means low

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "battery_level": self._evo_device.battery_state.get("battery_level"),
        }


class EvoWindow(EvoBinarySensorBase):
    """Representation of an open window sensor."""
    DEVICE_CLASS = DEVICE_CLASS_WINDOW
    STATE_ATTR = "window_open"  #  on means open
