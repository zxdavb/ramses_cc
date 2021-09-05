#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Provides support for binary sensors.
"""

import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_WINDOW,
    BinarySensorEntity,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoDeviceBase, EvoEntity
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

    new_systems = [
        EvoSystem(hass.data[DOMAIN][BROKER], system._evo, "schema")
        for system in discovery_info["new_devices"]
        if hasattr(system, "_evo") and system._is_controller
    ]

    if new_devices:
        async_add_entities(new_devices + new_systems)


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


class EvoSystem(EvoEntity, BinarySensorEntity):
    """Representation of a generic sensor."""

    def __init__(self, broker, device, state_attr, device_class=None, **kwargs) -> None:
        """Initialize a binary sensor."""
        _LOGGER.info("Found a System (%s), id=%s", state_attr, device.id)
        super().__init__(broker, device)

        self._name = f"{device.id} (schema)"
        self._unique_id = f"{device.id}-schema"

    @property
    def available(self) -> bool:
        """Return True if the controller has been seen recently."""
        if msg := self._device._msgs.get("1F09"):
            return dt.now() - msg.dtm < td(seconds=msg.payload["remaining_seconds"] * 2)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        other_list = [
            d.id
            for d in self._device._gwy.devices
            if d.id not in self._device._gwy._include.keys()
            and d.id not in self._device._gwy._exclude.keys()
        ]

        return {
            "schema_min": self._device._evo.schema_min,
            "schema": self._device._evo.schema,
            "known_list": [{k: v} for k, v in self._device._gwy._include.items()],
            "block_list": [{k: v} for k, v in self._device._gwy._exclude.items()],
            "other_list": sorted(other_list),
        }

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the controller has been seen recently."""
        return self.available

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name


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
