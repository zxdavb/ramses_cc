#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC."""

import logging
from datetime import timedelta as td

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID as CONF_ENTITY_ID
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from ramses_rf.const import SZ_DEVICE_ID
from ramses_rf.helpers import shrink
from ramses_rf.protocol.schema import LOG_FILE_NAME, LOG_ROTATE_BYTES, LOG_ROTATE_COUNT
from ramses_rf.protocol.schema import PORT_NAME as SZ_PORT_NAME
from ramses_rf.protocol.schema import SERIAL_PORT as SZ_SERIAL_PORT
from ramses_rf.schema import CONFIG_SCHEMA, DEV_REGEX_ANY
from ramses_rf.schema import EVOFW_FLAG as SZ_EVOFW_FLAG
from ramses_rf.schema import PACKET_LOG as SZ_PACKET_LOG
from ramses_rf.schema import SCH_DEVICE
from ramses_rf.schema import SERIAL_CONFIG as SZ_SERIAL_CONFIG
from ramses_rf.schema import SERIAL_CONFIG_SCHEMA as SCH_SERIAL_CONFIG
from ramses_rf.schema import SZ_BLOCK_LIST, SZ_CONFIG, SZ_KNOWN_LIST

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

# Configuration schema
SCAN_INTERVAL_DEFAULT = td(seconds=300)
SCAN_INTERVAL_MINIMUM = td(seconds=1)

SCH_PACKET_LOG = vol.Schema(
    {
        vol.Required(LOG_FILE_NAME): str,
        vol.Optional(LOG_ROTATE_BYTES, default=None): vol.Any(None, int),
        vol.Optional(LOG_ROTATE_COUNT, default=7): int,
    },
    extra=vol.PREVENT_EXTRA,
)

# Integration domain services for System/Controller
SVC_FAKE_DEVICE = "fake_device"
SVC_REFRESH_SYSTEM = "refresh_system"
SVC_RESET_SYSTEM_MODE = "reset_system_mode"
SVC_SEND_PACKET = "send_packet"
SVC_SET_SYSTEM_MODE = "set_system_mode"

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

SVCS_DOMAIN = {
    SVC_FAKE_DEVICE: SCH_FAKE_DEVICE,
    SVC_REFRESH_SYSTEM: None,
    SVC_SEND_PACKET: SCH_SEND_PACKET,
}

SVCS_DOMAIN_EVOHOME = {
    SVC_RESET_SYSTEM_MODE: None,
    SVC_SET_SYSTEM_MODE: SCH_SYSTEM_MODE,
}

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

SCH_DEVICE_LIST = vol.Schema(
    vol.All([vol.Any(DEV_REGEX_ANY, SCH_DEVICE)], vol.Length(min=0))
)

SZ_ADVANCED_FEATURES = "advanced_features"
SZ_MESSAGE_EVENTS = "message_events"
SZ_DEV_MODE = "dev_mode"
SZ_UNKNOWN_CODES = "unknown_codes"

