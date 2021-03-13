"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for sensors.
"""
import logging
from typing import Any, Dict, Optional

from homeassistant.const import (  # DEVICE_CLASS_BATTERY,; DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoDeviceBase, new_sensors
from .const import (
    ATTR_FAULT_LOG,
    ATTR_HEAT_DEMAND,
    ATTR_RELAY_DEMAND,
    ATTR_SETPOINT,
    ATTR_TEMPERATURE,
    BROKER,
    PERCENTAGE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]
    new_devices = new_sensors(broker)
    broker.sensors += new_devices

    new_entities = [
        klass(broker, device)
        for klass in (EvoHeatDemand, EvoRelayDemand, EvoTemperature, EvoFaultLog)
        for device in new_devices
        if hasattr(device, klass.STATE_ATTR)
    ]
    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoSensorBase(EvoDeviceBase):
    """Representation of a generic sensor."""

    DEVICE_UNITS = PERCENTAGE

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        _LOGGER.info("Found a Sensor (%s), id=%s", self.STATE_ATTR, device.id)
        super().__init__(broker, device)

        self._unique_id = f"{device.id}-{self.STATE_ATTR}"

    @property
    def available(self) -> bool:
        """Return True if the sensor is available."""
        return getattr(self._evo_device, self.STATE_ATTR) is not None

    @property
    def state(self) -> Optional[int]:
        """Return the state of the sensor."""
        state = getattr(self._evo_device, self.STATE_ATTR)
        if self.unit_of_measurement == PERCENTAGE:
            return int(state * 100) if state is not None else None
        return state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self.DEVICE_UNITS


class EvoHeatDemand(EvoSensorBase):
    """Representation of a heat demand sensor."""

    STATE_ATTR = ATTR_HEAT_DEMAND

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:radiator-off" if self.state == 0 else "mdi:radiator"


class EvoRelayDemand(EvoSensorBase):
    """Representation of a relay demand sensor."""

    STATE_ATTR = ATTR_RELAY_DEMAND

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        # return "mdi:power-plug-off" if self.state == 0 else "mdi:power-plug"
        # return "mdi:flash-off" if self.state == 0 else "mdi:flash"
        return (
            "mdi:electric-switch-closed" if self.state == 0 else "mdi:electric-switch"
        )


class EvoTemperature(EvoSensorBase):
    """Representation of a temperature sensor (incl. DHW sensor)."""

    DEVICE_CLASS = DEVICE_CLASS_TEMPERATURE
    DEVICE_UNITS = TEMP_CELSIUS
    STATE_ATTR = ATTR_TEMPERATURE

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes
        if hasattr(self._evo_device, ATTR_SETPOINT):
            attrs[ATTR_SETPOINT] = self._evo_device.setpoint
        return attrs


class EvoFaultLog(EvoDeviceBase):
    """Representation of a system's fault log."""

    # DEVICE_CLASS = DEVICE_CLASS_PROBLEM
    DEVICE_UNITS = "entries"
    STATE_ATTR = ATTR_FAULT_LOG

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._fault_log = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device._fault_log._fault_log_done

    @property
    def state(self) -> int:
        """Return the number of issues."""
        return len(self._fault_log)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the device state attributes."""
        return {
            **super().device_state_attributes,
            "fault_log": self._evo_device._fault_log,
        }

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        # self._fault_log = self._evo_device.fault_log()  # TODO: needs sorting out
        pass
