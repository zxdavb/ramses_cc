"""Schemas for RAMSES integration."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta as td
import logging

from ramses_rf.const import SZ_DEVICE_ID
from ramses_rf.helpers import merge, shrink
from ramses_rf.schemas import (
    SCH_DEVICE_ID_ANY,
    SCH_GATEWAY_CONFIG,
    SCH_GLOBAL_SCHEMAS_DICT,
    SCH_RESTORE_CACHE_DICT,
    SZ_CONFIG,
    SZ_RESTORE_CACHE,
)
from ramses_tx.schemas import (
    SCH_ENGINE_DICT,
    SZ_PORT_CONFIG,
    SZ_SERIAL_PORT,
    extract_serial_port,
    sch_global_traits_dict_factory,
    sch_packet_log_dict_factory,
    sch_serial_port_dict_factory,
)
import voluptuous as vol

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import ZoneMode

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
        vol.Required(SZ_DEVICE_ID): cv.matches_regex(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Optional("create_device", default=False): vol.Any(None, cv.boolean),
        vol.Optional("start_binding", default=False): vol.Any(None, cv.boolean),
    }
)
SCH_SEND_PACKET = vol.Schema(
    {
        vol.Required(SZ_DEVICE_ID): cv.matches_regex(r"^[0-9]{2}:[0-9]{6}$"),
        vol.Required("verb"): vol.In((" I", "I", "RQ", "RP", " W", "W")),
        vol.Required("code"): cv.matches_regex(r"^[0-9A-F]{4}$"),
        vol.Required("payload"): cv.matches_regex(r"^[0-9A-F]{1,48}$"),
    }
)

SVCS_DOMAIN = {
    SVC_FAKE_DEVICE: SCH_FAKE_DEVICE,
    SVC_FORCE_UPDATE: None,
    SVC_SEND_PACKET: SCH_SEND_PACKET,
}

CONF_ZONE_MODES = (
    ZoneMode.SCHEDULE,
    ZoneMode.PERMANENT,
    ZoneMode.ADVANCED,
    ZoneMode.TEMPORARY,
)

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

SCH_SET_DHW_SCHED = _SCH_ENTITY_ID.extend({vol.Required(CONF_SCHEDULE): cv.string})


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
# Remote platform services for HVAC
SZ_COMMAND = "command"
SZ_TIMEOUT = "timeout"
SZ_NUM_REPEATS = "num_repeats"
SZ_DELAY_SECS = "delay_secs"
SVC_DELETE_COMMAND = "delete_command"
SVC_LEARN_COMMAND = "learn_command"
SVC_SEND_COMMAND = "send_command"

SCH_VERB_COMMAND_BASE = _SCH_ENTITY_ID.extend({vol.Required(SZ_COMMAND): cv.string})
SCH_DELETE_COMMAND = SCH_VERB_COMMAND_BASE
SCH_LEARN_COMMAND = SCH_VERB_COMMAND_BASE.extend(
    {
        vol.Required(SZ_TIMEOUT, default=60): vol.All(
            cv.positive_int, vol.Range(min=30, max=300)
        )
    }
)
SCH_SEND_COMMAND = SCH_VERB_COMMAND_BASE.extend(
    {
        vol.Required(SZ_NUM_REPEATS, default=3): cv.positive_int,
        vol.Required(SZ_DELAY_SECS, default=0.2): cv.positive_float,
    }
)

SVCS_REMOTE = {
    SVC_DELETE_COMMAND: SCH_DELETE_COMMAND,
    SVC_LEARN_COMMAND: SCH_LEARN_COMMAND,
    SVC_SEND_COMMAND: SCH_SEND_COMMAND,
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
        vol.Optional(SVC_SEND_PACKET, default=False): cv.boolean,
        vol.Optional(SZ_MESSAGE_EVENTS, default=None): vol.Any(None, cv.is_regex),
        vol.Optional(SZ_DEV_MODE): cv.boolean,
        vol.Optional(SZ_UNKNOWN_CODES): cv.boolean,
    }
)

SCH_GLOBAL_TRAITS_DICT, SCH_TRAITS = sch_global_traits_dict_factory(
    hvac_traits={vol.Optional("commands"): dict}
)
SCH_DEVICE_LIST = vol.Schema(
    [{vol.Optional(SCH_DEVICE_ID_ANY): SCH_TRAITS}],  # vol.Length(min=0)
    extra=vol.PREVENT_EXTRA,
)  # TODO: what is this for?

SCH_GATEWAY_CONFIG = SCH_GATEWAY_CONFIG.extend(
    SCH_ENGINE_DICT,
    extra=vol.PREVENT_EXTRA,
)

SCH_DOMAIN_CONFIG = (
    vol.Schema(
        {
            vol.Optional("ramses_rf", default={}): SCH_GATEWAY_CONFIG,
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

    if not merge_cache:  # should not be None
        _LOGGER.debug("A cached schema was not provided/enabled")
        # cached_schema = {}  # in case is None
    else:
        _LOGGER.debug("Loading a cached schema: %s", cached_schema)

    if not config_schema:  # could be None
        _LOGGER.debug("A config schema was not provided")
        config_schema = {}  # in case is None
    else:  # normalise config_schema
        _LOGGER.debug("Loading a config schema: %s", config_schema)

    if not merge_cache or not cached_schema:
        _LOGGER.warning(
            "Using the config schema (cached schema IS NOT valid / enabled), "
            "consider using 'restore_cache: restore_schema: true'"
        )
        return {"the config": config_schema}  # maybe config = {}

    if _is_subset(shrink(config_schema), shrink(cached_schema)):
        _LOGGER.info(
            "Using the cached schema (cached schema is a superset of the config schema)"
        )
        return {
            "the cached": cached_schema,
            "the config": config_schema,
        }  # maybe even cached = config

    # maybe the config schema has changed...
    merged_schema = merge(config_schema, cached_schema)  # config takes precidence
    _LOGGER.debug("Created a merged schema: %s", merged_schema)

    if _is_subset(shrink(config_schema), shrink(merged_schema)):
        _LOGGER.info(
            "Using a merged schema (cached schema IS a superset of the config schema)"
        )
        return {
            "a merged (config/cached)": merged_schema,
            "the config": config_schema,
        }

    _LOGGER.warning(
        "Using the config schema (merged schema IS NOT a superset of the config schema)"
        ", this is unexpected, unless you have changed the config schema"
    )  # something went wrong!
    return {"the config": config_schema}  # maybe config = {}


SCH_MINIMUM_TCS = vol.Schema(
    {
        vol.Optional("system"): vol.Schema(
            {vol.Required("appliance_control"): vol.Match(r"^10:[0-9]{6}$")}
        ),
        vol.Optional("zones", default={}): vol.Schema(
            {
                vol.Required(str): vol.Schema(
                    {vol.Required("sensor"): vol.Match(r"^01:[0-9]{6}$")}
                )
            }
        ),
    },
    extra=vol.PREVENT_EXTRA,
)


@callback
def schema_is_minimal(schema: dict) -> bool:
    """Return True if the schema is minimal (i.e. no optional keys)."""

    key: str
    sch: dict

    for key, sch in schema.items():
        if key in ("block_list", "known_list", "orphans_heat", "orphans_hvac"):
            continue

        try:
            _ = SCH_MINIMUM_TCS(shrink(sch))
        except vol.Invalid:
            return False

        if "zones" in sch and list(sch["zones"].values())[0]["sensor"] != key:
            return False

        return True
