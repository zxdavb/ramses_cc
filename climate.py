"""Support for Climate devices of (RAMSES-II RF-based) Honeywell systems."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_NONE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoZoneBase
from .const import ATTR_HEAT_DEMAND

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create the evohome Controller, and its Zones, if any."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    new_zones = [z for z in broker.client.evo.zones if z not in broker.climates]
    if not new_zones:
        return

    broker.climates += new_zones
    new_entities = []

    for zone in [z for z in new_zones]:
        _LOGGER.warning(
            "Found a Zone (%s), id=%s, name=%s", zone.heating_type, zone.idx, zone.name,
        )
        new_entities.append(EvoZone(broker, zone))

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoZone(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell evohome Zone."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize a Zone."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        # self._icon = "mdi:radiator"

        self._supported_features = SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation ie. heat, cool mode."""
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_HEAT]

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""
        if hasattr(self._evo_device, "heat_demand"):
            return (
                CURRENT_HVAC_HEAT if self._evo_device.heat_demand else CURRENT_HVAC_IDLE
            )

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._evo_device.setpoint

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "heating_type": self._evo_device.heating_type,
            "zone_config": self._evo_device.zone_config,
        }
