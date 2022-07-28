#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

import asyncio
import logging
from datetime import datetime as dt
from datetime import timedelta as td
from threading import Lock
from typing import Any, Dict, List, Optional

import ramses_rf
import serial
import voluptuous as vol

#
from homeassistant.const import CONF_SCAN_INTERVAL, TEMP_CELSIUS, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from ramses_rf import Gateway
from ramses_rf.device.hvac import HvacRemoteBase, HvacVentilator
from ramses_rf.schemas import extract_schema

from .const import (
    BROKER,
    DATA,
    DOMAIN,
    SERVICE,
    STORAGE_KEY,
    STORAGE_VERSION,
    UNIQUE_ID,
)
from .schemas import (
    SCH_DOMAIN_CONFIG,
    SVC_SEND_PACKET,
    SVCS_DOMAIN,
    SVCS_DOMAIN_EVOHOME,
    SVCS_WATER_HEATER_EVOHOME,
    SZ_ADVANCED_FEATURES,
    SZ_MESSAGE_EVENTS,
    SZ_RESTORE_CACHE,
    SZ_RESTORE_SCHEMA,
    SZ_RESTORE_STATE,
    SZ_SCHEMA,
    merge_schemas,
    normalise_config,
)
from .version import __version__ as VERSION

_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema({DOMAIN: SCH_DOMAIN_CONFIG}, extra=vol.ALLOW_EXTRA)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]
SAVE_STATE_INTERVAL = td(seconds=300)  # TODO: 5 minutes


async def async_setup(
    hass: HomeAssistant,
    hass_config: ConfigType,
) -> bool:
    """Create a ramses_rf (RAMSES_II)-based system."""

    async def async_handle_exceptions(awaitable):
        """Wrap the serial port interface to catch/report exceptions."""
        try:
            return await awaitable
        except serial.SerialException as exc:
            _LOGGER.exception("There is a problem with the serial port: %s", exc)
            raise exc

    _LOGGER.info(f"{DOMAIN} v{VERSION}, is using ramses_rf v{ramses_rf.VERSION}")
    _LOGGER.debug("\r\n\nConfig = %s\r\n", hass_config[DOMAIN])

    broker = RamsesBroker(hass, hass_config)

    if _LOGGER.isEnabledFor(logging.DEBUG):
        app_storage = await broker.async_load_storage()
        _LOGGER.debug("\r\n\nStore = %s\r\n", app_storage)

    await broker.create_client()  # start with a merged/cached, config, null schema
    if broker.client is None:
        return False

    hass.data[DOMAIN] = {BROKER: broker}
    await broker.restore_state()  # load a cached packet log

    _LOGGER.debug("Starting the RF monitor...")  # TODO: move this out of setup?
    broker.loop_task = hass.loop.create_task(
        async_handle_exceptions(broker.client.start())
    )
    # TODO: all this scheduling needs sorting out
    hass.helpers.event.async_track_time_interval(
        broker.async_save_client_state, SAVE_STATE_INTERVAL
    )
    hass.helpers.event.async_track_time_interval(
        broker.async_update, hass_config[DOMAIN][CONF_SCAN_INTERVAL]
    )
    hass.helpers.event.async_call_later(15, broker.async_update)  # HACK: to remove

    register_service_functions(hass, broker)
    register_trigger_events(hass, broker)

    return True


