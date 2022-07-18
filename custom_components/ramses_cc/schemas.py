#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC."""

import logging
from copy import deepcopy
from datetime import timedelta as td

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID as CONF_ENTITY_ID
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from ramses_rf.const import SZ_DEVICE_ID
from ramses_rf.helpers import shrink
from ramses_rf.protocol.schemas import (
    SZ_LOG_FILE_NAME,
    SZ_LOG_ROTATE_BACKUPS,
    SZ_LOG_ROTATE_BYTES,
    SZ_PORT_NAME,
    SZ_SERIAL_PORT,
)
from ramses_rf.schemas import (
    SCH_CONFIG,
    SCH_DEVICE,
    SCH_DEVICE_ANY,
    SCH_SERIAL_CONFIG,
    SCH_TCS,
    SZ_BLOCK_LIST,
    SZ_CONFIG,
    SZ_CONTROLLER,
    SZ_EVOFW_FLAG,
    SZ_KNOWN_LIST,
    SZ_MAIN_CONTROLLER,
    SZ_ORPHANS_HEAT,
    SZ_ORPHANS_HVAC,
    SZ_PACKET_LOG,
    SZ_SCHEMA,
    SZ_SERIAL_CONFIG,
)

from .const import DOMAIN, SYSTEM_MODE_LOOKUP, SystemMode, ZoneMode

_LOGGER = logging.getLogger(__name__)

CONF_MODE = "mode"
CONF_SYSTEM_MODE = "system_mode"
CONF_DURATION_DAYS = "period"
CONF_DURATION_HOURS = "hours"

CONF_DURATION = "duration"
CONF_LOCAL_OVERRIDE = "local_override"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_MULTIROOM = "multiroom_mode"
CONF_OPENWINDOW = "openwindow_function"
CONF_SETPOINT = "setpoint"
CONF_TEMPERATURE = "temperature"
CONF_UNTIL = "until"

CONF_ACTIVE = "active"
CONF_DIFFERENTIAL = "differential"
CONF_OVERRUN = "overrun"

#
# Integration/domain generic services
SVC_FAKE_DEVICE = "fake_device"
SVC_REFRESH_SYSTEM = "refresh_system"
SVC_SEND_PACKET = "send_packet"

SCH_FAKE_DEVICE = vol.Schema(
    {
        vol.Required(SZ_DEVICE_ID): vol.Match(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Optional("create_device", default=False): vol.Any(None, bool),
        vol.Optional("start_binding", default=False): vol.Any(None, bool),
    }
)
SCH_SEND_PACKET = vol.Schema(
    {
        vol.Required(SZ_DEVICE_ID): vol.Match(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Required("verb"): vol.In((" I", "I", "RQ", "RP", " W", "W")),
        vol.Required("code"): vol.Match(r"^[0-9A-F]{4}$"),
        vol.Required("payload"): vol.Match(r"^[0-9A-F]{1,48}$"),
    }
)

SVCS_DOMAIN = {
    SVC_FAKE_DEVICE: SCH_FAKE_DEVICE,
    SVC_REFRESH_SYSTEM: None,
    SVC_SEND_PACKET: SCH_SEND_PACKET,
}

#
# Integration/domain services for TCS
SVC_RESET_SYSTEM_MODE = "reset_system_mode"
SVC_SET_SYSTEM_MODE = "set_system_mode"

SCH_SYSTEM_MODE = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In(SYSTEM_MODE_LOOKUP),  # incl. DAY_OFF_ECO
    }
)
SCH_SYSTEM_MODE_HOURS = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In([SystemMode.ECO_BOOST]),
        vol.Optional(CONF_DURATION, default=td(hours=1)): vol.All(
            cv.time_period, vol.Range(min=td(hours=1), max=td(hours=24))
        ),
    }
)
SCH_SYSTEM_MODE_DAYS = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In(
            [SystemMode.AWAY, SystemMode.CUSTOM, SystemMode.DAY_OFF]
        ),
        vol.Optional(CONF_DURATION_DAYS, default=td(days=0)): vol.All(
            cv.time_period, vol.Range(min=td(days=0), max=td(days=99))
        ),  # 0 means until the end of the day
    }
)
SCH_SYSTEM_MODE = vol.Any(SCH_SYSTEM_MODE, SCH_SYSTEM_MODE_HOURS, SCH_SYSTEM_MODE_DAYS)

