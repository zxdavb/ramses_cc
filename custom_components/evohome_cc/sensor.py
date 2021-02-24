"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for sensors.
"""
import logging
from typing import Any, Dict, Optional

from homeassistant.const import (
    # DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoDeviceBase, new_sensors
from .const import (
    # ATTR_BATTERY_STATE,
    ATTR_HEAT_DEMAND,
    ATTR_RELAY_DEMAND,
    ATTR_SETPOINT,
    ATTR_TEMPERATURE,
)

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

    for device in [d for d in new_devices if hasattr(d, ATTR_HEAT_DEMAND)]:
        _LOGGER.info(
            "Found a Sensor (heat demand), id=%s, zone=%s", device.id, device._domain_id
        )
        new_entities.append(EvoHeatDemand(broker, device, ATTR_HEAT_DEMAND))

    for device in [d for d in new_devices if hasattr(d, ATTR_RELAY_DEMAND)]:
        _LOGGER.info(
            "Found a Sensor (relay demand), id=%s, zone=%s",
            device.id,
            device._domain_id,
        )
        new_entities.append(EvoRelayDemand(broker, device, ATTR_RELAY_DEMAND))

    for device in [d for d in new_devices if hasattr(d, ATTR_TEMPERATURE)]:
        _LOGGER.info(
            "Found a Sensor (temp), id=%s, zone=%s", device.id, device._domain_id
        )
        new_entities.append(EvoTemperature(broker, device, DEVICE_CLASS_TEMPERATURE))

    for device in [d for d in new_devices if hasattr(d, "fault_log")]:
        _LOGGER.info(
            "Found a Sensor (fault log), id=%s, zone=%s", device.id, device._domain_id
        )
        new_entities.append(EvoFaultLog(broker, device, "fault_log"))

    if new_entities:
        broker.sensors += new_devices
        async_add_entities(new_entities, update_before_add=True)


class EvoSensorBase(EvoDeviceBase):
    """Representation of a generic sensor."""

    def __init__(self, evo_broker, evo_device, device_class) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = f"{evo_device.id}-{device_class}"
        self._device_class = device_class
        self._name = f"{evo_device.id} {device_class}"

        self._unit_of_measurement = {DEVICE_CLASS_TEMPERATURE: TEMP_CELSIUS}.get(
            device_class, "%"
        )

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement


class EvoHeatDemand(EvoSensorBase):
    """Representation of a heat demand sensor."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device.heat_demand is not None

    @property
    def state(self) -> Optional[int]:
        """Return the heat demand of the actuator."""
        if self._evo_device.heat_demand is not None:
            return int(self._evo_device.heat_demand * 100)


class EvoRelayDemand(EvoSensorBase):
    """Representation of a relay demand sensor."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device.relay_demand is not None

    @property
    def state(self) -> Optional[int]:
        """Return the heat demand of the actuator."""
        if self._evo_device.relay_demand is not None:
            return int(self._evo_device.relay_demand * 100)


class EvoTemperature(EvoSensorBase):
    """Representation of a temperature sensor (incl. DHW sensor)."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device.temperature is not None

    @property
    def state(self) -> Optional[str]:
        """Return the temperature of the sensor."""
        if self._evo_device.temperature is not None:
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

    def __init__(self, evo_broker, evo_device, device_class) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = f"{evo_device.id}-{device_class}"
        self._device_class = device_class
        self._name = f"{evo_device.id} {device_class}"

        self._fault_log = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device._fault_log._fault_log_done

    @property
    def state(self) -> str:
        """Return the number of issues."""
        if self._fault_log is not None:
            return len(self._fault_log)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the device state attributes."""
        return self._fault_log

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return "entries"

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        self._fault_log = self._evo_device.fault_log()  # TODO: needs sorting
