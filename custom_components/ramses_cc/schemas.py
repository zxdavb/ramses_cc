#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC."""
from __future__ import annotations

import logging
from copy import deepcopy
from datetime import timedelta as td

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID as CONF_ENTITY_ID
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from ramses_rf.const import SZ_DEVICE_ID
from ramses_rf.helpers import merge, shrink
from ramses_rf.protocol.schemas import (
    SZ_PORT_CONFIG,
    SZ_SERIAL_PORT,
    extract_serial_port,
    sch_global_traits_dict_factory,
    sch_packet_log_dict_factory,
    sch_serial_port_dict_factory,
)
from ramses_rf.schemas import (
    SCH_DEVICE_ID_ANY,
    SCH_GATEWAY_DICT,
    SCH_GLOBAL_SCHEMAS_DICT,
    SCH_RESTORE_CACHE_DICT,
    SZ_CONFIG,
    SZ_RESTORE_CACHE,
    SZ_RESTORE_SCHEMA,
)

from .const import SYSTEM_MODE_LOOKUP, SystemMode, ZoneMode

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
CONF_SCHEDULE = "schedule"
CONF_SETPOINT = "setpoint"
CONF_TEMPERATURE = "temperature"
CONF_UNTIL = "until"

CONF_ACTIVE = "active"
CONF_DIFFERENTIAL = "differential"
CONF_OVERRUN = "overrun"

#
# Generic services for Integration/domain
SVC_FAKE_DEVICE = "fake_device"
SVC_FORCE_UPDATE = "force_update"
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
    SVC_FORCE_UPDATE: None,
    SVC_SEND_PACKET: SCH_SEND_PACKET,
}

_SCH_ENTITY_ID = vol.Schema({vol.Required(CONF_ENTITY_ID): cv.entity_id})

#
# Climate platform services for CH/DHW CTLs
SVC_RESET_SYSTEM_MODE = "reset_system_mode"
SVC_SET_SYSTEM_MODE = "set_system_mode"

SCH_SYSTEM_MODE = _SCH_ENTITY_ID.extend(
    {
        vol.Required(CONF_MODE): vol.In(SYSTEM_MODE_LOOKUP),  # incl. DAY_OFF_ECO
    }
)
SCH_SYSTEM_MODE_HOURS = _SCH_ENTITY_ID.extend(
    {
        vol.Required(CONF_MODE): vol.In([SystemMode.ECO_BOOST]),
        vol.Optional(CONF_DURATION, default=td(hours=1)): vol.All(
            cv.time_period, vol.Range(min=td(hours=1), max=td(hours=24))
        ),
    }
)
SCH_SYSTEM_MODE_DAYS = _SCH_ENTITY_ID.extend(
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

SVCS_CLIMATE_EVO_TCS = {
    SVC_RESET_SYSTEM_MODE: _SCH_ENTITY_ID,
    SVC_SET_SYSTEM_MODE: SCH_SYSTEM_MODE,
}

#
# Climate platform services for CH/DHW Zones
SVC_GET_ZONE_SCHED = "get_zone_schedule"
SVC_PUT_ZONE_TEMP = "put_zone_temp"
SVC_RESET_ZONE_CONFIG = "reset_zone_config"
SVC_RESET_ZONE_MODE = "reset_zone_mode"
SVC_SET_ZONE_CONFIG = "set_zone_config"
SVC_SET_ZONE_MODE = "set_zone_mode"
SVC_SET_ZONE_SCHED = "set_zone_schedule"

CONF_ZONE_MODES = (
    ZoneMode.SCHEDULE,
    ZoneMode.PERMANENT,
    ZoneMode.ADVANCED,
    ZoneMode.TEMPORARY,
)

SCH_SET_ZONE_CONFIG = _SCH_ENTITY_ID.extend(
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

SCH_SET_ZONE_MODE = _SCH_ENTITY_ID.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.SCHEDULE]),
    }
)
SCH_SET_ZONE_MODE_SETPOINT = _SCH_ENTITY_ID.extend(
    {
        vol.Optional(CONF_MODE): vol.In([ZoneMode.PERMANENT, ZoneMode.ADVANCED]),
        vol.Optional(CONF_SETPOINT, default=21): vol.All(
            cv.positive_float,
            vol.Range(min=5, max=30),
        ),
    }
)
SCH_SET_ZONE_MODE_UNTIL = _SCH_ENTITY_ID.extend(
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

SCH_PUT_ZONE_TEMP = _SCH_ENTITY_ID.extend(
    {
        vol.Required(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)
        ),
    }
)

SCH_SET_ZONE_SCHED = _SCH_ENTITY_ID.extend({vol.Required(CONF_SCHEDULE): str})


SVCS_CLIMATE_EVO_ZONE = {
    SVC_GET_ZONE_SCHED: _SCH_ENTITY_ID,
    SVC_PUT_ZONE_TEMP: SCH_PUT_ZONE_TEMP,
    SVC_RESET_ZONE_CONFIG: _SCH_ENTITY_ID,
    SVC_RESET_ZONE_MODE: _SCH_ENTITY_ID,
    SVC_SET_ZONE_CONFIG: SCH_SET_ZONE_CONFIG,
    SVC_SET_ZONE_MODE: SCH_SET_ZONE_MODE,
    SVC_SET_ZONE_SCHED: SCH_SET_ZONE_SCHED,
}

#
# WaterHeater platform services for CH/DHW
SVC_GET_DHW_SCHED = "get_dhw_schedule"
SVC_PUT_DHW_TEMP = "put_dhw_temp"
SVC_RESET_DHW_MODE = "reset_dhw_mode"
SVC_RESET_DHW_PARAMS = "reset_dhw_params"
SVC_SET_DHW_BOOST = "set_dhw_boost"
SVC_SET_DHW_MODE = "set_dhw_mode"
SVC_SET_DHW_PARAMS = "set_dhw_params"
SVC_SET_DHW_SCHED = "set_dhw_schedule"

# CONF_DHW_MODES = (
#     ZoneMode.PERMANENT,
#     ZoneMode.ADVANCED,
#     ZoneMode.TEMPORARY,
# )

SCH_SET_DHW_MODE = _SCH_ENTITY_ID.extend(
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

SCH_SET_DHW_CONFIG = _SCH_ENTITY_ID.extend(
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

SCH_PUT_DHW_TEMP = _SCH_ENTITY_ID.extend(
    {
        vol.Required(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=-20, max=99)
        ),
    }
)

SCH_SET_DHW_SCHED = _SCH_ENTITY_ID.extend({vol.Required(CONF_SCHEDULE): str})


SVCS_WATER_HEATER_EVO_DHW = {
    SVC_GET_DHW_SCHED: _SCH_ENTITY_ID,
    SVC_RESET_DHW_MODE: _SCH_ENTITY_ID,
    SVC_RESET_DHW_PARAMS: _SCH_ENTITY_ID,
    SVC_SET_DHW_BOOST: _SCH_ENTITY_ID,
    SVC_SET_DHW_MODE: SCH_SET_DHW_MODE,
    SVC_SET_DHW_PARAMS: SCH_SET_DHW_CONFIG,
    SVC_PUT_DHW_TEMP: SCH_PUT_DHW_TEMP,
    SVC_SET_DHW_SCHED: SCH_SET_DHW_SCHED,
}

#
# BinarySensor/Sensor platform services for HVAC
SZ_CO2_LEVEL = "co2_level"
SZ_INDOOR_HUMIDITY = "indoor_humidity"
SZ_PRESENCE_DETECTED = "presence_detected"
SVC_PUT_CO2_LEVEL = f"put_{SZ_CO2_LEVEL}"
SVC_PUT_INDOOR_HUMIDITY = f"put_{SZ_INDOOR_HUMIDITY}"
SVC_PUT_PRESENCE_DETECT = f"put_{SZ_PRESENCE_DETECTED}"

SCH_PUT_CO2_LEVEL = _SCH_ENTITY_ID.extend(
    {
        vol.Required(SZ_CO2_LEVEL): vol.All(
            cv.positive_int,
            vol.Range(min=0, max=16384),
        ),
    }
)

SCH_PUT_INDOOR_HUMIDITY = _SCH_ENTITY_ID.extend(
    {
        vol.Required(SZ_INDOOR_HUMIDITY): vol.All(
            cv.positive_float,
            vol.Range(min=0, max=100),
        ),
    }
)

SCH_PUT_PRESENCE_DETECT = _SCH_ENTITY_ID.extend(
    {
        vol.Required(SZ_PRESENCE_DETECTED): cv.boolean,
    }
)

SVCS_BINARY_SENSOR = {
    SVC_PUT_PRESENCE_DETECT: SCH_PUT_PRESENCE_DETECT,
}

SVCS_SENSOR = {
    SVC_PUT_CO2_LEVEL: SCH_PUT_CO2_LEVEL,
    SVC_PUT_INDOOR_HUMIDITY: SCH_PUT_INDOOR_HUMIDITY,
}

#
# Remote platform services for HVAC
SZ_COMMAND = "command"
SZ_TIMEOUT = "timeout"
SZ_REPEATS = "repeats"
SZ_DELAY = "delay"
SVC_DELETE_COMMAND = "delete_command"
SVC_LEARN_COMMAND = "learn_command"
SVC_SEND_COMMAND = "send_command"

SCH_LEARN_COMMAND_BASE = _SCH_ENTITY_ID.extend({vol.Required(SZ_COMMAND): cv.string})
SCH_LEARN_COMMAND = SCH_LEARN_COMMAND_BASE.extend(
    {
        vol.Required(SZ_TIMEOUT): cv.positive_int,
    }
)
SCH_SEND_COMMAND = SCH_LEARN_COMMAND_BASE.extend(
    {
        vol.Required(SZ_REPEATS): cv.positive_int,
        vol.Required(SZ_DELAY): cv.positive_float,
    }
)

SVCS_REMOTE = {
    SVC_DELETE_COMMAND: SCH_LEARN_COMMAND_BASE,
    SVC_LEARN_COMMAND: SCH_LEARN_COMMAND,
    SVC_SEND_COMMAND: SCH_LEARN_COMMAND_BASE,
}

#
# Configuration schema for Integration/domain
SCAN_INTERVAL_DEFAULT = td(seconds=60)
SCAN_INTERVAL_MINIMUM = td(seconds=3)

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

SCH_GLOBAL_TRAITS_DICT, SCH_TRAITS = sch_global_traits_dict_factory(
    hvac_traits={vol.Optional("commands"): dict}
)
SCH_DEVICE_LIST = vol.Schema(
    [{vol.Optional(SCH_DEVICE_ID_ANY): SCH_TRAITS}],  # vol.Length(min=0)
    extra=vol.PREVENT_EXTRA,
)  # TODO: what is this for?

SCH_DOMAIN_CONFIG = (
    vol.Schema(
        {
            vol.Optional("ramses_rf", default={}): SCH_GATEWAY_DICT,
            vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT): vol.All(
                cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)
            ),
            vol.Optional(SZ_ADVANCED_FEATURES, default={}): SCH_ADVANCED_FEATURES,
        },
        extra=vol.PREVENT_EXTRA,  # will be system, orphan schemas for ramses_rf
    )
    .extend(SCH_GLOBAL_SCHEMAS_DICT)
    .extend(SCH_GLOBAL_TRAITS_DICT)
    .extend(sch_packet_log_dict_factory(default_backups=7))
    .extend(SCH_RESTORE_CACHE_DICT)
    .extend(sch_serial_port_dict_factory())
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


@callback
def normalise_config(config: dict) -> tuple[str, dict, dict]:
    """Return a port/client_config/broker_config for the library."""

    config = deepcopy(config)

    config[SZ_CONFIG] = config.pop("ramses_rf")

    port_name, port_config = extract_serial_port(config.pop(SZ_SERIAL_PORT))

    remote_commands = {
        k: v.pop("commands")
        for k, v in config["known_list"].items()
        if v.get("commands")
    }

    broker_keys = (CONF_SCAN_INTERVAL, SZ_ADVANCED_FEATURES, SZ_RESTORE_CACHE)
    return (
        port_name,
        {k: v for k, v in config.items() if k not in broker_keys}
        | {SZ_PORT_CONFIG: port_config},
        {k: v for k, v in config.items() if k in broker_keys}
        | {"remotes": remote_commands},
    )


@callback
def merge_schemas(merge_cache: bool, config_schema: dict, cached_schema: dict) -> dict:
    """Return a hierarchy of schema to try (merged/cached, config)."""

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

    merged_schema = merge(config_schema, cached_schema)  # config takes precidence
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
        "a merged (config/cached)": merged_schema,
        "the config": config_schema,
    }  # maybe merged = config
