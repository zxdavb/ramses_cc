"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import voluptuous as vol  # type: ignore[import-untyped, unused-ignore]
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType

from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_tx import exceptions as exc

from .broker import RamsesBroker
from .const import (
    CONF_ADVANCED_FEATURES,
    CONF_MESSAGE_EVENTS,
    CONF_SEND_PACKET,
    DOMAIN,
    SIGNAL_UPDATE,
)
from .schemas import (
    SCH_BIND_DEVICE,
    SCH_DOMAIN_CONFIG,
    SCH_NO_SVC_PARAMS,
    SCH_SEND_PACKET,
    SVC_BIND_DEVICE,
    SVC_FORCE_UPDATE,
    SVC_SEND_PACKET,
)

if TYPE_CHECKING:
    from ramses_tx.message import Message


_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.All(
    cv.deprecated(DOMAIN, raise_if_present=False),
    vol.Schema({DOMAIN: SCH_DOMAIN_CONFIG}, extra=vol.ALLOW_EXTRA),
)

PLATFORMS: Final[Platform] = (
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.REMOTE,
    Platform.WATER_HEATER,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ramses integration."""

    hass.data[DOMAIN] = {}

    # If required, do a one-off import of entry from config yaml
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create a ramses_rf (RAMSES_II)-based system."""

    _LOGGER.debug("Setting up entry %s...", entry.entry_id)

    broker = RamsesBroker(hass, entry)  # KeyError: 'serial_port'

    try:
        await broker.async_setup()
    except exc.TransportSourceInvalid as err:  # not TransportSerialError
        _LOGGER.error("Unrecoverable problem with the serial port: %s", err)
        return False
    except exc.TransportError as err:
        msg = f"There is a problem with the serial port: {err} (check config)"
        _LOGGER.warning(
            "Failed to set up entry %s (will retry): %s", entry.entry_id, msg
        )
        raise ConfigEntryNotReady(msg) from err  # TODO: when to give up?

    # Setup is complete and config is valid, so start polling
    hass.data[DOMAIN][entry.entry_id] = broker
    await broker.async_start()

    async_register_domain_services(hass, entry, broker)
    async_register_domain_events(hass, entry, broker)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    _LOGGER.debug("Successfully set up entry %s", entry.entry_id)
    return True


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    broker: RamsesBroker = hass.data[DOMAIN][entry.entry_id]
    if not await broker.async_unload_platforms():
        return False

    for svc in hass.services.async_services_for_domain(DOMAIN):
        hass.services.async_remove(DOMAIN, svc)

    hass.data[DOMAIN].pop(entry.entry_id)

    return True


@callback  # TODO: the following is a mess - to add register/deregister of clients
def async_register_domain_events(
    hass: HomeAssistant, entry: ConfigEntry, broker: RamsesBroker
) -> None:
    """Set up the handlers for the system-wide events."""

    features: dict[str, Any] = entry.options.get(CONF_ADVANCED_FEATURES, {})
    if message_events := features.get(CONF_MESSAGE_EVENTS):
        message_events_regex = re.compile(message_events)
    else:
        message_events_regex = None

    @callback
    def async_process_msg(msg: Message, *args: Any, **kwargs: Any) -> None:
        """Process a message from the event bus as pass it on."""

        if message_events_regex and message_events_regex.search(f"{msg!r}"):
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

        if broker.learn_device_id and broker.learn_device_id == msg.src.id:
            event_data = {
                "src": msg.src.id,
                "code": msg.code,
                "packet": str(msg._pkt),
            }
            hass.bus.async_fire(f"{DOMAIN}_learn", event_data)

    broker.client.add_msg_handler(async_process_msg)


@callback
def async_register_domain_services(
    hass: HomeAssistant, entry: ConfigEntry, broker: RamsesBroker
) -> None:
    """Set up the handlers for the domain-wide services."""

    @verify_domain_control(hass, DOMAIN)  # TODO: is a work in progress
    async def async_bind_device(call: ServiceCall) -> None:
        await broker.async_bind_device(call)

    @verify_domain_control(hass, DOMAIN)
    async def async_force_update(call: ServiceCall) -> None:
        await broker.async_force_update(call)

    @verify_domain_control(hass, DOMAIN)
    async def async_send_packet(call: ServiceCall) -> None:
        await broker.async_send_packet(call)

    hass.services.async_register(
        DOMAIN, SVC_BIND_DEVICE, async_bind_device, schema=SCH_BIND_DEVICE
    )
    hass.services.async_register(
        DOMAIN, SVC_FORCE_UPDATE, async_force_update, schema=SCH_NO_SVC_PARAMS
    )

    if entry.options.get(CONF_ADVANCED_FEATURES, {}).get(CONF_SEND_PACKET):
        hass.services.async_register(
            DOMAIN, SVC_SEND_PACKET, async_send_packet, schema=SCH_SEND_PACKET
        )


class RamsesEntity(Entity):
    """Base for any RAMSES II-compatible entity (e.g. Climate, Sensor)."""

    _broker: RamsesBroker
    _device: RamsesRFEntity

    _attr_should_poll = False

    entity_description: RamsesEntityDescription

    def __init__(
        self,
        broker: RamsesBroker,
        device: RamsesRFEntity,
        entity_description: RamsesEntityDescription,
    ) -> None:
        """Initialize the entity."""
        self.hass = broker.hass
        self._broker = broker
        self._device = device
        self.entity_description = entity_description

        self._attr_unique_id = device.id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device.id)})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = {
            ATTR_ID: self._device.id,
        }
        if self.entity_description.ramses_cc_extra_attributes:
            attrs |= {
                k: getattr(self._device, v)
                for k, v in self.entity_description.ramses_cc_extra_attributes.items()
                if hasattr(self._device, v)
            }
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._broker._entities[self.unique_id] = self
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE, self.async_write_ha_state
            )
        )

    @callback
    def async_write_ha_state_delayed(self, delay: int = 3) -> None:
        """Write to the state machine after a short delay to allow system to quiesce."""

        # NOTE: this doesn't work (below), as call_later injects `_now: dt`
        #     async_call_later(self.hass, delay, self.async_write_ha_state)
        # but only self is expected:
        #     def async_write_ha_state(self) -> None:

        self.hass.loop.call_later(delay, self.async_write_ha_state)


@dataclass(frozen=True, kw_only=True)
class RamsesEntityDescription(EntityDescription):
    """Class describing Ramses entities."""

    has_entity_name: bool = True

    # integration-specific attributes
    ramses_cc_extra_attributes: dict[str, str] | None = None  # TODO: may not be None?