@callback  # TODO: add async_ to routines where required to do so
def register_trigger_events(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @callback
    def process_msg(msg, *args, **kwargs):  # process_msg(msg, prev_msg=None)
        event_data = {
            "dtm": msg.dtm.isoformat(),
            "src": msg.src.id,
            "dst": msg.dst.id,
            "verb": msg.verb,
            "code": msg.code,
            "payload": msg.payload,
            "packet": str(msg._pkt),
        }
        hass.bus.async_fire(f"{DOMAIN}_message", event_data)

    if broker.config[SZ_ADVANCED_FEATURES][SZ_MESSAGE_EVENTS]:
        broker.client.create_client(process_msg)


@callback  # TODO: add async_ to routines where required to do so
def register_service_functions(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @verify_domain_control(hass, DOMAIN)
    async def svc_fake_device(call: ServiceCall) -> None:
        try:
            broker.client.fake_device(**call.data)
        except LookupError as exc:
            _LOGGER.error("%s", exc)
            return
        await asyncio.sleep(1)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_force_refresh(call: ServiceCall) -> None:
        await broker.async_update()
        # includes: async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_reset_system_mode(call: ServiceCall) -> None:
        payload = {
            UNIQUE_ID: broker.client.tcs.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_set_system_mode(call: ServiceCall) -> None:
        payload = {
            UNIQUE_ID: broker.client.tcs.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_send_packet(call: ServiceCall) -> None:
        broker.client.send_cmd(broker.client.create_cmd(**call.data))
        await asyncio.sleep(1)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_call_dhw_svc(call: ServiceCall) -> None:
        payload = {
            UNIQUE_ID: f"{broker.client.tcs.id}_HW",
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    [
        hass.services.async_register(DOMAIN, k, svc_call_dhw_svc, schema=v)
        for k, v in SVCS_WATER_HEATER_EVOHOME.items()
    ]

    domain_service = SVCS_DOMAIN
    if not broker.config[SZ_ADVANCED_FEATURES].get(SVC_SEND_PACKET):
        del domain_service[SVC_SEND_PACKET]
    domain_service |= SVCS_DOMAIN_EVOHOME

    services = {k: v for k, v in locals().items() if k.startswith("svc")}
    [
        hass.services.async_register(DOMAIN, k, services[f"svc_{k}"], schema=v)
        for k, v in SVCS_DOMAIN.items()
        if f"svc_{k}" in services
    ]


class RamsesBroker:
    """Container for client and data."""

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

        self.loop_task = None
        self._last_update = dt.min

        self._hgi = None  # HGI, is distinct from devices (has no intrinsic sensors)
        self._tcs = None
        self._dhw = None
        self._zones = []

        self._entities: dict[str, list] = {
            "devices": [],
            "domains": [],
            "fans": [],
            "remotes": [],
        }

        self._lock = Lock()

    async def create_client(self) -> None:
        """Create a client with an initial schema, possibly a cached schema."""

        storage = await self.async_load_storage()

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
                # LookupError: ...in the schema, but also in the block_list
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
        await self._store.async_save(
            {"client_state": {"schema": schema, "packets": packets}}
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
            if isinstance(f, HvacVentilator) and f not in self._entities["fans"]
        ]:
            self._entities["fans"].extend(new_fans)
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
            if isinstance(f, HvacRemoteBase) and f not in self._entities["remotes"]
        ]:
            self._entities["remotes"].extend(new_remotes)
            # self.hass.async_create_task(
            #     async_load_platform(
            #         self.hass,
            #         Platform.REMOTE,
            #         DOMAIN,
            #         {"remotes": new_remotes},
            #         self.hass_config,
            #     )
            # )

        return bool(new_fans or new_remotes)

    @callback
    def new_sensors(self) -> bool:
        """Discover & instantiate Sensor and BinarySensor entities."""

        discovery_info = {}

        if not self._hgi and self.client.hgi:  # TODO: check HGI is added as a device
            self._hgi = discovery_info["gateway"] = self.client.hgi

        if new_devices := [
            d for d in self.client.devices if d not in self._entities["devices"]
        ]:
            self._entities["devices"].extend(new_devices)
            discovery_info["devices"] = new_devices

        new_domains = []
        if self.client.tcs:  # assumes the primary TCS is the only TCS
            new_domains = [
                d for d in self.client.tcs.zones if d not in self._entities["domains"]
            ]
            if self.client.tcs not in self._entities["domains"]:
                new_domains.append(self.client.tcs)
            if (dhw := self.client.tcs.dhw) and dhw not in self._entities["domains"]:
                new_domains.append(dhw)
            # for domain in ("F9", "FA", "FC"):
            #     if f"{self.client.tcs}_{domain}" not in

        if new_domains:
            self._entities["domains"].extend(new_domains)
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
        if self._last_update < dt_now - td(seconds=10):
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


class RamsesEntity(Entity):
    """Base for any RAMSES II-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, broker, device) -> None:
        """Initialize the entity."""
        self.hass = broker.hass
        self._broker = broker
        self._device = device

        self._unique_id = self._name = None
        self._entity_state_attrs = ()

        # NOTE: this is bad: self.update_ha_state(delay=5)

    @callback
    def async_handle_dispatch(self, *args) -> None:  # TODO: remove as unneeded?
        """Process a dispatched message.

        Data validation is not required, it will have been done upstream.
        This routine is threadsafe.
        """
        if not args:
            self.update_ha_state()

    @callback
    def update_ha_state(self, delay=3) -> None:
        """Update HA state after a short delay to allow system to quiesce.

        This routine is threadsafe.
        """
        args = (delay, self.async_schedule_update_ha_state)
        self.hass.loop.call_soon_threadsafe(
            self.hass.helpers.event.async_call_later, *args
        )  # HACK: call_soon_threadsafe should not be needed

    @callback  # TODO: WIP
    def _call_client_api(self, func, *args, **kwargs) -> None:
        """Wrap client APIs to make them threadsafe."""
        # self.hass.loop.call_soon_threadsafe(
        #     func(*args, **kwargs)
        # )  # HACK: call_soon_threadsafe should not be needed

        func(*args, **kwargs)
        self.update_ha_state()

    @property
    def should_poll(self) -> bool:
        """Entities should not be polled."""
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._unique_id

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = {
            a: getattr(self._device, a)
            for a in self._entity_state_attrs
            if hasattr(self._device, a)
        }
        # TODO: use self._device._parent?
        # attrs["controller_id"] = self._device.ctl.id if self._device.ctl else None
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        async_dispatcher_connect(self.hass, DOMAIN, self.async_handle_dispatch)


class RamsesDeviceBase(RamsesEntity):
    """Base for any RAMSES II-compatible entity (e.g. BinarySensor, Sensor)."""

    def __init__(
        self,
        broker,
        device,
        device_id,
        attr_name,
        state_attr,
        device_class,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._unique_id = f"{device_id}-{attr_name}"

        self._device_class = device_class
        self._device_id = device.id  # e.g. 10:123456_alt
        self._state_attr = state_attr
        self._state_attr_friendly_name = attr_name

    @property
    def available(self) -> bool:
        """Return True if the sensor is available."""
        return getattr(self._device, self._state_attr) is not None

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().extra_state_attributes
        attrs["device_id"] = self._device.id

        if hasattr(self._device, "_domain_id"):
            attrs["domain_id"] = self._device._domain_id
        elif hasattr(self._device, "idx"):
            attrs["domain_id"] = self._device.idx

        if hasattr(self._device, "name"):
            attrs["domain_name"] = self._device.name
        else:
            try:
                attrs["domain_name"] = self._device.zone.name
            except AttributeError:
                pass

        if hasattr(self._device, "role"):
            attrs["role"] = self._device.role

        return attrs

    @property
    def name(self) -> str:
        """Return the name of the binary_sensor/sensor."""
        if not hasattr(self._device, "name") or not self._device.name:
            return f"{self._device_id} {self._state_attr_friendly_name}"
        return f"{self._device.name} {self._state_attr_friendly_name}"


class EvohomeZoneBase(RamsesEntity):
    """Base for any RAMSES RF-compatible entity (e.g. Controller, DHW, Zones)."""

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._unique_id = device.id

        self._hvac_modes = None
        self._preset_modes = None
        self._supported_features = None

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._device.temperature

    @property
    def name(self) -> str:
        """Return the name of the climate/water_heater entity."""
        return self._device.name or self._device.id

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return self._supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return self._hvac_modes

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        return self._preset_modes

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().extra_state_attributes,
            "schema": self._device.schema,
            "params": self._device.params,
            # "schedule": self._device.schedule,
        }
