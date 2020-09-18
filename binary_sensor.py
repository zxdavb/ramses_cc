"""Support for (RAMSES-II RF-based) devices of Honeywell systems."""
import logging
from typing import Any, Dict

from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    DEVICE_CLASS_WINDOW,
)

from . import DOMAIN, EvoDevice
from .const import ATTR_ACTUATOR_STATE, ATTR_WINDOW_STATE, DEVICE_HAS_BINARY_SENSOR

_LOGGER = logging.getLogger(__name__)


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
        if d not in broker.binary_sensors and d.type in DEVICE_HAS_BINARY_SENSOR
    ]
    if not new_devices:
        return

    broker.binary_sensors += new_devices
    new_entities = []

    for device in [d for d in new_devices if hasattr(d, ATTR_WINDOW_STATE)]:
        _LOGGER.warning(
            "Found a Binary Sensor (window), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoWindow(broker, device))

    for device in [d for d in new_devices if hasattr(d, ATTR_ACTUATOR_STATE)]:
        _LOGGER.warning(
            "Found a Binary Sensor (actuator), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoActuator(broker, device))

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoBinarySensor(EvoDevice, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    def __init__(self, evo_broker, evo_device, device_class) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = f"{evo_device.id}-{device_class}"
        self._device_class = device_class
        self._name = f"{evo_device.id} {device_class}"


class EvoActuator(EvoBinarySensor):
    """Representation of an actautor."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device, "actuator")

    @property
    def is_on(self) -> bool:
        """Return the status of the window."""
        return self._evo_device.actuator_enabled


class EvoWindow(EvoBinarySensor):
    """Representation of an open window sensor."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device, DEVICE_CLASS_WINDOW)

    @property
    def is_on(self) -> bool:
        """Return the status of the window."""
        if self._evo_device.window_state is None:
            return False  # assume window closed (state sent 1/day if no changea)
        return self._evo_device.window_state
