#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

import serial
import voluptuous as vol

try:
    from . import evohome_rf
except (ImportError, ModuleNotFoundError):
    import evohome_rf

from evohome_rf.const import (
    SYSTEM_MODE_MAP,
    SYSTEM_MODE_LOOKUP 
)

import homeassistant.helpers.config_validation as cv
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR
from homeassistant.components.climate import DOMAIN as CLIMATE
from homeassistant.components.sensor import DOMAIN as SENSOR
from homeassistant.components.water_heater import DOMAIN as WATER_HEATER
from homeassistant.const import CONF_SCAN_INTERVAL, TEMP_CELSIUS, ATTR_ENTITY_ID
from homeassistant.core import callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    BINARY_SENSOR_ATTRS,
    BROKER,
    DOMAIN,
    SENSOR_ATTRS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .version import __version__ as VERSION

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [BINARY_SENSOR, CLIMATE, SENSOR, WATER_HEATER]

SCAN_INTERVAL_DEFAULT = timedelta(seconds=300)
SCAN_INTERVAL_MINIMUM = timedelta(seconds=10)

ATTR_SYSTEM_MODE = "mode"
ATTR_DURATION_DAYS = "period"
ATTR_DURATION_HOURS = "duration"

ATTR_ZONE_TEMP = "setpoint"
ATTR_DURATION_UNTIL = "duration"

SVC_REFRESH_SYSTEM = "refresh_system"
SVC_SET_SYSTEM_MODE = "set_system_mode"
SVC_RESET_SYSTEM = "reset_system"
SVC_SET_ZONE_OVERRIDE = "set_zone_override"
SVC_RESET_ZONE_OVERRIDE = "clear_zone_override"

from .const import EVO_AWAY, EVO_CUSTOM, EVO_ECO, EVO_DAYOFF, EVO_RESET, EVO_AUTO, EVO_HEATOFF

RESET_ZONE_OVERRIDE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})
SET_ZONE_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_ZONE_TEMP): vol.All(
            vol.Coerce(float), vol.Range(min=5.0, max=35.0)
        ),
        vol.Optional(ATTR_DURATION_UNTIL): vol.All(
            cv.time_period, vol.Range(min=timedelta(days=0), max=timedelta(days=1))
        ),
    }
)
CONF_SERIAL_PORT = "serial_port"
CONF_CONFIG = "config"
CONF_SCHEMA = "schema"
CONF_GATEWAY_ID = "gateway_id"
CONF_PACKET_LOG = "packet_log"
CONF_MAX_ZONES = "max_zones"

CONF_ALLOW_LIST = "allow_list"
CONF_BLOCK_LIST = "block_list"
LIST_MSG = f"{CONF_ALLOW_LIST} and {CONF_BLOCK_LIST} are mutally exclusive"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                # vol.Optional(CONF_GATEWAY_ID): vol.Match(r"^18:[0-9]{6}$"),
                vol.Required(CONF_SERIAL_PORT): cv.string,
                vol.Optional("serial_config"): dict,
                vol.Required(CONF_CONFIG): vol.Schema(
                    {
                        vol.Optional(CONF_MAX_ZONES, default=12): vol.Any(None, int),
                        vol.Optional(CONF_PACKET_LOG): cv.string,
                        vol.Optional("enforce_allowlist"): bool,
                    }
                ),
                vol.Optional(CONF_SCHEMA): dict,
                vol.Exclusive(CONF_ALLOW_LIST, "device_filter", msg=LIST_MSG): list,
                vol.Exclusive(CONF_BLOCK_LIST, "device_filter", msg=LIST_MSG): list,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
            },
            extra=vol.ALLOW_EXTRA,  # TODO: remove for production
        )
    },
    extra=vol.ALLOW_EXTRA,
)


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
    """xxx."""

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
    kwargs["config"]["log_rotate_backups"] = (
        kwargs["config"].pop("log_rotate_backups", 7)
    )

    client = evohome_rf.Gateway(serial_port, loop=hass.loop, **kwargs)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][BROKER] = broker = EvoBroker(
        hass, client, store, hass_config[DOMAIN]
    )

    broker.hass_config = hass_config

    broker.loop_task = hass.loop.create_task(handle_exceptions(client.start()))

    hass.helpers.event.async_track_time_interval(
        broker.update, hass_config[DOMAIN][CONF_SCAN_INTERVAL]
    )

    setup_service_functions(hass, broker)

    return True

