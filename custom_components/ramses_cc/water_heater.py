"""Support for RAMSES water_heater entities."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import json
import logging
from typing import Any

from ramses_rf.device.base import Entity as RamsesRFEntity
from ramses_rf.system.heat import StoredHw
from ramses_rf.system.zones import DhwZone
from ramses_tx.const import SZ_MODE, SZ_SYSTEM_MODE
import voluptuous as vol

from homeassistant.components.water_heater import (
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesController, RamsesEntity, RamsesEntityDescription
from .const import (
    ATTR_ACTIVE,
    ATTR_DIFFERENTIAL,
    ATTR_DURATION,
    ATTR_MODE,
    ATTR_OVERRUN,
    ATTR_SCHEDULE,
    ATTR_SETPOINT,
    ATTR_TEMPERATURE,
    ATTR_UNTIL,
    CONTROLLER,
    DOMAIN,
    SERVICE_GET_DHW_SCHEDULE,
    SERVICE_PUT_DHW_TEMP,
    SERVICE_RESET_DHW_PARAMS,
    SERVICE_SET_DHW_BOOST,
    SERVICE_SET_DHW_MODE,
    SERVICE_SET_DHW_PARAMS,
    SERVICE_SET_DHW_SCHEDULE,
    SystemMode,
    ZoneMode,
)


@dataclass(kw_only=True)
class RamsesWaterHeaterEntityDescription(
    RamsesEntityDescription, WaterHeaterEntityEntityDescription
):
    """Class describing Ramses water heater entities."""


_LOGGER = logging.getLogger(__name__)


STATE_AUTO = "auto"
STATE_BOOST = "boost"

MODE_HA_TO_EVO = {
    STATE_AUTO: ZoneMode.SCHEDULE,
    STATE_BOOST: ZoneMode.TEMPORARY,
    STATE_OFF: ZoneMode.PERMANENT,
    STATE_ON: ZoneMode.PERMANENT,
}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Ramses water heaters."""
    controller: RamsesController = hass.data[DOMAIN][CONTROLLER]
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_GET_DHW_SCHEDULE, {}, "async_get_dhw_schedule"
    )

    platform.async_register_entity_service(
        SERVICE_SET_DHW_SCHEDULE,
        {vol.Required(ATTR_SCHEDULE): cv.string},
        "async_set_dhw_schedule",
    )

    platform.async_register_entity_service(
        SERVICE_PUT_DHW_TEMP,
        {
            vol.Required(ATTR_TEMPERATURE): vol.All(
                vol.Coerce(float), vol.Range(min=-20, max=99)
            ),
        },
        "async_put_dhw_temp",
    )

    platform.async_register_entity_service(
        SERVICE_SET_DHW_BOOST, {}, "async_set_dhw_boost"
    )

    platform.async_register_entity_service(
        SERVICE_SET_DHW_MODE,
        {
            vol.Optional(ATTR_MODE): vol.In(
                [ZoneMode.SCHEDULE, ZoneMode.PERMANENT, ZoneMode.TEMPORARY]
            ),
            vol.Optional(ATTR_ACTIVE): cv.boolean,
            vol.Exclusive(ATTR_UNTIL, ATTR_UNTIL): cv.datetime,
            vol.Exclusive(ATTR_DURATION, ATTR_UNTIL): vol.All(
                cv.time_period,
                vol.Range(min=timedelta(minutes=5), max=timedelta(days=1)),
            ),
        },
        "async_set_dhw_mode",
    )

    platform.async_register_entity_service(
        SERVICE_SET_DHW_MODE,
        {},
        "async_reset_dhw_mode",
    )

    platform.async_register_entity_service(
        SERVICE_SET_DHW_PARAMS,
        {
            vol.Optional(ATTR_SETPOINT, default=50): vol.All(
                cv.positive_float,
                vol.Range(min=30, max=85),
            ),
            vol.Optional(ATTR_OVERRUN, default=5): vol.All(
                cv.positive_int,
                vol.Range(max=10),
            ),
            vol.Optional(ATTR_DIFFERENTIAL, default=1): vol.All(
                cv.positive_float,
                vol.Range(max=10),
            ),
        },
        "async_set_dhw_params",
    )

    platform.async_register_entity_service(
        SERVICE_RESET_DHW_PARAMS,
        {},
        "async_reset_dhw_params",
    )

    async def async_add_new_entity(entity: RamsesRFEntity) -> None:
        entities = []

        if isinstance(entity, DhwZone):
            entities.append(
                RamsesDHW(
                    controller,
                    entity,
                    RamsesWaterHeaterEntityDescription(key="dhwzone"),
                )
            )

        async_add_entities(entities)

    controller.async_register_platform(platform, async_add_new_entity)


