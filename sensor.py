"""Support for (RAMSES-II RF-based) devices of Honeywell systems."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.const import (
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoEntity

# from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_CLASS_DEMAND: str = "heat_demand"


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    new_devices = [x for x in broker.client.devices if x not in broker.sensors]

    new_entities = []
    for device in [d for d in new_devices if d.device_type in ["STA", "TRV"]]:
        _LOGGER.warn(
            "Found a Device (%s), id=%s, zone=%s",
            device.device_type,
            device.device_id,
            device.parent_zone,
        )
        new_entities.append(EvoBattery(broker, device, DEVICE_CLASS_BATTERY))
        new_entities.append(EvoTemperature(broker, device, DEVICE_CLASS_TEMPERATURE))
        if device.device_type == "TRV":
            new_entities.append(EvoDemand(broker, device, DEVICE_CLASS_DEMAND))
        broker.sensors.append(device)

    new_devices = [d for d in broker.client.domains if d not in broker.sensors]
    for device in [d for d in new_devices if d.domain_id not in ["system"]]:
        _LOGGER.warn(
            "Found a Device (%s), id=%s",
            device._type,
            device.domain_id,
        )
        new_entities.append(EvoDemand(broker, device, DEVICE_CLASS_DEMAND))
        broker.sensors.append(device)

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoSensor(EvoEntity):
    """Representation of a generic sensor."""

    def __init__(self, broker, device, device_class) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._device_class = device_class

        _name_suffix = {
            DEVICE_CLASS_TEMPERATURE: "temp",
            DEVICE_CLASS_DEMAND: "demand",
        }.get(device_class, device_class)
        self._name = f"{device.device_id} {_name_suffix}"

        self._unit_of_measurement = {DEVICE_CLASS_TEMPERATURE: TEMP_CELSIUS}.get(
            device_class, "%"
        )

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        pass

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        zone = self._evo_broker.client.zone_by_id.get(self._evo_device.parent_zone)
        return {"parent_zone": zone.name if zone else None}


class EvoBattery(EvoSensor):
    """Representation of a battery sensor."""

    @property
    def state(self) -> Optional[int]:
        """Return the battery level of the device."""
        if self._evo_device.battery is not None:
            return int(self._evo_device.battery * 100)


class EvoDemand(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def state(self) -> Optional[int]:
        """Return the heat demand of the actuator."""
        if self._evo_device.heat_demand is not None:
            return int(self._evo_device.heat_demand * 100)



class EvoTemperature(EvoSensor):
    """Representation of a temperature sensor."""

    @property
    def state(self) -> Optional[str]:
        """Return the temperature of the sensor."""
        if self._evo_device.temperature is not None:
            return self._evo_device.temperature

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        zone = self._evo_broker.client.zone_by_id.get(self._evo_device.parent_zone)
        return {
            "parent_zone": zone.name if zone else None,
            "setpoint": self._evo_device.setpoint,
        }
