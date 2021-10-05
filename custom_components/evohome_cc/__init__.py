#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

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
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR
from homeassistant.components.climate import DOMAIN as CLIMATE
from homeassistant.components.sensor import DOMAIN as SENSOR
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER
from homeassistant.const import CONF_SCAN_INTERVAL, TEMP_CELSIUS
from homeassistant.core import callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import (
    BROKER,
    DATA,
    DOMAIN,
    SERVICE,
    STORAGE_KEY,
    STORAGE_VERSION,
    UNIQUE_ID,
)
from .schema import CONFIG_SCHEMA  # noqa: F401
from .schema import (
    CONF_RESTORE_STATE,
    DOMAIN_SERVICES,
    SVC_SEND_PACKET,
    WATER_HEATER_SERVICES,
    normalise_config_schema,
)
from .version import __version__ as VERSION

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [BINARY_SENSOR, CLIMATE, SENSOR, WATER_HEATER]
SAVE_STATE_INTERVAL = td(seconds=300)  # TODO: 5 minutes


async def async_setup(hass: HomeAssistantType, hass_config: ConfigType) -> bool:
    """Create a Honeywell RF (RAMSES_II)-based system."""

    async def async_handle_exceptions(awaitable):
        """Wrap the serial port interface to catch exceptions."""
        try:
            return await awaitable
        except serial.SerialException as exc:
            _LOGGER.error("There is a problem with the serial port: %s", exc)
            raise exc

    _LOGGER.debug(f"{DOMAIN} v{VERSION}, is using ramses_rf v{ramses_rf.VERSION}")

    _LOGGER.debug("\r\n\nConfig =  %s\r\n", hass_config[DOMAIN])

    store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
    evohome_store = await EvoBroker.async_load_store(store)
    _LOGGER.debug("\r\n\nStore = %s\r\n", evohome_store)

    serial_port, kwargs = normalise_config_schema(hass_config[DOMAIN])
    client = ramses_rf.Gateway(serial_port, loop=hass.loop, **kwargs)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][BROKER] = broker = EvoBroker(hass, client, store, hass_config)

    if hass_config[DOMAIN].get(CONF_RESTORE_STATE):
        _LOGGER.debug("Restoring client state...")
        await broker.async_load_client_state()
        await broker.async_update()
    else:
        _LOGGER.info("The restore client state feature has not been enabled.")
        hass.helpers.event.async_call_later(10, broker.async_update)
        hass.helpers.event.async_call_later(30, broker.async_update)

    broker.loop_task = hass.loop.create_task(async_handle_exceptions(client.start()))

    hass.helpers.event.async_track_time_interval(
        broker.async_update, hass_config[DOMAIN][CONF_SCAN_INTERVAL]
    )

    hass.helpers.event.async_track_time_interval(
        broker.async_save_client_state, SAVE_STATE_INTERVAL
    )

    register_service_functions(hass, broker)

    return True


