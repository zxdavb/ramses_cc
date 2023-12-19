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
    hvac_traits={vol.Optional("commands"): dict}
)

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
        if key in ("block_list", "known_list", "orphans_heat", "orphans_hvac"):
            continue

        try:
            _ = SCH_MINIMUM_TCS(shrink(sch))
        except vol.Invalid:
            return False

        if "zones" in sch and list(sch["zones"].values())[0]["sensor"] != key:
            return False

        return True
