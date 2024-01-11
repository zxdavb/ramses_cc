"""Schemas for RAMSES integration."""
from __future__ import annotations

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
import voluptuous as vol  # type: ignore[import-untyped]

_SchemaT: TypeAlias = dict[str, Any]

_LOGGER = logging.getLogger(__name__)

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
