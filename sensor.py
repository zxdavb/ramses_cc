"""Support for (RAMSES-II RF-based) devices of Honeywell systems."""
import logging
from typing import Any, Dict, Optional

from homeassistant.const import (
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoDevice
from .const import (
    ATTR_BATTERY,
    ATTR_HEAT_DEMAND,
    ATTR_SETPOINT,
    ATTR_TEMPERATURE,
    DEVICE_HAS_SENSOR,
)

_LOGGER = logging.getLogger(__name__)


DEVICE_CLASS_DEMAND: str = "heat_demand"


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    new_devices = [
        d
        for d in broker.client.evo.devices
        if d not in broker.sensors and d.type in DEVICE_HAS_SENSOR
    ]
    if not new_devices:
        return

    broker.sensors += new_devices
    new_entities = []

    for device in [d for d in new_devices if hasattr(d, ATTR_BATTERY)]:
        _LOGGER.warning(
            "Found a Sensor (battery), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoBattery(broker, device, DEVICE_CLASS_BATTERY))

    for device in [d for d in new_devices if hasattr(d, ATTR_HEAT_DEMAND)]:
        _LOGGER.warning(
            "Found a Sensor (demand), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoDemand(broker, device, DEVICE_CLASS_DEMAND))

    for device in [d for d in new_devices if hasattr(d, ATTR_TEMPERATURE)]:
        _LOGGER.warning(
            "Found a Sensor (temp), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoTemperature(broker, device, DEVICE_CLASS_TEMPERATURE))

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoSensor(EvoDevice):
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


class EvoBattery(EvoSensor):
    """Representation of a battery sensor."""

    @property
    def state(self) -> Optional[int]:
        """Return the battery level of the device."""
        if self._evo_device.battery_state is not None:
            if self._evo_device.battery_state.get("battery_level") is not None:
                return int(self._evo_device.battery_state["battery_level"] * 100)
            return 100 if self._evo_device.battery_state["low_battery"] else 10


class EvoDemand(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def state(self) -> Optional[int]:
        """Return the heat demand of the actuator."""
        if self._evo_device.heat_demand is not None:
            return int(self._evo_device.heat_demand * 100)


class EvoTemperature(EvoSensor):
    """Representation of a temperature sensor (incl. DHW sensor)."""

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
