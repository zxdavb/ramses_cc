"""Support for (RAMSES-II RF-based) devices of Honeywell systems."""
import logging
from typing import Any, Dict

from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_WINDOW,
)

from . import DOMAIN, EvoDeviceBase, new_binary_sensors
from .const import (
    ATTR_ACTUATOR_STATE,
    ATTR_BATTERY_STATE,
    ATTR_WINDOW_STATE,
)

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

    for device in [d for d in new_devices if hasattr(d, ATTR_ACTUATOR_STATE)]:
        _LOGGER.warning(
            "Found a Binary Sensor (actuator), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoActuator(broker, device, "actuator"))

    for device in [d for d in new_devices if hasattr(d, ATTR_BATTERY_STATE)]:
        _LOGGER.warning(
            "Found a Binary Sensor (battery), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoBattery(broker, device, DEVICE_CLASS_BATTERY))

    for device in [d for d in new_devices if hasattr(d, ATTR_WINDOW_STATE)]:
        _LOGGER.warning(
            "Found a Binary Sensor (window), id=%s, zone=%s", device.id, device.zone
        )
        new_entities.append(EvoWindow(broker, device, DEVICE_CLASS_WINDOW))

    if new_entities:
        broker.binary_sensors += new_devices
        async_add_entities(new_entities, update_before_add=True)


class EvoBinarySensorBase(EvoDeviceBase, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    def __init__(self, evo_broker, evo_device, device_class) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = f"{evo_device.id}-{device_class}_state"
        self._device_class = device_class
        self._name = f"{evo_device.id} {device_class}"


class EvoActuator(EvoBinarySensorBase):
    """Representation of an actuator."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device.actuator_enabled is not None

    @property
    def is_on(self) -> bool:
        """Return the status of the window."""
        return self._evo_device.actuator_enabled


class EvoBattery(EvoBinarySensorBase):
    """Representation of a low battery sensor."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device.battery_state is not None

    @property
    def is_on(self) -> bool:
        """Return the status of the battery: on means low."""
        if self._evo_device.battery_state is not None:
            return self._evo_device.battery_state.get("low_battery")

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        if self._evo_device.battery_state is None:
            battery_level = None
        else:
            battery_level = self._evo_device.battery_state.get("battery_level")
        return {**super().device_state_attributes, "battery_level": battery_level}


class EvoWindow(EvoBinarySensorBase):
    """Representation of an open window sensor."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device.window_state is not None

    @property
    def is_on(self) -> bool:
        """Return the status of the window."""
        if self._evo_device.window_state is None:
            return False  # assume window closed (state sent 1/day if no changea)
        return self._evo_device.window_state