SVCS_DOMAIN_EVOHOME = {
    SVC_RESET_SYSTEM_MODE: None,
    SVC_SET_SYSTEM_MODE: SCH_SYSTEM_MODE,
}

#
# Climate platform services for Zone
SVC_PUT_ZONE_TEMP = "put_zone_temp"
SVC_RESET_ZONE_CONFIG = "reset_zone_config"
SVC_RESET_ZONE_MODE = "reset_zone_mode"
SVC_SET_ZONE_CONFIG = "set_zone_config"
SVC_SET_ZONE_MODE = "set_zone_mode"

CONF_ZONE_MODES = (
    ZoneMode.SCHEDULE,
    ZoneMode.PERMANENT,
    ZoneMode.ADVANCED,
    ZoneMode.TEMPORARY,
)

SCH_SET_ZONE_BASE = vol.Schema({vol.Required(CONF_ENTITY_ID): cv.entity_id})

SCH_SET_ZONE_CONFIG = SCH_SET_ZONE_BASE.extend(
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
)

SCH_SET_ZONE_MODE = SCH_SET_ZONE_BASE.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.SCHEDULE]),
    }
)
SCH_SET_ZONE_MODE_SETPOINT = SCH_SET_ZONE_BASE.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.PERMANENT, ZoneMode.ADVANCED]),
        vol.Optional(CONF_SETPOINT, default=21): vol.All(
            cv.positive_float,
            vol.Range(min=5, max=30),
        ),
    }
)
SCH_SET_ZONE_MODE_UNTIL = SCH_SET_ZONE_BASE.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.TEMPORARY]),
        vol.Optional(CONF_SETPOINT, default=21): vol.All(
            cv.positive_float,
            vol.Range(min=5, max=30),
        ),
        vol.Exclusive(CONF_UNTIL, CONF_UNTIL): cv.datetime,
        vol.Exclusive(CONF_DURATION, CONF_UNTIL): vol.All(
            cv.time_period,
            vol.Range(min=td(minutes=5), max=td(days=1)),
        ),
    }
)
SCH_SET_ZONE_MODE = vol.Any(
    SCH_SET_ZONE_MODE,
    SCH_SET_ZONE_MODE_SETPOINT,
    SCH_SET_ZONE_MODE_UNTIL,
)

SCH_PUT_ZONE_TEMP = SCH_SET_ZONE_BASE.extend(
    {
        vol.Required(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)
        ),
    }
)

SVCS_CLIMATE_EVOHOME = {
    SVC_RESET_ZONE_CONFIG: SCH_SET_ZONE_BASE,
    SVC_RESET_ZONE_MODE: SCH_SET_ZONE_BASE,
    SVC_SET_ZONE_CONFIG: SCH_SET_ZONE_CONFIG,
    SVC_SET_ZONE_MODE: SCH_SET_ZONE_MODE,
    SVC_PUT_ZONE_TEMP: SCH_PUT_ZONE_TEMP,
}

#
# WaterHeater platform services for DHW
SVC_PUT_DHW_TEMP = "put_dhw_temp"
SVC_RESET_DHW_MODE = "reset_dhw_mode"
SVC_RESET_DHW_PARAMS = "reset_dhw_params"
SVC_SET_DHW_BOOST = "set_dhw_boost"
SVC_SET_DHW_MODE = "set_dhw_mode"
SVC_SET_DHW_PARAMS = "set_dhw_params"

# CONF_DHW_MODES = (
#     ZoneMode.PERMANENT,
#     ZoneMode.ADVANCED,
#     ZoneMode.TEMPORARY,
# )

SCH_SET_DHW_BASE = vol.Schema({})

SCH_SET_DHW_MODE = SCH_SET_DHW_BASE.extend(
    {
        vol.Optional(CONF_MODE): vol.In(
            [ZoneMode.SCHEDULE, ZoneMode.PERMANENT, ZoneMode.TEMPORARY]
        ),
        vol.Optional(CONF_ACTIVE): cv.boolean,
        vol.Exclusive(CONF_UNTIL, CONF_UNTIL): cv.datetime,
        vol.Exclusive(CONF_DURATION, CONF_UNTIL): vol.All(
            cv.time_period,
            vol.Range(min=td(minutes=5), max=td(days=1)),
        ),
    }
)

