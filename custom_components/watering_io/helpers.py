"""Helpers for schema and payload parsing."""

from __future__ import annotations

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


def total_water_ml(total_dosing_s: Any, pump_flow_ml_per_s: Any) -> int | float | None:
    """Calculate total pumped water from dosing time and pump flow."""
    total_seconds = coerce_numeric(total_dosing_s)
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
        value = item.get("sensor_modbus_id", item.get("sensorModbusId"))
    else:
        value = item
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_planter_unique_id(item: Any) -> str | None:
    """Extract a planter namespace unique id from schema data."""
    if not isinstance(item, dict):
        return None
    value = item.get("unique_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None
