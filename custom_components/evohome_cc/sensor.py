"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for sensors.
"""
import logging
from typing import Any, Dict, Optional

from homeassistant.const import (  # DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoDeviceBase, new_sensors
from .const import ATTR_SETPOINT

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]
    new_devices = new_sensors(broker)
    new_entities = []

    for klass in (EvoHeatDemand, EvoRelayDemand, EvoTemperature, EvoFaultLog):
        for device in [d for d in new_devices if hasattr(d, klass.STATE_ATTR)]:
            new_entities.append(klass(broker, device))

    if new_entities:
        broker.sensors += new_devices
        async_add_entities(new_entities, update_before_add=True)


class EvoSensorBase(EvoDeviceBase):
    """Representation of a generic sensor."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the sensor."""
        _LOGGER.info("Found a Sensor (%s), id=%s", self.STATE_ATTR, evo_device.id)

        super().__init__(evo_broker, evo_device)

        self._unique_id = f"{evo_device.id}-{self.STATE_ATTR}"
        self._unit_of_measurement = DEVICE_UNITS_BY_CLASS.get(self.__class__, "%")

    @property
    def available(self) -> bool:
        """Return True if the binary sensor is available."""
        return getattr(self._evo_device, self.STATE_ATTR) is not None

    @property
    def state(self) -> Optional[int]:
        """Return the heat demand of the actuator."""
        return int(getattr(self._evo_device, self.STATE_ATTR) * 100)

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement


class EvoHeatDemand(EvoSensorBase):
    """Representation of a heat demand sensor."""
    STATE_ATTR = "heat_demand"


class EvoRelayDemand(EvoSensorBase):
    """Representation of a relay demand sensor."""
    STATE_ATTR = "relay_demand"


class EvoTemperature(EvoSensorBase):
    """Representation of a temperature sensor (incl. DHW sensor)."""
    DEVICE_CLASS = DEVICE_CLASS_TEMPERATURE
    STATE_ATTR = "temperature"

    @property
    def state(self) -> Optional[str]:
        """Return the temperature of the sensor."""
        return self._evo_device.temperature

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        if hasattr(self._evo_device, ATTR_SETPOINT):
            return {
                **super().device_state_attributes,
                ATTR_SETPOINT: self._evo_device.setpoint,
            }
        return super().device_state_attributes


class EvoFaultLog(EvoDeviceBase):
    """Representation of a system's fault log."""
    STATE_ATTR = "fault_log"

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device)

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
        return self._fault_log

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        self._fault_log = self._evo_device.fault_log()  # TODO: needs sorting


DEVICE_UNITS_BY_CLASS = {
    EvoSensorBase.STATE_ATTR: None,
    EvoHeatDemand.STATE_ATTR: "%",
    EvoRelayDemand.STATE_ATTR: "%",
    EvoTemperature.STATE_ATTR: TEMP_CELSIUS,
    EvoFaultLog.STATE_ATTR: "entries",
}