SCH_SET_DHW_CONFIG = SCH_SET_DHW_BASE.extend(
    {
        vol.Optional(CONF_SETPOINT, default=50): vol.All(
            cv.positive_float,
            vol.Range(min=30, max=85),
        ),
        vol.Optional(CONF_OVERRUN, default=5): vol.All(
            cv.positive_int,
            vol.Range(max=10),
        ),
        vol.Optional(CONF_DIFFERENTIAL, default=1): vol.All(
            cv.positive_float,
            vol.Range(max=10),
        ),
    }
)

SCH_PUT_DHW_TEMP = SCH_SET_ZONE_BASE.extend(
    {
        vol.Required(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)  # TODO: check limits
        ),
    }
)

SVCS_WATER_HEATER_EVOHOME = {
    SVC_RESET_DHW_MODE: SCH_SET_DHW_BASE,
    SVC_RESET_DHW_PARAMS: SCH_SET_DHW_BASE,
    SVC_SET_DHW_BOOST: SCH_SET_DHW_BASE,
    SVC_SET_DHW_MODE: SCH_SET_DHW_MODE,
    SVC_SET_DHW_PARAMS: SCH_SET_DHW_CONFIG,
    SVC_PUT_DHW_TEMP: SCH_PUT_DHW_TEMP,
}

#
# WaterHeater platform services for HVAC sensors
SZ_CO2_LEVEL = "put_co2_level"
SZ_INDOOR_HUMIDITY = "put_indoor_humidity"
SZ_PRESENCE_DETECT = "put_presence_detect"
SVC_PUT_CO2_LEVEL = f"put_{SZ_CO2_LEVEL}"
SVC_PUT_INDOOR_HUMIDITY = f"put_{SZ_INDOOR_HUMIDITY}"
SVC_PUT_PRESENCE_DETECT = f"put_{SZ_PRESENCE_DETECT}"

SCH_PUT_SENSOR_BASE = vol.Schema({vol.Required(CONF_ENTITY_ID): cv.entity_id})

SCH_PUT_CO2_LEVEL = SCH_PUT_SENSOR_BASE.extend(
    {
        vol.Required(SZ_CO2_LEVEL): vol.All(
            cv.positive_int,
            vol.Range(min=0, max=16384),
        ),
    }
)

SCH_PUT_INDOOR_HUMIDITY = SCH_PUT_SENSOR_BASE.extend(
    {
        vol.Required(SZ_INDOOR_HUMIDITY): vol.All(
            cv.positive_float,
            vol.Range(min=0, max=100),
        ),
    }
)

SCH_PUT_PRESENCE_DETECT = SCH_PUT_SENSOR_BASE.extend(
    {
        vol.Required(SZ_PRESENCE_DETECT): cv.bool,
    }
)

SVCS_BINARY_SENSORS = {
    SVC_PUT_PRESENCE_DETECT: SCH_PUT_PRESENCE_DETECT,
}

SVCS_SENSORS = {
    SVC_PUT_CO2_LEVEL: SCH_PUT_CO2_LEVEL,
    SVC_PUT_INDOOR_HUMIDITY: SCH_PUT_INDOOR_HUMIDITY,
}

#
# Configuration schema
SCAN_INTERVAL_DEFAULT = td(seconds=300)
SCAN_INTERVAL_MINIMUM = td(seconds=1)

SCH_PACKET_LOG = vol.Schema(
    {
        vol.Required(SZ_LOG_FILE_NAME): str,
        vol.Optional(SZ_LOG_ROTATE_BYTES, default=None): vol.Any(None, int),
        vol.Optional(SZ_LOG_ROTATE_BACKUPS, default=7): int,
    },
    extra=vol.PREVENT_EXTRA,
)

SCH_DEVICE_LIST = vol.Schema(
    vol.All([vol.Any(SCH_DEVICE_ANY, SCH_DEVICE)], vol.Length(min=0))
)

SZ_ADVANCED_FEATURES = "advanced_features"
SZ_MESSAGE_EVENTS = "message_events"
SZ_DEV_MODE = "dev_mode"
SZ_UNKNOWN_CODES = "unknown_codes"

SCH_ADVANCED_FEATURES = vol.Schema(
    {
        vol.Optional(SVC_SEND_PACKET, default=False): bool,
        vol.Optional(SZ_MESSAGE_EVENTS, default=False): bool,
        vol.Optional(SZ_DEV_MODE): bool,
        vol.Optional(SZ_UNKNOWN_CODES): bool,
    }
)

SZ_RESTORE_CACHE = "restore_cache"
SZ_RESTORE_SCHEMA = "restore_schema"
SZ_RESTORE_STATE = "restore_state"

