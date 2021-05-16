#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Provides support for sensors.
"""

import logging
from typing import Any, Dict, Optional

from homeassistant.const import (  # DEVICE_CLASS_BATTERY,; DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoDeviceBase
from .const import ATTR_SETPOINT, BROKER, DOMAIN, PERCENTAGE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    new_entities = [
        v.get(ENTITY_CLASS, EvoSensor)(hass.data[DOMAIN][BROKER], device, k, **v)
        for k, v in SENSOR_ATTRS.items()
        for device in discovery_info
        if hasattr(device, k)
    ]

    if new_entities:
        async_add_entities(new_entities)


class EvoSensor(EvoDeviceBase):
    """Representation of a generic sensor."""

    def __init__(
        self, broker, device, state_attr, device_class=None, device_units=None, **kwargs
    ) -> None:
        """Initialize a sensor."""
        _LOGGER.info("Found a Sensor (%s), id=%s", state_attr, device.id)
        super().__init__(broker, device, state_attr, device_class)

        self._unique_id = f"{device.id}-{state_attr}"
        self._unit_of_measurement = device_units or PERCENTAGE

    @property
    def state(self) -> Optional[Any]:  # int or float
        """Return the state of the sensor."""
        state = getattr(self._device, self._state_attr)
        if self.unit_of_measurement == PERCENTAGE:
            return int(state * 100) if state is not None else None
        return state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement


class EvoHeatDemand(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:radiator-off" if self.state == 0 else "mdi:radiator"


class EvoRelayDemand(EvoSensor):
    """Representation of a relay demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:power-plug" if self.state else "mdi:power-plug-off"


class EvoTemperature(EvoSensor):
    """Representation of a temperature sensor (incl. DHW sensor)."""

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes
        if hasattr(self._device, ATTR_SETPOINT):
            attrs[ATTR_SETPOINT] = self._device.setpoint
        return attrs


class EvoFaultLog(EvoDeviceBase):
    """Representation of a system's fault log."""

    # DEVICE_CLASS = DEVICE_CLASS_PROBLEM
    DEVICE_UNITS = "entries"

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device, None, None)  # TODO

        self._fault_log = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device._fault_log._fault_log_done

    @property
    def state(self) -> int:
        """Return the number of issues."""
        return len(self._fault_log)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the device state attributes."""
        return {
            **super().device_state_attributes,
            "fault_log": self._device._fault_log,
        }

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        # self._fault_log = self._device.fault_log()  # TODO: needs sorting out
        pass


DEVICE_CLASS = "device_class"
DEVICE_UNITS = "device_units"
ENTITY_CLASS = "entity_class"

SENSOR_ATTRS = {
    "heat_demand": {
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoHeatDemand,
    },
    "modulation_level": {
        DEVICE_UNITS: PERCENTAGE,
    },
    "relay_demand": {
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoRelayDemand,
    },
    "temperature": {
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
        ENTITY_CLASS: EvoTemperature,
    },
    "boiler_setpoint": {
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "boiler_temp": {
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "ch_pressure": {
        DEVICE_CLASS: DEVICE_CLASS_PRESSURE,
        DEVICE_UNITS: "bar",
    },
    "cv_return_temp": {
        DEVICE_CLASS: DEVICE_CLASS_TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "dhw_rate": {
        DEVICE_UNITS: "l/min",
    },
    "rel_modulation_level": {
        DEVICE_UNITS: PERCENTAGE,
    },
    "boost_timer": {
        DEVICE_UNITS: "min",
    },
    "fan_rate": {
        DEVICE_UNITS: PERCENTAGE,
    },
    "relative_humidity": {
        DEVICE_CLASS: DEVICE_CLASS_HUMIDITY,
        DEVICE_UNITS: PERCENTAGE,
    },
}
