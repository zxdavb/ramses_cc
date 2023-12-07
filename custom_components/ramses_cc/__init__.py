"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime as dt, timedelta
import logging
from threading import Semaphore
from typing import Any

from ramses_rf import Gateway
from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_rf.helpers import merge
from ramses_rf.schemas import (
    SZ_CONFIG,
    SZ_RESTORE_CACHE,
    SZ_RESTORE_SCHEMA,
    SZ_RESTORE_STATE,
    SZ_SCHEMA,
)
from ramses_rf.system.heat import MultiZone
from ramses_tx.exceptions import TransportSerialError
from ramses_tx.schemas import SZ_PACKET_LOG, SZ_PORT_CONFIG
import voluptuous as vol

from homeassistant.const import ATTR_ID, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CODE,
    ATTR_CREATE_DEVICE,
    ATTR_DEVICE_ID,
    ATTR_PAYLOAD,
    ATTR_START_BINDING,
    ATTR_VERB,
    CONF_ADVANCED_FEATURES,
    CONF_MESSAGE_EVENTS,
    CONTROLLER,
    DOMAIN,
    SERVICE_FAKE_DEVICE,
    SERVICE_FORCE_UPDATE,
    SERVICE_SEND_PACKET,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .schemas import (
    SCH_DOMAIN_CONFIG,
    merge_schemas,
    normalise_config,
    schema_is_minimal,
)


@dataclass(kw_only=True)
class RamsesEntityDescription(EntityDescription):
    """Class describing Ramses entities."""

    has_entity_name: bool = True
    extra_attributes: list[str] = field(default_factory=list)


