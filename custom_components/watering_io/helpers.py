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


def extract_hub_id_from_topic(topic_prefix: str, topic: str) -> str | None:
    """Extract a V2 hub id from a Watering.IO hub topic."""
    hub_prefix = f"{topic_prefix.rstrip('/')}/hubs/"
    if not topic.startswith(hub_prefix):
        return None
    suffix = topic[len(hub_prefix) :]
    hub_id = suffix.split("/", 1)[0].strip()
    return hub_id or None


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


def coerce_bool(value: Any) -> bool | None:
    """Return a boolean value from payload data, or None if not boolean-like."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "on", "yes"}:
            return True
        if text in {"0", "false", "off", "no"}:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def nested_value(data: Any, path: tuple[str, ...]) -> Any:
    """Read a nested dict value using a tuple path."""
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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


def _config_value(config: dict[str, Any], key: str) -> Any:
    aliases = {
        "planter_id": ("planter_id", "id"),
        "sensor_modbus_id": ("sensor_modbus_id", "sensorModbusId"),
        "valve_route": ("valve_route", "valveRoute"),
        "target_moisture": ("target_moisture", "targetMoisture"),
        "fertilizer_steps": ("fertilizer_steps", "fertilizerSteps"),
    }
    for alias in aliases.get(key, (key,)):
        if config.get(alias) is not None:
            return config.get(alias)
    return None


def planter_config_set_payload(
    config: dict[str, Any],
    target_moisture: float | None = None,
    fertilizer_steps: int | None = None,
) -> dict[str, Any]:
    """Build a planter set payload with selected values updated."""
    required_keys = (
        "planter_id",
        "enabled",
        "sensor_modbus_id",
        "valve_route",
        "target_moisture",
        "hysteresis",
    )
    missing = [key for key in required_keys if _config_value(config, key) is None]
    if missing:
        raise ValueError(f"Missing planter config field(s): {', '.join(missing)}")

    payload = {
        "planter_id": int(_config_value(config, "planter_id")),
        "enabled": bool(_config_value(config, "enabled")),
        "sensor_modbus_id": int(_config_value(config, "sensor_modbus_id")),
        "valve_route": int(_config_value(config, "valve_route")),
        "target_moisture": float(
            target_moisture if target_moisture is not None else _config_value(config, "target_moisture")
        ),
        "hysteresis": float(_config_value(config, "hysteresis")),
    }
    fertilizer_value = (
        fertilizer_steps if fertilizer_steps is not None else _config_value(config, "fertilizer_steps")
    )
    if fertilizer_value is not None:
        payload["fertilizer_steps"] = int(fertilizer_value)
    return payload
