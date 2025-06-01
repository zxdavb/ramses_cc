"""Support for RAMSES HVAC RF remotes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
from typing import Any

from homeassistant.components.remote import (
    ENTITY_ID_FORMAT,
    RemoteEntity,
    RemoteEntityDescription,
    RemoteEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    EntityPlatform,
    async_get_current_platform,
)

from ramses_rf.device.hvac import HvacRemote
from ramses_tx.command import Command
from ramses_tx.const import Priority

from . import RamsesEntity, RamsesEntityDescription
from .broker import RamsesBroker
from .const import DOMAIN
from .schemas import (
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
    DEFAULT_TIMEOUT,
    SVCS_RAMSES_REMOTE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the remote platform."""
    broker: RamsesBroker = hass.data[DOMAIN][entry.entry_id]
    platform: EntityPlatform = async_get_current_platform()

    for k, v in SVCS_RAMSES_REMOTE.items():
        platform.async_register_entity_service(k, v, f"async_{k}")

    @callback
    def add_devices(devices: list[HvacRemote]) -> None:
        entities = [
            RamsesRemoteEntityDescription.ramses_cc_class(
                broker, device, RamsesRemoteEntityDescription()
            )
            for device in devices
        ]
        async_add_entities(entities)

    broker.async_register_platform(platform, add_devices)


class RamsesRemote(RamsesEntity, RemoteEntity):
    """Representation of a generic sensor."""

    _device: HvacRemote

    _attr_assumed_state: bool = True
    _attr_supported_features: int = (
        RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
    )

    def __init__(
        self,
        broker: RamsesBroker,
        device: HvacRemote,
        entity_description: RamsesRemoteEntityDescription,
    ) -> None:
        """Initialize a HVAC remote."""
        _LOGGER.info("Found %r", device)
        super().__init__(broker, device, entity_description)

        self.entity_id = ENTITY_ID_FORMAT.format(device.id)

        self._attr_is_on = True
        self._commands: dict[str, str] = broker._remotes.get(device.id, {})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return super().extra_state_attributes | {"commands": self._commands}

    async def async_delete_command(
        self,
        command: Iterable[str] | str,
        **kwargs: Any,
    ) -> None:
        """Delete commands from the database.

        service: remote.delete_command
        data:
          command: boost
        target:
          entity_id: remote.device_id
        """

        # HACK to make ramses_cc call work as per HA service call
        command = [command] if isinstance(command, str) else list(command)
        # if len(command) != 1:
        #     raise TypeError("must be exactly one command to delete")

        assert not kwargs, kwargs  # TODO: remove me

        self._commands = {k: v for k, v in self._commands.items() if k not in command}

    async def async_learn_command(
        self,
        command: Iterable[str] | str,
        timeout: int = DEFAULT_TIMEOUT,
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

        # HACK to make ramses_cc call work as per HA service call
        command = [command] if isinstance(command, str) else list(command)
        if len(command) != 1:
            raise TypeError("must be exactly one command to learn")

        assert not kwargs, kwargs  # TODO: remove me

        if command[0] in self._commands:
            await self.async_delete_command(command)

        @callback
        def event_filter(event: Event) -> bool:
            """Return True if the listener callable should run."""
            codes = ("22F1", "22F3", "22F7")
            return event.data["src"] == self._device.id and event.data["code"] in codes

        @callback
        def listener(event: Event) -> None:
            """Save the command to storage."""
            # if event.data["packet"] in self._commands.values():  # TODO
            #     raise DuplicateError
            self._commands[command[0]] = event.data["packet"]

        with self._broker._sem:
            self._broker.learn_device_id = self._device.id
            remove_listener = self.hass.bus.async_listen(
                f"{DOMAIN}_learn", listener, event_filter
            )

            dt_expires = dt.now() + timedelta(seconds=timeout)
            while dt.now() < dt_expires:
                await asyncio.sleep(0.005)
                if self._commands.get(command[0]):
                    break

            self._broker.learn_device_id = None
            remove_listener()

    async def async_send_command(
        self,
        command: Iterable[str] | str,
        num_repeats: int = DEFAULT_NUM_REPEATS,
        delay_secs: float = DEFAULT_DELAY_SECS,
        hold_secs: None = None,
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

        # HACK to make ramses_cc call work as per HA service call
        command = [command] if isinstance(command, str) else list(command)
        if len(command) != 1:
            raise TypeError("must be exactly one command to send")

        if hold_secs:
            raise TypeError("hold_secs is not supported")

        assert not kwargs, kwargs  # TODO: remove me

        if command[0] not in self._commands:
            raise LookupError(f"command '{command[0]}' is not known")

        if not self._device.is_faked:  # have to check here, as not using device method
            raise TypeError(f"{self._device.id} is not configured for faking")

        cmd = Command(self._commands[command[0]])
        for x in range(num_repeats):  # TODO: use ramses_rf's QoS
            if x != 0:
                await asyncio.sleep(delay_secs)
            await self._broker.client.async_send_cmd(cmd, priority=Priority.HIGH)

        await self._broker.async_update()


@dataclass(frozen=True, kw_only=True)
class RamsesRemoteEntityDescription(RamsesEntityDescription, RemoteEntityDescription):
    """Class describing Ramses remote entities."""

    key = "remote"

    # integration-specific attributes
    ramses_cc_class: type[RamsesRemote] = RamsesRemote
