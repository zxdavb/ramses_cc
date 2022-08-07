#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by HVAC.

Provides support for climate entities.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    PRECISION_TENTHS,
    TEMP_CELSIUS,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    PRESET_NONE,
)

from . import RamsesEntity

_LOGGER = logging.getLogger(__name__)


class RamsesHvac(RamsesEntity, ClimateEntity):
    """Base for a Honeywell HVAC unit (Fan, HRU, MVHR, PIV, etc)."""

    # PRESET_AWAY = away
    # PRESET_BOOST (timed), 15, 30, 60, other mins
    # PRESET_COMFORT: auto with lower CO2
    # PRESET_NONE: off, low/med/high or auto

    # Climate attrs....
    _attr_precision: float = PRECISION_TENTHS
    _attr_temperature_unit: str = TEMP_CELSIUS
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

    def __init__(self, broker, device) -> None:
        """Initialize a HVAC system."""
        _LOGGER.info("Found a HVAC system: %r", device)

        super().__init__(broker, device)

        self._attr_unique_id = (
            device.id
        )  # dont include domain (ramses_cc) / platform (climate)

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        if self._device.indoor_humidity is not None:
            return int(self._device.indoor_humidity * 100)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.indoor_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().extra_state_attributes,
        }

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return None

    @property
    def hvac_action(self) -> HVACAction | str | None:
        """Return the current running hvac operation if supported."""
        if self._device.fan_info is not None:
            return self._device.fan_info

    @property
    def hvac_mode(self) -> HVACMode | str | None:
        """Return hvac operation ie. heat, cool mode."""
        if self._device.fan_info is not None:
            return HVACMode.OFF if self._device.fan_info == "off" else HVACMode.AUTO

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend, if any."""
        return "mdi:hvac-off" if self._device.fan_info == "off" else "mdi:hvac"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._device.id

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp."""
        return PRESET_NONE
