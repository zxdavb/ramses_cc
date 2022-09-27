#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW (heat) & HVAC.

Provides support for climate entities.
"""
from __future__ import annotations

import logging

from homeassistant.components.climate import DOMAIN as PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .climate_heat import EvohomeController, EvohomeZone
from .climate_hvac import RamsesHvac
from .const import BROKER, DOMAIN
from .helpers import migrate_to_ramses_rf
from .schemas import SVCS_CLIMATE_EVO_TCS, SVCS_CLIMATE_EVO_ZONE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create the Climate entities for CH/DHW (heat) & HVAC."""

    def entity_factory(entity_class, broker, device):
        migrate_to_ramses_rf(hass, PLATFORM, f"{device.id}")
        return entity_class(broker, device)

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]
    new_entities = []

    register_svc = async_get_current_platform().async_register_entity_service

    if tcs := discovery_info.get("tcs"):
        new_entities.append(entity_factory(EvohomeController, broker, tcs))

        if not broker._services.get("climate_tcs"):
            broker._services["climate_tcs"] = True

            [register_svc(k, v, f"svc_{k}") for k, v in SVCS_CLIMATE_EVO_TCS.items()]

    for zone in [z for z in discovery_info.get("zones", [])]:
        new_entities.append(entity_factory(EvohomeZone, broker, zone))

        if not broker._services.get("climate_zone"):
            broker._services["climate_zone"] = True

            [register_svc(k, v, f"svc_{k}") for k, v in SVCS_CLIMATE_EVO_ZONE.items()]

    for fan in [f for f in discovery_info.get("fans", [])]:
        new_entities.append(RamsesHvac(broker, fan))

    if new_entities:
        async_add_entities(new_entities)
