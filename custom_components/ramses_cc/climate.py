"""Support for RAMSES climate entities."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import json
import logging
from typing import Any

from ramses_rf.device.base import Entity as RamsesRFEntity
from ramses_rf.device.hvac import HvacVentilator
from ramses_rf.system.heat import Evohome
from ramses_rf.system.zones import Zone
from ramses_tx.const import SZ_MODE, SZ_SETPOINT, SZ_SYSTEM_MODE
import voluptuous as vol

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    PRECISION_TENTHS,
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesController, RamsesEntity, RamsesEntityDescription
from .const import (
    ATTR_DURATION,
    ATTR_LOCAL_OVERRIDE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_MODE,
    ATTR_MULTIROOM,
    ATTR_OPENWINDOW,
    ATTR_PERIOD,
    ATTR_SCHEDULE,
    ATTR_SETPOINT,
    ATTR_TEMPERATURE,
    ATTR_UNTIL,
    CONTROLLER,
    DOMAIN,
    SERVICE_GET_ZONE_SCHED,
    SERVICE_PUT_ZONE_TEMP,
    SERVICE_RESET_SYSTEM_MODE,
    SERVICE_RESET_ZONE_CONFIG,
    SERVICE_RESET_ZONE_MODE,
    SERVICE_SET_SYSTEM_MODE,
    SERVICE_SET_ZONE_CONFIG,
    SERVICE_SET_ZONE_MODE,
    SERVICE_SET_ZONE_SCHED,
    SystemMode,
    ZoneMode,
)


@dataclass(kw_only=True)
class RamsesClimateEntityDescription(RamsesEntityDescription, ClimateEntityDescription):
    """Class describing Ramses binary sensor entities."""

    MODE_TCS_TO_HA = {
        SystemMode.AUTO: HVACMode.HEAT,  # NOTE: don't use _AUTO
        SystemMode.HEAT_OFF: HVACMode.OFF,
        SystemMode.RESET: HVACMode.HEAT,
    }


MODE_TO_TCS = {
    HVACMode.HEAT: SystemMode.AUTO,
    HVACMode.OFF: SystemMode.HEAT_OFF,
    HVACMode.AUTO: SystemMode.RESET,  # not all systems support this
}

PRESET_CUSTOM = "custom"  # NOTE: not an offical PRESET

PRESET_TCS_TO_HA = {
    SystemMode.AUTO: PRESET_NONE,
    SystemMode.AWAY: PRESET_AWAY,
    SystemMode.CUSTOM: PRESET_CUSTOM,
    SystemMode.DAY_OFF: PRESET_HOME,
    SystemMode.DAY_OFF_ECO: PRESET_HOME,
    SystemMode.ECO_BOOST: PRESET_ECO,  # or: PRESET_BOOST
    SystemMode.HEAT_OFF: PRESET_NONE,
    SystemMode.RESET: PRESET_NONE,
}

PRESET_TO_TCS = (
    SystemMode.AUTO,
    SystemMode.AWAY,
    SystemMode.CUSTOM,
    SystemMode.DAY_OFF,
    SystemMode.ECO_BOOST,
)
PRESET_TO_TCS = {v: k for k, v in PRESET_TCS_TO_HA.items() if k in PRESET_TO_TCS}

MODE_ZONE_TO_HA = {
    ZoneMode.ADVANCED: HVACMode.HEAT,
    ZoneMode.PERMANENT: HVACMode.HEAT,
    ZoneMode.TEMPORARY: HVACMode.HEAT,
    ZoneMode.SCHEDULE: HVACMode.AUTO,
}

MODE_TO_ZONE = (
    ZoneMode.SCHEDULE,
    ZoneMode.PERMANENT,
)
MODE_TO_ZONE = {v: k for k, v in MODE_ZONE_TO_HA.items() if k in MODE_TO_ZONE}

PRESET_ZONE_TO_HA = {
    ZoneMode.SCHEDULE: PRESET_NONE,
    ZoneMode.TEMPORARY: "temporary",
    ZoneMode.PERMANENT: "permanent",
}
PRESET_TO_ZONE = {v: k for k, v in PRESET_ZONE_TO_HA.items()}


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Ramses climates."""
    controller: RamsesController = hass.data[DOMAIN][CONTROLLER]
    platform = entity_platform.async_get_current_platform()

    # Controller services
    platform.async_register_entity_service(
        SERVICE_RESET_SYSTEM_MODE,
        {},
        "async_reset_system_mode",
    )

    platform.async_register_entity_service(
        SERVICE_SET_SYSTEM_MODE,
        {
            vol.Required(ATTR_MODE): cv.enum(SystemMode),
            vol.Optional(ATTR_PERIOD, default=timedelta(days=0)): vol.All(
                cv.time_period,
                vol.Range(min=timedelta(days=0), max=timedelta(days=99)),
            ),  # 0 means until the end of the day
            vol.Optional(ATTR_DURATION, default=timedelta(hours=1)): vol.All(
                cv.time_period,
                vol.Range(min=timedelta(hours=1), max=timedelta(hours=24)),
            ),
        },
        "async_set_system_mode",
    )

    # Zone services
    platform.async_register_entity_service(
        SERVICE_GET_ZONE_SCHED,
        {},
        "async_get_zone_schedule",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_SCHED,
        {vol.Required(ATTR_SCHEDULE): cv.string},
        "async_set_zone_schedule",
    )

    platform.async_register_entity_service(
        SERVICE_PUT_ZONE_TEMP,
        {
            vol.Required(ATTR_TEMPERATURE): vol.All(
                vol.Coerce(float), vol.Range(min=-20, max=99)
            ),
        },
        "async_put_zone_temp",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_CONFIG,
        {
            vol.Optional(ATTR_MAX_TEMP, default=35): vol.All(
                cv.positive_float,
                vol.Range(min=21, max=35),
            ),
            vol.Optional(ATTR_MIN_TEMP, default=5): vol.All(
                cv.positive_float,
                vol.Range(min=5, max=21),
            ),
            vol.Optional(ATTR_LOCAL_OVERRIDE, default=True): cv.boolean,
            vol.Optional(ATTR_OPENWINDOW, default=True): cv.boolean,
            vol.Optional(ATTR_MULTIROOM, default=True): cv.boolean,
        },
        "async_set_zone_config",
    )

    platform.async_register_entity_service(
        SERVICE_RESET_ZONE_CONFIG,
        {},
        "async_reset_zone_config",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_MODE,
        {
            vol.Optional(ATTR_MODE): cv.enum(ZoneMode),
            vol.Optional(ATTR_SETPOINT, default=21): vol.All(
                cv.positive_float,
                vol.Range(min=5, max=30),
            ),
            vol.Exclusive(ATTR_UNTIL, ATTR_UNTIL): cv.datetime,
            vol.Exclusive(ATTR_DURATION, ATTR_UNTIL): vol.All(
                cv.time_period,
                vol.Range(min=timedelta(minutes=5), max=timedelta(days=1)),
            ),
        },
        "async_set_zone_mode",
    )

    platform.async_register_entity_service(
        SERVICE_RESET_ZONE_MODE,
        {},
        "async_reset_zone_mode",
    )

    async def async_add_new_entity(entity: RamsesRFEntity) -> None:
        entities = []

        if isinstance(entity, Evohome):
            entities.append(
                RamsesEvohomeControllerEntity(
                    controller, entity, RamsesClimateEntityDescription(key="controller")
                )
            )
        elif isinstance(entity, Zone) and isinstance(entity.tcs, Evohome):
            entities.append(
                RamsesEvohomeZoneEntity(
                    controller, entity, RamsesClimateEntityDescription(key="zone")
                )
            )
        elif isinstance(entity, HvacVentilator):
            entities.append(
                RamsesHvacEntity(
                    controller, entity, RamsesClimateEntityDescription(key="hvac")
                )
            )

        async_add_entities(entities)

    controller.async_register_platform(platform, async_add_new_entity)


