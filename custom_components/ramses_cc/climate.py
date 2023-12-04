"""Support for RAMSES climate entities."""
from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.components.climate import DOMAIN as PLATFORM
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .climate_heat import EvohomeController, EvohomeZone
from .climate_hvac import RamsesHvac
from .const import BROKER, DOMAIN, SYSTEM_MODE_LOOKUP, SystemMode
from .helpers import migrate_to_ramses_rf
from .schemas import (
    CONF_DURATION,
    CONF_DURATION_DAYS,
    CONF_LOCAL_OVERRIDE,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_MODE,
    CONF_MULTIROOM,
    CONF_OPENWINDOW,
    CONF_SCHEDULE,
    CONF_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)

SCHEMA_SYSTEM_MODE = {
    vol.Required(CONF_MODE): vol.In(SYSTEM_MODE_LOOKUP),  # incl. DAY_OFF_ECO
}
SCHEMA_SYSTEM_MODE_HOURS = {
    vol.Required(CONF_MODE): vol.In([SystemMode.ECO_BOOST]),
    vol.Optional(CONF_DURATION, default=timedelta(hours=1)): vol.All(
        cv.time_period, vol.Range(min=timedelta(hours=1), max=timedelta(hours=24))
    ),
}
SCHEMA_SYSTEM_MODE_DAYS = {
    vol.Required(CONF_MODE): vol.In(
        [SystemMode.AWAY, SystemMode.CUSTOM, SystemMode.DAY_OFF]
    ),
    vol.Optional(CONF_DURATION_DAYS, default=timedelta(days=0)): vol.All(
        cv.time_period, vol.Range(min=timedelta(days=0), max=timedelta(days=99))
    ),  # 0 means until the end of the day
}

SERVICE_RESET_SYSTEM_MODE = "reset_system_mode"
SERVICE_SET_SYSTEM_MODE = "set_system_mode"

SERVICE_GET_ZONE_SCHED = "get_zone_schedule"
SERVICE_PUT_ZONE_TEMP = "put_zone_temp"
SERVICE_RESET_ZONE_CONFIG = "reset_zone_config"
SERVICE_RESET_ZONE_MODE = "reset_zone_mode"
SERVICE_SET_ZONE_CONFIG = "set_zone_config"
SERVICE_SET_ZONE_MODE = "set_zone_mode"
SERVICE_SET_ZONE_SCHED = "set_zone_schedule"


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create climate entities for CH/DHW (heat) & HVAC."""

    def entity_factory(entity_class, broker, device):  # TODO: deprecate
        migrate_to_ramses_rf(hass, PLATFORM, device.id)
        return entity_class(broker, device)

    if discovery_info is None:
        return

    platform = entity_platform.async_get_current_platform()

    # Controller services
    platform.async_register_entity_service(
        SERVICE_RESET_SYSTEM_MODE,
        cv.make_entity_service_schema(),
        "svc_reset_system_mode",
    )

    platform.async_register_entity_service(
        SERVICE_SET_SYSTEM_MODE,
        cv.make_entity_service_schema(
            vol.Any(
                SCHEMA_SYSTEM_MODE, SCHEMA_SYSTEM_MODE_HOURS, SCHEMA_SYSTEM_MODE_DAYS
            )
        ),
        "svc_reset_system_mode",
    )

    # Zone services
    platform.async_register_entity_service(
        SERVICE_GET_ZONE_SCHED,
        cv.make_entity_service_schema(),
        "svc_get_zone_schedule",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_SCHED,
        cv.make_entity_service_schema({vol.Required(CONF_SCHEDULE): cv.string}),
        "svc_set_zone_schedule",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_SCHED,
        cv.make_entity_service_schema({vol.Required(CONF_SCHEDULE): cv.string}),
        "svc_set_zone_schedule",
    )

    platform.async_register_entity_service(
        SERVICE_PUT_ZONE_TEMP,
        cv.make_entity_service_schema(
            {
                vol.Required(CONF_TEMPERATURE): vol.All(
                    vol.Coerce(float), vol.Range(min=-20, max=99)
                ),
            }
        ),
        "svc_put_zone_temp",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_CONFIG,
        cv.make_entity_service_schema(
            {
                vol.Optional(CONF_MAX_TEMP, default=35): vol.All(
                    cv.positive_float,
                    vol.Range(min=21, max=35),
                ),
                vol.Optional(CONF_MIN_TEMP, default=5): vol.All(
                    cv.positive_float,
                    vol.Range(min=5, max=21),
                ),
                vol.Optional(CONF_LOCAL_OVERRIDE, default=True): cv.boolean,
                vol.Optional(CONF_OPENWINDOW, default=True): cv.boolean,
                vol.Optional(CONF_MULTIROOM, default=True): cv.boolean,
            }
        ),
        "svc_set_zone_config",
    )

    platform.async_register_entity_service(
        SERVICE_RESET_ZONE_CONFIG,
        cv.make_entity_service_schema(),
        "svc_reset_zone_config",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ZONE_MODE,
        cv.make_entity_service_schema(
            vol.Any(
                SCHEMA_SYSTEM_MODE, SCHEMA_SYSTEM_MODE_HOURS, SCHEMA_SYSTEM_MODE_DAYS
            )
        ),
        "svc_set_zone_mode",
    )

    platform.async_register_entity_service(
        SERVICE_RESET_ZONE_MODE,
        cv.make_entity_service_schema(),
        "svc_reset_zone_mode",
    )

    broker = hass.data[DOMAIN][BROKER]
    new_entities = []

    if discovery_info.get("fans"):
        for fan in discovery_info["fans"]:
            new_entities.append(RamsesHvac(broker, fan))

    if discovery_info.get("ctls") or discovery_info.get("zons"):
        for tcs in discovery_info.get("ctls", []):
            new_entities.append(entity_factory(EvohomeController, broker, tcs))

        for zone in discovery_info.get("zons", []):
            new_entities.append(entity_factory(EvohomeZone, broker, zone))

    if new_entities:
        async_add_entities(new_entities)
