#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Provides support for water_heater entities.
"""

import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Dict, List, Optional

import homeassistant.util.dt as dt_util
from evohome_rf.systems import StoredHw
from homeassistant.components.water_heater import (
    ATTR_AWAY_MODE,
    SUPPORT_AWAY_MODE,
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterEntity,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import DOMAIN, EvoZoneBase

# from .const import

_LOGGER = logging.getLogger(__name__)

STATE_AUTO = "auto"
STATE_BOOST = "boost"
STATE_UNKNOWN = None

MODE_FOLLOW_SCHEDULE = "follow_schedule"
MODE_PERMANENT_OVERRIDE = "permanent_override"
MODE_TEMPORARY_OVERRIDE = "temporary_override"

STATE_EVO_TO_HA = {True: STATE_ON, False: STATE_OFF}
STATE_HA_TO_EVO = {v: k for k, v in STATE_EVO_TO_HA.items()}

MODE_EVO_TO_HA = {
    MODE_FOLLOW_SCHEDULE: STATE_AUTO,
    MODE_TEMPORARY_OVERRIDE: MODE_TEMPORARY_OVERRIDE,
    MODE_PERMANENT_OVERRIDE: MODE_PERMANENT_OVERRIDE,
}
# MODE_HA_TO_EVO = {v: k for k, v in MODE_EVO_TO_HA.items()}
MODE_HA_TO_EVO = {
    STATE_AUTO: MODE_FOLLOW_SCHEDULE,
    STATE_BOOST: MODE_TEMPORARY_OVERRIDE,
    STATE_OFF: MODE_PERMANENT_OVERRIDE,
    STATE_ON: MODE_PERMANENT_OVERRIDE,
}

SUPPORTED_FEATURES = sum(
    (
        # SUPPORT_AWAY_MODE,
        SUPPORT_OPERATION_MODE,
        SUPPORT_TARGET_TEMPERATURE,
    )
)

STATE_ATTRS_DHW = ("config", "mode", "status")

ACTIVE = "active"
MODE = "mode"
SYSTEM_MODE = "system_mode"
EVO_SYS_MODE_AWAY = "away"


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create an evohome DHW controller."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    dhw = broker.water_heater = broker.client.evo.dhw

    _LOGGER.info("Found a Water Heater (stored DHW), id=%s, name=%s", dhw.idx, dhw.name)

    async_add_entities([EvoDHW(broker, dhw)], update_before_add=True)


class EvoDHW(EvoZoneBase, WaterHeaterEntity):
    """Base for a DHW controller (aka boiler)."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize an evohome DHW controller."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        # self._icon = "mdi:thermometer-lines"
        self._operation_list = list(MODE_HA_TO_EVO)

    @property
    def state(self) -> Optional[str]:
        """Return the current state (On, or Off)."""
        if self.is_away_mode_on:
            return STATE_OFF
        try:
            return STATE_EVO_TO_HA[self._evo_device.mode[ACTIVE]]
        except TypeError:
            return

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        try:
            mode = self._evo_device.mode[MODE]
        except TypeError:
            return
        if mode == MODE_FOLLOW_SCHEDULE:
            return STATE_AUTO
        elif mode == MODE_PERMANENT_OVERRIDE:
            return STATE_ON if self._evo_device.mode[ACTIVE] else STATE_OFF
        else:  # there are a number of temporary modes
            return STATE_BOOST if self._evo_device.mode[ACTIVE] else STATE_OFF

    @property
    def is_away_mode_on(self):
        """Return True if away mode is on."""
        try:
            return self._evo_device._evo.system_mode[SYSTEM_MODE] == EVO_SYS_MODE_AWAY
        except TypeError:
            return

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._evo_device.temperature

    @property
    def max_temp(self):
        """Return the maximum setpoint temperature."""
        return StoredHw.MAX_SETPOINT

    @property
    def min_temp(self):
        """Return the minimum setpoint temperature."""
        return StoredHw.MIN_SETPOINT

    @property
    def operation_list(self) -> List[str]:
        """Return the list of available operations."""
        return self._operation_list

    @property
    def state_attributes(self) -> Dict:
        """Return the optional state attributes."""
        data = super().state_attributes
        data[ATTR_AWAY_MODE] = STATE_ON if self.is_away_mode_on else STATE_OFF
        data.update({k: getattr(self._evo_device, k) for k in STATE_ATTRS_DHW})
        return data

    @property
    def supported_features(self) -> int:
        """Return the bitmask of supported features."""
        return SUPPORTED_FEATURES

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._evo_device.setpoint

    async def async_set_operation_mode(self, operation_mode):
        """Set new target operation mode."""
        active = until = None  # for STATE_AUTO
        if operation_mode == STATE_BOOST:
            active = True
            until = dt.now() + td(hours=1)
        elif operation_mode == STATE_OFF:
            active = False
        elif operation_mode == STATE_ON:
            active = True

        self._evo_device.set_mode(
            mode=MODE_HA_TO_EVO[operation_mode], active=active, until=until
        )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        self._evo_device.setpoint = kwargs[ATTR_TEMPERATURE]
