"""Constants for RAMSES integration."""
from __future__ import annotations

from enum import StrEnum

from homeassistant.const import ATTR_TEMPERATURE

DOMAIN = "ramses_cc"
CONTROLLER = "controller"
STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN


# Volume Flow Rate units, these are not defined in HA v2023.1
class UnitOfVolumeFlowRate(StrEnum):
    """Volume flow rate units (defined by integration)."""

    LITERS_PER_MINUTE = "L/min"
    LITERS_PER_SECOND = "L/s"


class ZoneMode(StrEnum):
    """Zone modes for Ramses."""

    SCHEDULE = ("follow_schedule",)
    ADVANCED = ("advanced_override",)  # until the next setpoint
    PERMANENT = ("permanent_override",)  # indefinitely
    COUNTDOWN = ("countdown_override",)  # for a number of minutes (max 1,215)
    TEMPORARY = ("temporary_override",)  # until a given date/time


class SystemMode(StrEnum):
    """System modes for Ramses."""

    AUTO = "auto"
    AWAY = "away"
    CUSTOM = "custom"
    DAY_OFF = "day_off"
    DAY_OFF_ECO = "day_off_eco"  # set to Eco when DayOff ends
    ECO_BOOST = "eco_boost"  # Eco, or Boost
    HEAT_OFF = "heat_off"
    RESET = "auto_with_reset"


# Config keys
CONF_ADVANCED_FEATURES = "advanced_features"
CONF_SEND_PACKET = "send_packet"
CONF_MESSAGE_EVENTS = "message_events"
CONF_DEV_MODE = "dev_mode"
CONF_UNKNOWN_CODES = "unknown_codes"

# Entity/service call keys
ATTR_ACTIVE = "active"
ATTR_ACTIVE_FAULT = "active_fault"
ATTR_ACTUATOR = "enabled"
ATTR_BATTERY = "battery_low"
ATTR_CO2_LEVEL = "co2_level"
ATTR_CODE = "code"
ATTR_COMMAND = "command"
ATTR_CREATE_DEVICE = "create_device"
ATTR_DELAY_SECS = "delay_secs"
ATTR_DEVICE_ID = "device_id"
ATTR_DIFFERENTIAL = "differential"
ATTR_DURATION = "duration"
ATTR_FAN_RATE = "fan_rate"
ATTR_FAULT_LOG = "fault_log"
ATTR_HEAT_DEMAND = "heat_demand"
ATTR_HUMIDITY = "relative_humidity"
ATTR_INDOOR_HUMIDITY = "indoor_humidity"
ATTR_LATEST_EVENT = "latest_event"
ATTR_LATEST_FAULT = "latest_fault"
ATTR_LOCAL_OVERRIDE = "local_override"
ATTR_MAX_TEMP = "max_temp"
ATTR_MIN_TEMP = "min_temp"
ATTR_MODE = "mode"
ATTR_MULTIROOM = "multiroom_mode"
ATTR_NUM_REPEATS = "num_repeats"
ATTR_OPENWINDOW = "openwindow_function"
ATTR_OVERRUN = "overrun"
ATTR_PAYLOAD = "payload"
ATTR_PERIOD = "period"
ATTR_RELAY_DEMAND = "relay_demand"
ATTR_SCHEDULE = "schedule"
ATTR_SCHEMA = "schema"
ATTR_SETPOINT = "setpoint"
ATTR_START_BINDING = "start_binding"
ATTR_TIMEOUT = "timeout"
ATTR_UNTIL = "until"
ATTR_VERB = "verb"
ATTR_WINDOW = "window_open"

# Domain services
SERVICE_FAKE_DEVICE = "fake_device"
SERVICE_FORCE_UPDATE = "force_update"
SERVICE_SEND_PACKET = "send_packet"

# Climate controller services
SERVICE_RESET_SYSTEM_MODE = "reset_system_mode"
SERVICE_SET_SYSTEM_MODE = "set_system_mode"

# Climate zone services
SERVICE_GET_ZONE_SCHED = "get_zone_schedule"
SERVICE_PUT_ZONE_TEMP = "put_zone_temp"
SERVICE_RESET_ZONE_CONFIG = "reset_zone_config"
SERVICE_RESET_ZONE_MODE = "reset_zone_mode"
SERVICE_SET_ZONE_CONFIG = "set_zone_config"
SERVICE_SET_ZONE_MODE = "set_zone_mode"
SERVICE_SET_ZONE_SCHED = "set_zone_schedule"

# DHW services
SERVICE_GET_DHW_SCHEDULE = "get_dhw_schedule"
SERVICE_SET_DHW_SCHEDULE = "set_dhw_schedule"
SERVICE_PUT_DHW_TEMP = "put_dhw_temp"
SERVICE_SET_DHW_BOOST = "set_dhw_boost"
SERVICE_SET_DHW_MODE = "set_dhw_mode"
SERVICE_RESET_DHW_MODE = "reset_dhw_mode"
SERVICE_SET_DHW_PARAMS = "set_dhw_params"
SERVICE_RESET_DHW_PARAMS = "reset_dhw_params"

# Sensor services
SERVICE_PUT_CO2_LEVEL = "put_co2_level"
SERVICE_PUT_INDOOR_HUMIDITY = "put_indoor_humidity"

# Remote services
SERVICE_LEARN_COMMAND = "learn_command"
SERVICE_SEND_COMMAND = "send_command"
SERVICE_DELETE_COMMAND = "delete_command"

BINARY_SENSOR_ATTRS = (ATTR_ACTUATOR, ATTR_BATTERY, ATTR_WINDOW)
SENSOR_ATTRS = (
    ATTR_FAN_RATE,
    ATTR_HEAT_DEMAND,
    ATTR_HUMIDITY,
    ATTR_RELAY_DEMAND,
    ATTR_TEMPERATURE,
)  # ATTR_FAULT_LOG
