"""Coordinator for Watering.IO MQTT contract."""

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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_PUMP_1_FLOW_ML_PER_S, DEFAULT_PUMP_1_FLOW_ML_PER_S, DOMAIN
from .helpers import extract_planter_id, extract_sensor_id

_LOGGER = logging.getLogger(__name__)

SIGNAL_UPDATE = f"{DOMAIN}_update"


@dataclass
class WateringState:
    availability_online: bool = False
    device_info: dict[str, Any] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=dict)
    system_status: dict[str, Any] = field(default_factory=dict)
    pumps_status: dict[str, Any] = field(default_factory=dict)
    planter_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    sensor_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    topic_last_update: dict[str, datetime] = field(default_factory=dict)


class WateringIoCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.prefix = entry.data["topic_prefix"].rstrip("/")
        self.state = WateringState()
        self._unsubs: list = []

    async def async_initialize(self) -> None:
        await self._subscribe_base_topics()

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @property
    def device_id(self) -> str:
        return self.state.device_info.get("deviceId", "unknown")

    @property
    def device_available(self) -> bool:
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
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.state.device_info.get("name", "Watering.IO Hub"),
            manufacturer="Watering.IO",
            model="Watering.IO Hub",
            sw_version=self.state.device_info.get("firmwareVersion"),
        )

    def planter_device_info(self, planter_id: str) -> DeviceInfo:
        hub_identifier = (DOMAIN, self.device_id)
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.device_id}_planter_{planter_id}")},
            name=f"Planter {planter_id}",
            manufacturer="Watering.IO",
            model="Watering.IO Planter",
            via_device=hub_identifier,
        )

    def topic_is_stale(self, topic: str, seconds: int = 60) -> bool:
        last = self.state.topic_last_update.get(topic)
        if last is None:
            return True
        return datetime.utcnow() - last > timedelta(seconds=seconds)

    async def async_publish_rescan(self) -> None:
        await mqtt.async_publish(
            self.hass,
            f"{self.prefix}/command/sensors/rescan",
            "{}",
            qos=0,
            retain=False,
        )

    async def _subscribe_base_topics(self) -> None:
        for topic, cb in (
            (f"{self.prefix}/device/availability", self._handle_availability),
            (f"{self.prefix}/device/info", self._handle_device_info),
            (f"{self.prefix}/integration/schema", self._handle_schema),
            # Fallback subscriptions so we can discover planter/sensor entities even
            # before schema is received or when schema entity arrays are incomplete.
            (f"{self.prefix}/system/status", self._handle_status),
            (f"{self.prefix}/pumps/status", self._handle_status),
            (f"{self.prefix}/planter/+/status", self._handle_status),
            (f"{self.prefix}/planter/+/event/watering", self._handle_watering_event),
            (f"{self.prefix}/sensors/+/status", self._handle_status),
        ):
            unsub = await mqtt.async_subscribe(self.hass, topic, cb, qos=0)
            self._unsubs.append(unsub)

    async def _subscribe_schema_topics(self) -> None:
        topics = self.state.schema.get("topics", {})
        for key in ("systemStatus", "pumpsStatus"):
            topic = topics.get(key)
            if topic:
                unsub = await mqtt.async_subscribe(self.hass, topic, self._handle_status, qos=0)
                self._unsubs.append(unsub)

        # Always subscribe to wildcard status topics so planters/sensors are discovered
        # even when schema entity arrays are missing, delayed, or malformed.
        planter_template = topics.get("planterStatusTemplate", f"{self.prefix}/planter/{{id}}/status")
        planter_wildcard = planter_template.replace("{id}", "+")
        unsub = await mqtt.async_subscribe(self.hass, planter_wildcard, self._handle_status, qos=0)
        self._unsubs.append(unsub)

        sensor_template = topics.get("sensorStatusTemplate", f"{self.prefix}/sensors/{{sensorModbusId}}/status")
        sensor_wildcard = sensor_template.replace("{sensorModbusId}", "+")
        unsub = await mqtt.async_subscribe(self.hass, sensor_wildcard, self._handle_status, qos=0)
        self._unsubs.append(unsub)

        # Keep explicit subscriptions as well for strict schema behavior compatibility.
        for planter in self.state.schema.get("entities", {}).get("planters", []):
            planter_id = extract_planter_id(planter)
            if not planter_id:
                continue
            topic = planter_template.replace("{id}", planter_id)
            unsub = await mqtt.async_subscribe(self.hass, topic, self._handle_status, qos=0)
            self._unsubs.append(unsub)

        for sensor in self.state.schema.get("entities", {}).get("sensors", []):
            sensor_id = extract_sensor_id(sensor)
            if not sensor_id:
                continue
            topic = sensor_template.replace("{sensorModbusId}", sensor_id)
            unsub = await mqtt.async_subscribe(self.hass, topic, self._handle_status, qos=0)
            self._unsubs.append(unsub)

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def _mark_topic_update(self, topic: str) -> None:
        self.state.topic_last_update[topic] = datetime.utcnow()

    @callback
    def _handle_availability(self, msg: ReceiveMessage) -> None:
        self.state.availability_online = msg.payload == "online"
        self._mark_topic_update(msg.topic)
        self._notify()

    @callback
    def _handle_device_info(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict):
            return
        self.state.device_info = data
        self._mark_topic_update(msg.topic)
        self._upsert_device()
        self._notify()

    @callback
    def _handle_schema(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict):
            return
        if data.get("schemaVersion") != 1:
            _LOGGER.warning("Unsupported schemaVersion: %s", data.get("schemaVersion"))
            return
        self.state.schema = data
        self._mark_topic_update(msg.topic)
        self.hass.async_create_task(self._subscribe_schema_topics())
        self._notify()

    @callback
    def _handle_status(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict):
            return
        self._mark_topic_update(msg.topic)

        topics = self.state.schema.get("topics", {})
        if msg.topic == topics.get("systemStatus"):
            self.state.system_status = data
        elif msg.topic == topics.get("pumpsStatus"):
            self.state.pumps_status = data
        elif "/planter/" in msg.topic and msg.topic.endswith("/status"):
            planter_id = str(
                data.get("planter_id")
                or data.get("id")
                or msg.topic.split("/planter/")[-1].split("/")[0]
            )
            self.state.planter_status[planter_id] = data
        elif "/sensors/" in msg.topic and msg.topic.endswith("/status"):
            sensor_id = str(data.get("sensorModbusId") or msg.topic.split("/sensors/")[-1].split("/")[0])
            self.state.sensor_status[sensor_id] = data
        self._notify()

    @callback
    def _handle_watering_event(self, msg: ReceiveMessage) -> None:
        data = self._safe_json(msg.payload)
        if not isinstance(data, dict):
            return
        self._mark_topic_update(msg.topic)
        _LOGGER.debug("Watering event on %s: %s", msg.topic, data)

    def _safe_json(self, payload: str) -> Any:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.warning("Malformed JSON payload received")
            return None

    def _upsert_device(self) -> None:
        device_id = self.state.device_info.get("deviceId")
        if not device_id:
            return
        registry = dr.async_get(self.hass)
        registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, device_id)},
            name=self.state.device_info.get("name", "Watering.IO Hub"),
            model="Watering.IO Hub",
            sw_version=self.state.device_info.get("firmwareVersion"),
            manufacturer="Watering.IO",
        )
