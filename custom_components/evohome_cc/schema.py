#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others."""

import logging
from datetime import timedelta as td
from typing import Tuple

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID as CONF_ENTITY_ID
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from ramses_rf.protocol.schema import LOG_FILE_NAME, LOG_ROTATE_BYTES, LOG_ROTATE_COUNT
from ramses_rf.schema import (
    BLOCK_LIST,
    CONFIG,
    CONFIG_SCHEMA,
    DEVICE_DICT,
    DEVICE_ID,
    EVOFW_FLAG,
    KNOWN_LIST,
    PACKET_LOG,
    PORT_NAME,
    SERIAL_CONFIG,
    SERIAL_CONFIG_SCHEMA,
    SERIAL_PORT,
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

# Configuration schema
SCAN_INTERVAL_DEFAULT = td(seconds=300)
SCAN_INTERVAL_MINIMUM = td(seconds=1)

CONF_RESTORE_CACHE = "restore_schema"

PACKET_LOG_SCHEMA = vol.Schema(
    {
        vol.Required(LOG_FILE_NAME): str,
        vol.Optional(LOG_ROTATE_BYTES, default=None): vol.Any(None, int),
        vol.Optional(LOG_ROTATE_COUNT, default=7): vol.All(
            int, vol.Range(min=0, max=7)
        ),
    },
    extra=vol.PREVENT_EXTRA,
)

# Integration domain services for System/Controller
SVC_FAKE_DEVICE = "fake_device"
SVC_REFRESH_SYSTEM = "refresh_system"
SVC_RESET_SYSTEM_MODE = "reset_system_mode"
SVC_SEND_PACKET = "send_packet"
SVC_SET_SYSTEM_MODE = "set_system_mode"

FAKE_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.Match(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Optional("create_device", default=False): vol.Any(None, bool),
        vol.Optional("start_binding", default=False): vol.Any(None, bool),
    }
)
SEND_PACKET_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.Match(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Required("verb"): vol.In((" I", "RQ", "RP", " W")),
        vol.Required("code"): vol.Match(r"^[0-9A-F]{4}$"),
        vol.Required("payload"): vol.Match(r"^[0-9A-F]{1,48}$"),
    }
)
SET_SYSTEM_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In(SYSTEM_MODE_LOOKUP),  # incl. DAY_OFF_ECO
    }
)
SET_SYSTEM_MODE_SCHEMA_HOURS = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In([SystemMode.ECO_BOOST]),
        vol.Optional(CONF_DURATION, default=td(hours=1)): vol.All(
            cv.time_period, vol.Range(min=td(hours=1), max=td(hours=24))
        ),
    }
)
SET_SYSTEM_MODE_SCHEMA_DAYS = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In(
            [SystemMode.AWAY, SystemMode.CUSTOM, SystemMode.DAY_OFF]
        ),
        vol.Optional(CONF_DURATION_DAYS, default=td(days=0)): vol.All(
            cv.time_period, vol.Range(min=td(days=0), max=td(days=99))
        ),  # 0 means until the end of the day
    }
)
SET_SYSTEM_MODE_SCHEMA = vol.Any(
    SET_SYSTEM_MODE_SCHEMA, SET_SYSTEM_MODE_SCHEMA_HOURS, SET_SYSTEM_MODE_SCHEMA_DAYS
)

DOMAIN_SERVICES = {
    SVC_FAKE_DEVICE: FAKE_DEVICE_SCHEMA,
    SVC_REFRESH_SYSTEM: None,
    SVC_RESET_SYSTEM_MODE: None,
    SVC_SEND_PACKET: SEND_PACKET_SCHEMA,
    SVC_SET_SYSTEM_MODE: SET_SYSTEM_MODE_SCHEMA,
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

SET_ZONE_BASE_SCHEMA = vol.Schema({vol.Required(CONF_ENTITY_ID): cv.entity_id})

SET_ZONE_CONFIG_SCHEMA = SET_ZONE_BASE_SCHEMA.extend(
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

SET_ZONE_MODE_SCHEMA = SET_ZONE_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.SCHEDULE]),
    }
)
SET_ZONE_MODE_SCHEMA_SETPOINT = SET_ZONE_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.PERMANENT, ZoneMode.ADVANCED]),
        vol.Optional(CONF_SETPOINT, default=21): vol.All(
            cv.positive_float,
            vol.Range(min=5, max=30),
        ),
    }
)
SET_ZONE_MODE_SCHEMA_UNTIL = SET_ZONE_BASE_SCHEMA.extend(
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
SET_ZONE_MODE_SCHEMA = vol.Any(
    SET_ZONE_MODE_SCHEMA,
    SET_ZONE_MODE_SCHEMA_SETPOINT,
    SET_ZONE_MODE_SCHEMA_UNTIL,
)

PUT_ZONE_TEMP_SCHEMA = SET_ZONE_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)
        ),
    }
)

CLIMATE_SERVICES = {
    SVC_RESET_ZONE_CONFIG: SET_ZONE_BASE_SCHEMA,
    SVC_RESET_ZONE_MODE: SET_ZONE_BASE_SCHEMA,
    SVC_SET_ZONE_CONFIG: SET_ZONE_CONFIG_SCHEMA,
    SVC_SET_ZONE_MODE: SET_ZONE_MODE_SCHEMA,
    SVC_PUT_ZONE_TEMP: PUT_ZONE_TEMP_SCHEMA,
}

