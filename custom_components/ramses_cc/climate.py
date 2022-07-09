#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW (heat) & HVAC.

Provides support for climate entities.
"""

import logging

from homeassistant.components.climate import DOMAIN as PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .climate_heat import EvoController, EvoZone
from .climate_hvac import RamsesHvac
from .const import BROKER, DOMAIN
from .helpers import migrate_to_ramses_rf
from .schema import SVCS_CLIMATE_EVOHOME

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

    if tcs := discovery_info.get("tcs"):
        new_entities.append(entity_factory(EvoController, broker, tcs))

        if not broker._services.get(PLATFORM):
            broker._services[PLATFORM] = True

            register_svc = current_platform.get().async_register_entity_service
            [register_svc(k, v, f"svc_{k}") for k, v in SVCS_CLIMATE_EVOHOME.items()]

    for zone in [z for z in discovery_info.get("zones", [])]:
        new_entities.append(entity_factory(EvoZone, broker, zone))

    for fan in [f for f in discovery_info.get("fans", [])]:
        new_entities.append(RamsesHvac(broker, fan))

    if new_entities:
        async_add_entities(new_entities)
