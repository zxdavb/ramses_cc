#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for climate entities.
"""
import logging
from typing import Any, Dict, List, Optional

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

from . import (
    ATTR_DURATION_DAYS,
    ATTR_DURATION_HOURS,
    ATTR_DURATION_UNTIL,
    ATTR_SYSTEM_MODE,
    ATTR_ZONE_TEMP,
    SVC_RESET_ZONE_OVERRIDE,
    SVC_SET_SYSTEM_MODE,
)

# from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
import homeassistant.util.dt as dt_util

from . import DOMAIN, EvoZoneBase
from .const import (
    BROKER,
    EVO_MODE_AUTO,
    EVO_MODE_AWAY,
    EVO_MODE_CUSTOM,
    EVO_MODE_DAY_OFF,
    EVO_MODE_DAY_OFF_ECO,
    EVO_MODE_ECO,
    EVO_MODE_HEAT_OFF,
    EVO_MODE_RESET,
    ZONE_MODE_FOLLOW,
    ZONE_MODE_PERM,
    ZONE_MODE_TEMP,
)

# from .const import ATTR_HEAT_DEMAND

_LOGGER = logging.getLogger(__name__)

PRESET_RESET = "Reset"  # reset all child zones to EVO_FOLLOW
PRESET_CUSTOM = "Custom"

TCS_PRESET_TO_HA = {
    EVO_MODE_AUTO: None,
    EVO_MODE_AWAY: PRESET_AWAY,
    EVO_MODE_CUSTOM: PRESET_CUSTOM,
    EVO_MODE_DAY_OFF: PRESET_HOME,
    EVO_MODE_ECO: PRESET_ECO,
    EVO_MODE_RESET: PRESET_RESET,
}

HA_PRESET_TO_TCS = {v: k for k, v in TCS_PRESET_TO_HA.items()}
HA_HVAC_TO_TCS = {HVAC_MODE_OFF: EVO_MODE_HEAT_OFF, HVAC_MODE_HEAT: EVO_MODE_AUTO}

EVOZONE_PRESET_TO_HA = {
    ZONE_MODE_FOLLOW: PRESET_NONE,
    ZONE_MODE_TEMP: "temporary",
    ZONE_MODE_PERM: "permanent",
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
        _LOGGER.info("Found a Controller, id=%s", broker.client.evo.id)
        new_entities.append(EvoController(broker, broker.client.evo))
        broker.climates.append(broker.client.evo)

    for zone in [z for z in broker.client.evo.zones if z not in broker.climates]:
        _LOGGER.info(
            "Found a Zone (%s), id=%s, name=%s", zone.heating_type, zone.idx, zone.name
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

        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE
        self._preset_modes = list(HA_PRESET_TO_EVOZONE)

    def zone_svc_request(self, service: dict, data: dict) -> None:
        """Process a service request (setpoint override) for a zone."""
        
        if service == SVC_RESET_ZONE_OVERRIDE:
            self._evo_device.reset_mode()
            return

        # otherwise it is SVC_SET_ZONE_OVERRIDE
        setpoint = max(min(data[ATTR_ZONE_TEMP], self.max_temp), self.min_temp)

        if ATTR_DURATION_UNTIL in data:
            duration = data[ATTR_DURATION_UNTIL]
            if duration.total_seconds() > 0:
                until = dt_util.now() + data[ATTR_DURATION_UNTIL]
        else:
            until = None  # indefinitely

        until = dt_util.as_utc(until) if until else None
        if until is None:
            self._evo_device.set_mode(mode=ZONE_MODE_PERM, setpoint=setpoint)
        elif duration.total_seconds() == 0:
            self._evo_device.set_mode(mode=ZONE_MODE_TEMP, setpoint=setpoint)
        else:
            self._evo_device.set_mode(mode=ZONE_MODE_TEMP, setpoint=setpoint, until=until)

        self._refresh()

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "heating_type": self._evo_device.heating_type,
            "config": self._evo_device.config,
            "heat_demand": self._evo_device.heat_demand,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        if self._evo_device.heat_demand:
            return CURRENT_HVAC_HEAT
        if self._evo_device._evo.system_mode is None:
            return
        if self._evo_device._evo.system_mode["system_mode"] == EVO_MODE_HEAT_OFF:
            return CURRENT_HVAC_OFF
        if self._evo_device._evo.system_mode is not None:
            return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""
        # print(f"hvac_mode(CTL) mode={self._evo_device.mode}")

        if self._evo_device._evo.system_mode is None:
            return
        if self._evo_device._evo.system_mode["system_mode"] == EVO_MODE_HEAT_OFF:
            return HVAC_MODE_OFF
        if self._evo_device._evo.system_mode["system_mode"] == EVO_MODE_AWAY:
            return HVAC_MODE_AUTO

        if self._evo_device.mode is None:
            return
        if (
            self._evo_device.config
            and self._evo_device.mode["setpoint"] <= self._evo_device.config["min_temp"]
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
        if self._evo_device.config:
            return self._evo_device.config["max_temp"]

    @property
    def min_temp(self) -> Optional[float]:
        """Return the minimum target temperature of a Zone."""
        if self._evo_device.config:
            return self._evo_device.config["min_temp"]

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""
        if self._evo_device._evo.system_mode is None or self._evo_device.mode is None:
            return

        if self._evo_device._evo.system_mode["system_mode"] in (EVO_MODE_AWAY, EVO_MODE_HEAT_OFF):
            return TCS_PRESET_TO_HA.get(
                self._evo_device._evo.system_mode["system_mode"]
            )
        return EVOZONE_PRESET_TO_HA.get(self._evo_device.mode["mode"])

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        return self._preset_modes

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._evo_device.setpoint

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        if hvac_mode == HVAC_MODE_AUTO:  # FollowSchedule
            self._evo_device.reset_mode()

        elif hvac_mode == HVAC_MODE_HEAT:  # TemporaryOverride
            self._evo_device.set_mode(mode=ZONE_MODE_PERM, setpoint=25)

        else:  # HVAC_MODE_OFF, PermentOverride, temp = min
            self._evo_device.set_frost_mode()

        self._refresh()

    def set_temperature(self, **kwargs) -> None:
        """Set a new target temperature."""
        setpoint = kwargs["temperature"]
        mode = kwargs.get("mode")
        until = kwargs.get("until")

        if mode is None and until is None:
            self._evo_device.setpoint = setpoint
        else:
            self._evo_device(mode=mode, setpoint=setpoint, until=until)

        self._refresh()

    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to following the schedule."""
        evozone_preset_mode = HA_PRESET_TO_EVOZONE.get(preset_mode, ZONE_MODE_FOLLOW)
        setpoint = self._evo_device.setpoint

        if evozone_preset_mode == ZONE_MODE_FOLLOW:
            self._evo_device.reset_mode()
        elif evozone_preset_mode == ZONE_MODE_TEMP:
            self._evo_device.set_mode(mode=ZONE_MODE_TEMP, setpoint=setpoint)
        elif evozone_preset_mode == ZONE_MODE_PERM:
            self._evo_device.set_mode(mode=ZONE_MODE_PERM, setpoint=setpoint)

        self._refresh()