@callback  # TODO: add async_ to routines where required to do so
def register_service_functions(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @verify_domain_control(hass, DOMAIN)
    async def svc_fake_device(call) -> None:
        try:
            broker.client.fake_device(**call.data)
        except LookupError as exc:
            _LOGGER.error("%s", exc)
            return
        await asyncio.sleep(1)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_force_refresh(call) -> None:
        await broker.async_update()
        # includes: async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_reset_system_mode(call) -> None:
        payload = {
            UNIQUE_ID: broker.client.evo.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_set_system_mode(call) -> None:
        payload = {
            UNIQUE_ID: broker.client.evo.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_send_packet(call) -> None:
        broker.client.send_cmd(broker.client.make_cmd(**call.data))
        await asyncio.sleep(1)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_call_dhw_svc(call) -> None:
        payload = {
            UNIQUE_ID: f"{broker.client.evo.id}_HW",
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    [
        hass.services.async_register(DOMAIN, k, svc_call_dhw_svc, schema=v)
        for k, v in WATER_HEATER_SERVICES.items()
    ]

    domain_service = DOMAIN_SERVICES
    if not broker.config[DOMAIN].get(SVC_SEND_PACKET):
        del domain_service[SVC_SEND_PACKET]

    services = {k: v for k, v in locals().items() if k.startswith("svc")}
    [
        hass.services.async_register(DOMAIN, k, services[f"svc_{k}"], schema=v)
        for k, v in DOMAIN_SERVICES.items()
        if f"svc_{k}" in services
    ]


class EvoBroker:
    """Container for client and data."""

    def __init__(self, hass, client, store, hass_config) -> None:
        """Initialize the client and its data structure(s)."""
        self.hass = hass
        self.client = client
        self._store = store
        self.config = hass_config

        self.status = None

        self.binary_sensors = []
        self.climates = []
        self.water_heater = None
        self.sensors = []
        self.services = {}

        self.loop_task = None
        self._last_update = dt.min

        self._hgi = None
        self._devices = []
        self._domains = []
        self._lock = Lock()

    @staticmethod
    async def async_load_store(store) -> Optional[Dict]:
        app_storage = await store.async_load()
        return dict(app_storage or {})

    async def async_load_client_state(self) -> None:
        """Restore the client state from the app store."""
        app_storage = await self.async_load_store(self._store)
        if app_storage.get("client_state"):
            await self.client._set_state(**app_storage["client_state"])

    async def async_save_client_state(self, *args, **kwargs) -> None:
        """Save the client state to the app store"""
        (schema, packets) = self.client._get_state()
        await self._store.async_save(
            {"client_state": {"schema": schema, "packets": packets}}
        )

    @callback
    def new_domains(self) -> bool:
        evohome = self.client.evo
        if evohome is None:
            _LOGGER.info("Schema = %s", {})
            return False

        save_updated_schema = False
        new_domains = [z for z in evohome.zones if z not in self.climates]
        if new_domains:
            self.hass.async_create_task(
                async_load_platform(self.hass, CLIMATE, DOMAIN, {}, self.config)
            )
            # new_domains = {"new_domains": new_domains + [self.client.evo]}
            # self.hass.async_create_task(
            #     async_load_platform(self.hass, SENSOR, DOMAIN, new_domains, self.config)
            # )
            save_updated_schema = True

        if evohome.dhw and self.water_heater is None:
            self.hass.async_create_task(
                async_load_platform(self.hass, WATER_HEATER, DOMAIN, {}, self.config)
            )
            save_updated_schema = True

        _LOGGER.info("Schema = %s", evohome.schema)
        _LOGGER.info("Params = %s", evohome.params)
        _LOGGER.info(
            "Status = %s", {k: v for k, v in evohome.status.items() if k != "devices"}
        )
        return save_updated_schema

    @callback
    def new_devices(self) -> bool:

        discovery_info = {}

        if self._hgi is None and self.client.hgi:
            discovery_info["gateway"] = self._hgi = self.client.hgi

        if new_devices := [
            d
            for d in self.client.devices
            if d not in self._devices
            and (
                self.client.config.enforce_known_list
                and d.id in self.client._include
                or d.id not in self.client._exclude
            )
        ]:
            discovery_info["devices"] = new_devices
            self._devices.extend(new_devices)

        new_domains = []
        if self.client.evo:
            new_domains = [d for d in self.client.evo.zones if d not in self._domains]
            if self.client.evo not in self._domains:
                new_domains.append(self.client.evo)

        if new_domains:
            discovery_info["domains"] = new_domains
            self._domains.extend(new_domains)

        if discovery_info:
            for platform in (BINARY_SENSOR, SENSOR):
                self.hass.async_create_task(
                    async_load_platform(
                        self.hass, platform, DOMAIN, discovery_info, self.config
                    )
                )

        _LOGGER.info("Devices = %s", [d.id for d in self._devices])
        return bool(new_devices or new_domains)

    async def async_update(self, *args, **kwargs) -> None:
        """Retrieve the latest state data from the client library."""

        self._lock.acquire()  # HACK: workaround bug

        dt_now = dt.now()
        if self._last_update < dt_now - td(seconds=10):
            self._last_update = dt_now

            new_domains = self.new_domains()
            new_devices = self.new_devices()

            if new_domains or new_devices:
                self.hass.helpers.event.async_call_later(
                    5, self.async_save_client_state
                )

        self._lock.release()

        # inform the evohome devices that their state data may have changed
        async_dispatcher_send(self.hass, DOMAIN)


class EvoEntity(Entity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, broker, device) -> None:
        """Initialize the entity."""
        self.hass = broker.hass
        self._broker = broker
        self._device = device

        self._unique_id = self._name = None
        self._entity_state_attrs = ()

        self.update_ha_state(delay=5)  # give time to collect entire state

    @callback
    def async_handle_dispatch(self, *args) -> None:  # TODO: remove as unneeded?
        """Process a dispatched message.

        Data validation is not required, it will have been done upstream.
        This routine is threadsafe.
        """
        if not args:
            self.update_ha_state()

    @callback
    def update_ha_state(self, delay=1) -> None:
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
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = {
            a: getattr(self._device, a)
            for a in self._entity_state_attrs
            if hasattr(self._device, a)
        }
        attrs["controller_id"] = self._device._ctl.id if self._device._ctl else None
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        async_dispatcher_connect(self.hass, DOMAIN, self.async_handle_dispatch)


class EvoDeviceBase(EvoEntity):
    """Base for any evohome II-compatible entity (e.g. BinarySensor, Sensor)."""

    def __init__(self, broker, device, state_attr, device_class) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._name = f"{device.id} ({state_attr})"
        # if device.zone:  # not all have this attr
        #     self._name = f"{device.zone.name} ({klass})"
        self._device_class = device_class
        self._state_attr = state_attr

    @property
    def available(self) -> bool:
        """Return True if the sensor is available."""
        return getattr(self._device, self._state_attr) is not None

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes
        attrs["device_id"] = self._device.id
        if hasattr(self._device, "_domain_id"):
            attrs["domain_id"] = self._device._domain_id
        if hasattr(self._device, "role"):
            attrs["role"] = self._device.role
        try:
            attrs["domain_name"] = self._device.zone.name
        except AttributeError:
            pass
        return attrs

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name
        # klass = self.DEVICE_CLASS if self.DEVICE_CLASS else self.STATE_ATTR
        # self._name = f"{self._device.id} ({klass})"
        # if getattr(self._device, "zone", None):
        #     return f"{self._device.zone.name} ({klass})"
        # else:
        # return f"{self._device.id} ({klass})"


class EvoZoneBase(EvoEntity):
    """Base for any evohome RF-compatible entity (e.g. Controller, DHW, Zones)."""

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._hvac_modes = None
        self._preset_modes = None
        self._supported_features = None

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._device.temperature

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._device.name

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
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            "zone_idx": self._device.idx,
            "config": self._device.config,
            "heat_demand": self._device.heat_demand,
            "mode": self._device.mode,
        }
