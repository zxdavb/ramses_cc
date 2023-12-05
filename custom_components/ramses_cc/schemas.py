"""Schemas for RAMSES integration."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import logging

from ramses_rf.helpers import merge, shrink
from ramses_rf.schemas import (
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

from .const import (
    CONF_ADVANCED_FEATURES,
    CONF_DEV_MODE,
    CONF_MESSAGE_EVENTS,
    CONF_SEND_PACKET,
    CONF_UNKNOWN_CODES,
)

_LOGGER = logging.getLogger(__name__)

SCH_GLOBAL_TRAITS_DICT, _ = sch_global_traits_dict_factory(
    hvac_traits={vol.Optional("commands"): dict}
)

SCH_DOMAIN_CONFIG = (
    vol.Schema(
        {
            vol.Optional("ramses_rf", default={}): SCH_GATEWAY_CONFIG.extend(
                SCH_ENGINE_DICT,
                extra=vol.PREVENT_EXTRA,
            ),
            vol.Optional(CONF_SCAN_INTERVAL, default=timedelta(seconds=60)): vol.All(
                cv.time_period, vol.Range(min=timedelta(seconds=3))
            ),
            vol.Optional(CONF_ADVANCED_FEATURES, default={}): vol.Schema(
                {
                    vol.Optional(CONF_SEND_PACKET, default=False): cv.boolean,
                    vol.Optional(CONF_MESSAGE_EVENTS, default=None): vol.Any(
                        None, cv.is_regex
                    ),
                    vol.Optional(CONF_DEV_MODE): cv.boolean,
                    vol.Optional(CONF_UNKNOWN_CODES): cv.boolean,
                }
            ),
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
    """Return a port/client_config/controller_config for the library."""

    config = deepcopy(config)

    config[SZ_CONFIG] = config.pop("ramses_rf")

    port_name, port_config = extract_serial_port(config.pop(SZ_SERIAL_PORT))

    remote_commands = {
        k: v.pop("commands")
        for k, v in config["known_list"].items()
        if v.get("commands")
    }

    controller_keys = (CONF_SCAN_INTERVAL, CONF_ADVANCED_FEATURES, SZ_RESTORE_CACHE)
    return (
        port_name,
        {k: v for k, v in config.items() if k not in controller_keys}
        | {SZ_PORT_CONFIG: port_config},
        {k: v for k, v in config.items() if k in controller_keys}
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