_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema({DOMAIN: SCH_DOMAIN_CONFIG}, extra=vol.ALLOW_EXTRA)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.REMOTE,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Create a ramses_rf (RAMSES_II)-based system."""

    hass.data.setdefault(DOMAIN, {})
    controller = hass.data[DOMAIN][CONTROLLER] = RamsesController(hass, config)

    for platform in PLATFORMS:
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))

    hass.async_create_task(controller.start())

    return True


class RamsesController:
    """Controller for client and data."""

    _hass: HomeAssistant
    _config: dict

    _port_name: str
    _client_config: dict
    _client: Gateway | None

    _entities: dict[str, Entity] = {}

    _known_commands: dict
    learn_device_id = None

    _platforms = {p: False for p in PLATFORMS}

    def __init__(self, hass: HomeAssistant, config: ConfigType) -> None:
        """Initialize the client and its data structure(s)."""
        self._hass = hass
        self._rf_entity_ids: set = set()
        self._update_interval = config[DOMAIN][CONF_SCAN_INTERVAL]
        self._store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
        self._port_name, self._client_config, self._config = normalise_config(
            config[DOMAIN]
        )
        self._known_commands = self._config["remotes"]
        self._sem = Semaphore(value=1)
        self._client = None

    async def start(self) -> None:
        """Start the RAMSES co-ordinator."""

        try:
            await self._create_client()
        except TransportSerialError as exc:
            _LOGGER.error("There is a problem with the serial port: %s", exc)

        if self._config[SZ_RESTORE_CACHE][SZ_RESTORE_STATE]:
            await self._async_load_client_state()
            _LOGGER.info("Restored the cached state")
        else:
            _LOGGER.info(
                "Not restoring any cached state (disabled), "
                "consider using 'restore_cache: restore_state: true'"
            )

        await self.async_register_domain_events()
        self._hass.async_create_task(self.async_register_domain_services())

        _LOGGER.debug("Starting the RF monitor")
        await self._client.start()

        self._async_create_update_tasks()

    async def _create_client(self) -> None:
        """Create a client with an inital schema.

        The order of preference for the schema is: merged/cached/config/null.
        """

        storage = await self._async_load_storage()
        self._known_commands = merge(self._known_commands, storage.get("remotes", {}))

        CONFIG_KEYS = (SZ_CONFIG, SZ_PACKET_LOG, SZ_PORT_CONFIG)
        config = {k: v for k, v in self._client_config.items() if k in CONFIG_KEYS}
        schema = {k: v for k, v in self._client_config.items() if k not in config}

        if not schema_is_minimal(schema):  # TODO: move all this logix in ramses_rf
            _LOGGER.warning("The config schema is not minimal (consider minimising it)")

        schemas = merge_schemas(
            self._config[SZ_RESTORE_CACHE][SZ_RESTORE_SCHEMA],
            schema,
            storage.get("client_state", {}).get(SZ_SCHEMA, {}),
        )
        for msg, schema in schemas.items():
            try:
                self._client = Gateway(
                    self._port_name, loop=self._hass.loop, **config, **schema
                )
            except (LookupError, vol.MultipleInvalid) as exc:
                # LookupError:     ...in the schema, but also in the block_list
                # MultipleInvalid: ...extra keys not allowed @ data['???']
                _LOGGER.warning("Failed to initialise with %s schema: %s", msg, exc)
            else:
                _LOGGER.info("Success initialising with %s schema: %s", msg, schema)
                break
        else:
            self._client = Gateway(self._port_name, loop=self._hass.loop, **config)
            _LOGGER.warning("Required to initialise with an empty schema: {}")

    async def _async_load_storage(self) -> dict:
        """May return an empty dict."""
        app_storage = await self._store.async_load()  # return None if no store
        return app_storage or {}

    async def _async_load_client_state(self) -> None:
        """Restore the client state from the application store."""

        _LOGGER.info("Restoring the client state cache (packets)")
        app_storage = await self._async_load_storage()
        if client_state := app_storage.get("client_state"):
            packets = {
                k: m
                for k, m in client_state["packets"].items()
                if dt.fromisoformat(k) > dt.now() - timedelta(days=1)
                and (
                    m[41:45] in ("10E0")
                    or self._config[SZ_RESTORE_CACHE][SZ_RESTORE_SCHEMA]
                    or m[41:45] not in ("0004", "0005", "000C")
                )  # force-load new schema (dont use cached schema pkts)
            }
            await self._client._set_state(packets=packets)  # FIXME, issue #79

    async def async_register_domain_events(self) -> None:
        """Set up the handlers for the system-wide events."""

        @callback
        def process_msg(msg, *args, **kwargs):  # process_msg(msg, prev_msg=None)
            if (
                regex := self._config[CONF_ADVANCED_FEATURES][CONF_MESSAGE_EVENTS]
            ) and regex.match(f"{msg!r}"):
                event_data = {
                    "dtm": msg.dtm.isoformat(),
                    "src": msg.src.id,
                    "dst": msg.dst.id,
                    "verb": msg.verb,
                    "code": msg.code,
                    "payload": msg.payload,
                    "packet": str(msg._pkt),
                }
                self._hass.bus.async_fire(f"{DOMAIN}_message", event_data)

            if self.learn_device_id and self.learn_device_id == msg.src.id:
                event_data = {
                    "src": msg.src.id,
                    "code": msg.code,
                    "packet": str(msg._pkt),
                }
                self._hass.bus.async_fire(f"{DOMAIN}_learn", event_data)

        self._client.add_msg_handler(process_msg)

    async def async_register_domain_services(self):
        """Set up the handlers for the domain-wide services."""

        @verify_domain_control(self._hass, DOMAIN)
        async def svc_fake_device(call: ServiceCall) -> None:
            try:
                self._client.fake_device(**call.data)
            except LookupError as exc:
                _LOGGER.error("%s", exc)
                return
            self._hass.helpers.event.async_call_later(5, self.async_update)

        @verify_domain_control(self._hass, DOMAIN)
        async def svc_force_update(_: ServiceCall) -> None:
            await self.async_update()

        @verify_domain_control(self._hass, DOMAIN)
        async def svc_send_packet(call: ServiceCall) -> None:
            kwargs = dict(call.data.items())  # is ReadOnlyDict
            if (
                call.data["device_id"] == "18:000730"
                and kwargs.get("from_id", "18:000730") == "18:000730"
                and self._client.hgi.id
            ):
                kwargs["device_id"] = self._client.client.hgi.id
            self._client.send_cmd(self._client.client.create_cmd(**kwargs))
            self._hass.helpers.event.async_call_later(5, self.async_update)

        self._hass.services.async_register(
            DOMAIN,
            SERVICE_FAKE_DEVICE,
            svc_fake_device,
            schema=vol.Schema(
                {
                    vol.Required(ATTR_DEVICE_ID): cv.matches_regex(
                        r"^[0-9]{2}:[0-9]{6}$"
                    ),
                    vol.Optional(ATTR_CREATE_DEVICE, default=False): vol.Any(
                        None, cv.boolean
                    ),
                    vol.Optional(ATTR_START_BINDING, default=False): vol.Any(
                        None, cv.boolean
                    ),
                }
            ),
        )

        self._hass.services.async_register(
            DOMAIN, SERVICE_FORCE_UPDATE, svc_force_update
        )

        if self._config[CONF_ADVANCED_FEATURES].get(SERVICE_SEND_PACKET):
            self._hass.services.async_register(
                DOMAIN,
                SERVICE_SEND_PACKET,
                svc_send_packet,
                schema=vol.Schema(
                    {
                        vol.Required(ATTR_DEVICE_ID): cv.matches_regex(
                            r"^[0-9]{2}:[0-9]{6}$"
                        ),
                        vol.Required(ATTR_VERB): vol.In(
                            (" I", "I", "RQ", "RP", " W", "W")
                        ),
                        vol.Required(ATTR_CODE): cv.matches_regex(r"^[0-9A-F]{4}$"),
                        vol.Required(ATTR_PAYLOAD): cv.matches_regex(
                            r"^[0-9A-F]{1,48}$"
                        ),
                    }
                ),
            )

    async def async_save_client_state(self, _: dt | None = None) -> None:
        """Save the client state to the application store."""

        _LOGGER.debug("Saving the client state cache (packets, schema)")

        (schema, packets) = self._client._get_state()
        remote_commands = self._known_commands | {
            k: v._commands for k, v in self._entities.items() if hasattr(v, "_commands")
        }

        await self._store.async_save(
            {
                "client_state": {"schema": schema, "packets": packets},
                "remotes": remote_commands,
            }
        )

    async def async_update(self, _: dt | None = None) -> None:
        """Retrieve the latest state data from the client library."""
        if not all(self._platforms.values()):
            return

        rf_entities: list[RamsesRFEntity] = []
        for device in self._client.devices:
            rf_entities.append(device)
        for system in self._client.systems:
            rf_entities.append(system)
            if isinstance(system, MultiZone):
                rf_entities.extend([z for z in system.zones if z.name])

        have_new_entities = False
        for rf_entity in rf_entities:
            unique_id = f"{rf_entity.__class__.__module__}.{rf_entity.__class__.__qualname__}|{rf_entity.id}"
            if unique_id in self._rf_entity_ids:
                async_dispatcher_send(self._hass, f"RAMSES_RF_UPDATE_{rf_entity.id}")
            else:
                async_dispatcher_send(self._hass, "RAMSES_RF_NEW_ENTITY", rf_entity)
                self._rf_entity_ids.add(unique_id)
                have_new_entities = True

        if have_new_entities:
            async_call_later(self._hass, 5, self.async_save_client_state)

    @callback
    def async_register_platform(
        self, platform: EntityPlatform, add_new_entity: Callable[[RamsesRFEntity], None]
    ) -> None:
        """Register a platform as ready and connect new entity listener."""
        self._platforms[platform.domain] = True
        async_dispatcher_connect(self._hass, "RAMSES_RF_NEW_ENTITY", add_new_entity)
        self._async_create_update_tasks()

    @callback
    def _async_create_update_tasks(self):
        """Create tasks to watch for updates when initalised."""
        if all(self._platforms.values()) and self._client:
            self._hass.create_task(self.async_update())
            async_track_time_interval(
                self._hass, self.async_update, self._update_interval
            )
            async_track_time_interval(
                self._hass, self.async_save_client_state, timedelta(seconds=300)
            )

    @callback
    def async_register_entity(self, entity: Entity) -> None:
        """Register an entity."""
        self._entities[entity.unique_id] = entity


class RamsesEntity(Entity):
    """Base for any Ramses entity."""

    rf_entity: RamsesRFEntity
    entity_description: RamsesEntityDescription
    _attr_should_poll = False

    def __init__(
        self,
        controller: RamsesController,
        rf_entity: RamsesRFEntity,
        entity_description: RamsesEntityDescription,
    ) -> None:
        """Initialize the entity."""
        self.controller = controller
        self.rf_entity = rf_entity
        self.entity_description = entity_description
        self._attr_unique_id = rf_entity.id

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return state attributes."""
        attrs = {
            ATTR_ID: self.rf_entity.id,
        }
        if self.entity_description.extra_attributes:
            attrs |= {
                k: getattr(self.rf_entity, v)
                for k, v in self.entity_description.extra_attributes
                if hasattr(self.rf_entity, v)
            }
        return attrs

    async def async_added_to_hass(self) -> None:
        """Connect to an updater."""
        self.controller.async_register_entity(self)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"RAMSES_RF_UPDATE_{self.rf_entity.id}",
                self.async_write_ha_state,
            )
        )
