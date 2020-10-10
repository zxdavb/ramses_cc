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
    PRESET_BOOST,
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
            "Found a Zone (%s), id=%s, name=%s",
            zone.heating_type,
            zone.idx,
            zone.name,
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
            "heat_demand": self._evo_device.heat_demand,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        if self._evo_device.heat_demand:
            return CURRENT_HVAC_HEAT
        if self._evo_device._ctl.mode is None:
            return
        if self._evo_device._ctl.mode["system_mode"] == "heat_off":
            return CURRENT_HVAC_OFF
        if self._evo_device._ctl.mode is not None:
            return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""
        # print(f"hvac_mode(CTL) mode={self._evo_device.mode}")

        if self._evo_device._ctl.mode is None:
            return
        if self._evo_device._ctl.mode["system_mode"] == "heat_off":
            return HVAC_MODE_OFF
        if self._evo_device._ctl.mode["system_mode"] == "away":
            return HVAC_MODE_AUTO

        if self._evo_device.mode is None:
            return
        if (
            self._evo_device.zone_config
            and self._evo_device.mode["setpoint"]
            <= self._evo_device.zone_config["min_temp"]
        ):
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]  # HVAC_MODE_AUTO,

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

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        if hvac_mode == HVAC_MODE_AUTO:  # FollowSchedule
            self._evo_device.cancel_override()

        elif hvac_mode == HVAC_MODE_HEAT:  # TemporaryOverride
            self._evo_device.set_override(mode="permanent_override", setpoint=25)

        else:  # HVAC_MODE_OFF, PermentOverride, temp = min
            self._evo_device.frost_protect()

    def set_temperature(self, **kwargs) -> None:
        """Set a new target temperature."""
        setpoint = kwargs["temperature"]
        mode = kwargs.get("mode")
        until = kwargs.get("until")

        if mode is None and until is None:
            self._evo_device.setpoint = setpoint
        else:
            self._evo_device(mode=mode, setpoint=setpoint, until=until)


class EvoController(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell Controller/Location."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize a Controller."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        self._icon = "mdi:thermostat"

        self._supported_features = SUPPORT_PRESET_MODE

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the average current temperature of the heating Zones.

        Controllers do not have a current temp, but one is expected by HA.
        """
        temps = [
            z.temperature for z in self._evo_device.zones if z.temperature is not None
        ]
        return round(sum(temps) / len(temps), 1) if temps else None

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "heat_demand": self._evo_device.heat_demand,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        # return

        if self._evo_device.mode is None:
            return
        if self._evo_device.mode["system_mode"] == "heat_off":
            return CURRENT_HVAC_OFF
        if self._evo_device.heat_demand:  # TODO: is maybe because of DHW
            return CURRENT_HVAC_HEAT
        return CURRENT_HVAC_IDLE
        # return CURRENT_HVAC_HEAT

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return the current operating mode of a Controller."""

        if self._evo_device.mode is None:
            return
        if self._evo_device.mode["system_mode"] == "heat_off":
            return HVAC_MODE_OFF
        if self._evo_device.mode["system_mode"] == "away":
            return HVAC_MODE_AUTO  # users can't adjust setpoints in away mode
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""

        return [HVAC_MODE_OFF, HVAC_MODE_HEAT]  # HVAC_MODE_AUTO,

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

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""

        if self._evo_device.mode is None:
            return

        return {
            "away": PRESET_AWAY,
            "custom": "custom",
            "day_off": PRESET_HOME,
            "day_off_eco": PRESET_HOME,
            "eco": PRESET_ECO,
        }.get(self._evo_device.mode["system_mode"], PRESET_NONE)

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        return [PRESET_NONE, PRESET_ECO, PRESET_AWAY, PRESET_HOME, "custom"]

    # async def async_set_temperature(self, **kwargs) -> None:
    #     """Raise exception as Controllers don't have a target temperature."""
    #     raise NotImplementedError("Evohome Controllers don't have target temperatures.")

    # async def async_set_hvac_mode(self, hvac_mode: str) -> None:
    #     """Set an operating mode for a Controller."""
    #     await self._set_tcs_mode(HA_HVAC_TO_TCS.get(hvac_mode))

    # async def async_set_preset_mode(self, preset_mode: Optional[str]) -> None:
    #     """Set the preset mode; if None, then revert to 'Auto' mode."""
    #     await self._set_tcs_mode(HA_PRESET_TO_TCS.get(preset_mode, EVO_AUTO))
