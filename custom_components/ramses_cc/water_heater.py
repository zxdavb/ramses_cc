#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW (heat).

Provides support for water_heater entities.
"""

import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any

from homeassistant.components.water_heater import DOMAIN as PLATFORM
from homeassistant.components.water_heater import (
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from ramses_rf.system.heat import StoredHw

from . import EvohomeZoneBase
from .const import BROKER, DATA, DOMAIN, SERVICE, UNIQUE_ID, SystemMode, ZoneMode
from .helpers import migrate_to_ramses_rf
from .schemas import CONF_ACTIVE, CONF_MODE, CONF_SYSTEM_MODE

_LOGGER = logging.getLogger(__name__)


STATE_AUTO = "auto"
STATE_BOOST = "boost"
STATE_UNKNOWN = None

STATE_EVO_TO_HA = {True: STATE_ON, False: STATE_OFF}
STATE_HA_TO_EVO = {v: k for k, v in STATE_EVO_TO_HA.items()}

MODE_EVO_TO_HA = {
    ZoneMode.SCHEDULE: STATE_AUTO,
    ZoneMode.TEMPORARY: "temporary",
    ZoneMode.PERMANENT: "permanent",
}
# MODE_HA_TO_EVO = {v: k for k, v in MODE_EVO_TO_HA.items()}
MODE_HA_TO_EVO = {
    STATE_AUTO: ZoneMode.SCHEDULE,
    STATE_BOOST: ZoneMode.TEMPORARY,
    STATE_OFF: ZoneMode.PERMANENT,
    STATE_ON: ZoneMode.PERMANENT,
}

STATE_ATTRS_DHW = ("config", "mode", "status")


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create a DHW controller."""

    def entity_factory(entity_class, broker, device):
        migrate_to_ramses_rf(hass, "water_heater", f"{device.id}")
        return entity_class(broker, device)

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    if not discovery_info.get("dhw"):
        return

    async_add_entities([entity_factory(EvohomeDHW, broker, discovery_info["dhw"])])

    if broker._services.get(PLATFORM):
        return
    broker._services[PLATFORM] = True

    # register_svc = current_platform.get().async_register_entity_service
    # [register_svc(k, v, f"svc_{k}") for k, v in CLIMATE_SERVICES.items()]


class EvohomeDHW(EvohomeZoneBase, WaterHeaterEntity):
    """Base for a DHW controller (aka boiler)."""

    _attr_icon: str = "mdi:thermometer-lines"
    _attr_max_temp: float = StoredHw.MAX_SETPOINT
    _attr_min_temp: float = StoredHw.MIN_SETPOINT
    _attr_operation_list: list[str] = list(MODE_HA_TO_EVO)
    _attr_supported_features: int = (
        WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )

    def __init__(self, broker, device) -> None:
        """Initialize an TCS DHW controller."""
        _LOGGER.info("Found a DHW controller: %s", device)
        super().__init__(broker, device)

        self._attr_unique_id = (
            device.id
        )  # dont include domain (ramses_cc) / platform (water_heater)

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        # if self.is_away_mode_on:
        #     return STATE_OFF
        # try:
        #     return STATE_EVO_TO_HA[self._device.mode[CONF_ACTIVE]]
        # except (KeyError, TypeError):
        #     return

        try:
            mode = self._device.mode[CONF_MODE]
        except TypeError:
            return
        if mode == ZoneMode.SCHEDULE:
            return STATE_AUTO
        elif mode == ZoneMode.PERMANENT:
            return STATE_ON if self._device.mode[CONF_ACTIVE] else STATE_OFF
        else:  # there are a number of temporary modes
            return STATE_BOOST if self._device.mode[CONF_ACTIVE] else STATE_OFF

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        # data = super().state_attributes
        # data[ATTR_AWAY_MODE] = STATE_ON if self.is_away_mode_on else STATE_OFF
        # data.update({k: getattr(self._device, k) for k in STATE_ATTRS_DHW})
        # return data
        return {
            "mode": self._device.mode,
            **super().extra_state_attributes,
        }

    @property
    def is_away_mode_on(self) -> bool | None:
        """Return True if away mode is on."""
        try:
            return self._device.tcs.system_mode[CONF_SYSTEM_MODE] == SystemMode.AWAY
        except TypeError:
            return

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._device.setpoint

    @callback
    def async_handle_dispatch(self, *args: Any) -> None:
        """Process a service request (system mode) for a controller."""
        if not args:
            self.update_ha_state()
            return

        payload = args[0]
        if payload.get(UNIQUE_ID) != self.unique_id:
            return

        try:
            getattr(self, f"svc_{payload[SERVICE]}")(**dict(payload[DATA]))
        except AttributeError:
            pass

    @callback
    def set_operation_mode(self, operation_mode: str) -> None:
        """Set the operating mode of the water heater."""
        active = until = None  # for STATE_AUTO
        if operation_mode == STATE_BOOST:
            active = True
            until = dt.now() + td(hours=1)
        elif operation_mode == STATE_OFF:
            active = False
        elif operation_mode == STATE_ON:
            active = True

        self.svc_set_dhw_mode(
            mode=MODE_HA_TO_EVO[operation_mode], active=active, until=until
        )

    @callback
    def svc_reset_dhw_mode(self) -> None:
        """Reset the operating mode of the water heater."""
        self._call_client_api(self._device.reset_mode)

    @callback
    def svc_reset_dhw_params(self) -> None:
        """Reset the configuration of the water heater."""
        self._call_client_api(self._device.reset_config)

    @callback
    def svc_set_dhw_boost(self) -> None:
        """Enable the water heater for an hour."""
        self._call_client_api(self._device.set_boost_mode)

    @callback
    def svc_set_dhw_mode(
        self, mode=None, active: bool = None, duration=None, until=None
    ) -> None:
        """Set the (native) operating mode of the water heater."""
        if until is None and duration is not None:
            until = dt.now() + duration
        self._call_client_api(
            self._device.set_mode, mode=mode, active=active, until=until
        )

    @callback
    def svc_set_dhw_params(
        self, setpoint: float = None, overrun=None, differential=None
    ) -> None:
        """Set the configuration of the water heater."""
        self._call_client_api(
            self._device.set_config,
            setpoint=setpoint,
            overrun=overrun,
            differential=differential,
        )

    @callback
    def set_temperature(self, temperature: float = None, **kwargs: Any) -> None:
        """Set the target temperature of the water heater."""
        self.svc_set_dhw_params(setpoint=temperature)
