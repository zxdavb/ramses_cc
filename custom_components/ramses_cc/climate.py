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
    """Create climate entities for CH/DHW (heat) & HVAC."""

    def entity_factory(entity_class, broker, device):  # TODO: deprecate
        migrate_to_ramses_rf(hass, PLATFORM, device.id)
        return entity_class(broker, device)

    if discovery_info is None:
        return

    register_svc = async_get_current_platform().async_register_entity_service
    broker = hass.data[DOMAIN][BROKER]
    new_entities = []

    if discovery_info.get("fans"):
        if not broker._services.get(f"{PLATFORM}_hvac"):
            broker._services[f"{PLATFORM}_hvac"] = True
            # [register_svc(k, v, f"svc_{k}") for k, v in SVCS_CLIMATE_HVAC.items()]

        for fan in discovery_info["fans"]:
            new_entities.append(RamsesHvac(broker, fan))

    if discovery_info.get("ctls") or discovery_info.get("zons"):
        if not broker._services.get(f"{PLATFORM}_heat"):
            broker._services[f"{PLATFORM}_heat"] = True
            [register_svc(k, v, f"svc_{k}") for k, v in SVCS_CLIMATE_EVO_TCS.items()]
            [register_svc(k, v, f"svc_{k}") for k, v in SVCS_CLIMATE_EVO_ZONE.items()]

        for tcs in discovery_info.get("ctls", []):
            new_entities.append(entity_factory(EvohomeController, broker, tcs))

        for zone in discovery_info.get("zons", []):
            new_entities.append(entity_factory(EvohomeZone, broker, zone))

    if new_entities:
        async_add_entities(new_entities)
