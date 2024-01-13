"""Schemas for RAMSES integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, TypeAlias

from ramses_rf.helpers import deep_merge, shrink
from ramses_rf.schemas import (
    SZ_APPLIANCE_CONTROL,
    SZ_BLOCK_LIST,
    SZ_KNOWN_LIST,
    SZ_ORPHANS_HEAT,
    SZ_ORPHANS_HVAC,
    SZ_SENSOR,
    SZ_SYSTEM,
    SZ_ZONES,
)
from ramses_tx.const import COMMAND_REGEX
from ramses_tx.schemas import sch_global_traits_dict_factory
import voluptuous as vol  # type: ignore[import-untyped]

from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ACTIVE,
    ATTR_CO2_LEVEL,
    ATTR_COMMAND,
    ATTR_DELAY_SECS,
    ATTR_DEVICE_ID,
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
    CONF_COMMANDS,
    SystemMode,
    ZoneMode,
)

_SchemaT: TypeAlias = dict[str, Any]

_LOGGER = logging.getLogger(__name__)

SCH_GLOBAL_TRAITS_DICT, SCH_TRAITS = sch_global_traits_dict_factory(
    hvac_traits={vol.Optional(CONF_COMMANDS): dict}
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


# services for ramses_cc integration

_SCH_DEVICE_ID = cv.matches_regex(r"^[0-9]{2}:[0-9]{6}$")
_SCH_CMD_CODE = cv.matches_regex(r"^[0-9A-F]{4}$")
_SCH_DOM_IDX = cv.matches_regex(r"^[0-9A-F]{2}$")
_SCH_COMMAND = cv.matches_regex(COMMAND_REGEX)

_SCH_BINDING = vol.Schema({vol.Required(_SCH_CMD_CODE): vol.Any(None, _SCH_DOM_IDX)})

# SCH = vol.All(_SCH_BINDING, vol.Length(min=1))

SCH_BIND_DEVICE = vol.Schema(
    {
        vol.Required("device_id"): _SCH_DEVICE_ID,
        vol.Required("offer"): vol.All(_SCH_BINDING, vol.Length(min=1)),
        vol.Optional("confirm", default={}): vol.Any(
            {}, vol.All(_SCH_BINDING, vol.Length(min=1))
        ),
        vol.Optional("device_info", default=None): vol.Any(None, _SCH_COMMAND),
    },
    extra=vol.PREVENT_EXTRA,
)

SCH_SEND_PACKET = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.matches_regex(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Required("verb"): vol.In((" I", "I", "RQ", "RP", " W", "W")),
        vol.Required("code"): cv.matches_regex(r"^[0-9A-F]{4}$"),
        vol.Required("payload"): cv.matches_regex(r"^[0-9A-F]{1,48}$"),
    }
)

SVC_BIND_DEVICE = "bind_device"
SVC_FORCE_UPDATE = "force_update"
SVC_SEND_PACKET = "send_packet"

_SVCS_RAMSES_CC_ASYNC = {
    SVC_BIND_DEVICE: SCH_BIND_DEVICE,
    SVC_FORCE_UPDATE: {},
    SVC_SEND_PACKET: SCH_SEND_PACKET,
}

# services for sensor platform

MIN_CO2_LEVEL = 300
MAX_CO2_LEVEL = 9999

SVC_PUT_CO2_LEVEL = "put_co2_level"
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

SVC_PUT_DHW_TEMP = "put_dhw_temp"
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

SVC_PUT_INDOOR_HUMIDITY = "put_indoor_humidity"
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

SVC_PUT_ROOM_TEMP = "put_room_temp"
SCH_PUT_ROOM_TEMP = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_ROOM_TEMP, max=MAX_ROOM_TEMP),
        ),
    }
)

SVCS_SENSOR = {
    SVC_PUT_CO2_LEVEL: SCH_PUT_CO2_LEVEL,
    SVC_PUT_DHW_TEMP: SCH_PUT_DHW_TEMP,
    SVC_PUT_INDOOR_HUMIDITY: SCH_PUT_INDOOR_HUMIDITY,
    SVC_PUT_ROOM_TEMP: SCH_PUT_ROOM_TEMP,
}

# services for climate platform

SVC_SET_SYSTEM_MODE = "set_system_mode"
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

SVC_SET_ZONE_CONFIG = "set_zone_config"
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

SVC_SET_ZONE_MODE = "set_zone_mode"
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

SVC_SET_ZONE_SCHEDULE = "set_zone_schedule"
SCH_SET_ZONE_SCHEDULE = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE): cv.string,
    }
)

SVC_FAKE_ZONE_TEMP = "fake_zone_temp"
SVC_GET_ZONE_SCHEDULE = "get_zone_schedule"
SVC_RESET_SYSTEM_MODE = "reset_system_mode"
SVC_RESET_ZONE_CONFIG = "reset_zone_config"
SVC_RESET_ZONE_MODE = "reset_zone_mode"

SVCS_CLIMATE = {
    SVC_FAKE_ZONE_TEMP: SCH_PUT_ROOM_TEMP,  # a convenience for SVC_PUT_ROOM_TEMP
    SVC_SET_SYSTEM_MODE: SCH_SET_SYSTEM_MODE,
    SVC_SET_ZONE_CONFIG: SCH_SET_ZONE_CONFIG,
    SVC_SET_ZONE_MODE: SCH_SET_ZONE_MODE,
    SVC_RESET_SYSTEM_MODE: {},
    SVC_RESET_ZONE_CONFIG: {},
    SVC_RESET_ZONE_MODE: {},
}
SVCS_CLIMATE_ASYNC = {
    SVC_GET_ZONE_SCHEDULE: {},
    SVC_SET_ZONE_SCHEDULE: SCH_SET_ZONE_SCHEDULE,
}

# services for water_heater platform

SVC_SET_DHW_MODE = "set_dhw_mode"
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

SVC_SET_DHW_PARAMS = "set_dhw_params"
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

SVC_SET_DHW_SCHEDULE = "set_dhw_schedule"
SCH_SET_DHW_SCHEDULE = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SCHEDULE): cv.string,
    }
)

SVC_FAKE_DHW_TEMP = "fake_dhw_temp"
SVC_GET_DHW_SCHEDULE = "get_dhw_schedule"
SVC_RESET_DHW_MODE = "reset_dhw_mode"
SVC_RESET_DHW_PARAMS = "reset_dhw_params"
SVC_SET_DHW_BOOST = "set_dhw_boost"

SVCS_WATER_HEATER = {
    SVC_FAKE_DHW_TEMP: SCH_PUT_DHW_TEMP,  # a convenience for SVC_PUT_DHW_TEMP
    SVC_RESET_DHW_MODE: {},
    SVC_RESET_DHW_PARAMS: {},
    SVC_SET_DHW_BOOST: {},
    SVC_SET_DHW_MODE: SCH_SET_DHW_MODE,
    SVC_SET_DHW_PARAMS: SCH_SET_DHW_PARAMS,
    SVC_SET_DHW_SCHEDULE: SCH_SET_DHW_SCHEDULE,
}
SVCS_WATER_HEATER_ASYNC = {
    SVC_GET_DHW_SCHEDULE: {},
    SVC_SET_DHW_SCHEDULE: SCH_SET_DHW_SCHEDULE,
}
# services for remote platform

SVC_LEARN_COMMAND = "learn_command"
SCH_LEARN_COMMAND = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Required(ATTR_TIMEOUT, default=60): vol.All(
            cv.positive_int, vol.Range(min=30, max=300)
        ),
    }
)

SVC_SEND_COMMAND = "send_command"
SCH_SEND_COMMAND = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Required(ATTR_NUM_REPEATS, default=3): cv.positive_int,
        vol.Required(ATTR_DELAY_SECS, default=0.2): cv.positive_float,
    },
)

SVC_DELETE_COMMAND = "delete_command"
SCH_DELETE_COMMAND = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
    },
)

SVCS_REMOTE_ASYNC = {
    SVC_DELETE_COMMAND: SCH_DELETE_COMMAND,
    SVC_LEARN_COMMAND: SCH_LEARN_COMMAND,
    SVC_SEND_COMMAND: SCH_SEND_COMMAND,
}