SCH_RESTORE_CACHE = vol.Schema(
    {
        vol.Optional(SZ_RESTORE_SCHEMA, default=True): bool,
        vol.Optional(SZ_RESTORE_STATE, default=True): bool,
    }
)

# SCH_SCHEMA = SCH_TCS.extend({vol.Required(SZ_CONTROLLER): cv.string})
SCH_CONFIG = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(SZ_SERIAL_PORT): vol.Any(
                    cv.string,
                    SCH_SERIAL_CONFIG.extend({vol.Required(SZ_PORT_NAME): cv.string}),
                ),
                vol.Optional(SZ_KNOWN_LIST, default=[]): SCH_DEVICE_LIST,
                vol.Optional(SZ_BLOCK_LIST, default=[]): SCH_DEVICE_LIST,
                cv.deprecated(SZ_CONFIG, "ramses_rf"): vol.Any(),
                vol.Optional("ramses_rf", default={}): SCH_CONFIG,
                cv.deprecated(SZ_RESTORE_STATE, SZ_RESTORE_CACHE): vol.Any(),
                vol.Optional(SZ_RESTORE_CACHE, default=True): vol.Any(
                    bool, SCH_RESTORE_CACHE
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
                vol.Optional(SZ_PACKET_LOG): vol.Any(str, SCH_PACKET_LOG),
                cv.deprecated(SVC_SEND_PACKET, SZ_ADVANCED_FEATURES): vol.Any(),
                vol.Optional(SZ_ADVANCED_FEATURES, default={}): SCH_ADVANCED_FEATURES,
            },
            extra=vol.ALLOW_EXTRA,  # will be system, orphan schemas for ramses_rf
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def _is_subset(subset, superset) -> bool:  # TODO: move to ramses_rf?
    """Return True is one dict (or list/set) is a subset of another."""
    if isinstance(subset, dict):
        return all(
            key in superset and _is_subset(val, superset[key])
            for key, val in subset.items()
        )
    if isinstance(subset, list) or isinstance(subset, set):
        return all(
            any(_is_subset(subitem, superitem) for superitem in superset)
            for subitem in subset
        )
    return subset == superset  # not dict, list nor set


def _merge(src: dict, dst: dict, _dc: bool = None) -> dict:  # TODO: move to ramses_rf?
    """Merge src dict (precident) into the dst dict and return the result.

    run me with nosetests --with-doctest file.py

    >>> a = {'first': {'all_rows': {'pass': 'dog', 'number': '1'}}}
    >>> b = {'first': {'all_rows': {'fail': 'cat', 'number': '5'}}}
    >>> _merge(b, a) == {'first': {'all_rows': {'pass': 'dog', 'fail': 'cat', 'number': '5'}}}
    True
    """

    new_dst = dst if _dc else deepcopy(dst)  # start with copy of dst, merge src into it
    for key, value in src.items():  # values are only: dict, list, value or None

        if isinstance(value, dict):  # is dict
            node = new_dst.setdefault(key, {})  # get node or create one
            _merge(value, node, _dc=True)

        elif not isinstance(value, list):  # is value
            new_dst[key] = value  # src takes precidence, assert will fail

        elif key not in new_dst or not isinstance(new_dst[key], list):  # is list
            new_dst[key] = src[key]  # shouldn't happen: assert will fail

        else:
            new_dst[key] = list(set(src[key] + new_dst[key]))  # will sort

    # assert _is_subset(shrink(src), shrink(new_dst))
    return new_dst


