"""Helpers for schema and payload parsing."""

from __future__ import annotations

from typing import Any


def configured_topic_root(topic_prefix: str) -> tuple[str, str | None]:
    """Return the MQTT discovery root and optional hub id from a configured prefix."""
    prefix = topic_prefix.strip().rstrip("/")
    marker = "/hubs/"
    if marker not in prefix:
        return prefix, None

    root, hub_suffix = prefix.split(marker, 1)
    hub_id = hub_suffix.split("/", 1)[0].strip()
    return root.rstrip("/"), hub_id or None


def watering_device_identifier_belongs_to_hub(identifier: str, hub_id: str) -> bool:
    """Return true when a Watering.IO device identifier belongs to a hub."""
    identifier = identifier.strip()
    hub_id = hub_id.strip()
    if not identifier or not hub_id:
        return False
    if identifier == hub_id:
        return True
    return identifier.startswith(
        (
            f"{hub_id}_planter_",
            f"{hub_id}_pump_",
            f"{hub_id}_sensor_",
        )
    )


def watering_device_identifier_is_stale(identifier: str, current_hub_id: str) -> bool:
    """Return true when a Watering.IO device identifier does not belong to the current hub."""
    identifier = identifier.strip()
    current_hub_id = current_hub_id.strip()
    if not identifier or not current_hub_id:
        return False
    return not watering_device_identifier_belongs_to_hub(identifier, current_hub_id)


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


def extract_pump_id(item: Any) -> str | None:
    """Extract a fixed pump id from mixed schema/config formats."""
    if isinstance(item, dict):
        value = item.get("pump_id", item.get("id"))
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


def daily_water_history(data: dict[str, Any], pump_flow_ml_per_s: Any) -> list[dict[str, int | float | str]]:
    """Return daily water history converted from firmware dosing seconds."""
    items = data.get("daily_dosing_s") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    history: list[dict[str, int | float | str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "").strip()
        water = total_water_ml(item.get("dosing_s"), pump_flow_ml_per_s)
        if not date or water is None:
            continue
        history.append({"date": date, "water_ml": water})
    return history


def today_water_ml(data: dict[str, Any], pump_flow_ml_per_s: Any) -> int | float | None:
    """Return the rightmost daily water bucket as today's water value."""
    history = daily_water_history(data, pump_flow_ml_per_s)
    if not history:
        return None
    return history[-1]["water_ml"]


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


def _pump_config_value(config: dict[str, Any], key: str) -> Any:
    aliases = {
        "pump_id": ("pump_id", "id"),
        "level_sensor_modbus_id": ("level_sensor_modbus_id", "level_sensor_id", "sensor_modbus_id"),
        "low_level_threshold_percent": ("low_level_threshold_percent", "low_threshold_percent"),
        "set_level_percent": ("set_level_percent", "set_level"),
        "max_relay_on_time_s": ("max_relay_on_time_s", "max_relay_on_time_seconds"),
        "max_daily_refill_on_time_s": (
            "max_daily_refill_on_time_s",
            "max_daily_refill_on_time_seconds",
        ),
    }
    for alias in aliases.get(key, (key,)):
        if config.get(alias) is not None:
            return config.get(alias)
    return None


def _config_value(config: dict[str, Any], key: str) -> Any:
    aliases = {
        "planter_id": ("planter_id", "id"),
        "sensor_modbus_id": ("sensor_modbus_id", "sensorModbusId"),
        "valve_route": ("valve_route", "valveRoute"),
        "target_moisture": ("target_moisture", "targetMoisture"),
        "fertilizer_steps": ("fertilizer_steps", "fertilizerSteps"),
        "max_daily_dosing_s": ("max_daily_dosing_s", "maxDailyDosingS"),
    }
    for alias in aliases.get(key, (key,)):
        if config.get(alias) is not None:
            return config.get(alias)
    return None


def pump_config_set_payload(
    config: dict[str, Any],
    level_sensor_modbus_id: int | None = None,
    low_level_threshold_percent: int | None = None,
    set_level_percent: int | None = None,
    max_relay_on_time_s: int | None = None,
    max_daily_refill_on_time_s: int | None = None,
) -> dict[str, Any]:
    """Build a fixed pump reservoir set payload with selected values updated."""
    required_keys = (
        "pump_id",
        "level_sensor_modbus_id",
        "low_level_threshold_percent",
        "set_level_percent",
        "max_relay_on_time_s",
    )
    missing = [key for key in required_keys if _pump_config_value(config, key) is None]
    if missing:
        raise ValueError(f"Missing pump config field(s): {', '.join(missing)}")

    payload = {
        "pump_id": int(_pump_config_value(config, "pump_id")),
        "level_sensor_modbus_id": int(
            level_sensor_modbus_id
            if level_sensor_modbus_id is not None
            else _pump_config_value(config, "level_sensor_modbus_id")
        ),
        "low_level_threshold_percent": int(
            low_level_threshold_percent
            if low_level_threshold_percent is not None
            else _pump_config_value(config, "low_level_threshold_percent")
        ),
        "set_level_percent": int(
            set_level_percent
            if set_level_percent is not None
            else _pump_config_value(config, "set_level_percent")
        ),
        "max_relay_on_time_s": int(
            max_relay_on_time_s
            if max_relay_on_time_s is not None
            else _pump_config_value(config, "max_relay_on_time_s")
        ),
        "max_daily_refill_on_time_s": int(
            max_daily_refill_on_time_s
            if max_daily_refill_on_time_s is not None
            else (_pump_config_value(config, "max_daily_refill_on_time_s") or 0)
        ),
    }
    return payload


def pump_config_update_source(
    config: dict[str, Any] | None,
    status: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the first source complete enough for a safe pump config update."""
    for candidate in (config, status):
        if not candidate:
            continue
        try:
            pump_config_set_payload(candidate)
        except (TypeError, ValueError):
            continue
        return candidate
    return None


def planter_config_set_payload(
    config: dict[str, Any],
    target_moisture: float | None = None,
    fertilizer_steps: int | None = None,
    max_daily_dosing_s: int | None = None,
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
    max_daily_value = (
        max_daily_dosing_s if max_daily_dosing_s is not None else _config_value(config, "max_daily_dosing_s")
    )
    if max_daily_value is not None:
        payload["max_daily_dosing_s"] = int(max_daily_value)
    return payload


def planter_config_update_source(
    config: dict[str, Any] | None,
    status: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the first source complete enough for a safe planter config update."""
    for candidate in (config, status):
        if not candidate:
            continue
        try:
            planter_config_set_payload(candidate)
        except (TypeError, ValueError):
            continue
        return candidate
    return None
