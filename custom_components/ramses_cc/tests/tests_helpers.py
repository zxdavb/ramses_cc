"""Tests for RAMSES_CC integration helper APIs."""

from custom_components.ramses_cc.schemas import deep_merge

# I had a quick look at HAC dev docs - it is not clear how to include tests, e.g.
# location of tests folder, etc.


def test_deep_merge() -> None:
    XXX = {"a": 10, "b": 20}
    YYY = {"a": 11, "c": 31}

    assert deep_merge(XXX, YYY) == YYY | XXX  # TODO: == x | y
    assert deep_merge(YYY, XXX) == XXX | YYY  # TODO: == y | x

    XXX = {"a": 10, "b": 20, "x": {"a": 70, "b": 80}}
    YYY = {"a": 11, "c": 31, "x": {"a": 71, "c": 91}}

    assert deep_merge(XXX, YYY) == {
        "a": 10,
        "c": 31,
        "x": {"a": 70, "c": 91, "b": 80},
        "b": 20,
    }
    assert deep_merge(YYY, XXX) == {
        "a": 11,
        "b": 20,
        "x": {"a": 71, "b": 80, "c": 91},
        "c": 31,
    }

    ZZZ = {"a": 10, "b": 20, "x": None}

    # assert deep_merge(x, z) == {}
    assert deep_merge(ZZZ, XXX) == {"a": 10, "b": 20, "x": None}