@callback
def normalise_config(config: dict) -> tuple[str, dict, dict]:
    """Return a port/config/schema for the library."""

    config[SZ_CONFIG] = config.pop("ramses_rf")

    if isinstance(config[SZ_SERIAL_PORT], dict):
        serial_port = config[SZ_SERIAL_PORT].pop(SZ_PORT_NAME)
        config[SZ_CONFIG][SZ_EVOFW_FLAG] = config[SZ_SERIAL_PORT].pop(
            SZ_EVOFW_FLAG, None
        )
        config[SZ_CONFIG][SZ_SERIAL_CONFIG] = config.pop(SZ_SERIAL_PORT)
    else:
        serial_port = config.pop(SZ_SERIAL_PORT)

    config[SZ_KNOWN_LIST] = _normalise_device_list(config[SZ_KNOWN_LIST])
    config[SZ_BLOCK_LIST] = _normalise_device_list(config[SZ_BLOCK_LIST])

    if SZ_PACKET_LOG not in config:
        config[SZ_CONFIG][SZ_PACKET_LOG] = {}
    elif isinstance(config[SZ_PACKET_LOG], dict):
        config[SZ_CONFIG][SZ_PACKET_LOG] = config.pop(SZ_PACKET_LOG)
    else:
        config[SZ_CONFIG][SZ_PACKET_LOG] = {SZ_LOG_FILE_NAME: config.pop(SZ_PACKET_LOG)}

    if isinstance(config[SZ_RESTORE_CACHE], bool):
        config[SZ_RESTORE_CACHE] = {
            SZ_RESTORE_SCHEMA: config[SZ_RESTORE_CACHE],
            SZ_RESTORE_STATE: config[SZ_RESTORE_CACHE],
        }

    config[SZ_SCHEMA] = _normalise_schema(config.pop(SZ_SCHEMA, {}))

    broker_keys = (CONF_SCAN_INTERVAL, SZ_ADVANCED_FEATURES, SZ_RESTORE_CACHE)
    return (
        serial_port,
        {k: v for k, v in config.items() if k not in broker_keys},
        {k: v for k, v in config.items() if k in broker_keys},
    )


@callback
def _normalise_device_list(device_list) -> dict:
    """Convert a device_list schema into a ramses_rf format."""
    # convert: ['01:123456',    {'03:123456': None}, {'18:123456': {'a': 1, 'b': 2}}]
    #    into: {'01:123456': {}, '03:123456': {},     '18:123456': {'a': 1, 'b': 2}}
    if isinstance(device_list, list):
        result = [
            {k: v for k, v in x.items()} if isinstance(x, dict) else {x: None}
            for x in device_list
        ]
        return {k: v or {} for d in result for k, v in d.items()}

    # elif isinstance(device_list, dict):
    return {k: v or {} for k, v in device_list.items()}


@callback
def _normalise_schema(config_schema: dict) -> dict:
    """Normalise a config schema to a ramses_rf-compatible schema."""

    orphans_heat = config_schema.pop(SZ_ORPHANS_HEAT, [])
    orphans_hvac = config_schema.pop(SZ_ORPHANS_HVAC, [])

    if _ctl := config_schema.pop(SZ_CONTROLLER, None):
        result = {SZ_MAIN_CONTROLLER: _ctl, _ctl: SCH_TCS(config_schema)}
    else:
        result = config_schema  # would usually be be {}

    result[SZ_ORPHANS_HEAT] = orphans_heat
    result[SZ_ORPHANS_HVAC] = orphans_hvac

    return result


@callback
def merge_schemas(merge_cache: bool, config_schema: dict, cached_schema: dict) -> dict:
    """Return a hierarchy of schema to try (merged, config, {})."""

    if not merge_cache:
        _LOGGER.debug("A cached schema was not enabled (not recommended)")
        # cached_schema = {}  # in case is None
    else:
        _LOGGER.debug("Loaded a cached schema: %s", cached_schema)

    if not config_schema:  # could be None
        _LOGGER.debug("A config schema was not provided")
        config_schema = {}  # in case is None
    else:  # normalise config_schema
        _LOGGER.debug("Loaded a config schema: %s", config_schema)

    if not merge_cache or not cached_schema:
        _LOGGER.info(
            "Using the config schema (cached schema is not enabled / is invalid)"
            f", consider using '{SZ_RESTORE_CACHE}: {SZ_RESTORE_SCHEMA}: true'"
        )
        return {"the config": config_schema}  # maybe config = {}

    if _is_subset(shrink(config_schema), shrink(cached_schema)):
        _LOGGER.info(
            "Using the cached schema (cached schema is a superset of config schema)"
        )
        return {
            "the cached": cached_schema,
            "the config": config_schema,
        }  # maybe cached = config

    merged_schema = _merge(config_schema, cached_schema)  # config takes precidence
    _LOGGER.debug("Created a merged schema: %s", merged_schema)

    if not _is_subset(shrink(config_schema), shrink(merged_schema)):
        _LOGGER.info(
            "Using the config schema (merged schema not a superset of config schema)"
        )  # something went wrong!
        return {"the config": config_schema}  # maybe config = {}

    _LOGGER.warning(
        "Using a merged schema (cached schema is not a superset of config schema)"
        f", if required, use '{SZ_RESTORE_CACHE}: {SZ_RESTORE_SCHEMA}: false'"
    )
    return {
        "a merged (cached)": merged_schema,
        "the config": config_schema,
    }  # maybe merged = config
