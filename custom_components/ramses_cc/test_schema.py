#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC."""

import logging

from .schema import _is_subset, _merge, _normalise_schema

_LOGGER = logging.getLogger(__name__)

assert _normalise_schema(False, None, {}) == {}
assert _normalise_schema(False, {}, {}) == {}
assert _normalise_schema(False, {"controller": None}, {}) == (
    {
        "orphans_heat": [],
        "orphans_hvac": [],
    }
)
assert _normalise_schema(False, {"controller": "01:123456"}, {}) == (
    {
        "main_controller": "01:123456",
        "01:123456": {
            "system": {},
            "stored_hotwater": {},
            "underfloor_heating": {},
            "zones": {},
            "orphans": [],
        },
        "orphans_heat": [],
        "orphans_hvac": [],
    }
)
assert _normalise_schema(False, {"controller": "01:123456", "system": {}}, {}) == (
    {
        "main_controller": "01:123456",
        "01:123456": {
            "system": {},
            "stored_hotwater": {},
            "underfloor_heating": {},
            "zones": {},
            "orphans": [],
        },
        "orphans_heat": [],
        "orphans_hvac": [],
    }
)
assert _normalise_schema(
    False, {"controller": "01:123456", "system": {"appliance_control": "10:123456"}}, {}
) == (
    {
        "main_controller": "01:123456",
        "01:123456": {
            "system": {
                "appliance_control": "10:123456",
                "class": "evohome",
            },
            "stored_hotwater": {},
            "underfloor_heating": {},
            "zones": {},
            "orphans": [],
        },
        "orphans_heat": [],
        "orphans_hvac": [],
    }
)


def _test_set(src, dst, result):
    assert _merge(src, dst) == result
    assert _is_subset(src, result)
    # assert _is_subset(dst, result)


def test_helpers():
    _test_set({}, {}, {})
    _test_set({"src": 1}, {}, {"src": 1})
    _test_set({}, {"dst": 2}, {"dst": 2})
    _test_set({"src": 1}, {"dst": 2}, {"src": 1, "dst": 2})
    _test_set({"val": {}}, {"val": {}}, {"val": {}})
    _test_set({"val": "src"}, {"val": "dst"}, {"val": "src"})  # src is precident
    _test_set({"val": [1, 2]}, {"val": [2]}, {"val": [1, 2]})
    _test_set({"val": [1, 3]}, {"val": [2, 4]}, {"val": [1, 2, 3, 4]})
    _test_set({"val": {"xxx": "src"}}, {"val": {"xxx": "dst"}}, {"val": {"xxx": "src"}})
    _test_set({"val": {"src": 1}}, {"val": {"dst": 2}}, {"val": {"src": 1, "dst": 2}})
