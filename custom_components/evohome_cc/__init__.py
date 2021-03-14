#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

import logging
from typing import Any, Dict, Optional

import evohome_rf
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
    BINARY_SENSOR_ATTRS,
    BROKER,
    DOMAIN,
    SENSOR_ATTRS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .schema import CONFIG_SCHEMA  # noqa: F401
from .schema import CONF_ALLOW_LIST, CONF_BLOCK_LIST, CONF_SERIAL_PORT, DOMAIN_SERVICES
from .version import __version__ as VERSION

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [BINARY_SENSOR, CLIMATE, SENSOR, WATER_HEATER]


def new_binary_sensors(broker) -> list:
    sensors = [
        s
        for s in broker.client.devices + [broker.client.evo]
        if any([hasattr(s, a) for a in BINARY_SENSOR_ATTRS])
    ]
    return [s for s in sensors if s not in broker.binary_sensors]


def new_sensors(broker) -> list:
    sensors = [
        s
        for s in broker.client.devices + [broker.client.evo]
        if any([hasattr(s, a) for a in SENSOR_ATTRS])
    ]
    return [s for s in sensors if s not in broker.sensors]


async def async_setup(hass: HomeAssistantType, hass_config: ConfigType) -> bool:
    """Create a Honeywell RF (RAMSES_II)-based system."""

    async def handle_exceptions(awaitable):
        try:
            return await awaitable
        except serial.SerialException as exc:
            _LOGGER.error("Unable to open the serial port. Message is: %s", exc)
            raise exc

    async def load_system_config(store) -> Optional[Dict]:
        app_storage = await store.async_load()
        return dict(app_storage if app_storage else {})

    if VERSION == evohome_rf.VERSION:
        _LOGGER.warning(
            "evohome_cc v%s, using evohome_rf v%s - versions match (this is good)",
            VERSION,
            evohome_rf.VERSION,
        )
    else:
        _LOGGER.error(
            "evohome_cc v%s, using evohome_rf v%s - versions don't match (this is bad)",
            VERSION,
            evohome_rf.VERSION,
        )

    store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
    evohome_store = await load_system_config(store)

    _LOGGER.debug("Store = %s, Config =  %s", evohome_store, hass_config[DOMAIN])

    kwargs = dict(hass_config[DOMAIN])
    serial_port = kwargs.pop(CONF_SERIAL_PORT)
    kwargs["allowlist"] = dict.fromkeys(kwargs.pop(CONF_ALLOW_LIST, []), {})
    kwargs["blocklist"] = dict.fromkeys(kwargs.pop(CONF_BLOCK_LIST, []), {})
    kwargs["config"]["log_rotate_backups"] = kwargs["config"].pop(
        "log_rotate_backups", 7
    )

    client = evohome_rf.Gateway(serial_port, loop=hass.loop, **kwargs)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][BROKER] = broker = EvoBroker(
        hass, client, store, hass_config[DOMAIN]
    )

    broker.hass_config = hass_config

    broker.loop_task = hass.loop.create_task(handle_exceptions(client.start()))

    hass.helpers.event.async_track_time_interval(
        broker.async_update, hass_config[DOMAIN][CONF_SCAN_INTERVAL]
    )

    setup_service_functions(hass, broker)

    return True


@callback
def setup_service_functions(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @verify_domain_control(hass, DOMAIN)
    async def svc_force_refresh(call) -> None:
        """Obtain the latest state data via the vendor's RESTful API."""
        await broker.async_update()

    @verify_domain_control(hass, DOMAIN)
    async def svc_reset_system(call) -> None:
        """Set the system mode."""
        payload = {
            "unique_id": broker.client.evo.id,
            "service": call.service,
            "data": call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_set_system_mode(call) -> None:
        """Set the system mode."""
        payload = {
            "unique_id": broker.client.evo.id,
            "service": call.service,
            "data": call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    services = {k: v for k, v in locals().items() if k.startswith("svc")}
    [
        hass.services.async_register(DOMAIN, k, services[f"svc_{k}"], schema=v)
        for k, v in DOMAIN_SERVICES.items()
        if f"svc_{k}" in services
    ]


class EvoBroker:
    """Container for client and data."""

    def __init__(self, hass, client, store, params) -> None:
        """Initialize the client and its data structure(s)."""
        self.hass = hass
        self.client = client
        self._store = store
        self.params = params

        self.config = None
        self.status = None

        self.binary_sensors = []
        self.climates = []
        self.water_heater = None
        self.sensors = []
        self.services = {}

        self.hass_config = None
        self.loop_task = None

    async def save_system_config(self) -> None:
        """Save..."""
        app_storage = {}

        await self._store.async_save(app_storage)

    async def async_update(self, *args, **kwargs) -> None:
        """Retrieve the latest state data..."""

        #     self.hass.async_create_task(self._update(self.hass, *args, **kwargs))

        # async def _update(self, *args, **kwargs) -> None:
        #     """Retrieve the latest state data..."""

        evohome = self.client.evo
        _LOGGER.info("Schema = %s", evohome.schema if evohome is not None else None)
        _LOGGER.info(
            "Devices = %s", {d.id: d.status for d in sorted(self.client.devices)}
        )
        if evohome is None:
            return

        if [z for z in evohome.zones if z not in self.climates]:
            self.hass.async_create_task(
                async_load_platform(self.hass, "climate", DOMAIN, {}, self.hass_config)
            )

        if evohome.dhw and self.water_heater is None:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, "water_heater", DOMAIN, {}, self.hass_config
                )
            )

        if new_sensors(self):
            self.hass.async_create_task(
                async_load_platform(self.hass, "sensor", DOMAIN, {}, self.hass_config)
            )

        if new_binary_sensors(self):
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, "binary_sensor", DOMAIN, {}, self.hass_config
                )
            )

        _LOGGER.info("Params = %s", evohome.params if evohome is not None else None)
        _LOGGER.info(
            "Status = %s", {k: v for k, v in evohome.status.items() if k != "devices"}
        )

        # inform the evohome devices that state data has been updated
        self.hass.helpers.dispatcher.async_dispatcher_send(DOMAIN)


class EvoEntity(Entity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, broker, device) -> None:
        """Initialize the entity."""
        self._device = device
        self._broker = broker

        self._unique_id = self._name = None
        self._entity_state_attrs = ()

    @callback
    def _handle_dispatch(self, *args) -> None:
        """Process a dispatched message."""
        if not args:
            self.async_schedule_update_ha_state(force_refresh=True)

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
        attrs["controller"] = self._device._ctl.id if self._device._ctl else None
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        async_dispatcher_connect(self.hass, DOMAIN, self._handle_dispatch)


class EvoDeviceBase(EvoEntity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    DEVICE_CLASS = None
    STATE_ATTR = "enabled"

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        klass = self.DEVICE_CLASS if self.DEVICE_CLASS else self.STATE_ATTR
        self._name = f"{device.id} ({klass})"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return getattr(self._device, self.STATE_ATTR) is not None

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self.DEVICE_CLASS

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes
        attrs["domain_id"] = self._device._domain_id
        return attrs

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name


class EvoZoneBase(EvoEntity):
    """Base for any evohome RF-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)
        self._supported_features = None

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._device.temperature

    @property
    def name(self) -> str:
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
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().device_state_attributes
        attrs["zone_idx"] = self._device.idx
        return attrs
