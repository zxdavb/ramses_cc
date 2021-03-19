#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Provides support for climate entities.
"""
import logging
from datetime import datetime as dt
from typing import Any, Dict, Optional

from evohome_rf.const import SystemMode, ZoneMode
from homeassistant.components.climate import DOMAIN as PLATFORM
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    CURRENT_HVAC_HEAT,  # PRESET_BOOST,; is heating
)
from homeassistant.components.climate.const import CURRENT_HVAC_IDLE  # is idle
from homeassistant.components.climate.const import CURRENT_HVAC_OFF  # is off
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,  # user cannot adjust the setpoint
)
from homeassistant.components.climate.const import HVAC_MODE_HEAT  # heating
from homeassistant.components.climate.const import (
    HVAC_MODE_OFF,  # all activity is disabled, device is off/standby
)
from homeassistant.components.climate.const import PRESET_AWAY  # device is in away mode
from homeassistant.components.climate.const import (
    PRESET_ECO,  # there is also PRESET_BOOST, PRESET_ECO_BOOST = "eco_boost"
)
from homeassistant.components.climate.const import PRESET_HOME  # device is in home mode
from homeassistant.components.climate.const import PRESET_NONE  # no preset is active
from homeassistant.components.climate.const import (
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoZoneBase
from .const import ATTR_SETPOINT, BROKER, DOMAIN
from .schema import (
    CLIMATE_SERVICES,
    CONF_MODE,
    CONF_SYSTEM_MODE,
    CONF_UNTIL,
    SVC_RESET_SYSTEM,
    SVC_SET_SYSTEM_MODE,
)

_LOGGER = logging.getLogger(__name__)


MODE_TCS_TO_HA = {
    SystemMode.AUTO: HVAC_MODE_AUTO,  # or: HVAC_MODE_HEAT?
    SystemMode.HEAT_OFF: HVAC_MODE_OFF,
}
MODE_TCS_TO_HA[SystemMode.RESET] = MODE_TCS_TO_HA[SystemMode.AUTO]

MODE_TO_TCS = {v: k for k, v in MODE_TCS_TO_HA.items()}

PRESET_TCS_TO_HA = {
    SystemMode.AUTO: PRESET_NONE,
    SystemMode.AWAY: PRESET_AWAY,
    SystemMode.CUSTOM: "custom",  # NOTE: not an offical PRESET
    SystemMode.DAY_OFF: PRESET_HOME,
    SystemMode.ECO_BOOST: PRESET_ECO,  # or: PRESET_BOOST
    SystemMode.HEAT_OFF: PRESET_NONE,
}
PRESET_TCS_TO_HA[SystemMode.DAY_OFF_ECO] = PRESET_TCS_TO_HA[SystemMode.DAY_OFF]
PRESET_TCS_TO_HA[SystemMode.RESET] = PRESET_TCS_TO_HA[SystemMode.AUTO]

PRESET_TO_TCS = {
    v: k
    for k, v in PRESET_TCS_TO_HA.items()
    if k
    in (
        SystemMode.AUTO,
        SystemMode.AWAY,
        SystemMode.DAY_OFF,
        SystemMode.ECO_BOOST,
    )
}
#
MODE_ZONE_TO_HA = {
    ZoneMode.ADVANCED: HVAC_MODE_HEAT,
    ZoneMode.SCHEDULE: HVAC_MODE_AUTO,
}
MODE_ZONE_TO_HA[ZoneMode.PERMANENT] = MODE_ZONE_TO_HA[ZoneMode.ADVANCED]
MODE_ZONE_TO_HA[ZoneMode.TEMPORARY] = MODE_ZONE_TO_HA[ZoneMode.ADVANCED]

MODE_TO_ZONE = {
    v: k
    for k, v in PRESET_TCS_TO_HA.items()
    if k
    in (
        ZoneMode.SCHEDULE,
        ZoneMode.PERMANENT,
    )
}
PRESET_ZONE_TO_HA = {
    ZoneMode.SCHEDULE: PRESET_NONE,
    ZoneMode.TEMPORARY: "temporary",
    ZoneMode.PERMANENT: "permanent",
}
PRESET_TO_ZONE = {v: k for k, v in PRESET_ZONE_TO_HA.items()}


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
        async_add_entities(new_entities)  # TODO: , update_before_add=True)

    if broker.services.get(PLATFORM):
        return
    broker.services[PLATFORM] = True

    register_svc = entity_platform.current_platform.get().async_register_entity_service
    [register_svc(k, v, f"svc_{k}") for k, v in CLIMATE_SERVICES.items()]


class EvoZone(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell evohome Zone."""

    def __init__(self, broker, device) -> None:
        """Initialize a Zone."""
        _LOGGER.info("Found a Zone (%s), id=%s", device.heating_type, device.idx)
        super().__init__(broker, device)

        self._unique_id = device.id
        self._icon = "mdi:radiator"
        self._hvac_modes = list(MODE_TO_ZONE)
        self._preset_modes = list(PRESET_TO_ZONE)
        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "config": self._device.config,
            "heating_type": self._device.heating_type,
            "heat_demand": self._device.heat_demand,
            "mode": self._device.mode,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Done. Return the current running hvac operation if supported."""

        if self._device._evo.system_mode is None:
            return  # unable to determine
        if self._device._evo.system_mode[CONF_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return CURRENT_HVAC_OFF

        if self._device.heat_demand:
            return CURRENT_HVAC_HEAT
        if self._device.heat_demand is not None:
            return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return hvac operation ie. heat, cool mode."""

        if self._device._evo.system_mode is None:
            return  # unable to determine
        if self._device._evo.system_mode[CONF_SYSTEM_MODE] == SystemMode.AWAY:
            return HVAC_MODE_AUTO
        if self._device._evo.system_mode[CONF_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVAC_MODE_OFF

        if self._device.mode is None:
            return  # unable to determine
        if (
            self._device.config
            and self._device.mode[ATTR_SETPOINT] <= self._device.config["min_temp"]
        ):
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""

        if self._device._evo.system_mode is None:
            return  # unable to determine
        if self._device._evo.system_mode[CONF_SYSTEM_MODE] in MODE_TCS_TO_HA:
            return PRESET_TCS_TO_HA[self._device._evo.system_mode[CONF_SYSTEM_MODE]]

        if self._device.mode is None:
            return  # unable to determine
        if self._device.mode[CONF_MODE] == ZoneMode.SCHEDULE:
            return PRESET_TCS_TO_HA[self._device._evo.system_mode[CONF_SYSTEM_MODE]]
        return PRESET_ZONE_TO_HA.get(self._device.mode[CONF_MODE])

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
        mode = kwargs.get(CONF_MODE)
        until = kwargs.get(CONF_UNTIL)

        if mode is None and until is None:
            self._device.setpoint = setpoint
        else:
            self._device(mode=mode, setpoint=setpoint, until=until)

    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to following the schedule."""

        evozone_preset_mode = PRESET_TO_ZONE.get(preset_mode, ZoneMode.SCHEDULE)

        if evozone_preset_mode == ZoneMode.SCHEDULE:
            self._device.reset_mode()
        else:
            setpoint = self._device.setpoint  # TODO: what if not known
            self._device.set_mode(mode=ZoneMode.TEMPORARY, setpoint=setpoint)

    def svc_reset_zone_config(self) -> None:
        """Reset the configuration of the Zone."""
        self._device.reset_config()

    def svc_set_zone_config(self, **kwargs) -> None:
        """Set the configuration of the Zone (min/max temp, etc.)."""
        self.svc_set_zone_mode(**kwargs)

    def svc_reset_zone_mode(self) -> None:
        """Reset the (native) operating mode of the Zone."""
        self._device.reset_mode()

    def svc_set_zone_mode(
        self, mode=None, setpoint=None, duration=None, until=None
    ) -> None:
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
        self._hvac_modes = list(MODE_TO_TCS)
        self._preset_modes = list(PRESET_TO_TCS)
        self._supported_features = SUPPORT_PRESET_MODE | SUPPORT_TARGET_TEMPERATURE

    def _handle_dispatch(self, *args) -> None:
        """Process a service request (system mode) for a controller.

        Data validation is not required, it will have been done upstream.
        """
        if not args:
            self.async_schedule_update_ha_state()  # TODO: force_refresh=True)
            return

        payload = args[0]
        if payload.get("unique_id") != self._device.id:
            return
        elif payload["service"] == SVC_RESET_SYSTEM:
            self.svc_reset_system()
        elif payload["service"] == SVC_SET_SYSTEM_MODE:
            self.svc_set_system_mode(**payload["data"])

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
            "system_mode": self._device.system_mode,
            "tpi_params": self._device.tpi_params,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Done. Return the current running hvac operation if supported."""

        if self._device.system_mode is None:
            return  # unable to determine
        if self._device.system_mode[CONF_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return CURRENT_HVAC_OFF

        if self._device.heat_demand:
            return CURRENT_HVAC_HEAT
        if self._device.heat_demand is not None:
            return CURRENT_HVAC_IDLE

    @property
    def hvac_mode(self) -> Optional[str]:
        """Done. Return the current operating mode of a Controller."""

        if self._device.system_mode is None:
            return  # unable to determine
        if self._device.system_mode[CONF_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVAC_MODE_OFF
        if self._device.system_mode[CONF_SYSTEM_MODE] == SystemMode.AWAY:
            return HVAC_MODE_AUTO  # users can't adjust setpoints in away mode
        return HVAC_MODE_HEAT

    @property
    def preset_mode(self) -> Optional[str]:
        """Done. Return the current preset mode, e.g., home, away, temp."""

        if self._device.system_mode is None:
            return  # unable to determine
        return PRESET_TCS_TO_HA[self._device.system_mode[CONF_SYSTEM_MODE]]

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
        """Return the name of the Controller."""
        return "Controller"

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

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set an operating mode for a Controller."""
        self.svc_set_system_mode(MODE_TO_TCS.get(hvac_mode))

    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to 'Auto' mode."""
        self.svc_set_system_mode(PRESET_TO_TCS.get(preset_mode, SystemMode.AUTO))

    def svc_reset_system(self) -> None:
        """Reset the (native) operating mode of the Controller."""
        self._device.reset_mode()

    def svc_set_system_mode(self, mode, period=None, days=None) -> None:
        """Set the (native) operating mode of the Controller."""
        if period is not None:
            until = dt.now() + period
        elif days is not None:
            until = dt.now() + days
        else:
            until = None
        self._device.set_mode(system_mode=mode, until=until)
