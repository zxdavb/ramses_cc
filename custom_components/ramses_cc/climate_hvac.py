#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by HVAC.

Provides support for climate entities.
"""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import TEMP_CELSIUS  # "°C"
from homeassistant.core import callback

from . import EvoZoneBase

_LOGGER = logging.getLogger(__name__)


class RamsesHvac(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell HVAC unit (Fan, HRU, MVHR, PIV, etc)."""

    # PRESET_AWAY = away
    # PRESET_BOOST (timed), 15, 30, 60, other mins
    # PRESET_COMFORT: auto with lower CO2
    # PRESET_NONE: off, low/med/high or auto

    # fan states....
    _attr_fan_modes = [FAN_OFF, FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH]
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_HUMIDITY
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
    )

    _attr_target_temperature_step = 0.1
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(self, broker, device) -> None:
        """Initialize a HVAC system."""
        _LOGGER.info("Found a HVAC system: %r", device)

        super().__init__(broker, device)

        self._icon = "mdi:fan"
        self._hvac_modes = None
        self._preset_modes = None
        self._supported_features = None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().extra_state_attributes,
        }

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the Zone's current running hvac operation."""
        return

    @property
    def hvac_mode(self) -> Optional[str]:
        """Return the Zone's hvac operation ie. heat, cool mode."""
        return

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the Zone's current preset mode, e.g., home, away, temp."""
        return

    @callback
    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set a Zone to one of its native operating modes."""
        return

    @callback
    def set_preset_mode(self, preset_mode: Optional[str]) -> None:
        """Set the preset mode; if None, then revert to following the schedule."""
        return
