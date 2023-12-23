"""Broker for RAMSES integration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime as dt, timedelta
import logging
from threading import Semaphore
from typing import Any

from ramses_rf import Gateway
from ramses_rf.device.base import Device
from ramses_rf.device.hvac import HvacRemoteBase, HvacVentilator
from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_rf.schemas import (
    SZ_CONFIG,
    SZ_RESTORE_CACHE,
    SZ_RESTORE_SCHEMA,
    SZ_RESTORE_STATE,
    SZ_SCHEMA,
)
from ramses_rf.system.heat import Evohome, MultiZone, System
from ramses_rf.system.zones import DhwZone, Zone
from ramses_tx.schemas import SZ_PACKET_LOG, SZ_PORT_CONFIG
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import SIGNAL_NEW_DEVICES, SIGNAL_UPDATE, STORAGE_KEY, STORAGE_VERSION
from .schemas import merge_schemas, normalise_config, schema_is_minimal

_LOGGER = logging.getLogger(__name__)

SZ_CLIENT_STATE = "client_state"
SZ_PACKETS = "packets"
SZ_REMOTES = "remotes"

SAVE_STATE_INTERVAL = timedelta(seconds=300)  # TODO: 5 minutes


class RamsesBroker:
    """Container for client and data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the client and its data structure(s)."""

        self.hass = hass
        self.entry = entry
        self._store: Store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)

        _LOGGER.debug("Config = %s", entry.data)
        self._ser_name, self._client_config, self.config = normalise_config(entry.data)

        self.client: Gateway = None  # type: ignore[assignment]
        self._remotes: dict[str, str] = None  # type: ignore[assignment]

        self._platform_setup_tasks = {}
        self.entry.async_on_unload(self._async_unload_platforms)

        self._entities = {}  # domain entities

        # Discovered client objects...
        self._devices: set[Device] = set()
        self._systems: set[System] = set()
        self._zones: set[Zone] = set()

        self._sem = Semaphore(value=1)

        self.learn_device_id = None  # TODO: remove me

    async def async_setup(self) -> None:
        """Set up the client, loading and checking state and config."""

        CONFIG_KEYS = (SZ_CONFIG, SZ_PACKET_LOG, SZ_PORT_CONFIG)

        storage = await self._store.async_load() or {}
        _LOGGER.debug("Storage = %s", storage)

        self._remotes = storage.get(SZ_REMOTES, {}) | self.config[SZ_REMOTES]
        client_state: dict[str, Any] = storage.get(SZ_CLIENT_STATE, {})

        restore_state = self.config[SZ_RESTORE_CACHE][SZ_RESTORE_STATE]
        restore_schema = self.config[SZ_RESTORE_CACHE][SZ_RESTORE_SCHEMA]

        self.client = self._create_client(
            {k: v for k, v in self._client_config.items() if k in CONFIG_KEYS},
            {k: v for k, v in self._client_config.items() if k not in CONFIG_KEYS},
            client_state.get(SZ_SCHEMA, {}) if restore_schema else {},
        )

        def cached_packets() -> dict[str, str]:  # dtm_str, packet_as_str
            if not restore_state:
                return {}

            msg_code_filter = ["313F"]
            if not restore_schema:
                msg_code_filter.extend(["0005", "000C"])

            return {
                dtm: pkt
                for dtm, pkt in client_state.get(SZ_PACKETS, {}).items()
                if dt.fromisoformat(dtm) > dt.now() - timedelta(days=100)
                and pkt[41:45] not in msg_code_filter
            }

        await self.client.start(cached_packets=cached_packets())
        self.entry.async_on_unload(self.client.stop)

    async def async_start(self) -> None:
        """Perform initial update, then poll and save state at intervals."""
        await self.async_update()
        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass,
                self.async_update,
                timedelta(seconds=self.config[CONF_SCAN_INTERVAL]),
            )
        )

        self.entry.async_on_unload(
            async_track_time_interval(
                self.hass, self.async_save_client_state, SAVE_STATE_INTERVAL
            )
        )
        self.entry.async_on_unload(self.async_save_client_state)

    def _create_client(
        self,
        client_config: dict[str:Any],
        config_schema: dict[str:Any],
        cached_schema: dict[str:Any] | None = None,
    ) -> Gateway:
        """Create a client with an inital schema (merged or config)."""

        # TODO: move this to volutuous schema
        if not schema_is_minimal(config_schema):  # move this logic into ramses_rf?
            _LOGGER.warning("The config schema is not minimal (consider minimising it)")

        if cached_schema and (merged := merge_schemas(config_schema, cached_schema)):
            try:
                return Gateway(
                    self._ser_name, loop=self.hass.loop, **client_config, **merged
                )
            except (LookupError, vol.MultipleInvalid) as exc:
                # LookupError:     ...in the schema, but also in the block_list
                # MultipleInvalid: ...extra keys not allowed @ data['???']
                _LOGGER.warning("Failed to initialise with merged schema: %s", exc)

        return Gateway(
            self._ser_name, loop=self.hass.loop, **client_config, **config_schema
        )

    async def async_save_client_state(self, *args, **kwargs) -> None:
        """Save the client state to the application store."""

        _LOGGER.info("Saving the client state cache (packets, schema)")

        (schema, packets) = self.client._get_state()
        remotes = self._remotes | {
            k: v._commands for k, v in self._entities.items() if hasattr(v, "_commands")
        }

        await self._store.async_save(
            {
                SZ_CLIENT_STATE: {SZ_SCHEMA: schema, SZ_PACKETS: packets},
                SZ_REMOTES: remotes,
            }
        )

    def async_register_platform(
        self,
        platform: EntityPlatform,
        add_new_devices: Callable[[RamsesRFEntity], None],
    ) -> None:
        """Register a platform for device addition."""
        self.entry.async_on_unload(
            async_dispatcher_connect(
                self.hass, SIGNAL_NEW_DEVICES.format(platform.domain), add_new_devices
            )
        )

    async def _async_setup_platform(self, platform: str) -> None:
        """Set up a platform."""
        if platform not in self._platform_setup_tasks:
            self._platform_setup_tasks[platform] = self.hass.async_create_task(
                self.hass.config_entries.async_forward_entry_setup(self.entry, platform)
            )
        await self._platform_setup_tasks[platform]

    async def _async_unload_platforms(self) -> None:
        """Unload platforms."""
        tasks = []

        for platform, task in self._platform_setup_tasks.items():
            if task.done():
                tasks.append(
                    self.hass.config_entries.async_forward_entry_unload(
                        self.entry, platform
                    )
                )
            else:
                task.cancel()
                tasks.append(task)

        return all(await asyncio.gather(*tasks))

    async def async_update(self, _: dt | None = None) -> None:
        """Retrieve the latest state data from the client library."""

        async def async_add_devices(
            platform: str, devices: list[RamsesRFEntity]
        ) -> None:
            if not devices:
                return
            await self._async_setup_platform(platform)
            async_dispatcher_send(
                self.hass, SIGNAL_NEW_DEVICES.format(platform), devices
            )

        def new_entities(
            known: set[RamsesRFEntity], current: list[RamsesRFEntity]
        ) -> list[RamsesRFEntity]:
            new = current - known
            known |= new
            return new

        new_devices = new_entities(self._devices, set(self.client.devices))
        new_systems = new_entities(self._systems, set(self.client.systems))
        new_zones = new_entities(
            self._zones,
            set().union(
                *[s.zones for s in self.client.systems if isinstance(s, MultiZone)]
            ),
        )

        new_sensor_devices = new_devices | new_systems | new_zones
        await async_add_devices(Platform.BINARY_SENSOR, new_sensor_devices)
        await async_add_devices(Platform.SENSOR, new_sensor_devices)

        await async_add_devices(
            Platform.CLIMATE, [d for d in new_devices if isinstance(d, HvacVentilator)]
        )
        await async_add_devices(
            Platform.REMOTE, [d for d in new_devices if isinstance(d, HvacRemoteBase)]
        )
        await async_add_devices(
            Platform.CLIMATE, [s for s in new_systems if isinstance(s, Evohome)]
        )

        for zone in new_zones:
            if isinstance(zone, DhwZone):
                await async_add_devices(Platform.WATER_HEATER, [zone])
            elif isinstance(zone.tcs, Evohome):
                await async_add_devices(Platform.CLIMATE, [zone])

        if new_devices or new_systems or new_zones:
            async_call_later(self.hass, 5, self.async_save_client_state)

        # Trigger state updates of all entities
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
