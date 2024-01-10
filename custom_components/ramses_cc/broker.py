"""Broker for RAMSES integration."""
from __future__ import annotations

from datetime import datetime as dt, timedelta
import logging
from threading import Semaphore
from typing import TYPE_CHECKING, Any

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
from ramses_rf.system import Evohome, System, Zone
from ramses_tx.schemas import SZ_PACKET_LOG, SZ_PORT_CONFIG
import voluptuous as vol  # type: ignore[import-untyped]

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SIGNAL_UPDATE, STORAGE_KEY, STORAGE_VERSION
from .schemas import merge_schemas, normalise_config, schema_is_minimal

if TYPE_CHECKING:
    from . import RamsesEntity


_LOGGER = logging.getLogger(__name__)

SZ_CLIENT_STATE = "client_state"
SZ_PACKETS = "packets"
SZ_REMOTES = "remotes"

SAVE_STATE_INTERVAL = timedelta(seconds=300)  # TODO: 5 minutes


class RamsesBroker:
    """Container for client and data."""

    def __init__(self, hass: HomeAssistant, hass_config: ConfigType) -> None:
        """Initialize the client and its data structure(s)."""

        self.hass = hass
        self._store: Store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)

        self.hass_config = hass_config
        _LOGGER.debug("Config = %s", hass_config)
        self._ser_name, self._client_config, self.config = normalise_config(
            hass_config[DOMAIN]
        )

        self.client: Gateway = None  # type: ignore[assignment]
        self._remotes: dict[str, dict[str, str]] = {}

        self._services: dict = {}
        self._entities: dict[str, RamsesEntity] = {}  # domain entities

        # Discovered client objects...
        self._devices: list[Device] = []
        self._systems: list[System] = []
        self._zones: list[Zone] = []
        self._dhws: list[Zone] = []

        self._sem = Semaphore(value=1)

        self.learn_device_id = None  # TODO: remove me

    async def start(self) -> None:
        """Invoke the client/co-ordinator (according to the config/cache)."""

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

            msg_code_filter = ["313F"]  # ? 1FC9
            if not restore_schema:
                msg_code_filter.extend(["0005", "000C"])

            return {
                dtm: pkt
                for dtm, pkt in client_state.get(SZ_PACKETS, {}).items()
                if dt.fromisoformat(dtm) > dt.now() - timedelta(days=1)
                and pkt[41:45] not in msg_code_filter
            }

        await self.client.start(cached_packets=cached_packets())

        # Perform initial update, then poll at intervals
        await self.async_update()
        async_track_time_interval(
            self.hass, self.async_update, self.hass_config[DOMAIN][CONF_SCAN_INTERVAL]
        )

        async_track_time_interval(
            self.hass, self.async_save_client_state, SAVE_STATE_INTERVAL
        )

    def _create_client(
        self,
        client_config: dict[str, Any],
        config_schema: dict[str, Any],
        cached_schema: dict[str, Any] | None = None,
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

        schema, packets = self.client.get_state()
        remotes = self._remotes | {
            k: v._commands for k, v in self._entities.items() if hasattr(v, "_commands")
        }

        await self._store.async_save(
            {
                SZ_CLIENT_STATE: {SZ_SCHEMA: schema, SZ_PACKETS: packets},
                SZ_REMOTES: remotes,
            }
        )

    async def async_update(self, _: dt | None = None) -> None:
        """Retrieve the latest state data from the client library."""

        gwy: Gateway = self.client

        def async_add_entities(platform: str, devices: list[RamsesRFEntity]) -> None:
            if not devices:
                return None
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, platform, DOMAIN, {"devices": devices}, self.hass_config
                )
            )

        def find_new_entities(
            known: list[RamsesRFEntity], current: list[RamsesRFEntity]
        ) -> tuple[list[RamsesRFEntity], list[RamsesRFEntity]]:
            new = [x for x in current if x not in known]
            return known + new, new

        self._systems, new_systems = find_new_entities(
            self._systems,
            [s for s in gwy.systems if isinstance(s, Evohome)],
        )
        self._zones, new_zones = find_new_entities(
            self._zones,
            [z for s in gwy.systems for z in s.zones if isinstance(s, Evohome)],
        )
        self._dhws, new_dhws = find_new_entities(
            self._dhws,
            [s.dhw for s in gwy.systems if s.dhw if isinstance(s, Evohome)],
        )
        self._devices, new_devices = find_new_entities(self._devices, gwy.devices)

        new_entities = new_devices + new_systems + new_zones + new_dhws
        async_add_entities(Platform.BINARY_SENSOR, new_entities)
        async_add_entities(Platform.SENSOR, new_entities)

        #  these isinstance(d, ) are required...
        async_add_entities(
            Platform.CLIMATE, [d for d in new_devices if isinstance(d, HvacVentilator)]
        )
        async_add_entities(
            Platform.REMOTE, [d for d in new_devices if isinstance(d, HvacRemoteBase)]
        )

        #  these isinstance(x, ) are not required...
        async_add_entities(Platform.CLIMATE, [s for s in new_systems])  # (s, Evohome)
        async_add_entities(Platform.CLIMATE, [z for z in new_zones])  # (z.tcs, Evohome)
        async_add_entities(Platform.WATER_HEATER, [d for d in new_dhws])  # (d, DhwZone)

        if new_entities:
            async_call_later(self.hass, 5, self.async_save_client_state)

        # Trigger state updates of all entities
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
