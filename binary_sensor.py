"""Support for (RAMSES-II RF-based) devices of Honeywell systems."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.components.binary_sensor import (
    BinarySensorDevice,
    DEVICE_CLASS_WINDOW,
)

from . import DOMAIN, EvoEntity

# from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTR_WINDOW_OPEN: str = "window_open"  # On means open, Off means closed


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor sensor entities."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    new_devices = [d for d in broker.client.devices if d not in broker.binary_sensors]

    new_entities = []
    for device in [d for d in new_devices if d.device_type == "TRV"]:
        _LOGGER.warn(
            "Found a Device (%s), id=%s, zone=%s",
            device.device_type,
            device.device_id,
            device.parent_zone,
        )
        new_entities.append(EvoWindow(broker, device))
        broker.binary_sensors.append(device)

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoWindow(EvoEntity, BinarySensorDevice):
    """Representation of an open window sensor."""

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._name = f"{device.device_id} {DEVICE_CLASS_WINDOW}"

    @property
    def is_on(self) -> bool:
        """Return the status of the window."""
        if self._evo_device.window_state is None:
            return False  # assume window closed (state sent 1/day if no changea)
        return self._evo_device.window_state

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_WINDOW

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        zone = self._evo_broker.client.zone_by_id.get(self._evo_device.parent_zone)
        return {"parent_zone": zone.name if zone else None}

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        pass
