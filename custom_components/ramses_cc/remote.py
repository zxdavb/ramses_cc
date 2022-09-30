#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for HVAC RF remotes.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any, Iterable

from homeassistant.components.remote import DOMAIN as PLATFORM
from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.typing import DiscoveryInfoType
from ramses_rf.protocol import Command, Priority

from . import RamsesEntity
from .const import BROKER, DOMAIN
from .schemas import SVCS_REMOTE

QOS_HIGH = {"priority": Priority.HIGH, "retries": 3}

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create remotes for HVAC."""

    if discovery_info is None:  # or not discovery_info.get("remotes")  # not needed
        return

    broker = hass.data[DOMAIN][BROKER]

    register_svc = async_get_current_platform().async_register_entity_service
    [register_svc(k, v, f"svc_{k}") for k, v in SVCS_REMOTE.items()]

    async_add_entities(
        [RamsesRemote(broker, device) for device in discovery_info["remotes"]]
    )

    if not broker._services.get(PLATFORM):
        broker._services[PLATFORM] = True


class RamsesRemote(RamsesEntity, RemoteEntity):
    """Representation of a generic sensor."""

    # entity_description: RemoteEntityDescription
    # _attr_activity_list: list[str] | None = None
    _attr_assumed_state: bool = True
    # _attr_current_activity: str | None = None
    _attr_supported_features: int = (
        RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
    )
    # _attr_state: None = None

    def __init__(self, broker, device, **kwargs) -> None:
        """Initialize a sensor."""
        _LOGGER.info("Found a Remote: %s", device)
        super().__init__(broker, device)

        self.entity_id = f"{DOMAIN}.{device.id}"

        self._attr_is_on = True
        self._attr_unique_id = (
            device.id
        )  # dont include domain (ramses_cc) / platform (remote)

        self._commands: dict[str, dict] = broker._known_commands.get(device.id, {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return super().extra_state_attributes | {"commands": self._commands}

    async def async_delete_command(
        self,
        command: Iterable[str],
        **kwargs: Any,
    ) -> None:
        """Delete commands from the database.

        service: remote.delete_command
        data:
          command: boost
        target:
          entity_id: remote.device_id
        """

        self._commands = {k: v for k, v in self._commands.items() if k not in command}

    async def async_learn_command(
        self,
        command: Iterable[str],
        timeout: float = 60,
        **kwargs: Any,
    ) -> None:
        """Learn a command from a device (remote) and add to the database.

        service: remote.learn_command
        data:
          command: boost
          timeout: 3
        target:
          entity_id: remote.device_id
        """

        @callback
        def event_filter(event: Event) -> bool:
            """Return True if the listener callable should run."""
            codes = ("22F1", "22F3", "22F7")
            return event.data["src"] == self._device.id and event.data["code"] in codes

        @callback
        def listener(event: Event) -> None:
            """Save the command to storage."""
            self._commands[command[0]] = event.data["packet"]

        if len(command) != 1:
            raise TypeError("must be exactly one command to learn")
        if not isinstance(timeout, (float, int)) or not 5 <= timeout <= 300:
            raise TypeError("timeout must be 5 to 300 (default 60)")

        if command[0] in self._commands:
            await self.async_delete_command(command)

        with self._broker._sem:
            remove_listener = self.hass.bus.async_listen(
                f"{DOMAIN}_message", listener, event_filter
            )

            dt_expires = dt.now() + td(seconds=timeout)
            while dt.now() < dt_expires:
                await asyncio.sleep(0.005)
                if self._commands.get(command[0]):
                    break

            remove_listener()

    async def async_send_command(
        self,
        command: Iterable[str],
        delay_secs: float = 0.05,
        num_repeats: int = 3,
        **kwargs: Any,
    ) -> None:
        """Send commands from a device (remote).

        service: remote.send_command
        data:
          command: boost
          delay_secs: 0.05
          num_repeats: 3
        target:
          entity_id: remote.device_id
        """

        if len(command) != 1:
            raise TypeError("must be exactly one command to send")
        if not isinstance(delay_secs, (float, int)) or not 0.02 <= delay_secs <= 1:
            raise TypeError("delay_secs must be 0.02 to 1.0 (default 0.05)")
        if not isinstance(num_repeats, int) or not 1 <= num_repeats <= 5:
            raise TypeError("num_repeats must be 1 to 5 (default 3)")

        if command[0] not in self._commands:
            raise LookupError(f"command '{command[0]}' is not known")

        if not self._device.is_faked:  # have to check here, as not using device method
            raise TypeError(f"{self._device.id} is not enabled for faking")

        for x in range(num_repeats):
            if x != 0:
                await asyncio.sleep(delay_secs)
            cmd = Command(
                self._commands[command[0]],
                qos={"priority": Priority.HIGH, "retries": 0},
            )
            self._broker.client.send_cmd(cmd)

        self._broker.async_update()

    async def svc_delete_command(self, *args, **kwargs) -> None:
        """Delete a RAMSES remote command from the database.

        This is a RAMSES-specific convenience wrapper for async_delete_command().
        """
        await self.async_learn_command(*args, **kwargs)

    async def svc_learn_command(self, *args, **kwargs) -> None:
        """Learn a command from a RAMSES remote and add to the database.

        This is a RAMSES-specific convenience wrapper for async_learn_command().
        """
        await self.async_learn_command(*args, **kwargs)

    async def svc_send_command(self, *args, **kwargs) -> None:
        """Send a command as is from a RAMSES remote.

        This is a RAMSES-specific convenience wrapper for async_send_command().
        """
        await self.async_learn_command(*args, **kwargs)