class RamsesDHW(RamsesEntity, WaterHeaterEntity):
    """Base for a DHW controller (aka boiler)."""

    rf_entity: DhwZone
    entity_description: RamsesWaterHeaterEntityDescription

    _attr_icon: str = "mdi:thermometer-lines"
    _attr_max_temp: float = StoredHw.MAX_SETPOINT
    _attr_min_temp: float = StoredHw.MIN_SETPOINT
    _attr_operation_list: list[str] = list(MODE_HA_TO_EVO)
    _attr_supported_features: int = (
        WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = PRECISION_TENTHS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        try:
            mode = self.rf_entity.mode[SZ_MODE]
        except TypeError:
            return
        if mode == ZoneMode.SCHEDULE:
            return STATE_AUTO
        elif mode == ZoneMode.PERMANENT:
            return STATE_ON if self.rf_entity.mode["active"] else STATE_OFF
        else:  # there are a number of temporary modes
            return STATE_BOOST if self.rf_entity.mode["active"] else STATE_OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.rf_entity.temperature

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the integration-specific state attributes."""
        return super().extra_state_attributes | {
            "mode": self.rf_entity.mode,
            "config": self.rf_entity.mode,
            "schema": self.rf_entity.schema,
            "schedule": self.rf_entity.schedule,
            "schedule_version": self.rf_entity.schedule_version,
        }

    @property
    def is_away_mode_on(self) -> bool | None:
        """Return True if away mode is on."""
        try:
            return self.rf_entity.tcs.system_mode[SZ_SYSTEM_MODE] == SystemMode.AWAY
        except TypeError:
            return

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self.rf_entity.name

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self.rf_entity.setpoint

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operating mode of the water heater."""
        active = until = None  # for STATE_AUTO
        if operation_mode == STATE_BOOST:
            active = True
            until = dt.now() + timedelta(hours=1)
        elif operation_mode == STATE_OFF:
            active = False
        elif operation_mode == STATE_ON:
            active = True

        await self.async_set_dhw_mode(
            mode=MODE_HA_TO_EVO[operation_mode], active=active, until=until
        )

    async def async_set_temperature(self, temperature: float = None, **kwargs) -> None:
        """Set the target temperature of the water heater."""
        self.async_set_dhw_params(setpoint=temperature)

    async def async_put_dhw_temp(self) -> None:
        """Fake the measured temperature of the DHW's sensor."""
        raise NotImplementedError

    async def async_reset_dhw_mode(self) -> None:
        """Reset the operating mode of the water heater."""
        self._call_client_api(self.rf_entity.reset_mode)

    async def async_reset_dhw_params(self) -> None:
        """Reset the configuration of the water heater."""
        self._call_client_api(self.rf_entity.reset_config)

    async def async_set_dhw_boost(self) -> None:
        """Enable the water heater for an hour."""
        await self.rf_entity.set_boost_mode()
        self.async_write_ha_state()

    async def async_set_dhw_mode(
        self, mode=None, active: bool = None, duration=None, until=None
    ) -> None:
        """Set the (native) operating mode of the water heater."""
        if until is None and duration is not None:
            until = dt.now() + duration
        await self.rf_entity.set_mode(mode=mode, active=active, until=until)
        self.async_write_ha_state()

    async def async_set_dhw_params(
        self, setpoint: float = None, overrun=None, differential=None
    ) -> None:
        """Set the configuration of the water heater."""
        await self.rf_entity.set_config(
            setpoint=setpoint, overrun=overrun, differential=differential
        )
        self.async_write_ha_state()

    async def async_get_dhw_schedule(self, **kwargs) -> None:
        """Get the latest weekly schedule of the DHW."""
        await self.rf_entity.get_schedule()
        self.async_write_ha_state()

    async def async_set_dhw_schedule(self, schedule: str, **kwargs) -> None:
        """Set the weekly schedule of the DHW."""
        await self.rf_entity.set_schedule(json.loads(schedule))
        self.async_write_ha_state()
