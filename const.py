"""Support for Honeywell's RAMSES II protocol."""
DOMAIN = "evohome_rf"

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

ATTR_BATTERY = "battery_state"
ATTR_HEAT_DEMAND = "heat_demand"
ATTR_SETPOINT = "setpoint"
ATTR_TEMPERATURE = "temperature"

ATTR_ACTUATOR_STATE: str = "actuator_enabled"
ATTR_WINDOW_STATE: str = "window_state"  # On means open, Off means closed

DEVICE_HAS_SENSOR = (
    "03",
    "04",
    "07",
    "12",
    "22",
    "34",
)
DEVICE_HAS_BINARY_SENSOR = ("04", "10", "13")
