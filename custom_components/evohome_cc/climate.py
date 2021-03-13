#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for climate entities.
"""
import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any, Dict, List, Optional

import voluptuous as vol
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (  # PRESET_BOOST,
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
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoZoneBase
from .const import ATTR_SETPOINT, BROKER, MODE, SYSTEM_MODE, SystemMode, ZoneMode

# from .const import ATTR_HEAT_DEMAND

PLATFORM = "climate"
_LOGGER = logging.getLogger(__name__)

CONF_MODE = "mode"
CONF_SETPOINT = "setpoint"
CONF_DURATION = "duration"
CONF_UNTIL = "until"

ZONE_MODES = (
    ZoneMode.SCHEDULE,
    ZoneMode.ADVANCED,
    ZoneMode.PERMANENT,
    ZoneMode.TEMPORARY,
)
SET_ZONE_BASE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})
SET_ZONE_MODE_SCHEMA = SET_ZONE_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_MODE): vol.In(ZONE_MODES),
        vol.Optional(CONF_SETPOINT, default=21): vol.All(
            cv.positive_float,
            vol.Range(min=5, max=30),
        ),
        vol.Exclusive(CONF_UNTIL, "until"): cv.datetime,
        vol.Exclusive(CONF_DURATION, "until"): vol.All(
            cv.time_period,
            vol.Range(min=td(minutes=5), max=td(days=1)),
        ),
    }
)
PLATFORM_SERVICES = {
    "reset_zone_config": SET_ZONE_BASE_SCHEMA,
    "reset_zone_mode": SET_ZONE_BASE_SCHEMA,
    "set_zone_mode": SET_ZONE_MODE_SCHEMA,
}

PRESET_RESET = "Reset"  # reset all child zones to EVO_FOLLOW
PRESET_CUSTOM = "Custom"

TCS_PRESET_TO_HA = {
    SystemMode.AUTO: None,
    SystemMode.AWAY: PRESET_AWAY,
    SystemMode.CUSTOM: PRESET_CUSTOM,
    SystemMode.DAY_OFF: PRESET_HOME,
    SystemMode.ECO: PRESET_ECO,
    SystemMode.RESET: PRESET_RESET,
}

HA_PRESET_TO_TCS = {v: k for k, v in TCS_PRESET_TO_HA.items()}
HA_HVAC_TO_TCS = {HVAC_MODE_OFF: SystemMode.HEAT_OFF, HVAC_MODE_HEAT: SystemMode.AUTO}

TCS_MODE_TO_HA_PRESET = {
    SystemMode.AWAY: PRESET_AWAY,
    SystemMode.CUSTOM: "custom",
    SystemMode.DAY_OFF: PRESET_HOME,
    SystemMode.DAY_OFF_ECO: PRESET_HOME,
    SystemMode.ECO: PRESET_ECO,
}

EVOZONE_PRESET_TO_HA = {
    ZoneMode.SCHEDULE: PRESET_NONE,
    ZoneMode.TEMPORARY: "temporary",
    ZoneMode.PERMANENT: "permanent",
}
HA_PRESET_TO_EVOZONE = {v: k for k, v in EVOZONE_PRESET_TO_HA.items()}


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create the evohome Controller, and its Zones, if any."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]
    new_entities = []

    if broker.client.evo not in broker.climates:
        new_entities.append(EvoController(broker, broker.client.evo))
        broker.climates.append(broker.client.evo)

    for zone in [z for z in broker.client.evo.zones if z not in broker.climates]:
        new_entities.append(EvoZone(broker, zone))
        broker.climates.append(zone)

    if new_entities:
        async_add_entities(new_entities, update_before_add=True)

    if broker.services.get(PLATFORM):
        return
    broker.services[PLATFORM] = True

    register_svc = entity_platform.current_platform.get().async_register_entity_service
    [register_svc(k, v, f"svc_{k}") for k, v in PLATFORM_SERVICES.items()]


class EvoZone(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell evohome Zone."""

    def __init__(self, broker, device) -> None:
        """Initialize a Zone."""
        _LOGGER.info("Found a Zone (%s), id=%s", device.heating_type, device.idx)
        super().__init__(broker, device)

        self._unique_id = device.id
        self._icon = "mdi:radiator"

        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE
        self._preset_modes = list(HA_PRESET_TO_EVOZONE)

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "heating_type": self._device.heating_type,
            "config": self._device.config,
            "heat_demand": self._device.heat_demand,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        if self._device.heat_demand:
            return CURRENT_HVAC_HEAT
        if self._device._evo.system_mode is None:
            return
        if self._device._evo.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return CURRENT_HVAC_OFF
        if self._device._evo.system_mode is not None:
            return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""

        if self._device._evo.system_mode is None:
            return
        if self._device._evo.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVAC_MODE_OFF
        if self._device._evo.system_mode[SYSTEM_MODE] == SystemMode.AWAY:
            return HVAC_MODE_AUTO

        if self._device.mode is None:
            return
        if (
            self._device.config
            and self._device.mode[ATTR_SETPOINT] <= self._device.config["min_temp"]
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
        if self._device.config:
            return self._device.config["max_temp"]

    @property
    def min_temp(self) -> Optional[float]:
        """Return the minimum target temperature of a Zone."""
        if self._device.config:
            return self._device.config["min_temp"]

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""
        if self._device._evo.system_mode is None or self._device.mode is None:
            return

        if self._device._evo.system_mode[SYSTEM_MODE] in (
            SystemMode.AWAY,
            SystemMode.HEAT_OFF,
        ):
            return TCS_PRESET_TO_HA.get(self._device._evo.system_mode[SYSTEM_MODE])
        return EVOZONE_PRESET_TO_HA.get(self._device.mode[MODE])

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        return self._preset_modes

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._device.setpoint

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        if hvac_mode == HVAC_MODE_AUTO:  # FollowSchedule
            self._device.reset_mode()

        elif hvac_mode == HVAC_MODE_HEAT:  # TemporaryOverride
            self._device.set_mode(mode=ZoneMode.PERMANENT, setpoint=25)

        else:  # HVAC_MODE_OFF, PermentOverride, temp = min
            self._device.set_frost_mode()

    def set_temperature(self, **kwargs) -> None:
        """Set a new target temperature."""
        setpoint = kwargs["temperature"]
        mode = kwargs.get(MODE)
        until = kwargs.get("until")

        if mode is None and until is None:
            self._device.setpoint = setpoint
        else:
            self._device(mode=mode, setpoint=setpoint, until=until)

    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to following the schedule."""
        evozone_preset_mode = HA_PRESET_TO_EVOZONE.get(preset_mode, ZoneMode.SCHEDULE)
        setpoint = self._device.setpoint

        if evozone_preset_mode == ZoneMode.SCHEDULE:
            self._device.reset_mode()
        elif evozone_preset_mode == ZoneMode.TEMPORARY:
            self._device.set_mode(mode=ZoneMode.TEMPORARY, setpoint=setpoint)
        elif evozone_preset_mode == ZoneMode.PERMANENT:
            self._device.set_mode(mode=ZoneMode.PERMANENT, setpoint=setpoint)

    def svc_reset_zone_config(self):
        """Reset the configuration of the Zone."""
        self._device.reset_config()

    def svc_reset_zone_mode(self):
        """Reset the operating mode of the Zone."""
        self._device.reset_mode()

    def svc_set_zone_mode(self, mode=None, setpoint=None, duration=None, until=None):
        """Set the (native) operating mode of the Zone."""
        if until is None and duration is not None:
            until = dt.now() + duration
        self._device.set_mode(mode=mode, setpoint=setpoint, until=until)


class EvoController(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell Controller/Location."""

    def __init__(self, broker, device) -> None:
        """Initialize a Controller."""
        _LOGGER.info("Found a Controller, id=%s", device.id)
        super().__init__(broker, device)

        self._unique_id = device.id
        self._icon = "mdi:thermostat"

        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the average current temperature of the heating Zones.

        Controllers do not have a current temp, but one is expected by HA.
        """
        temps = [z.temperature for z in self._device.zones if z.temperature is not None]
        return round(sum(temps) / len(temps), 1) if temps else None

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "heat_demand": self._device.heat_demand,
            "heat_demands": self._device.heat_demands,
            "relay_demands": self._device.relay_demands,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        # return

        if self._device.system_mode is None:
            return
        if self._device.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return CURRENT_HVAC_OFF
        if self._device.heat_demand:  # TODO: is maybe because of DHW
            return CURRENT_HVAC_HEAT
        return CURRENT_HVAC_IDLE
        # return CURRENT_HVAC_HEAT

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return the current operating mode of a Controller."""

        if self._device.system_mode is None:
            return
        if self._device.system_mode[SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVAC_MODE_OFF
        if self._device.system_mode[SYSTEM_MODE] == SystemMode.AWAY:
            return HVAC_MODE_AUTO  # users can't adjust setpoints in away mode
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""

        return [HVAC_MODE_OFF, HVAC_MODE_HEAT]  # HVAC_MODE_AUTO,

    @property
    def max_temp(self) -> None:
        """Return None as Controllers don't have a target temperature."""
        return

    @property
    def min_temp(self) -> None:
        """Return None as Controllers don't have a target temperature."""
        return

    @property
    def name(self) -> str:
        return "Controller"

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""

        if self._device.system_mode is None:
            return

        return TCS_MODE_TO_HA_PRESET.get(
            self._device.system_mode[SYSTEM_MODE], PRESET_NONE
        )

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        return [PRESET_NONE, PRESET_ECO, PRESET_AWAY, PRESET_HOME, "custom"]

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        zones = [z for z in self._device.zones if z.setpoint is not None]
        temps = [z.setpoint for z in zones if z.heat_demand is not None]
        if temps:
            return min(temps)
        return max([z.setpoint for z in zones]) if temps else None

        # temps = [z.setpoint for z in self._device.zones]
        # return round(sum(temps) / len(temps), 1) if temps else None

    # async def async_set_temperature(self, **kwargs) -> None:
    #     """Raise exception as Controllers don't have a target temperature."""
    #     raise NotImplementedError("Evohome Controllers don't have setpoints.")

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set an operating mode for a Controller."""
        await self._device.set_mode(HA_HVAC_TO_TCS.get(hvac_mode))

    async def async_set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to 'Auto' mode."""
        await self._device.set_mode(HA_PRESET_TO_TCS.get(preset_mode, SystemMode.AWAY))