SCH_ADVANCED_FEATURES = vol.Schema(
    {
        vol.Optional(SVC_SEND_PACKET, default=False): bool,
        vol.Optional(SZ_MESSAGE_EVENTS, default=False): bool,
        vol.Optional(SZ_DEV_MODE, default=False): bool,
        vol.Optional(SZ_UNKNOWN_CODES, default=False): bool,
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

SZ_SCHEMA = "schema"
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
                vol.Optional("ramses_rf", default={}): CONFIG_SCHEMA,
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


def _merge(src: dict, dst: dict) -> dict:  # TODO: move to ramses_rf?
    """Merge src dict (precident) into the dst dict and return the result.

    run me with nosetests --with-doctest file.py

    >>> a = {'first': {'all_rows': {'pass': 'dog', 'number': '1'}}}
    >>> b = {'first': {'all_rows': {'fail': 'cat', 'number': '5'}}}
    >>> _merge(b, a) == {'first': {'all_rows': {'pass': 'dog', 'fail': 'cat', 'number': '5'}}}
    True
    """
    from copy import deepcopy

    dst = deepcopy(dst)
    for key, value in src.items():
        if isinstance(value, dict):
            node = dst.setdefault(key, {})  # get node or create one
            _merge(value, node)
        elif isinstance(value, list):
            dst[key] = list(set(src[key] + dst[key]))
        else:
            dst[key] = value  # src takes precidence

    assert _is_subset(src, dst)
    return dst


@callback
def normalise_hass_config(hass_config: dict, storage: dict) -> dict:
    """Return a port/config/schema for the library (modifies hass_config)."""

    hass_config[SZ_CONFIG] = hass_config.pop("ramses_rf")

    if isinstance(hass_config[SZ_SERIAL_PORT], dict):
        serial_port = hass_config[SZ_SERIAL_PORT].pop(SZ_PORT_NAME)
        hass_config[SZ_CONFIG][SZ_EVOFW_FLAG] = hass_config[SZ_SERIAL_PORT].pop(
            SZ_EVOFW_FLAG, None
        )
        hass_config[SZ_CONFIG][SZ_SERIAL_CONFIG] = hass_config.pop(SZ_SERIAL_PORT)
    else:
        serial_port = hass_config.pop(SZ_SERIAL_PORT)

    hass_config[SZ_KNOWN_LIST] = _normalise_device_list(hass_config[SZ_KNOWN_LIST])
    hass_config[SZ_BLOCK_LIST] = _normalise_device_list(hass_config[SZ_BLOCK_LIST])

    if SZ_PACKET_LOG not in hass_config:
        hass_config[SZ_CONFIG][SZ_PACKET_LOG] = {}
    elif isinstance(hass_config[SZ_PACKET_LOG], dict):
        hass_config[SZ_CONFIG][SZ_PACKET_LOG] = hass_config.pop(SZ_PACKET_LOG)
    else:
        hass_config[SZ_CONFIG][SZ_PACKET_LOG] = {
            LOG_FILE_NAME: hass_config.pop(SZ_PACKET_LOG)
        }

    if isinstance(hass_config[SZ_RESTORE_CACHE], bool):
        hass_config[SZ_RESTORE_CACHE] = {
            SZ_RESTORE_SCHEMA: hass_config[SZ_RESTORE_CACHE],
            SZ_RESTORE_STATE: hass_config[SZ_RESTORE_CACHE],
        }

    schema = _normalise_schema(
        hass_config[SZ_RESTORE_CACHE][SZ_RESTORE_SCHEMA],
        hass_config.get(SZ_SCHEMA),
        storage["client_state"].get(SZ_SCHEMA, {}) if "client_state" in storage else {},
    )

    unwanted_keys = (CONF_SCAN_INTERVAL, SZ_ADVANCED_FEATURES, SZ_RESTORE_CACHE)
    library_config = {k: v for k, v in hass_config.items() if k not in unwanted_keys}

    return serial_port, library_config, schema


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
def _normalise_schema(restore_cache, config_schema, cached_schema) -> dict:
    """Return a ramses system schema extracted from the merged config/store."""

    if not restore_cache:
        _LOGGER.debug("A cached schema was not enabled (not recommended)")
        # cached_schema = {}  # in case is None
    else:
        _LOGGER.debug("Loaded a cached schema: %s", cached_schema)

    if not config_schema:
        _LOGGER.debug("A config schema was not provided")
        config_schema = {}  # in case is None
    else:  # normalise config_schema
        _LOGGER.debug("Loaded a config schema: %s", config_schema)
        orphans_heat = config_schema.pop("orphans_heat", [])
        orphans_hvac = config_schema.pop("orphans_hvac", [])
        if _ctl := config_schema.pop("controller", None):
            config_schema = {"main_controller": _ctl, _ctl: config_schema}
        config_schema["orphans_heat"] = orphans_heat
        config_schema["orphans_hvac"] = orphans_hvac

    if not cached_schema:
        _LOGGER.info(
            "Using a config schema (cached schema is not enabled/invalid)"
            f", consider using '{SZ_RESTORE_CACHE}: {SZ_RESTORE_SCHEMA}: true'"
        )
        return config_schema

    elif _is_subset(shrink(config_schema), shrink(cached_schema)):
        _LOGGER.info(
            "Using a cached schema (cached schema is a superset of config schema)"
        )
        return cached_schema

    schema = _merge(config_schema, cached_schema)  # config takes precidence
    assert _is_subset(shrink(config_schema), shrink(schema))

    _LOGGER.debug("Created a merged schema: %s", schema)
    _LOGGER.warning(
        "Using a merged schema (cached schema is not a superset of config schema)"
        f", if required, use '{SZ_RESTORE_CACHE}: {SZ_RESTORE_SCHEMA}: false'"
    )
    return schema
