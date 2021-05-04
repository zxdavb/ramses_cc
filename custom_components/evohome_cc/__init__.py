#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

import logging
from datetime import timedelta as td
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
    BINARY_SENSOR_ATTRS,
    BROKER,
    DATA,
    DOMAIN,
    SENSOR_ATTRS,
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
    normalise_config_schema,
)
from .version import __version__ as VERSION

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [BINARY_SENSOR, CLIMATE, SENSOR, WATER_HEATER]
SAVE_STATE_INTERVAL = td(seconds=300)  # TODO: 5 minutes


async def _load_store(store) -> Optional[Dict]:
    # return store.async_save(app_storage)  # HOWTO: save store
    app_storage = await store.async_load()
    return dict(app_storage or {})


async def async_setup(hass: HomeAssistantType, hass_config: ConfigType) -> bool:
    """Create a Honeywell RF (RAMSES_II)-based system."""

    async def handle_exceptions(awaitable):
        try:
            return await awaitable
        except serial.SerialException as exc:
            _LOGGER.error("Unable to open the serial port. Message is: %s", exc)
            raise exc

    if VERSION == ramses_rf.VERSION:
        _LOGGER.warning(
            "evohome_cc v%s, using ramses_rf v%s - versions match (this is good)",
            VERSION,
            ramses_rf.VERSION,
        )
    else:
        _LOGGER.error(
            "evohome_cc v%s, using ramses_rf v%s - versions don't match (this is bad)",
            VERSION,
            ramses_rf.VERSION,
        )

    _LOGGER.debug("\r\n\nConfig =  %s\r\n", hass_config[DOMAIN])

    store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
    evohome_store = await _load_store(store)
    _LOGGER.debug("\r\n\nStore = %s\r\n", evohome_store)

    serial_port, kwargs = normalise_config_schema(dict(hass_config[DOMAIN]))
    client = ramses_rf.Gateway(serial_port, loop=hass.loop, **kwargs)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][BROKER] = broker = EvoBroker(
        hass, client, store, hass_config[DOMAIN]
    )

    broker.hass_config = hass_config  # TODO: don't think this is needed
    broker.loop_task = hass.loop.create_task(handle_exceptions(client.start()))

    if hass_config[DOMAIN][CONF_RESTORE_STATE]:
        _LOGGER.debug("Restoring client state...")
        await broker.async_restore_client_state()
        await broker.async_update()
    else:
        _LOGGER.warning("The restore client state feature has been disabled.")
        hass.helpers.event.async_call_later(10, broker.async_update)
        hass.helpers.event.async_call_later(30, broker.async_update)

    hass.helpers.event.async_track_time_interval(
        broker.async_update, hass_config[DOMAIN][CONF_SCAN_INTERVAL]
    )

    hass.helpers.event.async_track_time_interval(
        broker.async_save_client_state, SAVE_STATE_INTERVAL
    )

    setup_service_functions(hass, broker)

    return True


