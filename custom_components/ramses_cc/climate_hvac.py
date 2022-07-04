#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by HVAC.

Provides support for climate entities.
"""

import logging
from datetime import datetime as dt
from typing import Any, Dict, Optional

from homeassistant.components.climate import ClimateEntity
from homeassistant.core import callback

from . import EvoZoneBase


_LOGGER = logging.getLogger(__name__)


class RamsesHvac(EvoZoneBase, ClimateEntity):
    """Base for a Honeywell HVAC system."""

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