class RamsesEvohomeControllerEntity(RamsesEntity, ClimateEntity):
    """Base for a Ramses system."""

    rf_entity: Evohome
    entity_description: RamsesClimateEntityDescription

    _attr_icon = "mdi:thermostat"
    _attr_hvac_modes = list(MODE_TO_TCS)
    _attr_preset_modes = list(PRESET_TO_TCS)
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE
    _attr_precision = PRECISION_TENTHS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> float | None:
        """Return the average current temperature of the heating Zones.

        Controllers do not have a current temp, but one is expected by HA.
        """
        temps = [
            z.temperature for z in self.rf_entity.zones if z.temperature is not None
        ]
        return round(sum(temps) / len(temps), 1) if temps else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the integration-specific state attributes."""
        return super().extra_state_attributes | {
            "heat_demand": self.rf_entity.heat_demand,
            "heat_demands": self.rf_entity.heat_demands,
            "relay_demands": self.rf_entity.relay_demands,
            "system_mode": self.rf_entity.system_mode,
            "tpi_params": self.rf_entity.tpi_params,
            # "faults": self.rf_entity.faultlog,
        }

    @property
    def hvac_action(self) -> str | None:
        """Return the Controller's current running hvac operation."""

        if self.rf_entity.system_mode is None:
            return  # unable to determine
        if self.rf_entity.system_mode[SZ_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVACAction.OFF

        if self.rf_entity.heat_demand:
            return HVACAction.HEATING
        if self.rf_entity.heat_demand is not None:
            return HVACAction.IDLE

        return None

    @property
    def hvac_mode(self) -> str | None:
        """Return the Controller's current operating mode of a Controller."""

        if self.rf_entity.system_mode is None:
            return  # unable to determine
        if self.rf_entity.system_mode[SZ_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVACMode.OFF
        if self.rf_entity.system_mode[SZ_SYSTEM_MODE] == SystemMode.AWAY:
            return HVACMode.AUTO  # users can't adjust setpoints in away mode
        return HVACMode.HEAT

    @property
    def name(self) -> str:
        """Return the name of the controller."""
        return "Controller"

    @property
    def preset_mode(self) -> str | None:
        """Return the Controller's current preset mode, e.g., home, away, temp."""
        if self.rf_entity.system_mode is None:
            return  # unable to determine
        return PRESET_TCS_TO_HA[self.rf_entity.system_mode[SZ_SYSTEM_MODE]]

    @property
    def target_temperature(self) -> float | None:
        """Return the maximum temperature we try to reach."""
        zones = [z for z in self.rf_entity.zones if z.setpoint is not None]
        temps = [z.setpoint for z in zones if z.heat_demand is not None]
        return max(z.setpoint for z in zones) if temps else None

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set an operating mode for a Controller."""
        await self.async_set_system_mode(MODE_TO_TCS.get(hvac_mode))

    async def async_set_preset_mode(self, preset_mode: str | None) -> None:
        """Set the preset mode; if None, then revert to 'Auto' mode."""
        await self.async_set_system_mode(
            PRESET_TO_TCS.get(preset_mode, SystemMode.AUTO)
        )

    async def async_reset_system_mode(self) -> None:
        """Reset the (native) operating mode of the Controller."""
        await self.rf_entity.reset_mode()
        self.async_write_ha_state()

    async def async_set_system_mode(self, mode, period=None, days=None) -> None:
        """Set the (native) operating mode of the Controller."""
        if period is not None:
            until = dt.now() + period
        elif days is not None:
            until = dt.now() + days  # TODO: round down
        else:
            until = None
        await self.rf_entity.set_mode(system_mode=mode, until=until)
        self.async_write_ha_state()


class RamsesEvohomeZoneEntity(RamsesEntity, ClimateEntity):
    """Representation of a Ramses zone."""

    rf_entity: Zone
    entity_description: RamsesClimateEntityDescription

    _attr_icon = "mdi:radiator"
    _attr_hvac_modes = list(MODE_TO_ZONE)
    _attr_preset_modes = list(PRESET_TO_ZONE)
    _attr_supported_features = (
        ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TARGET_TEMPERATURE
    )
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = PRECISION_TENTHS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    @property
    def _tcs(self) -> Evohome:
        return self.rf_entity.tcs

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the integration-specific state attributes."""
        return super().extra_state_attributes | {
            "zone_idx": self.rf_entity.idx,
            "heating_type": self.rf_entity.heating_type,
            "name": self.rf_entity.name,
            "mode": self.rf_entity.mode,
            "config": self.rf_entity.config,
            "schema": self.rf_entity.schema,
            "schedule": self.rf_entity.schedule,
            "schedule_version": self.rf_entity.schedule_version,
        }

    @property
    def hvac_action(self) -> str | None:
        """Return the Zone's current running hvac operation."""

        if self._tcs.system_mode is None:
            return None  # unable to determine
        if self._tcs.system_mode[SZ_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVACAction.OFF

        if self.rf_entity.heat_demand:
            return HVACAction.HEATING
        if self.rf_entity.heat_demand is not None:
            return HVACAction.IDLE
        return None

    @property
    def hvac_mode(self) -> str | None:
        """Return the Zone's hvac operation ie. heat, cool mode."""

        if self._tcs.system_mode is None:
            return  # unable to determine
        if self._tcs.system_mode[SZ_SYSTEM_MODE] == SystemMode.AWAY:
            return HVACMode.AUTO
        if self._tcs.system_mode[SZ_SYSTEM_MODE] == SystemMode.HEAT_OFF:
            return HVACMode.OFF

        if self.rf_entity.mode is None or self.rf_entity.mode[SZ_SETPOINT] is None:
            return  # unable to determine
        if (
            self.rf_entity.config
            and self.rf_entity.mode[SZ_SETPOINT] <= self.rf_entity.config["min_temp"]
        ):
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def max_temp(self) -> float | None:
        """Return the maximum target temperature of a Zone."""
        try:
            return self.rf_entity.config["max_temp"]
        except TypeError:  # 'NoneType' object is not subscriptable
            return None

    @property
    def min_temp(self) -> float | None:
        """Return the minimum target temperature of a Zone."""
        try:
            return self.rf_entity.config["min_temp"]
        except TypeError:  # 'NoneType' object is not subscriptable
            return None

    @property
    def preset_mode(self) -> str | None:
        """Return the Zone's current preset mode, e.g., home, away, temp."""

        if self.rf_entity.tcs.system_mode is None:
            return None  # unable to determine
        # if self.rf_entity.tcs.system_mode[SZ_SYSTEM_MODE] in MODE_TCS_TO_HA:
        if self.rf_entity.tcs.system_mode[SZ_SYSTEM_MODE] in (
            SystemMode.AWAY,
            SystemMode.HEAT_OFF,
        ):
            return PRESET_TCS_TO_HA[self.rf_entity.tcs.system_mode[SZ_SYSTEM_MODE]]

        if self.rf_entity.mode is None:
            return None  # unable to determine
        if self.rf_entity.mode[SZ_MODE] == ZoneMode.SCHEDULE:
            return PRESET_TCS_TO_HA[self.rf_entity.tcs.system_mode[SZ_SYSTEM_MODE]]
        return PRESET_ZONE_TO_HA.get(self.rf_entity.mode[SZ_MODE])

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self.rf_entity.setpoint

    @property
    def name(self) -> str:
        """Return the name of the zone."""
        return self.rf_entity.name or f"Zone {self.rf_entity.idx}"

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        if hvac_mode == HVACMode.AUTO:  # FollowSchedule
            await self.async_reset_zone_mode()
        elif hvac_mode == HVACMode.HEAT:  # TemporaryOverride
            await self.async_set_zone_mode(
                mode=ZoneMode.PERMANENT, setpoint=25
            )  # TODO:
        else:  # HVACMode.OFF, PermentOverride, temp = min
            await self.async_set_zone_mode(self.rf_entity.set_frost_mode)  # TODO:

    async def async_set_preset_mode(self, preset_mode: str | None) -> None:
        """Set the preset mode; if None, then revert to following the schedule."""
        await self.async_set_zone_mode(
            mode=PRESET_TO_ZONE.get(preset_mode),
            setpoint=self.target_temperature if preset_mode == "permanent" else None,
        )

    async def async_set_temperature(self, temperature: float = None, **kwargs) -> None:
        """Set a new target temperature."""
        await self.async_set_zone_mode(setpoint=temperature)

    async def async_put_zone_temp(
        self, temperature: float, **kwargs
    ) -> None:  # set_current_temp
        """Fake the measured temperature of the Zone sensor.

        This is not the setpoint (see: async_set_temperature), but the measured temperature.
        """
        self.rf_entity.sensor._make_fake()
        self.rf_entity.sensor.temperature = temperature
        await self.rf_entity._get_temp()
        self.async_write_ha_state()

    async def async_reset_zone_config(self) -> None:
        """Reset the configuration of the Zone."""
        await self.rf_entity.reset_config()
        self.async_write_ha_state()

    async def async_reset_zone_mode(self) -> None:
        """Reset the (native) operating mode of the Zone."""
        await self.rf_entity.reset_mode()
        self.async_write_ha_state()

    async def async_set_zone_config(self, **kwargs) -> None:
        """Set the configuration of the Zone (min/max temp, etc.)."""
        await self.rf_entity.set_config(**kwargs)
        self.async_write_ha_state()

    async def async_set_zone_mode(
        self, mode=None, setpoint=None, duration=None, until=None
    ) -> None:
        """Set the (native) operating mode of the Zone."""
        if until is None and duration is not None:
            until = dt.now() + duration
        await self.rf_entity.set_mode(mode=mode, setpoint=setpoint, until=until)
        self.async_write_ha_state()

    async def async_get_zone_schedule(self, **kwargs) -> None:
        """Get the latest weekly schedule of the Zone."""
        await self.rf_entity.get_schedule()
        self.async_write_ha_state()

    async def async_set_zone_schedule(self, schedule: str, **kwargs) -> None:
        """Set the weekly schedule of the Zone."""
        await self.rf_entity.set_schedule(json.loads(schedule))
        self.async_write_ha_state()


class RamsesHvacEntity(RamsesEntity, ClimateEntity):
    """Representation of a Ramses HVAC unit."""

    rf_entity: HvacVentilator
    entity_description: RamsesClimateEntityDescription

    _attr_precision: float = PRECISION_TENTHS
    _attr_temperature_unit: str = UnitOfTemperature.CELSIUS
    _attr_fan_modes: list[str] | None = [
        FAN_OFF,
        FAN_AUTO,
        FAN_LOW,
        FAN_MEDIUM,
        FAN_HIGH,
    ]
    _attr_hvac_modes: list[HVACMode] | list[str] = [HVACMode.AUTO, HVACMode.OFF]
    _attr_preset_modes: list[str] | None = None
    _attr_supported_features: int = (
        ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE
    )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.rf_entity.id

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        if self.rf_entity.indoor_humidity is not None:
            return int(self.rf_entity.indoor_humidity * 100)
        return None

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.rf_entity.indoor_temp

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return None

    @property
    def hvac_action(self) -> HVACAction | str | None:
        """Return the current running hvac operation if supported."""
        if self.rf_entity.fan_info is not None:
            return self.rf_entity.fan_info

    @property
    def hvac_mode(self) -> HVACMode | str | None:
        """Return hvac operation ie. heat, cool mode."""
        if self.rf_entity.fan_info is not None:
            return HVACMode.OFF if self.rf_entity.fan_info == "off" else HVACMode.AUTO

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend, if any."""
        return "mdi:hvac-off" if self.rf_entity.fan_info == "off" else "mdi:hvac"

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp."""
        return PRESET_NONE
