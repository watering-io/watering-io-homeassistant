"""Helpers for schema parsing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def extract_planter_id(item: Any) -> str | None:
    """Extract a planter id from mixed schema formats."""
    if isinstance(item, dict):
        value = item.get("planter_id", item.get("id"))
    else:
        value = item
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def coerce_numeric(value: Any) -> int | float | None:
    """Return a numeric value from payload data, or None if not numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


def milliseconds_to_seconds(value: Any) -> int | float | None:
    """Convert a millisecond payload value to seconds."""
    milliseconds = coerce_numeric(value)
    if milliseconds is None:
        return None
    seconds = milliseconds / 1000
    return int(seconds) if seconds.is_integer() else seconds


def unix_to_utc_datetime(value: Any) -> datetime | None:
    """Convert a Unix timestamp payload value to a UTC datetime."""
    timestamp = coerce_numeric(value)
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def total_water_ml(total_dosing_ms: Any, pump_flow_ml_per_s: Any) -> int | float | None:
    """Calculate total pumped water from dosing time and pump flow."""
    total_seconds = milliseconds_to_seconds(total_dosing_ms)
    flow = coerce_numeric(pump_flow_ml_per_s)
    if total_seconds is None or flow is None:
        return None
    value = total_seconds * flow
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def extract_sensor_id(item: Any) -> str | None:
    """Extract a sensor modbus id from mixed schema formats."""
    if isinstance(item, dict):
        value = item.get("sensorModbusId")
    else:
        value = item
    if value is None:
        return None
    text = str(value).strip()
    return text or None
