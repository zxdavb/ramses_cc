#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine, Generator
from datetime import datetime as dt
from datetime import timedelta as td
import logging
from threading import Lock, Semaphore

from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import voluptuous as vol

from ramses_rf import Gateway
from ramses_rf.device.hvac import HvacRemoteBase, HvacVentilator
from ramses_rf.helpers import merge
from ramses_rf.schemas import (
    SZ_RESTORE_CACHE,
    SZ_RESTORE_SCHEMA,
    SZ_RESTORE_STATE,
    SZ_SCHEMA,
    extract_schema,
)

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .schemas import (
    merge_schemas,
    normalise_config,
)


_LOGGER = logging.getLogger(__name__)


class RamsesCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from single endpoint."""

    def __init__(
        self, hass: HomeAssistant, update_interval: td | None = None,
    ) -> None:

        super().__init(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            update_method=self.async_update,
        )

    async def async_update():
        pass


class RamsesBroker:
    """Container for client and data."""

    MAX_SEMAPHORE_LOCKS: int = 3

    def __init__(self, hass, hass_config) -> None:
        """Initialize the client and its data structure(s)."""

        self.hass = hass
        self._store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)

        self.hass_config = hass_config
        self._ser_name, self._client_config, self.config = normalise_config(
            hass_config[DOMAIN]
        )

        self.status = None
        self.client: Gateway = None  # type: ignore[assignment]
        self._services = {}
        self._entities = {}  # domain entities
        self._known_commands = self.config["remotes"]

        # Discovered client entities...
        self._hgi = None  # HGI, is distinct from devices (has no intrinsic sensors)
        self._tcs = None
        self._dhw = None
        self._zones = []
        self._objects: dict[str, list] = {
            "devices": [],
            "domains": [],
            "fans": [],
            "remotes": [],
        }

        self.loop_task = None
        self._last_update = dt.min
        self._lock = Lock()
        self._sem = Semaphore(value=self.MAX_SEMAPHORE_LOCKS)

    async def create_client(self) -> None:
        """Create a client with an initial schema, possibly a cached schema."""

        storage = await self.async_load_storage()
        self._known_commands = merge(self._known_commands, storage.get("remotes", {}))

        schema = extract_schema(**self._client_config)
        config = {k: v for k, v in self._client_config.items() if k not in schema}

        schemas = merge_schemas(
            self.config[SZ_RESTORE_CACHE][SZ_RESTORE_SCHEMA],
            schema,
            storage.get("client_state", {}).get(SZ_SCHEMA, {}),
        )
        for msg, schema in schemas.items():
            try:
                self.client = Gateway(
                    self._ser_name, loop=self.hass.loop, **config, **schema
                )
            except (LookupError, vol.MultipleInvalid) as exc:
                # LookupError:     ...in the schema, but also in the block_list
                # MultipleInvalid: ...extra keys not allowed @ data['???']
                _LOGGER.warning(f"Failed to initialise with {msg} schema: %s", exc)
            else:
                _LOGGER.info(f"Success initialising with {msg} schema: %s", schema)
                break
        else:
            self.client = Gateway(
                self._ser_name, loop=self.hass.loop, **self._client_config
            )
            _LOGGER.warning("Required to initialise with an empty schema: {}")

    async def restore_state(self) -> None:
        """Restore a cached state (a packet log) to the client."""

        if self.config[SZ_RESTORE_CACHE][SZ_RESTORE_STATE]:
            await self.async_load_client_state()
            _LOGGER.info("Restored the cached state.")
        else:
            _LOGGER.info("Not restoring any cached state (disabled).")

    async def async_load_storage(self) -> dict:
        """May return an empty dict."""
        app_storage = await self._store.async_load()  # return None if no store
        return app_storage or {}

    async def async_load_client_state(self) -> None:
        """Restore the client state from the application store."""

        _LOGGER.info("Restoring the client state cache (packets only)...")
        app_storage = await self.async_load_storage()
        if client_state := app_storage.get("client_state"):
            await self.client._set_state(packets=client_state["packets"])

    async def async_save_client_state(self, *args, **kwargs) -> None:
        """Save the client state to the application store."""

        _LOGGER.info("Saving the client state cache (packets, schema)...")

        (schema, packets) = self.client._get_state()
        remote_commands = self._known_commands | {
            k: v._commands for k, v in self._entities.items() if hasattr(v, "_commands")
        }

        await self._store.async_save(
            {
                "client_state": {"schema": schema, "packets": packets},
                "remotes": remote_commands,
            }
        )

    @callback
    def new_heat_entities(self) -> bool:
        """Discover & instantiate Climate & WaterHeater entities (Heat)."""

        if self.client.tcs is None:  # assumes the primary TCS is the only TCS
            return False

        discovery_info = {}

        if not self._tcs:
            self._tcs = discovery_info["tcs"] = self.client.tcs

        if new_zones := [z for z in self.client.tcs.zones if z not in self._zones]:
            self._zones.extend(new_zones)
            discovery_info["zones"] = new_zones

        if discovery_info:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.CLIMATE,
                    DOMAIN,
                    discovery_info,
                    self.hass_config,
                )
            )

        if self.client.tcs.dhw and self._dhw is None:
            self._dhw = discovery_info["dhw"] = self.client.tcs.dhw
            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.WATER_HEATER,
                    DOMAIN,
                    {"dhw": self._dhw},
                    self.hass_config,
                )
            )

        return bool(discovery_info)

    @callback
    def new_hvac_entities(self) -> bool:
        """Discover & instantiate HVAC entities (Climate, Remote)."""

        if new_fans := [
            f
            for f in self.client.devices
            if isinstance(f, HvacVentilator) and f not in self._objects["fans"]
        ]:
            self._objects["fans"].extend(new_fans)
            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.CLIMATE,
                    DOMAIN,
                    {"fans": new_fans},
                    self.hass_config,
                )
            )

        if new_remotes := [
            f
            for f in self.client.devices
            if isinstance(f, HvacRemoteBase) and f not in self._objects["remotes"]
        ]:
            self._objects["remotes"].extend(new_remotes)
            self.hass.async_create_task(
                async_load_platform(
                    self.hass,
                    Platform.REMOTE,
                    DOMAIN,
                    {"remotes": new_remotes},
                    self.hass_config,
                )
            )

        return bool(new_fans or new_remotes)

    @callback
    def new_sensors(self) -> bool:
        """Discover & instantiate Sensor and BinarySensor entities."""

        discovery_info = {}

        if not self._hgi and self.client.hgi:  # TODO: check HGI is added as a device
            self._hgi = discovery_info["gateway"] = self.client.hgi

        if new_devices := [
            d for d in self.client.devices if d not in self._objects["devices"]
        ]:
            self._objects["devices"].extend(new_devices)
            discovery_info["devices"] = new_devices

        new_domains = []
        if self.client.tcs:  # assumes the primary TCS is the only TCS
            new_domains = [
                d for d in self.client.tcs.zones if d not in self._objects["domains"]
            ]
            if self.client.tcs not in self._objects["domains"]:
                new_domains.append(self.client.tcs)
            if (dhw := self.client.tcs.dhw) and dhw not in self._objects["domains"]:
                new_domains.append(dhw)
            # for domain in ("F9", "FA", "FC"):
            #     if f"{self.client.tcs}_{domain}" not in

        if new_domains:
            self._objects["domains"].extend(new_domains)
            discovery_info["domains"] = new_domains

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

        self._lock.acquire()  # HACK: workaround bug

        dt_now = dt.now()
        if self._last_update < dt_now - td(seconds=1):
            self._last_update = dt_now

            if (
                self.new_sensors()
                or self.new_heat_entities()
                or self.new_hvac_entities()
            ):
                self.hass.helpers.event.async_call_later(
                    5, self.async_save_client_state
                )

        self._lock.release()

        # inform the devices that their state data may have changed
        # FIXME: no good here, as async_setup_platform will be called later
        async_dispatcher_send(self.hass, DOMAIN)


