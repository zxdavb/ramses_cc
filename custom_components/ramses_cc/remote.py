#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for HVAC RF remotes.
"""

import logging
from typing import Any, Dict, Iterable, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.remote import DOMAIN as PLATFORM
from homeassistant.components.remote import ATTR_NUM_REPEATS, RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType

from . import RamsesDeviceBase as RamsesEntity
from .const import BROKER, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Set up the remote entities.

    discovery_info keys:
      gateway: is the ramses_rf protocol stack (gateway/protocol/transport/serial)
      devices: heat (e.g. CTL, OTB, BDR, TRV) or hvac (e.g. FAN, CO2, REM)
      domains: TCS, DHW and Zones
    """

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    new_remotes = [
        RamsesRemote(broker, device)
        for device in discovery_info["remotes"]
    ]  # and (not device._is_faked or device["fakable"])

    async_add_entities(new_remotes)

    if not broker._services.get(PLATFORM) and new_remotes:
        broker._services[PLATFORM] = True


class RamsesRemote(RamsesEntity, RemoteEntity):
    """Representation of a generic sensor."""

    def __init__(self, broker, device, **kwargs) -> None:
        """Initialize a sensor."""
        _LOGGER.info("Found a Remote: %s", device)
        super().__init__(broker, device)

        device_id = device.id

        _attr_name = f"{device.id}_remote"

    @property
    def is_on(self) -> None | bool:
        """Return true if device is on."""
        return not self.coordinator.data.state.standby

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        await self.coordinator.roku.remote("poweron")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self.coordinator.roku.remote("poweroff")

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send a command to one device."""
        num_repeats = kwargs[ATTR_NUM_REPEATS]

        for _ in range(num_repeats):
            for single_command in command:
                await self.coordinator.roku.remote(single_command)
