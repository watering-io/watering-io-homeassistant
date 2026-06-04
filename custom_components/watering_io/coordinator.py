"""Coordinator for Watering.IO MQTT schema V2."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_PUMP_1_FLOW_ML_PER_S, DEFAULT_PUMP_1_FLOW_ML_PER_S, DOMAIN
from .helpers import extract_hub_id_from_topic, extract_planter_id, extract_sensor_id

_LOGGER = logging.getLogger(__name__)

SIGNAL_UPDATE = f"{DOMAIN}_update"


def _first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _configured_topic_root(topic_prefix: str) -> tuple[str, str | None]:
    """Return the discovery root and optional hub id from a configured prefix."""
    prefix = topic_prefix.rstrip("/")
    marker = "/hubs/"
    if marker not in prefix:
        return prefix, None

    root, hub_suffix = prefix.split(marker, 1)
    hub_id = hub_suffix.split("/", 1)[0].strip()
    return root.rstrip("/"), hub_id or None


def _schema_version_is_v2(value: Any) -> bool:
    try:
        return float(value) == 2.0
    except (TypeError, ValueError):
        return False


def _items_from_payload(data: Any, *keys: str) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    values = list(data.values())
    if values and all(isinstance(value, dict) for value in values):
        return values
    return []


def _hub_device_name(base_name: Any, hub_id: str) -> str:
    """Return a hub device name that exposes the logical hub id."""
    name = str(base_name or f"Watering.IO Hub {hub_id}").strip()
    if not name:
        name = f"Watering.IO Hub {hub_id}"
    if hub_id and hub_id != "unknown" and hub_id.lower() not in name.lower():
        return f"{name} ({hub_id})"
    return name


@dataclass
class WateringState:
    hub_id: str | None = None
    availability_online: bool = False
    availability_seen: bool = False
    device_info: dict[str, Any] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=dict)
    schedule_config: dict[str, Any] = field(default_factory=dict)
    fertilizer_config: dict[str, Any] = field(default_factory=dict)
    device_status: dict[str, Any] = field(default_factory=dict)
    system_status: dict[str, Any] = field(default_factory=dict)
    schedule_status: dict[str, Any] = field(default_factory=dict)
    pumps_status: dict[str, Any] = field(default_factory=dict)
    fertilizer_status: dict[str, Any] = field(default_factory=dict)
    planter_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    sensor_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    planter_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_config_ack: dict[str, Any] = field(default_factory=dict)
    topic_last_update: dict[str, datetime] = field(default_factory=dict)


class WateringIoCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.prefix, configured_hub_id = _configured_topic_root(entry.data["topic_prefix"])
        self.state = WateringState(hub_id=entry.data.get("hub_id") or configured_hub_id)
        self._unsubs: list = []
        self._subscribed_topics: set[tuple[str, str]] = set()

    async def async_initialize(self) -> None:
        await self._subscribe_base_topics()
        await self._subscribe_hub_topics()

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._subscribed_topics.clear()

    @property
    def hub_id(self) -> str:
        return self.state.hub_id or ""

    @property
    def hub_id_available(self) -> bool:
        return bool(self.state.hub_id)

    @property
    def hub_root(self) -> str | None:
        if not self.state.hub_id:
            return None
        return f"{self.prefix}/hubs/{self.state.hub_id}"

    def _hub_root_required(self) -> str:
        root = self.hub_root
        if root is None:
            raise HomeAssistantError("Watering.IO hub_id has not been discovered yet")
        return root

    @property
    def device_id(self) -> str:
        for source in (self.state.device_info, self.state.device_status, self.state.system_status):
            value = _first_value(source, "device_id", "deviceId")
            if value:
                return str(value)
        return "unknown"

    @property
    def device_available(self) -> bool:
        if self.state.availability_seen:
            return self.state.availability_online
        if (
            self.state.device_info
            or self.state.schema
            or self.state.system_status
            or self.state.schedule_status
            or self.state.pumps_status
            or self.state.fertilizer_status
            or self.state.planter_status
            or self.state.sensor_status
        ):
            return True
        return self.state.availability_online

    @property
    def pump_1_flow_ml_per_s(self) -> float:
        value = self.entry.options.get(CONF_PUMP_1_FLOW_ML_PER_S, DEFAULT_PUMP_1_FLOW_ML_PER_S)
        try:
            flow = float(value)
        except (TypeError, ValueError):
            return DEFAULT_PUMP_1_FLOW_ML_PER_S
        if flow < 0:
            return DEFAULT_PUMP_1_FLOW_ML_PER_S
        return flow

    @property
    def hub_device_info(self) -> DeviceInfo:
        hub_id = self.hub_id or "unknown"
        return DeviceInfo(
            identifiers={(DOMAIN, hub_id)},
            name=_hub_device_name(self.state.device_info.get("name"), hub_id),
            manufacturer="Watering.IO",
            model=self.state.device_info.get("model", "Watering.IO Hub"),
            serial_number=hub_id if hub_id != "unknown" else None,
            sw_version=_first_value(
                self.state.device_info,
                "firmware_version",
                "firmwareVersion",
            ),
        )

    @property
    def stable_unique_prefix(self) -> str:
        return self.hub_id

    def planter_unique_id(self, planter_id: str) -> str | None:
        if not self.hub_id_available:
            return None
        return f"{self.hub_id}_planter_{planter_id}"

    def sensor_unique_id(self, sensor_id: str, metric: str) -> str | None:
        if not self.hub_id_available:
            return None
        return f"{self.hub_id}_sensor_{sensor_id}_{metric}"

    def planter_device_info(self, planter_id: str, planter_unique_id: str | None = None) -> DeviceInfo:
        planter_identifier = planter_unique_id or self.planter_unique_id(planter_id)
        if planter_identifier is None or not self.hub_id_available:
            return self.hub_device_info
        return DeviceInfo(
            identifiers={(DOMAIN, planter_identifier)},
            name=f"Planter {planter_id}",
            manufacturer="Watering.IO",
            model="Watering.IO Planter",
            via_device=(DOMAIN, self.hub_id),
        )

    def topic_is_stale(self, topic: str, seconds: int = 60) -> bool:
        last = self.state.topic_last_update.get(topic)
        if last is None:
            return True
        return datetime.utcnow() - last > timedelta(seconds=seconds)

    async def async_publish_rescan(self) -> None:
        await mqtt.async_publish(
            self.hass,
            f"{self._hub_root_required()}/cmd/sensors/rescan",
            "{}",
            qos=0,
            retain=False,
        )

    async def async_publish_planter_set(
        self,
        *,
        planter_id: int,
        enabled: bool,
        sensor_modbus_id: int,
        valve_route: int,
        target_moisture: float,
        hysteresis: float,
        fertilizer_steps: int | None = None,
    ) -> None:
        payload = {
            "planter_id": planter_id,
            "enabled": enabled,
            "sensor_modbus_id": sensor_modbus_id,
            "valve_route": valve_route,
            "target_moisture": target_moisture,
            "hysteresis": hysteresis,
        }
        if fertilizer_steps is not None:
            payload["fertilizer_steps"] = fertilizer_steps
        await self._publish_json(f"{self._hub_root_required()}/cmd/config/planters/set", payload)

    async def async_publish_planter_delete(self, planter_id: int) -> None:
        await self._publish_json(
            f"{self._hub_root_required()}/cmd/config/planters/delete",
            {"planter_id": planter_id},
        )

    async def async_publish_planter_get(self) -> None:
        await self._publish_json(f"{self._hub_root_required()}/cmd/config/planters/get", {})

    async def _publish_json(self, topic: str, payload: dict[str, Any]) -> None:
        await mqtt.async_publish(
            self.hass,
            topic,
            json.dumps(payload, separators=(",", ":")),
            qos=0,
            retain=False,
        )

    async def _subscribe_base_topics(self) -> None:
        for topic, cb in (
            (f"{self.prefix}/hubs/+/schema", self._handle_schema),
            (f"{self.prefix}/hubs/+/info", self._handle_device_info),
        ):
            await self._subscribe_once(topic, cb)

    async def _subscribe_hub_topics(self) -> None:
        root = self.hub_root
        if root is None:
            return
        for topic, cb in (
            (f"{root}/availability", self._handle_availability),
            (f"{root}/config/schedule", self._handle_schedule_config),
            (f"{root}/config/fertilizer", self._handle_fertilizer_config),
            (f"{root}/config/planters", self._handle_planter_configs),
            (f"{root}/status/system", self._handle_status),
            (f"{root}/status/schedule", self._handle_status),
            (f"{root}/status/pumps", self._handle_status),
            (f"{root}/status/fertilizer", self._handle_status),
            (f"{root}/status/sensors", self._handle_status),
            (f"{root}/planters/+/status", self._handle_status),
            (f"{root}/sensors/+/status", self._handle_status),
            (f"{root}/planters/+/events/watering", self._handle_event),
            (f"{root}/events/manual_dosing_unassigned", self._handle_event),
            (f"{root}/events/fertilizer/move", self._handle_event),
            (f"{root}/ack/#", self._handle_ack),
        ):
            await self._subscribe_once(topic, cb)

    async def _subscribe_once(self, topic: str, cb) -> None:
        key = (topic, getattr(cb, "__name__", repr(cb)))
        if key in self._subscribed_topics:
            return
        unsub = await mqtt.async_subscribe(self.hass, topic, cb, qos=0)
        self._unsubs.append(unsub)
        self._subscribed_topics.add(key)

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def _mark_topic_update(self, topic: str) -> None:
        self.state.topic_last_update[topic] = datetime.utcnow()

    def _hub_topic_suffix(self, topic: str) -> str | None:
        root = self.hub_root
        if root is None:
            return None
        topic_root = f"{root}/"
        if not topic.startswith(topic_root):
            return None
        return topic[len(topic_root) :]

    def _accept_hub_topic(self, topic: str, data: dict[str, Any] | None = None) -> bool:
        topic_hub_id = extract_hub_id_from_topic(self.prefix, topic)
        payload_hub_id = _first_value(data or {}, "hub_id", "hubId")
        hub_id = topic_hub_id or (str(payload_hub_id).strip() if payload_hub_id else None)
        if not hub_id:
            return False
        if self.state.hub_id and hub_id != self.state.hub_id:
            _LOGGER.debug("Ignoring Watering.IO topic for hub %s; coordinator is bound to %s", hub_id, self.hub_id)
            return False

        if not self.state.hub_id:
            self.state.hub_id = hub_id
            self.hass.async_create_task(self._subscribe_hub_topics())

        if topic_hub_id and payload_hub_id and str(payload_hub_id).strip() != topic_hub_id:
            _LOGGER.warning(
                "Watering.IO payload hub_id %s does not match topic hub_id %s",
                payload_hub_id,
                topic_hub_id,
            )
        return True

    @callback
    def _handle_availability(self, msg: ReceiveMessage) -> None:
        if not self._accept_hub_topic(msg.topic):
            return
        self.state.availability_seen = True
        self.state.availability_online = str(msg.payload).strip().lower() == "online"
        self._mark_topic_update(msg.topic)
        self._notify()

    @callback
    def _handle_device_info(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        self.state.device_info = data
        self._mark_topic_update(msg.topic)
        self._upsert_device()
        self._notify()

    @callback
    def _handle_schema(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        schema_version = _first_value(data, "schema_version", "schemaVersion")
        if not _schema_version_is_v2(schema_version):
            _LOGGER.warning("Unsupported schema_version: %s", schema_version)
            return
        self.state.schema = data
        self._mark_topic_update(msg.topic)
        self._notify()

    @callback
    def _handle_schedule_config(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        self.state.schedule_config = data
        self._mark_topic_update(msg.topic)
        self._notify()

    @callback
    def _handle_fertilizer_config(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        self.state.fertilizer_config = data
        self._mark_topic_update(msg.topic)
        self._notify()

    @callback
    def _handle_status(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        self._mark_topic_update(msg.topic)

        suffix = self._hub_topic_suffix(msg.topic)
        if suffix == "status/system":
            self.state.system_status = data
        elif suffix == "status/schedule":
            self.state.schedule_status = data
        elif suffix == "status/pumps":
            self.state.pumps_status = data
        elif suffix == "status/fertilizer":
            self.state.fertilizer_status = data
        elif suffix == "status/sensors":
            for sensor in _items_from_payload(data, "sensors"):
                sensor_id = extract_sensor_id(sensor)
                if sensor_id and isinstance(sensor, dict):
                    self.state.sensor_status[sensor_id] = sensor
        elif suffix and suffix.startswith("planters/") and suffix.endswith("/status"):
            planter_id = str(data.get("planter_id") or data.get("id") or suffix.split("/")[1])
            self.state.planter_status[planter_id] = data
        elif suffix and suffix.startswith("sensors/") and suffix.endswith("/status"):
            sensor_id = str(
                data.get("sensor_modbus_id")
                or data.get("sensorModbusId")
                or suffix.split("/")[1]
            )
            self.state.sensor_status[sensor_id] = data
        self._notify()

    @callback
    def _handle_event(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        self._mark_topic_update(msg.topic)
        _LOGGER.debug("Watering.IO event on %s: %s", msg.topic, data)

    @callback
    def _handle_planter_configs(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not self._accept_hub_topic(msg.topic, data if isinstance(data, dict) else None):
            return
        self._mark_topic_update(msg.topic)
        configs = {}
        for config in _items_from_payload(data, "planters", "configs"):
            planter_id = extract_planter_id(config)
            if planter_id and isinstance(config, dict):
                configs[planter_id] = config
        self.state.planter_configs = configs
        self._notify()

    @callback
    def _handle_ack(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict) or not self._accept_hub_topic(msg.topic, data):
            return
        self.state.last_config_ack = {"topic": msg.topic, **data}
        self._mark_topic_update(msg.topic)
        self._notify()

    def _safe_json(self, payload: str) -> Any:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.warning("Malformed JSON payload received")
            return None

    def _upsert_device(self) -> None:
        if not self.hub_id_available:
            return
        registry = dr.async_get(self.hass)
        registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, self.hub_id)},
            name=_hub_device_name(self.state.device_info.get("name"), self.hub_id),
            model=self.state.device_info.get("model", "Watering.IO Hub"),
            serial_number=self.hub_id,
            sw_version=_first_value(
                self.state.device_info,
                "firmware_version",
                "firmwareVersion",
            ),
            manufacturer="Watering.IO",
        )
