"""Support for RAMSES water_heater entities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import json
import logging
from typing import Any

from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_rf.system.heat import StoredHw
from ramses_rf.system.zones import DhwZone
from ramses_tx.const import SZ_ACTIVE, SZ_MODE, SZ_SYSTEM_MODE
import voluptuous as vol

from homeassistant.components.water_heater import (
    DOMAIN as PLATFORM,
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesEntity, RamsesEntityDescription
from .broker import RamsesBroker
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
    BROKER,
    DOMAIN,
    SVC_GET_DHW_SCHEDULE,
    SVC_PUT_DHW_TEMP,
    SVC_RESET_DHW_MODE,
    SVC_RESET_DHW_PARAMS,
    SVC_SET_DHW_BOOST,
    SVC_SET_DHW_MODE,
    SVC_SET_DHW_PARAMS,
    SVC_SET_DHW_SCHEDULE,
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

MODE_HA_TO_RAMSES = {
    STATE_AUTO: ZoneMode.SCHEDULE,
    STATE_BOOST: ZoneMode.TEMPORARY,
    STATE_OFF: ZoneMode.PERMANENT,
    STATE_ON: ZoneMode.PERMANENT,
}

SVC_PUT_DHW_TEMP_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)
        ),
    }
)

SVC_SET_DHW_MODE_SCHEMA = cv.make_entity_service_schema(
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
    }
)

SVC_SET_DHW_PARAMS_SCHEMA = cv.make_entity_service_schema(
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
    }
)

SVC_SET_DHW_SCHEDULE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create DHW controllers for CH/DHW (heat)."""

    if discovery_info is None:
        return

    broker: RamsesBroker = hass.data[DOMAIN][BROKER]

    if not broker._services.get(PLATFORM):
        broker._services[PLATFORM] = True

        platform = entity_platform.async_get_current_platform()

        platform.async_register_entity_service(
            SVC_PUT_DHW_TEMP, SVC_PUT_DHW_TEMP_SCHEMA, "async_put_dhw_temp"
        )
        platform.async_register_entity_service(
            SVC_SET_DHW_BOOST, {}, "async_set_dhw_boost"
        )
        platform.async_register_entity_service(
            SVC_SET_DHW_MODE, SVC_SET_DHW_MODE_SCHEMA, "async_set_dhw_mode"
        )
        platform.async_register_entity_service(
            SVC_RESET_DHW_MODE, {}, "async_reset_dhw_mode"
        )
        platform.async_register_entity_service(
            SVC_SET_DHW_PARAMS, SVC_SET_DHW_PARAMS_SCHEMA, "async_set_dhw_params"
        )
        platform.async_register_entity_service(
            SVC_RESET_DHW_PARAMS, {}, "async_reset_dhw_params"
        )
        platform.async_register_entity_service(
            SVC_GET_DHW_SCHEDULE, {}, "async_get_dhw_schedule"
        )
        platform.async_register_entity_service(
            SVC_SET_DHW_SCHEDULE, SVC_SET_DHW_SCHEDULE_SCHEMA, "async_set_dhw_schedule"
        )

    entites = [
        RamsesWaterHeater(
            broker, device, RamsesWaterHeaterEntityDescription(key="dhwzone")
        )
        for device in discovery_info["devices"]
    ]
    async_add_entities(entites)


class RamsesWaterHeater(RamsesEntity, WaterHeaterEntity):
    """Representation of a Rames DHW controller."""

    _device: DhwZone

    _attr_icon: str = "mdi:thermometer-lines"
    _attr_max_temp: float = StoredHw.MAX_SETPOINT
    _attr_min_temp: float = StoredHw.MIN_SETPOINT
    _attr_operation_list: list[str] = list(MODE_HA_TO_RAMSES)
    _attr_supported_features: int = (
        WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        broker: RamsesBroker,
        device: DhwZone,
        entity_description: RamsesWaterHeaterEntityDescription,
    ) -> None:
        """Initialize a TCS DHW controller."""
        _LOGGER.info("Found DHW %r", device)
        super().__init__(broker, device, entity_description)

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        try:
            mode = self._device.mode[SZ_MODE]
        except TypeError:
            return
        if mode == ZoneMode.SCHEDULE:
            return STATE_AUTO
        elif mode == ZoneMode.PERMANENT:
            return STATE_ON if self._device.mode[SZ_ACTIVE] else STATE_OFF
        else:  # there are a number of temporary modes
            return STATE_BOOST if self._device.mode[SZ_ACTIVE] else STATE_OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return super().extra_state_attributes | {
            "params": self._device.params,
            "mode": self._device.mode,
            "schedule": self._device.schedule,
            "schedule_version": self._device.schedule_version,
        }

    @property
    def is_away_mode_on(self) -> bool | None:
        """Return True if away mode is on."""
        try:
            return self._device.tcs.system_mode[SZ_SYSTEM_MODE] == SystemMode.AWAY
        except TypeError:
            return

    @property
    def name(self) -> str | None:
        """Return the name of the zone."""
        return self._device.name

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._device.setpoint

    def set_operation_mode(self, operation_mode: str) -> None:
        """Set the operating mode of the water heater."""
        active = until = None  # for STATE_AUTO
        if operation_mode == STATE_BOOST:
            active = True
            until = dt.now() + timedelta(hours=1)
        elif operation_mode == STATE_OFF:
            active = False
        elif operation_mode == STATE_ON:
            active = True

        self.async_set_dhw_mode(
            mode=MODE_HA_TO_RAMSES[operation_mode], active=active, until=until
        )

    def set_temperature(self, temperature: float = None, **kwargs) -> None:
        """Set the target temperature of the water heater."""
        self.async_set_dhw_params(setpoint=temperature)

    @callback
    def async_put_dhw_temp(self) -> None:
        """Fake the measured temperature of the DHW's sensor."""
        raise NotImplementedError

    @callback
    def async_reset_dhw_mode(self) -> None:
        """Reset the operating mode of the water heater."""
        self._device.reset_mode()
        self.async_write_ha_state_delayed()

    @callback
    def async_reset_dhw_params(self) -> None:
        """Reset the configuration of the water heater."""
        self._device.reset_config()
        self.async_write_ha_state_delayed()

    @callback
    def async_set_dhw_boost(self) -> None:
        """Enable the water heater for an hour."""
        self._device.set_boost_mode()
        self.async_write_ha_state_delayed()

    @callback
    def async_set_dhw_mode(
        self, mode=None, active: bool = None, duration=None, until=None
    ) -> None:
        """Set the (native) operating mode of the water heater."""
        if until is None and duration is not None:
            until = dt.now() + duration
        self._device.set_mode(mode=mode, active=active, until=until)
        self.async_write_ha_state_delayed()

    @callback
    def async_set_dhw_params(
        self, setpoint: float = None, overrun=None, differential=None
    ) -> None:
        """Set the configuration of the water heater."""
        self._device.set_config(
            setpoint=setpoint,
            overrun=overrun,
            differential=differential,
        )
        self.async_write_ha_state_delayed()

    async def async_get_dhw_schedule(self, **kwargs) -> None:
        """Get the latest weekly schedule of the DHW."""
        # {{ state_attr('water_heater.stored_hw', 'schedule') }}
        await self._device.get_schedule()
        self.async_write_ha_state()

    async def async_set_dhw_schedule(self, schedule: str, **kwargs) -> None:
        """Set the weekly schedule of the DHW."""
        await self._device.set_schedule(json.loads(schedule))
