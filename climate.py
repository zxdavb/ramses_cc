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
    new_entities = []

    if broker.client.evo not in broker.climates:
        _LOGGER.warning("Found a Controller, id=%s", broker.client.evo)
        new_entities.append(EvoController(broker, broker.client.evo))
        broker.climates.append(broker.client.evo)

    for zone in [z for z in broker.client.evo.zones if z not in broker.climates]:
        _LOGGER.warning(
            "Found a Zone (%s), id=%s, name=%s", zone.heating_type, zone.idx, zone.name,
        )
        new_entities.append(EvoZone(broker, zone))
        broker.climates.append(zone)

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)


class EvoZone(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell evohome Zone."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize a Zone."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        self._icon = "mdi:radiator"

        self._supported_features = SUPPORT_TARGET_TEMPERATURE  # SUPPORT_PRESET_MODE |

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "heating_type": self._evo_device.heating_type,
            "zone_config": self._evo_device.zone_config,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""
        if hasattr(self._evo_device, "heat_demand"):
            return (
                CURRENT_HVAC_HEAT if self._evo_device.heat_demand else CURRENT_HVAC_IDLE
            )

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""
        if self._evo_device.mode is None:
            return

        if self._evo_device.mode["mode"] == "FollowSchedule":
            return HVAC_MODE_AUTO

        if self._evo_device.mode["mode"] == "PermanentOverride":
            if (
                self.target_temperature
                and self.min_temp
                and self.target_temperature <= self.min_temp
            ):
                return HVAC_MODE_OFF

        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_AUTO, HVAC_MODE_OFF, HVAC_MODE_HEAT]

    @property
    def max_temp(self) -> Optional[float]:
        """Return the maximum target temperature of a Zone."""
        if self._evo_device.zone_config:
            return self._evo_device.zone_config["max_temp"]

    @property
    def min_temp(self) -> Optional[float]:
        """Return the minimum target temperature of a Zone."""
        if self._evo_device.zone_config:
            return self._evo_device.zone_config["min_temp"]

    # @property
    # def preset_mode(self) -> Optional[str]:
    #     """Return the current preset mode, e.g., home, away, temp."""
    #     if self._evo_tcs.systemModeStatus["mode"] in [EVO_AWAY, EVO_HEATOFF]:
    #         return TCS_PRESET_TO_HA.get(self._evo_tcs.systemModeStatus["mode"])
    #     return EVO_PRESET_TO_HA.get(self._evo_device.setpointStatus["setpointMode"])

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._evo_device.setpoint

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        if hvac_mode == HVAC_MODE_AUTO:  # FollowSchedule
            await self._evo_device.cancel_override()

        elif hvac_mode == HVAC_MODE_HEAT:  # TemporaryOverride
            await self._evo_device.set_override(mode="02", setpoint=25)

        else:  # HVAC_MODE_OFF, PermentOverride, temp = min
            await self._evo_device.frost_protect()


class EvoController(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell Controller/Location."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize a Controller."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        self._icon = "mdi:thermostat"

        self._supported_features = 0  # SUPPORT_PRESET_MODE

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the average current temperature of the heating Zones.

        Controllers do not have a current temp, but one is expected by HA.
        """
        temps = [
            z.temperature
            for z in self._evo_device.zones
            if z.temperature is not None
        ]
        return round(sum(temps) / len(temps), 1) if temps else None

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""
        # if self._evo_device.mode is None:
        #     return
        # if self._evo_device.mode["system_mode"] == "HeatOff":
        #     return CURRENT_HVAC_OFF
        # if True:
        #     return CURRENT_HVAC_HEAT
        return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> str:
        """Return the current operating mode of a Controller."""
        # tcs_mode = self._evo_tcs.systemModeStatus["mode"]
        # return HVAC_MODE_OFF if tcs_mode == EVO_HEATOFF else HVAC_MODE_HEAT
        pass

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_AUTO, HVAC_MODE_OFF, HVAC_MODE_HEAT]

    @property
    def max_temp(self) -> None:
        """Return None as Controllers don't have a target temperature."""
        return None

    @property
    def min_temp(self) -> None:
        """Return None as Controllers don't have a target temperature."""
        return None

    @property
    def name(self) -> str:
        return "Controller"

    # @property
    # def preset_mode(self) -> Optional[str]:
    #     """Return the current preset mode, e.g., home, away, temp."""
    #     return TCS_PRESET_TO_HA.get(self._evo_tcs.systemModeStatus["mode"])

    # async def async_set_temperature(self, **kwargs) -> None:
    #     """Raise exception as Controllers don't have a target temperature."""
    #     raise NotImplementedError("Evohome Controllers don't have target temperatures.")

    # async def async_set_hvac_mode(self, hvac_mode: str) -> None:
    #     """Set an operating mode for a Controller."""
    #     await self._set_tcs_mode(HA_HVAC_TO_TCS.get(hvac_mode))

    # async def async_set_preset_mode(self, preset_mode: Optional[str]) -> None:
    #     """Set the preset mode; if None, then revert to 'Auto' mode."""
    #     await self._set_tcs_mode(HA_PRESET_TO_TCS.get(preset_mode, EVO_AUTO))