class EvoController(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell Controller/Location."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize a Controller."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        self._icon = "mdi:thermostat"

        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE

    def controller_svc_request(self, service: dict, data: dict) -> None:
        """Process a service request (system mode) for a controller.
        Data validation is not required, it will have been done upstream.
        """
        if service == SVC_SET_SYSTEM_MODE:
            mode = data[ATTR_SYSTEM_MODE]
        else:  # otherwise it is SVC_RESET_SYSTEM
            mode = HA_PRESET_TO_TCS.get(preset_mode, EVO_MODE_AUTO)

        self._evo_device.set_mode(
            mode=mode,
            setpoint=data[ATTR_ZONE_TEMP],
            until=data[ATTR_DURATION_UNTIL]
)

        self._refresh()

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
            "heat_demand": self._evo_device.heat_demand,
            "heat_demands": self._evo_device.heat_demands,
            "relay_demands": self._evo_device.relay_demands,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported."""

        # return

        if self._evo_device.system_mode is None:
            return
        if self._evo_device.system_mode["system_mode"] == EVO_MODE_HEAT_OFF:
            return CURRENT_HVAC_OFF
        if self._evo_device.heat_demand:  # TODO: is maybe because of DHW
            return CURRENT_HVAC_HEAT
        return CURRENT_HVAC_IDLE
        # return CURRENT_HVAC_HEAT

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return the current operating mode of a Controller."""

        if self._evo_device.system_mode is None:
            return
        if self._evo_device.system_mode["system_mode"] == EVO_MODE_HEAT_OFF:
            return HVAC_MODE_OFF
        if self._evo_device.system_mode["system_mode"] == EVO_MODE_AWAY:
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

        if self._evo_device.system_mode is None:
            return

        return {
            EVO_MODE_AWAY: PRESET_AWAY,
            EVO_MODE_CUSTOM: "custom",
            EVO_MODE_DAY_OFF: PRESET_HOME,
            EVO_MODE_DAY_OFF_ECO: PRESET_HOME,
            EVO_MODE_ECO: PRESET_ECO,
        }.get(self._evo_device.system_mode["system_mode"], PRESET_NONE)

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        return [PRESET_NONE, PRESET_ECO, PRESET_AWAY, PRESET_HOME, "custom"]

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        zones = [z for z in self._evo_device.zones if z.setpoint is not None]
        temps = [z.setpoint for z in zones if z.heat_demand is not None]
        if temps:
            return min(temps)
        return max([z.setpoint for z in zones]) if temps else None

        # temps = [z.setpoint for z in self._evo_device.zones]
        # return round(sum(temps) / len(temps), 1) if temps else None

    # async def async_set_temperature(self, **kwargs) -> None:
    #     """Raise exception as Controllers don't have a target temperature."""
    #     raise NotImplementedError("Evohome Controllers don't have setpoints.")

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set an operating mode for a Controller."""
        await self._evo_device.set_mode(HA_HVAC_TO_TCS.get(hvac_mode))

        self._refresh()

    async def async_set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to 'Auto' mode."""
        await self._evo_device.set_mode(HA_PRESET_TO_TCS.get(preset_mode, EVO_MODE_AWAY))

        self._refresh()
        