@callback
def setup_service_functions(hass: HomeAssistantType, broker):
    @verify_domain_control(hass, DOMAIN)
    async def force_refresh(call) -> None:
        """Obtain the latest state data via the vendor's RESTful API."""
        await broker.update()

    @verify_domain_control(hass, DOMAIN)
    async def set_system_mode(call) -> None:
        """Set the system mode."""
        payload = {
            "unique_id": broker.client.evo.unique_id,
            "service": call.service,
            "data": call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def set_zone_override(call) -> None:
        """Set the zone override (setpoint)."""

        entity_id = call.data[ATTR_ENTITY_ID]

        registry = await hass.helpers.entity_registry.async_get_registry()
        registry_entry = registry.async_get(entity_id)

        if registry_entry is None or registry_entry.platform != DOMAIN:
            raise ValueError(f"'{entity_id}' is not a known {DOMAIN} entity")

        if registry_entry.domain != "climate":
            raise ValueError(f"'{entity_id}' is not an {DOMAIN} controller/zone")

        payload = {
            "unique_id": registry_entry.unique_id,
            "service": call.service,
            "data": call.data,
        }

        async_dispatcher_send(hass, DOMAIN, payload)

    hass.services.async_register(DOMAIN, SVC_REFRESH_SYSTEM, force_refresh)

    system_mode_schemas = []

    # Not all systems support "AutoWithReset": register this handler only if required
    if [m for m in SYSTEM_MODE_LOOKUP if m == EVO_RESET]:
        hass.services.async_register(DOMAIN, SVC_RESET_SYSTEM, set_system_mode)

    # These modes are set for a number of hours (or indefinitely): use this schema
    temp_modes = [m for m in SYSTEM_MODE_LOOKUP if m == EVO_ECO]
    if temp_modes:  # any of: "AutoWithEco", permanent or for 0-24 hours
        schema = vol.Schema(
            {
                vol.Required(ATTR_SYSTEM_MODE): vol.In(temp_modes),
                vol.Optional(ATTR_DURATION_HOURS): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(hours=0), max=timedelta(hours=24)),
                ),
            }
        )
        system_mode_schemas.append(schema)

    # These modes are set for a number of days (or indefinitely): use this schema
    temp_modes = [m for m in SYSTEM_MODE_LOOKUP if m == EVO_AWAY or m == EVO_CUSTOM or m == EVO_DAYOFF]
    if temp_modes:  # any of: EVO_AWAY, EVO_CUSTOM, EVO_DAYOFF, permanent or for 1-99 days
        schema = vol.Schema(
            {
                vol.Required(ATTR_SYSTEM_MODE): vol.In(temp_modes),
                vol.Optional(ATTR_DURATION_DAYS): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(days=1), max=timedelta(days=99)),
                ),
            }
        )
        system_mode_schemas.append(schema)

    if system_mode_schemas:
        hass.services.async_register(
            DOMAIN,
            SVC_SET_SYSTEM_MODE,
            set_system_mode,
            schema=vol.Any(*system_mode_schemas),
        )

    # The zone modes are consistent across all systems and use the same schema
    hass.services.async_register(
        DOMAIN,
        SVC_RESET_ZONE_OVERRIDE,
        set_zone_override,
        schema=RESET_ZONE_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SVC_SET_ZONE_OVERRIDE,
        set_zone_override,
        schema=SET_ZONE_OVERRIDE_SCHEMA,
    )


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

        self.hass_config = None
        self.loop_task = None

    async def save_system_config(self) -> None:
        """Save..."""
        app_storage = {}

        await self._store.async_save(app_storage)

    async def update(self, *args, **kwargs) -> None:
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

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the entity."""
        self._evo_device = evo_device
        self._evo_broker = evo_broker

        self._unique_id = self._name = None
        self._device_state_attrs = {}

    @callback
    def _refresh(self, payload: Optional[dict] = None) -> None:
        if payload is None:
            self.async_schedule_update_ha_state(force_refresh=True)
            return
        if payload["unique_id"] != self._unique_id:
            return
        if payload["service"] in [SVC_SET_ZONE_OVERRIDE, SVC_RESET_ZONE_OVERRIDE]:
            self.zone_svc_request(payload["service"], payload["data"])
            return
        self.controller_svc_request(payload["service"], payload["data"])

    def controller_svc_request(self, service: dict, data: dict) -> None:
        """Process a service request (system mode) for a controller."""
        raise NotImplementedError

    def zone_svc_request(self, service: dict, data: dict) -> None:
        """Process a service request (setpoint override) for a zone."""
        raise NotImplementedError

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
        # result = {}
        # for attr in ("schema", "config", "status"):
        #     if hasattr(self._evo_device, attr):
        #         result.update({attr: getattr(self._evo_device, attr)})
        return {
            "controller": self._evo_device._ctl.id if self._evo_device._ctl else None
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(DOMAIN, self._refresh)


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
        return getattr(self._evo_device, self.STATE_ATTR) is not None

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self.DEVICE_CLASS

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            # "domain_id": self._evo_device.self._domain_id,
            # "zone_name": self._evo_device.zone.name if self._evo_device.zone else None,
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name


class EvoZoneBase(EvoEntity):
    """Base for any evohome RF-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the sensor."""
        super().__init__(evo_broker, evo_device)
        self._supported_features = None

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._evo_device.temperature

    @property
    def name(self) -> str:
        return self._evo_device.name

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
        return {
            **super().device_state_attributes,
            # "zone_idx": self._evo_device.idx,
            # "zone_name": self._evo_device.zone.name if self._evo_device.zone else None,
        }
