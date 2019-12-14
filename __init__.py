"""Support for Honeywell's evohome II RF protocol.

Requires a Honeywell HGI80 (or compatible) gateway.
"""
from datetime import timedelta
import logging
from typing import Any, Dict, Optional, Tuple

import serial
import evohome
import voluptuous as vol

from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({
        vol.Required("serial_port"): cv.string,
        vol.Required("packet_log"): cv.string

    })}, extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistantType, hass_config: ConfigType) -> bool:
    """xxx."""

    async def load_system_config(store) -> Optional[Dict]:
        app_storage = await store.async_load()
        return dict(app_storage if app_storage else {})

    store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
    evohome_store = await load_system_config(store)

    _LOGGER.warning("Store = %s", evohome_store)
    _LOGGER.warning("Config =  %s", hass_config[DOMAIN])

    # import ptvsd  # pylint: disable=import-error

    _LOGGER.setLevel(logging.DEBUG)
    # _LOGGER.warning("Waiting for debugger to attach...")
    # ptvsd.enable_attach(address=("172.27.0.138", 5679))

    # ptvsd.wait_for_attach()
    # _LOGGER.debug("Debugger is attached!")

    try:  # TODO: test invalid serial_port="AA"
        client = evohome.Gateway(
            serial_port=hass_config[DOMAIN]["serial_port"],
            output_file=hass_config[DOMAIN]["packet_log"],
            loop=hass.loop
        )
    except serial.SerialException as exc:
        _LOGGER.exception("Unable to open serial port. Message is: %s", exc)
        return False

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["broker"] = broker = EvoBroker(
        hass, client, store, hass_config[DOMAIN]
    )

    broker.hass_config = hass_config

    # broker.loop_task = hass.async_create_task(client.start())
    broker.loop_task = hass.loop.create_task(client.start())

    hass.helpers.event.async_track_time_interval(broker.update, SCAN_INTERVAL)

    return True


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
        self.sensors = []

        self.hass_config = None
        self.loop_task = None

    async def save_system_config(self) -> None:
        """Save..."""
        app_storage = {}

        await self._store.async_save(app_storage)

    async def discover(self, *args, **kwargs) -> None:
        """Enumerate the Controller, all Zones, and the DHW relay (if any)."""

        try:
            self.config = await self.client.discover()
        except serial.SerialException as exc:
            _LOGGER.exception("message = %s", exc)
            return

        _LOGGER.debug("Config = %s", self.config)

    async def update(self, *args, **kwargs) -> None:
        """Retreive the latest state data..."""

        #     self.hass.async_create_task(self._update(self.hass, *args, **kwargs))

        # async def _update(self, *args, **kwargs) -> None:
        #     """Retreive the latest state data..."""

        _zones = [x for x in self.client.zones if x not in self.climates]
        if [z for z in _zones if z.zone_type == "Radiator Valve" and z.name]:
            self.hass.async_create_task(
                async_load_platform(self.hass, "climate", DOMAIN, {}, self.hass_config)
            )

        _domains = [x for x in self.client.domains if x not in self.sensors]
        _devices = [x for x in self.client.devices if x not in self.sensors]
        if [d for d in _domains if d.domain_id not in ["system"]] or [
            d for d in _devices if d.device_type in ["STA", "TRV"]
        ]:
            self.hass.async_create_task(
                async_load_platform(self.hass, "sensor", DOMAIN, {}, self.hass_config)
            )

        _devices = [x for x in self.client.devices if x not in self.binary_sensors]
        if [d for d in _devices if d.device_type == "TRV"]:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, "binary_sensor", DOMAIN, {}, self.hass_config
                )
            )

        # inform the evohome devices that state data has been updated
        self.hass.helpers.dispatcher.async_dispatcher_send(DOMAIN)

        _LOGGER.debug("Status = %s", None)


class EvoEntity(Entity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the entity."""
        self._evo_device = evo_device
        self._evo_broker = evo_broker

        self._unique_id = self._name = None
        self._device_state_attrs = {}

    @callback
    def _refresh(self) -> None:
        self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def should_poll(self) -> bool:
        """Entities should not be polled."""
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return None  # self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {"state": self._device_state_attrs}

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(DOMAIN, self._refresh)