# WaterHeater platform services for DHW
SVC_PUT_DHW_TEMP = "put_dhw_temp"
SVC_RESET_DHW_MODE = "reset_dhw_mode"
SVC_RESET_DHW_PARAMS = "reset_dhw_params"
SVC_SET_DHW_BOOST = "set_dhw_boost"
SVC_SET_DHW_MODE = "set_dhw_mode"
SVC_SET_DHW_PARAMS = "set_dhw_params"

CONF_DHW_MODES = (
    ZoneMode.PERMANENT,
    ZoneMode.ADVANCED,
    ZoneMode.TEMPORARY,
)

SET_DHW_BASE_SCHEMA = vol.Schema({})

SET_DHW_MODE_SCHEMA = SET_DHW_BASE_SCHEMA.extend(
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

SET_DHW_CONFIG_SCHEMA = SET_DHW_BASE_SCHEMA.extend(
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

PUT_DHW_TEMP_SCHEMA = SET_ZONE_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)  # TODO: check limits
        ),
    }
)

WATER_HEATER_SERVICES = {
    SVC_RESET_DHW_MODE: SET_DHW_BASE_SCHEMA,
    SVC_RESET_DHW_PARAMS: SET_DHW_BASE_SCHEMA,
    SVC_SET_DHW_BOOST: SET_DHW_BASE_SCHEMA,
    SVC_SET_DHW_MODE: SET_DHW_MODE_SCHEMA,
    SVC_SET_DHW_PARAMS: SET_DHW_CONFIG_SCHEMA,
    SVC_PUT_DHW_TEMP: PUT_DHW_TEMP_SCHEMA,
}

DEVICE_LIST = vol.Schema(vol.All([vol.Any(DEVICE_ID, DEVICE_DICT)], vol.Length(min=0)))

ADVANCED_FEATURES = "advanced_features"
MESSAGE_EVENTS = "message_events"
DEV_MODE = "dev_mode"
UNKNOWN_CODES = "unknown_codes"
ADVANCED_FEATURES_SCHEMA = vol.Schema(
    {
        vol.Optional(SVC_SEND_PACKET, default=False): bool,
        vol.Optional(MESSAGE_EVENTS, default=False): bool,
        vol.Optional(DEV_MODE, default=False): bool,
        vol.Optional(UNKNOWN_CODES, default=False): bool,
    }
)
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(SERIAL_PORT): vol.Any(
                    cv.string,
                    SERIAL_CONFIG_SCHEMA.extend({vol.Required(PORT_NAME): cv.string}),
                ),
                vol.Optional(KNOWN_LIST, default=[]): DEVICE_LIST,
                vol.Optional(BLOCK_LIST, default=[]): DEVICE_LIST,
                cv.deprecated(CONFIG, "ramses_rf"): vol.Any(),
                vol.Optional("ramses_rf", default={}): CONFIG_SCHEMA,
                cv.deprecated("restore_state", CONF_RESTORE_CACHE): vol.Any(),
                vol.Optional(CONF_RESTORE_CACHE, default=True): vol.Any(bool),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
                vol.Optional(PACKET_LOG): vol.Any(str, PACKET_LOG_SCHEMA),
                cv.deprecated(SVC_SEND_PACKET, ADVANCED_FEATURES): vol.Any(),
                vol.Optional(ADVANCED_FEATURES, default={}): ADVANCED_FEATURES_SCHEMA,
            },
            extra=vol.ALLOW_EXTRA,  # will be system schemas
        )
    },
    extra=vol.ALLOW_EXTRA,
)


@callback
def normalise_device_list(device_list) -> dict:
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
def normalise_config_schema(config, store) -> Tuple[str, dict]:
    """Convert a HA config dict into the client library's own format."""

    _LOGGER.debug("\r\n\nConfig = %s\r\n", config)
    _LOGGER.debug("\r\n\nStore = %s\r\n", store)

    schema = {}

    if config[CONF_RESTORE_CACHE]:
        schema = store["client_state"].get("schema") if "client_state" in store else {}
        if schema:
            _LOGGER.warning("Using a Schema restored from cache: %s", schema)

    if (
        not schema
        and (_schema := config.get("schema"))
        and (ctl_id := _schema.pop("controller", None))
    ):
        schema = {"main_controller": ctl_id, ctl_id: _schema}
        if schema:
            _LOGGER.warning("Using a Schema loaded from configuration file: %s", schema)

    if not schema:
        _LOGGER.warning("Using an empty Schema: %s", {})

    config = {
        k: v
        for k, v in config.items()
        if k
        not in (
            CONF_RESTORE_CACHE,
            CONF_SCAN_INTERVAL,
            SVC_SEND_PACKET,
            "schema",
        )
    }
    config[CONFIG] = config.pop("ramses_rf")

    if isinstance(config[SERIAL_PORT], dict):
        serial_port = config[SERIAL_PORT].pop(PORT_NAME)
        config[CONFIG][EVOFW_FLAG] = config[SERIAL_PORT].pop(EVOFW_FLAG, None)
        config[CONFIG][SERIAL_CONFIG] = config.pop(SERIAL_PORT)
    else:
        serial_port = config.pop(SERIAL_PORT)

    if PACKET_LOG not in config:
        config[CONFIG][PACKET_LOG] = {}
    elif isinstance(config[PACKET_LOG], dict):
        config[CONFIG][PACKET_LOG] = config.pop(PACKET_LOG)
    else:
        config[CONFIG][PACKET_LOG] = PACKET_LOG_SCHEMA(
            {LOG_FILE_NAME: config.pop(PACKET_LOG)}
        )

    config[KNOWN_LIST] = normalise_device_list(config[KNOWN_LIST])
    config[BLOCK_LIST] = normalise_device_list(config[BLOCK_LIST])

    return serial_port, config, schema
