"""Support for Climate devices of (RAMSES-II RF-based) Honeywell systems."""
import logging
from typing import List, Optional

from homeassistant.components.climate import ClimateDevice
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
from homeassistant.const import PRECISION_TENTHS, TEMP_CELSIUS
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.util.dt import parse_datetime

from . import EvoEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create the evohome Controller, and its Zones, if any."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    new_zones = [z for z in broker.client.zones if z not in broker.climates]

    new_entities = []
    for zone in [z for z in new_zones if z.zone_type == "Radiator Valve"]:
        _LOGGER.warn(
            "Found a Zone (%s), id=%s, name=%s",
            zone.zone_type,
            zone.zone_idx,
            zone.name,
        )
        new_entities.append(EvoZone(broker, zone))
        broker.climates.append(zone)

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoZone(EvoEntity, ClimateDevice):
    """Base for a Honeywell evohome Zone."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize a Zone."""
        super().__init__(evo_broker, evo_device)

        self.entity_id = f"climate.rf_zone_{evo_device.zone_idx}"
        self._name = evo_device.name
        self._icon = "mdi:radiator"

    @property
    def name(self) -> str:
        return self._name

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

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
        return CURRENT_HVAC_HEAT if self._evo_device.heat_demand else CURRENT_HVAC_IDLE

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        if self._evo_device.temperature is not None:
            return self._evo_device.temperature

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        if self._evo_device.setpoint_status:
            return self._evo_device.setpoint_status["setpoint"]

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE
