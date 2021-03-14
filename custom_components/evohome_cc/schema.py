#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome."""

from datetime import timedelta as td

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID as CONF_ENTITY_ID
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.helpers import config_validation as cv

from .const import (  # CONF_MODE,; CONF_SETPOINT,; CONF_DURATION,; CONF_UNTIL,; CONF_MAX_TEMP,; CONF_MIN_TEMP,; CONF_LOCAL_OVERRIDE,; CONF_OPENWINDOW,; CONF_MULTIROOM,; CONF_DURATION_DAYS,; CONF_DURATION_HOURS,
    DOMAIN,
    SystemMode,
    ZoneMode,
)

CONF_MODE = "mode"
CONF_SETPOINT = "setpoint"
CONF_DURATION = "duration"
CONF_UNTIL = "until"

CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_LOCAL_OVERRIDE = "local_override"
CONF_OPENWINDOW = "openwindow_function"
CONF_MULTIROOM = "multiroom_mode"
CONF_DURATION_DAYS = "period"
CONF_DURATION_HOURS = "days"

CONF_ACTIVE = "active"
CONF_OVERRUN = "overrun"
CONF_DIFFERENTIAL = "differential"

CONF_SYSTEM_MODES = (
    SystemMode.AUTO,
    SystemMode.AWAY,
    SystemMode.HEAT_OFF,
    SystemMode.RESET,
)
CONF_DHW_MODES = (ZoneMode.PERMANENT, ZoneMode.ADVANCED, ZoneMode.TEMPORARY)
CONF_ZONE_MODES = (
    ZoneMode.SCHEDULE,
    ZoneMode.PERMANENT,
    ZoneMode.ADVANCED,
    ZoneMode.TEMPORARY,
)

# Configuration schema
SCAN_INTERVAL_DEFAULT = td(seconds=300)
SCAN_INTERVAL_MINIMUM = td(seconds=10)

CONF_SERIAL_PORT = "serial_port"
CONF_CONFIG = "config"
CONF_SCHEMA = "schema"
CONF_GATEWAY_ID = "gateway_id"
CONF_PACKET_LOG = "packet_log"
CONF_MAX_ZONES = "max_zones"

CONF_ALLOW_LIST = "allow_list"
CONF_BLOCK_LIST = "block_list"
LIST_MSG = f"{CONF_ALLOW_LIST} and {CONF_BLOCK_LIST} are mutally exclusive"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                # vol.Optional(CONF_GATEWAY_ID): vol.Match(r"^18:[0-9]{6}$"),
                vol.Required(CONF_SERIAL_PORT): cv.string,
                vol.Optional("serial_config"): dict,
                vol.Required(CONF_CONFIG): vol.Schema(
                    {
                        vol.Optional(CONF_MAX_ZONES, default=12): vol.Any(None, int),
                        vol.Optional(CONF_PACKET_LOG): cv.string,
                        vol.Optional("enforce_allowlist"): bool,
                    }
                ),
                vol.Optional(CONF_SCHEMA): dict,
                vol.Exclusive(CONF_ALLOW_LIST, "device_filter", msg=LIST_MSG): list,
                vol.Exclusive(CONF_BLOCK_LIST, "device_filter", msg=LIST_MSG): list,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
            },
            extra=vol.ALLOW_EXTRA,  # TODO: remove for production
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# Integration domain services for System/Controller
SVC_REFRESH_SYSTEM = "force_refresh"
SVC_RESET_SYSTEM = "reset_system"
SVC_SET_SYSTEM_MODE = "set_system_mode"

SET_SYSTEM_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In(CONF_SYSTEM_MODES),
    }
)
SET_SYSTEM_MODE_SCHEMA_HOURS = vol.Schema(
    {
        vol.Required(CONF_MODE): vol.In([SystemMode.ECO]),
        vol.Optional(CONF_DURATION_HOURS, default=td(hours=1)): vol.All(
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
    SVC_REFRESH_SYSTEM: None,
    SVC_RESET_SYSTEM: None,
    SVC_SET_SYSTEM_MODE: SET_SYSTEM_MODE_SCHEMA,
}

# Climate platform services for Zone
SVC_RESET_ZONE_CONFIG = "reset_zone_config"
SVC_RESET_ZONE_MODE = "reset_zone_mode"
SVC_SET_ZONE_CONFIG = "set_zone_config"
SVC_SET_ZONE_MODE = "set_zone_mode"

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
        vol.Exclusive(CONF_UNTIL, "until"): cv.datetime,
        vol.Exclusive(CONF_DURATION, "until"): vol.All(
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

CLIMATE_SERVICES = {
    SVC_RESET_ZONE_CONFIG: SET_ZONE_BASE_SCHEMA,
    SVC_RESET_ZONE_MODE: SET_ZONE_BASE_SCHEMA,
    SVC_SET_ZONE_CONFIG: SET_ZONE_CONFIG_SCHEMA,
    SVC_SET_ZONE_MODE: SET_ZONE_MODE_SCHEMA,
}

# WaterHeater platform services for DHW
SVC_RESET_DHW_MODE = "reset_dhw_mode"
SVC_RESET_DHW_CONFIG = "reset_dhw_params"
SVC_SET_DHW_BOOST = "set_dhw_boost"
SVC_SET_DHW_MODE = "set_dhw_mode"
SVC_SET_DHW_PARAMS = "set_dhw_params"

SET_DHW_BASE_SCHEMA = vol.Schema({vol.Required(CONF_ENTITY_ID): cv.entity_id})

SET_DHW_MODE_SCHEMA = SET_DHW_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_MODE): vol.In(
            [ZoneMode.SCHEDULE, ZoneMode.PERMANENT, ZoneMode.TEMPORARY]
        ),
        vol.Optional(CONF_ACTIVE): cv.boolean,
        vol.Exclusive(CONF_UNTIL, "until"): cv.datetime,
        vol.Exclusive(CONF_DURATION, "until"): vol.All(
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

WATER_HEATER_SERVICES = {
    SVC_RESET_DHW_MODE: SET_DHW_BASE_SCHEMA,
    SVC_RESET_DHW_CONFIG: SET_DHW_BASE_SCHEMA,
    SVC_SET_DHW_BOOST: SET_DHW_BASE_SCHEMA,
    SVC_SET_DHW_MODE: SET_DHW_MODE_SCHEMA,
    SVC_SET_DHW_PARAMS: SET_DHW_CONFIG_SCHEMA,
}
