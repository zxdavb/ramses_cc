"""Support for RAMSES water_heater entities."""
from __future__ import annotations

from datetime import datetime as dt, timedelta
import json
import logging
from typing import Any

from ramses_rf.system.heat import StoredHw
from ramses_rf.system.zones import DhwZone
from ramses_tx.const import SZ_ACTIVE, SZ_MODE, SZ_SYSTEM_MODE

from homeassistant.components.water_heater import (
    DOMAIN as PLATFORM,
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesEntity
from .const import BROKER, DOMAIN, SystemMode, ZoneMode
from .coordinator import RamsesBroker
from .schemas import SVCS_WATER_HEATER_EVO_DHW

_LOGGER = logging.getLogger(__name__)


STATE_AUTO = "auto"
STATE_BOOST = "boost"

MODE_HA_TO_RAMSES = {
    STATE_AUTO: ZoneMode.SCHEDULE,
    STATE_BOOST: ZoneMode.TEMPORARY,
    STATE_OFF: ZoneMode.PERMANENT,
    STATE_ON: ZoneMode.PERMANENT,
}


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create DHW controllers for CH/DHW (heat)."""

    def entity_factory(entity_class, broker: RamsesBroker, device):  # TODO: deprecate
        return entity_class(broker, device)

    if discovery_info is None:  # or not discovery_info.get("dhw"):  # not needed
        return

    broker = hass.data[DOMAIN][BROKER]

    async_add_entities(
        [
            entity_factory(RamsesWaterHeater, broker, dhw)
            for dhw in discovery_info["dhw"]
        ]
    )

    if not broker._services.get(PLATFORM):
        broker._services[PLATFORM] = True

        platform = entity_platform.async_get_current_platform()

        for name, schema in SVCS_WATER_HEATER_EVO_DHW.items():
            platform.async_register_entity_service(name, schema, f"svc_{name}")


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

    def __init__(self, broker, device) -> None:
        """Initialize a TCS DHW controller."""
        _LOGGER.info("Found %r", device)
        super().__init__(broker, device)

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

        self.svc_set_dhw_mode(
            mode=MODE_HA_TO_RAMSES[operation_mode], active=active, until=until
        )

    def set_temperature(self, temperature: float = None, **kwargs) -> None:
        """Set the target temperature of the water heater."""
        self.svc_set_dhw_params(setpoint=temperature)

    @callback
    def svc_put_dhw_temp(self) -> None:
        """Fake the measured temperature of the DHW's sensor."""
        raise NotImplementedError

    @callback
    def svc_reset_dhw_mode(self) -> None:
        """Reset the operating mode of the water heater."""
        self._device.reset_mode()
        self.async_write_ha_state_delayed()

    @callback
    def svc_reset_dhw_params(self) -> None:
        """Reset the configuration of the water heater."""
        self._device.reset_config()
        self.async_write_ha_state_delayed()

    @callback
    def svc_set_dhw_boost(self) -> None:
        """Enable the water heater for an hour."""
        self._device.set_boost_mode()
        self.async_write_ha_state_delayed()

    @callback
    def svc_set_dhw_mode(
        self, mode=None, active: bool = None, duration=None, until=None
    ) -> None:
        """Set the (native) operating mode of the water heater."""
        if until is None and duration is not None:
            until = dt.now() + duration
        self._device.set_mode(mode=mode, active=active, until=until)
        self.async_write_ha_state_delayed()

    @callback
    def svc_set_dhw_params(
        self, setpoint: float = None, overrun=None, differential=None
    ) -> None:
        """Set the configuration of the water heater."""
        self._device.set_config(
            setpoint=setpoint,
            overrun=overrun,
            differential=differential,
        )
        self.async_write_ha_state_delayed()

    async def svc_get_dhw_schedule(self, **kwargs) -> None:
        """Get the latest weekly schedule of the DHW."""
        # {{ state_attr('water_heater.stored_hw', 'schedule') }}
        await self._device.get_schedule()
        self.async_write_ha_state()

    async def svc_set_dhw_schedule(self, schedule: str, **kwargs) -> None:
        """Set the weekly schedule of the DHW."""
        await self._device.set_schedule(json.loads(schedule))