@callback
def setup_service_functions(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @verify_domain_control(hass, DOMAIN)
    async def svc_create_sensor(call) -> None:
        broker.client._bind_fake_sensor()

    @verify_domain_control(hass, DOMAIN)
    async def svc_force_refresh(call) -> None:
        await broker.async_update()  #: includes async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_reset_system_mode(call) -> None:
        payload = {
            UNIQUE_ID: broker.client.evo.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_set_system_mode(call) -> None:
        payload = {
            UNIQUE_ID: broker.client.evo.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_send_packet(call) -> None:
        broker.client.send_cmd(broker.client.make_cmd(**call.data))
        async_dispatcher_send(hass, DOMAIN)

    domain_service = DOMAIN_SERVICES
    if not broker.hass_config[DOMAIN].get(SVC_SEND_PACKET):
        del domain_service[SVC_SEND_PACKET]

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

        self.config = None
        self.params = params
        self.status = None

        self.binary_sensors = []
        self.climates = []
        self.water_heater = None
        self.sensors = []
        self.services = {}

        self.hass_config = None
        self.loop_task = None

    async def async_restore_client_state(self) -> None:
        """Save..."""
        app_storage = await _load_store(self._store)

        if app_storage.get("client_state"):
            await self.client._set_state(**app_storage["client_state"])

    async def async_save_client_state(self, *args, **kwargs) -> None:
        """Save..."""
        (schema, packets) = self.client._get_state()

        await self._store.async_save(
            {"client_state": {"schema": schema, "packets": packets}}
        )

    async def async_update(self, *args, **kwargs) -> None:
        """Retrieve the latest state data..."""

        _LOGGER.info("Devices = %s", {d.id: d.status for d in self.client.devices})

        evohome = self.client.evo
        if evohome is None:
            return

        _LOGGER.info("Schema = %s", evohome.schema)
        _LOGGER.info("Params = %s", evohome.params)
        _LOGGER.info(
            "Status = %s", {k: v for k, v in evohome.status.items() if k != "devices"}
        )

        save_updated_schema = False
        if [z for z in evohome.zones if z not in self.climates]:
            self.hass.async_create_task(
                async_load_platform(self.hass, CLIMATE, DOMAIN, {}, self.hass_config)
            )
            save_updated_schema = True

        if evohome.dhw and self.water_heater is None:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, WATER_HEATER, DOMAIN, {}, self.hass_config
                )
            )
            save_updated_schema = True

        if self.find_new_sensors():
            self.hass.async_create_task(
                async_load_platform(self.hass, SENSOR, DOMAIN, {}, self.hass_config)
            )
            save_updated_schema = True

        if self.find_new_binary_sensors():
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, BINARY_SENSOR, DOMAIN, {}, self.hass_config
                )
            )
            save_updated_schema = True

        if save_updated_schema:
            self.hass.helpers.event.async_call_later(5, self.async_save_client_state)

        # inform the evohome devices that their state data may have changed
        async_dispatcher_send(self.hass, DOMAIN)

    def find_new_binary_sensors(self) -> list:
        """Produce a list of any unknown binary sensors."""
        sensors = [
            s
            for s in self.client.devices + [self.client.evo]
            if any(hasattr(s, a) for a in BINARY_SENSOR_ATTRS)
        ]
        return [s for s in sensors if s not in self.binary_sensors]

    def find_new_sensors(self) -> list:
        """Produce a list of any unknown sensors."""
        # if self.client.evo.heat_demands or self.client.evo.relay_demands:
        #     x = 0
        sensors = [
            s
            for s in self.client.devices + [self.client.evo]
            if any(hasattr(s, a) for a in SENSOR_ATTRS)
        ]
        return [s for s in sensors if s not in self.sensors]


class EvoEntity(Entity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, broker, device) -> None:
        """Initialize the entity."""
        self.hass = broker.hass
        self._broker = broker
        self._device = device

        self._unique_id = self._name = None
        self._entity_state_attrs = ()

        self._req_ha_state_update(delay=5)  # give time to collect entire state

    @callback
    def _handle_dispatch(self, *args) -> None:  # TODO: remove as unneeded?
        """Process a dispatched message.

        Data validation is not required, it will have been done upstream.
        """
        if not args:
            self.async_schedule_update_ha_state()

    def _req_ha_state_update(self, delay=1) -> None:
        """Update HA state after a short delay to allow system to quiesce."""
        self.hass.helpers.event.async_call_later(
            delay, self.async_schedule_update_ha_state
        )

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
        async_dispatcher_connect(self.hass, DOMAIN, self._handle_dispatch)


class EvoDeviceBase(EvoEntity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    DEVICE_CLASS = None
    STATE_ATTR = "enabled"

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        klass = self.DEVICE_CLASS or self.STATE_ATTR
        self._name = f"{device.id} ({klass})"
        # if device.zone:  # not all have this attr
        #     self._name = f"{device.zone.name} ({klass})"

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
        attrs["device_id"] = self._device.id
        attrs["domain_id"] = self._device._domain_id
        if hasattr(self._device, "zone"):
            attrs["zone"] = self._device.zone.name if self._device.zone else None
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
    """Base for any evohome RF-compatible entity (e.g. Climate, Sensor)."""

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
