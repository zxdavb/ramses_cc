"""Schemas for RAMSES integration."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import logging
from typing import Any, TypeAlias

from ramses_rf.helpers import deep_merge, shrink
from ramses_rf.schemas import (
    SCH_GATEWAY_CONFIG,
    SCH_GLOBAL_SCHEMAS_DICT,
    SCH_RESTORE_CACHE_DICT,
    SZ_APPLIANCE_CONTROL,
    SZ_BLOCK_LIST,
    SZ_CONFIG,
    SZ_KNOWN_LIST,
    SZ_ORPHANS_HEAT,
    SZ_ORPHANS_HVAC,
    SZ_RESTORE_CACHE,
    SZ_SENSOR,
    SZ_SYSTEM,
    SZ_ZONES,
)
from ramses_tx.const import COMMAND_REGEX
from ramses_tx.schemas import (
    SCH_ENGINE_DICT,
    SZ_PORT_CONFIG,
    SZ_SERIAL_PORT,
    extract_serial_port,
    sch_global_traits_dict_factory,
    sch_packet_log_dict_factory,
    sch_serial_port_dict_factory,
)
import voluptuous as vol  # type: ignore[import-untyped]

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ACTIVE,
    ATTR_CO2_LEVEL,
    ATTR_COMMAND,
    ATTR_DELAY_SECS,
    ATTR_DIFFERENTIAL,
    ATTR_DURATION,
    ATTR_INDOOR_HUMIDITY,
    ATTR_LOCAL_OVERRIDE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_MODE,
    ATTR_MULTIROOM,
    ATTR_NUM_REPEATS,
    ATTR_OPENWINDOW,
    ATTR_OVERRUN,
    ATTR_PERIOD,
    ATTR_SCHEDULE,
    ATTR_SETPOINT,
    ATTR_TEMPERATURE,
    ATTR_TIMEOUT,
    ATTR_UNTIL,
    CONF_ADVANCED_FEATURES,
    CONF_COMMANDS,
    CONF_DEV_MODE,
    CONF_MESSAGE_EVENTS,
    CONF_RAMSES_RF,
    CONF_SEND_PACKET,
    CONF_UNKNOWN_CODES,
    SystemMode,
    ZoneMode,
)

_SchemaT: TypeAlias = dict[str, Any]

_LOGGER = logging.getLogger(__name__)

#
# Configuration schema for Integration/domain
SCAN_INTERVAL_DEFAULT = timedelta(seconds=60)
SCAN_INTERVAL_MINIMUM = timedelta(seconds=3)


SCH_ADVANCED_FEATURES = vol.Schema(
    {
        vol.Optional(CONF_SEND_PACKET, default=False): cv.boolean,
        vol.Optional(CONF_MESSAGE_EVENTS, default=None): vol.Any(None, cv.is_regex),
        vol.Optional(CONF_DEV_MODE): cv.boolean,
        vol.Optional(CONF_UNKNOWN_CODES): cv.boolean,
    }
)

SCH_GLOBAL_TRAITS_DICT, SCH_TRAITS = sch_global_traits_dict_factory(
    hvac_traits={vol.Optional(CONF_COMMANDS): {str: cv.matches_regex(COMMAND_REGEX)}}
)

SCH_GATEWAY_CONFIG = SCH_GATEWAY_CONFIG.extend(
    SCH_ENGINE_DICT,
    extra=vol.PREVENT_EXTRA,
)

SCH_DOMAIN_CONFIG = (
    vol.Schema(
        {
            vol.Optional(CONF_RAMSES_RF, default={}): SCH_GATEWAY_CONFIG,
            vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT): vol.All(
                cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)
            ),
            vol.Optional(CONF_ADVANCED_FEATURES, default={}): SCH_ADVANCED_FEATURES,
        },
        extra=vol.PREVENT_EXTRA,  # will be system, orphan schemas for ramses_rf
    )
    .extend(SCH_GLOBAL_SCHEMAS_DICT)
    .extend(SCH_GLOBAL_TRAITS_DICT)
    .extend(sch_packet_log_dict_factory(default_backups=7))
    .extend(SCH_RESTORE_CACHE_DICT)
    .extend(sch_serial_port_dict_factory())
)

SCH_MINIMUM_TCS = vol.Schema(
    {
        vol.Optional(SZ_SYSTEM): vol.Schema(
            {vol.Required(SZ_APPLIANCE_CONTROL): vol.Match(r"^10:[0-9]{6}$")}
        ),
        vol.Optional(SZ_ZONES, default={}): vol.Schema(
            {
                vol.Required(str): vol.Schema(
                    {vol.Required(SZ_SENSOR): vol.Match(r"^01:[0-9]{6}$")}
                )
            }
        ),
    },
    extra=vol.PREVENT_EXTRA,
)


def _is_subset(subset, superset) -> bool:  # TODO: move to ramses_rf?
    """Return True is one dict (or list/set) is a subset of another."""
    if isinstance(subset, dict):
        return all(
            key in superset and _is_subset(val, superset[key])
            for key, val in subset.items()
        )
    if isinstance(subset, list | set):
        return all(
            any(_is_subset(subitem, superitem) for superitem in superset)
            for subitem in subset
        )
    return subset == superset  # not dict, list nor set


@callback
def normalise_config(config: dict) -> tuple[str, dict, dict]:
    """Return a port/client_config/broker_config for the library."""

    config = deepcopy(config)

    config[SZ_CONFIG] = config.pop(CONF_RAMSES_RF)

    port_name, port_config = extract_serial_port(config.pop(SZ_SERIAL_PORT))

    remote_commands = {
        k: v.pop(CONF_COMMANDS)
        for k, v in config[SZ_KNOWN_LIST].items()
        if v.get(CONF_COMMANDS)
    }

    broker_keys = (CONF_SCAN_INTERVAL, CONF_ADVANCED_FEATURES, SZ_RESTORE_CACHE)
    return (
        port_name,
        {k: v for k, v in config.items() if k not in broker_keys}
        | {SZ_PORT_CONFIG: port_config},
        {k: v for k, v in config.items() if k in broker_keys}
        | {"remotes": remote_commands},
    )


@callback
def merge_schemas(config_schema: _SchemaT, cached_schema: _SchemaT) -> _SchemaT | None:
    """Return the config schema deep merged into the cached schema."""

    if _is_subset(shrink(config_schema), shrink(cached_schema)):
        _LOGGER.info("Using the cached schema")
        return cached_schema

    merged_schema = deep_merge(config_schema, cached_schema)  # 1st takes precedence

    if _is_subset(shrink(config_schema), shrink(merged_schema)):
        _LOGGER.info("Using a merged schema")
        return merged_schema

    _LOGGER.info("Cached schema is a subset of config schema")
    return None


@callback
def schema_is_minimal(schema: dict) -> bool:
    """Return True if the schema is minimal (i.e. no optional keys)."""

    key: str
    sch: dict

    for key, sch in schema.items():
        if key in (SZ_BLOCK_LIST, SZ_KNOWN_LIST, SZ_ORPHANS_HEAT, SZ_ORPHANS_HVAC):
            continue

        try:
            _ = SCH_MINIMUM_TCS(shrink(sch))
        except vol.Invalid:
            return False

        if SZ_ZONES in sch and list(sch[SZ_ZONES].values())[0][SZ_SENSOR] != key:
            return False

    return True


# Service call consts & schemas
MIN_CO2_LEVEL = 300
MAX_CO2_LEVEL = 9999

SCH_PUT_CO2_LEVEL = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_CO2_LEVEL): vol.All(
            cv.positive_int,
            vol.Range(min=MIN_CO2_LEVEL, max=MAX_CO2_LEVEL),
        ),
    }
)

MIN_DHW_TEMP = 0
MAX_DHW_TEMP = 99

SCH_PUT_DHW_TEMP = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_DHW_TEMP, max=MAX_DHW_TEMP),
        ),
    }
)

MIN_INDOOR_HUMIDITY = 0
MAX_INDOOR_HUMIDITY = 100

SCH_PUT_INDOOR_HUMIDITY = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_INDOOR_HUMIDITY): vol.All(
            cv.positive_float,
            vol.Range(min=MIN_INDOOR_HUMIDITY, max=MAX_INDOOR_HUMIDITY),
        ),
    }
)

MIN_ROOM_TEMP = -20
MAX_ROOM_TEMP = 60

SCH_PUT_ROOM_TEMP = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_ROOM_TEMP, max=MAX_ROOM_TEMP),
        ),
    }
)

SCH_SET_SYSTEM_MODE = vol.Schema(
    vol.Any(
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_MODE): vol.In(
                    [
                        SystemMode.AUTO,
                        SystemMode.HEAT_OFF,
                        SystemMode.RESET,
                    ]
                )
            }
        ),
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_MODE): vol.In([SystemMode.ECO_BOOST]),
                vol.Optional(ATTR_DURATION, default=timedelta(hours=1)): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(hours=1), max=timedelta(hours=24)),
                ),
            }
        ),
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_MODE): vol.In(
                    [
                        SystemMode.AWAY,
                        SystemMode.CUSTOM,
                        SystemMode.DAY_OFF,
                        SystemMode.DAY_OFF_ECO,
                    ]
                ),
                vol.Optional(ATTR_PERIOD, default=timedelta(days=0)): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(days=0), max=timedelta(days=99)),
                ),  # 0 means until the end of the day
            }
        ),
    )
)

SCH_SET_ZONE_CONFIG = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_MAX_TEMP, default=35): vol.All(
            cv.positive_float, vol.Range(min=21, max=35)
        ),
        vol.Optional(ATTR_MIN_TEMP, default=5): vol.All(
            cv.positive_float, vol.Range(min=5, max=21)
        ),
        vol.Optional(ATTR_LOCAL_OVERRIDE, default=True): cv.boolean,
        vol.Optional(ATTR_OPENWINDOW, default=True): cv.boolean,
        vol.Optional(ATTR_MULTIROOM, default=True): cv.boolean,
    }
)

SCH_SET_ZONE_MODE = vol.Schema(
    vol.Any(
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_MODE): vol.In([ZoneMode.SCHEDULE]),
            }
        ),
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_MODE): vol.In(
                    [ZoneMode.PERMANENT, ZoneMode.ADVANCED]
                ),
                vol.Optional(ATTR_SETPOINT, default=21): vol.All(
                    cv.positive_float, vol.Range(min=5, max=30)
                ),
            }
        ),
        cv.make_entity_service_schema(
            {
                vol.Required(ATTR_MODE): vol.In([ZoneMode.TEMPORARY]),
                vol.Optional(ATTR_SETPOINT, default=21): vol.All(
                    cv.positive_float, vol.Range(min=5, max=30)
                ),
                vol.Exclusive(ATTR_UNTIL, ATTR_UNTIL): cv.datetime,
                vol.Exclusive(ATTR_DURATION, ATTR_UNTIL): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(minutes=5), max=timedelta(days=1)),
                ),
            }
        ),
    )
)

SCH_SET_ZONE_SCHEDULE = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE): cv.string,
    }
)

SCH_SET_DHW_MODE = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_MODE): vol.In(
            [ZoneMode.SCHEDULE, ZoneMode.PERMANENT, ZoneMode.TEMPORARY]
        ),
        vol.Optional(ATTR_ACTIVE): cv.boolean,
        vol.Exclusive(ATTR_UNTIL, ATTR_UNTIL): cv.datetime,
        vol.Exclusive(ATTR_DURATION, ATTR_UNTIL): vol.All(
            cv.time_period,
            vol.Range(min=timedelta(minutes=5), max=timedelta(days=1)),
        ),
    }
)

SCH_SET_DHW_PARAMS = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_SETPOINT, default=50): vol.All(
            cv.positive_float,
            vol.Range(min=30, max=85),
        ),
        vol.Optional(ATTR_OVERRUN, default=5): vol.All(
            cv.positive_int,
            vol.Range(max=10),
        ),
        vol.Optional(ATTR_DIFFERENTIAL, default=1): vol.All(
            cv.positive_float,
            vol.Range(max=10),
        ),
    }
)

SCH_SET_DHW_SCHEDULE = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE): cv.string,
    }
)

SCH_LEARN_COMMAND = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Required(ATTR_TIMEOUT, default=60): vol.All(
            cv.positive_int, vol.Range(min=30, max=300)
        ),
    }
)

SCH_SEND_COMMAND = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Required(ATTR_NUM_REPEATS, default=3): cv.positive_int,
        vol.Required(ATTR_DELAY_SECS, default=0.2): cv.positive_float,
    },
)

SCH_DELETE_COMMAND = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
    },
)
