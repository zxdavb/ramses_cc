"""Broker for RAMSES integration."""
from __future__ import annotations

from datetime import datetime as dt, timedelta
import logging
from threading import Semaphore
from typing import Any

from ramses_rf import Gateway
from ramses_rf.device.hvac import HvacRemoteBase, HvacVentilator
from ramses_rf.schemas import (
    SZ_CONFIG,
    SZ_RESTORE_CACHE,
    SZ_RESTORE_SCHEMA,
    SZ_RESTORE_STATE,
    SZ_SCHEMA,
)
from ramses_tx.schemas import SZ_PACKET_LOG, SZ_PORT_CONFIG
import voluptuous as vol

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SIGNAL_UPDATE, STORAGE_KEY, STORAGE_VERSION
from .schemas import merge_schemas, normalise_config, schema_is_minimal

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
        self._remotes: dict[str, str] = None  # type: ignore[assignment]

        self._services = {}
        self._entities = {}  # domain entities

        # Discovered client objects...
        self._hgi = None  # HGI, is distinct from devices
        self._ctls = []
        self._dhws = []
        self._devs = []
        self._fans = []
        self._rems = []
        self._zons = []

        self._sem = Semaphore(value=1)

        self.learn_device_id = None  # TODO: remove me

    async def start(self) -> None:
        """Invoke the client/co-ordinator (according to the config/cache)."""

        CONFIG_KEYS = (SZ_CONFIG, SZ_PACKET_LOG, SZ_PORT_CONFIG)

        storage = await self._async_load_storage()
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

        cached_packets = (
            self._filter_cached_packets(
                client_state.get(SZ_PACKETS, {}), restore_schema
            )
            if restore_state
            else {}
        )

        await self.client.start(cached_packets=cached_packets)

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

    def _filter_cached_packets(
        self, cached_packets: dict, restore_schema: bool
    ) -> dict:
        """Filter cached packets for replay on startup."""

        msg_code_filter = ["313F"]
        if not restore_schema:
            msg_code_filter.extend(["0005", "000C"])

        return {
            dtm: pkt
            for dtm, pkt in cached_packets.items()
            if dt.fromisoformat(dtm) > dt.now() - timedelta(days=1)
            and pkt[41:45] not in msg_code_filter
        }

    async def _async_load_storage(self) -> dict:
        """May return an empty dict."""

        app_storage = await self._store.async_load()  # return None if no store
        return app_storage or {}

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

    @callback
    def _find_new_heat_entities(self) -> bool:
        """Create Heat entities: Climate, WaterHeater, BinarySensor & Sensor."""

        if self.client.tcs is None:  # may only be HVAC
            return False

        if new_ctls := [s for s in self.client.systems if s not in self._ctls]:
            self._ctls.extend(new_ctls)
        if new_zons := [z for s in self._ctls for z in s.zones if z not in self._zons]:
            self._zons.extend(new_zons)
        if new_dhws := [s.dhw for s in self._ctls if s.dhw and s.dhw not in self._dhws]:
            self._dhws.extend(new_dhws)

        if new_ctls or new_zons:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.CLIMATE,
                    DOMAIN,
                    {"ctls": new_ctls, "zons": new_zons},  # discovery_info,
                    self.hass_config,
                )
            )
        if new_dhws:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.WATER_HEATER,
                    DOMAIN,
                    {"dhw": new_dhws},  # discovery_info,
                    self.hass_config,
                )
            )
        if new_doms := new_ctls + new_zons + new_dhws:
            # for domain in ("F9", "FA", "FC"):
            #     if f"{self.client.tcs}_{domain}" not in...
            for platform in (Platform.BINARY_SENSOR, Platform.SENSOR):
                self.hass.async_create_task(
                    async_load_platform(
                        self.hass,
                        platform,
                        DOMAIN,
                        {"domains": new_doms},  # discovery_info,
                        self.hass_config,
                    )
                )

        return bool(new_ctls + new_zons + new_dhws)

    @callback
    def _find_new_hvac_entities(self) -> bool:
        """Create HVAC entities: Climate, Remote."""

        if new_fans := [
            f
            for f in self.client.devices
            if isinstance(f, HvacVentilator) and f not in self._fans
        ]:
            self._fans.extend(new_fans)

            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.CLIMATE,
                    DOMAIN,
                    {"fans": new_fans},  # discovery_info,
                    self.hass_config,
                )
            )

        if new_remotes := [
            f
            for f in self.client.devices
            if isinstance(f, HvacRemoteBase) and f not in self._rems
        ]:
            self._rems.extend(new_remotes)

            discovered = {SZ_REMOTES: new_remotes}
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, Platform.REMOTE, DOMAIN, discovered, self.hass_config
                )
            )

        return bool(new_fans or new_remotes)

    @callback
    def _find_new_sensors(self) -> bool:
        """Create HVAC entities: BinarySensor & Sensor."""

        discovery_info = {}

        if not self._hgi and self.client.hgi:  # TODO: check HGI is added as a device
            self._hgi = discovery_info["gateway"] = self.client.hgi

        if new_devices := [d for d in self.client.devices if d not in self._devs]:
            self._devs.extend(new_devices)
            discovery_info["devices"] = new_devices

        if discovery_info:
            for platform in (Platform.BINARY_SENSOR, Platform.SENSOR):
                self.hass.async_create_task(
                    async_load_platform(
                        self.hass, platform, DOMAIN, discovery_info, self.hass_config
                    )
                )

        return bool(discovery_info)

    async def async_update(self, *args, **kwargs) -> None:
        """Retrieve the latest state data from the client library."""

        new_sensors = self._find_new_sensors()
        new_heat_entities = self._find_new_heat_entities()
        new_hvac_entities = self._find_new_hvac_entities()

        if new_sensors or new_heat_entities or new_hvac_entities:
            async_call_later(self.hass, 5, self.async_save_client_state)

        # Trigger state updates of all entities
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
