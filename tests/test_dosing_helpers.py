from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


const = load_module("watering_io_const", "custom_components/watering_io/const.py")
helpers = load_module("watering_io_helpers", "custom_components/watering_io/helpers.py")


class DosingHelperTests(unittest.TestCase):
    def test_sensor_scan_diagnostic_fields_are_exposed(self) -> None:
        source = (ROOT / "custom_components/watering_io/sensor.py").read_text(encoding="utf-8")

        self.assertIn('"today_scans"', source)
        self.assertIn('"today_missed_scans"', source)
        self.assertIn('"missed_scans"', source)
        self.assertIn('"today_scans": ("today_scans", "todayScans")', source)
        self.assertIn('"today_missed_scans": ("today_missed_scans", "todayMissedScans")', source)
        self.assertIn('"relay_on_total_seconds"', source)
        self.assertIn('"relay_on_total_seconds": ("relay_on_total_seconds", "relayOnTotalSeconds")', source)
        self.assertIn('"max_daily_refill_on_time_s"', source)
        self.assertIn('"refill_on_today_s"', source)
        self.assertIn('"refill_remaining_today_s"', source)
        self.assertIn('"refill_fault_reason"', source)
        self.assertIn('"refill_fault_since_unix"', source)
        self.assertIn('"refill_fault_date"', source)
        self.assertIn('"relay_counter_overflows"', source)
        self.assertIn('"relay_counter_resets"', source)
        self.assertIn('"reservoir_capacity_l"', source)
        self.assertIn('"reservoir_volume_l"', source)
        self.assertIn('"water_consumed_today_l"', source)
        self.assertIn('"water_consumption_date"', source)

    def test_system_input_voltage_and_nested_pump_status_are_exposed(self) -> None:
        sensor_source = (ROOT / "custom_components/watering_io/sensor.py").read_text(encoding="utf-8")
        binary_source = (ROOT / "custom_components/watering_io/binary_sensor.py").read_text(encoding="utf-8")

        self.assertIn('"bus_current_a"', sensor_source)
        self.assertIn('"input_current_a"', sensor_source)
        self.assertIn('"boot_count"', sensor_source)
        self.assertIn('"reset_reason"', sensor_source)
        self.assertIn('"reset_reason_name"', sensor_source)
        self.assertIn('"free_heap"', sensor_source)
        self.assertIn('"boot_count": ("boot_count", "bootCount")', sensor_source)
        self.assertIn('"reset_reason_name": ("reset_reason_name", "resetReasonName")', sensor_source)
        self.assertIn('CURRENT_FIELDS = {"bus_current_a", "input_current_a"}', sensor_source)
        self.assertIn('"input_voltage"', sensor_source)
        self.assertIn('VOLTAGE_FIELDS = {"input_voltage"}', sensor_source)
        self.assertIn('UnitOfElectricPotential.VOLT', sensor_source)
        self.assertIn('PumpBinarySensor(coordinator, ("pump1", "on"), "pump_a")', binary_source)
        self.assertIn('PumpBinarySensor(coordinator, ("pump2", "on"), "pump_b")', binary_source)
        self.assertIn('"refill_daily_limit_reached"', binary_source)
        self.assertIn('"refill_fault_latched"', binary_source)
        self.assertIn('"bus_power_cutoff_requested"', binary_source)
        self.assertIn('"refill_accounting_time_synced"', binary_source)
        self.assertIn('("sw1_pressed", "SW1 pressed", ("sw1_pressed",))', binary_source)
        self.assertIn("SystemBinarySensor(coordinator, unique_suffix, name, path)", binary_source)
        self.assertIn("nested_value(self.coordinator.state.system_status, self.path)", binary_source)
        self.assertIn("nested_value(self.coordinator.state.pumps_status, self.path)", binary_source)

    def test_new_planter_status_payload_dosing_fields(self) -> None:
        payload = {
            "hub_id": "greenhouse",
            "planter_id": 3,
            "moisture": 42,
            "target_moisture": 45.0,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "watering": False,
            "online": True,
            "next_dose_in_s": -1,
            "total_dosing_s": 842,
        }

        self.assertEqual(helpers.extract_planter_id(payload), "3")
        self.assertEqual(helpers.extract_sensor_id(payload), "1")
        self.assertEqual(
            helpers.total_water_ml(payload["total_dosing_s"], const.DEFAULT_PUMP_1_FLOW_ML_PER_S),
            842,
        )

    def test_extract_planter_id_accepts_new_payload_key(self) -> None:
        self.assertEqual(helpers.extract_planter_id({"planter_id": 3}), "3")

    def test_extract_sensor_id_accepts_new_payload_key(self) -> None:
        self.assertEqual(helpers.extract_sensor_id({"sensor_modbus_id": 1}), "1")

    def test_sensor_temperature_payload_is_numeric_degrees_celsius(self) -> None:
        payload = {"temperature": "21"}

        self.assertEqual(helpers.coerce_numeric(payload["temperature"]), 21)

    def test_schedule_status_nested_values(self) -> None:
        payload = {
            "schedule": {"night_start": "21:00"},
            "fertilizer": {"completed_count": 2},
        }

        self.assertEqual(helpers.nested_value(payload, ("schedule", "night_start")), "21:00")
        self.assertEqual(helpers.nested_value(payload, ("fertilizer", "completed_count")), 2)
        self.assertIsNone(helpers.nested_value(payload, ("fertilizer", "last_error")))

    def test_schedule_boolean_payload_values(self) -> None:
        self.assertTrue(helpers.coerce_bool(True))
        self.assertFalse(helpers.coerce_bool("false"))
        self.assertIsNone(helpers.coerce_bool("not-a-bool"))

    def test_extract_hub_id_from_schema_v2_topic(self) -> None:
        self.assertEqual(
            helpers.extract_hub_id_from_topic("watering.io", "watering.io/hubs/greenhouse/schema"),
            "greenhouse",
        )

    def test_configured_topic_root_extracts_embedded_hub_id(self) -> None:
        self.assertEqual(
            helpers.configured_topic_root("watering.io/hubs/greenhouse"),
            ("watering.io", "greenhouse"),
        )

    def test_config_flow_exposes_explicit_hub_id(self) -> None:
        source = (ROOT / "custom_components/watering_io/config_flow.py").read_text(encoding="utf-8")

        self.assertIn('CONF_HUB_ID = "hub_id"', (ROOT / "custom_components/watering_io/const.py").read_text(encoding="utf-8"))
        self.assertIn("vol.Optional(CONF_HUB_ID, default=\"\")", source)
        self.assertIn("def async_step_hub_settings", source)
        self.assertIn("return f\"{root}::hub::{hub_id.strip().lower()}\"", source)

    def test_current_hub_device_identifiers_are_protected(self) -> None:
        for identifier in (
            "greenhouse",
            "greenhouse_planter_1",
            "greenhouse_pump_1",
            "greenhouse_sensor_8_temperature",
        ):
            self.assertTrue(helpers.watering_device_identifier_belongs_to_hub(identifier, "greenhouse"))
            self.assertFalse(helpers.watering_device_identifier_is_stale(identifier, "greenhouse"))

    def test_other_hub_device_identifiers_are_stale(self) -> None:
        for identifier in (
            "garage",
            "garage_planter_1",
            "garage_pump_1",
            "garage_sensor_8_temperature",
        ):
            self.assertFalse(helpers.watering_device_identifier_belongs_to_hub(identifier, "greenhouse"))
            self.assertTrue(helpers.watering_device_identifier_is_stale(identifier, "greenhouse"))

    def test_remove_config_entry_device_hook_is_exposed(self) -> None:
        source = (ROOT / "custom_components/watering_io/__init__.py").read_text(encoding="utf-8")

        self.assertIn("async def async_remove_config_entry_device", source)
        self.assertIn("watering_device_identifier_is_stale", source)

    def test_coordinator_accepts_schema_v2_and_v3(self) -> None:
        source = (ROOT / "custom_components/watering_io/coordinator.py").read_text(encoding="utf-8")

        self.assertIn("def _schema_version_is_supported", source)
        self.assertIn("return float(value) in (2.0, 3.0)", source)
        self.assertIn("if not _schema_version_is_supported(schema_version):", source)
        self.assertNotIn("_schema_version_is_v2", source)

    def test_non_hub_topics_do_not_extract_hub_id(self) -> None:
        self.assertIsNone(
            helpers.extract_hub_id_from_topic("watering.io", "watering.io/other/info")
        )

    def test_total_water_uses_default_pump_flow(self) -> None:
        payload = {"total_dosing_s": 842}

        self.assertEqual(
            helpers.total_water_ml(payload["total_dosing_s"], const.DEFAULT_PUMP_1_FLOW_ML_PER_S),
            842,
        )

    def test_total_water_uses_string_seconds(self) -> None:
        payload = {"total_dosing_s": "842"}

        self.assertEqual(
            helpers.total_water_ml(payload["total_dosing_s"], const.DEFAULT_PUMP_1_FLOW_ML_PER_S),
            842,
        )

    def test_total_water_uses_configured_pump_flow(self) -> None:
        payload = {"total_dosing_s": 842}

        self.assertEqual(helpers.total_water_ml(payload["total_dosing_s"], 1.5), 1263)

    def test_invalid_values_return_none(self) -> None:
        self.assertIsNone(helpers.total_water_ml("not-a-number", 1.0))

    def test_daily_water_history_converts_dosing_seconds_to_ml(self) -> None:
        payload = {
            "daily_dosing_s": [
                {"date": "2026-05-30", "dosing_s": 0},
                {"date": "2026-05-31", "dosing_s": 18},
                {"date": "2026-06-01", "dosing_s": "42"},
            ]
        }

        self.assertEqual(
            helpers.daily_water_history(payload, 1.5),
            [
                {"date": "2026-05-30", "water_ml": 0},
                {"date": "2026-05-31", "water_ml": 27},
                {"date": "2026-06-01", "water_ml": 63},
            ],
        )

    def test_today_water_uses_rightmost_daily_bucket(self) -> None:
        payload = {
            "daily_dosing_s": [
                {"date": "2026-05-30", "dosing_s": 18},
                {"date": "2026-06-01", "dosing_s": 42},
            ]
        }

        self.assertEqual(helpers.today_water_ml(payload, 2.0), 84)

    def test_daily_water_history_ignores_invalid_entries(self) -> None:
        payload = {
            "daily_dosing_s": [
                {"date": "2026-05-30", "dosing_s": 18},
                {"date": "", "dosing_s": 42},
                {"date": "2026-06-01", "dosing_s": "bad"},
                "bad",
            ]
        }

        self.assertEqual(
            helpers.daily_water_history(payload, 1.0),
            [{"date": "2026-05-30", "water_ml": 18}],
        )

    def test_planter_config_set_payload_updates_only_target_moisture(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
        }

        self.assertEqual(
            helpers.planter_config_set_payload(config, 52),
            {
                "planter_id": 3,
                "enabled": True,
                "sensor_modbus_id": 1,
                "valve_route": 5,
                "target_moisture": 52.0,
                "fertilizer_steps": 120,
                "hysteresis": 4.0,
            },
        )

    def test_planter_config_set_payload_updates_only_fertilizer_steps(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
        }

        self.assertEqual(
            helpers.planter_config_set_payload(config, fertilizer_steps=180),
            {
                "planter_id": 3,
                "enabled": True,
                "sensor_modbus_id": 1,
                "valve_route": 5,
                "target_moisture": 45.0,
                "fertilizer_steps": 180,
                "hysteresis": 4.0,
            },
        )

    def test_planter_config_set_payload_preserves_max_daily_dosing(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
            "max_daily_dosing_s": 300,
        }

        self.assertEqual(
            helpers.planter_config_set_payload(config, 52),
            {
                "planter_id": 3,
                "enabled": True,
                "sensor_modbus_id": 1,
                "valve_route": 5,
                "target_moisture": 52.0,
                "fertilizer_steps": 120,
                "hysteresis": 4.0,
                "max_daily_dosing_s": 300,
            },
        )

    def test_planter_config_set_payload_updates_only_max_daily_dosing(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
            "max_daily_dosing_s": 300,
        }

        self.assertEqual(
            helpers.planter_config_set_payload(config, max_daily_dosing_s=0),
            {
                "planter_id": 3,
                "enabled": True,
                "sensor_modbus_id": 1,
                "valve_route": 5,
                "target_moisture": 45.0,
                "fertilizer_steps": 120,
                "hysteresis": 4.0,
                "max_daily_dosing_s": 0,
            },
        )

    def test_set_planter_settings_service_accepts_max_daily_dosing(self) -> None:
        source = (ROOT / "custom_components/watering_io/__init__.py").read_text(encoding="utf-8")

        self.assertIn('max_daily_dosing_s = call.data.get("max_daily_dosing_s")', source)
        self.assertIn("max_daily_dosing_s=max_daily_dosing_s", source)
        self.assertIn('vol.Optional("max_daily_dosing_s")', source)
        self.assertIn("vol.Range(min=0, max=MAX_DAILY_DOSING_SECONDS)", source)

    def test_planter_config_set_payload_requires_complete_config(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "target_moisture": 45.0,
            "hysteresis": 4.0,
        }

        with self.assertRaises(ValueError):
            helpers.planter_config_set_payload(config, 52)

    def test_planter_config_set_payload_accepts_schema_aliases(self) -> None:
        config = {
            "id": 3,
            "enabled": True,
            "sensorModbusId": 1,
            "valveRoute": 5,
            "targetMoisture": 45.0,
            "fertilizerSteps": 120,
            "hysteresis": 4.0,
            "maxDailyDosingS": 300,
        }

        self.assertEqual(
            helpers.planter_config_set_payload(config, 52),
            {
                "planter_id": 3,
                "enabled": True,
                "sensor_modbus_id": 1,
                "valve_route": 5,
                "target_moisture": 52.0,
                "fertilizer_steps": 120,
                "hysteresis": 4.0,
                "max_daily_dosing_s": 300,
            },
        )

    def test_planter_config_update_source_uses_status_when_config_missing(self) -> None:
        status = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
            "max_daily_dosing_s": 300,
        }

        self.assertIs(helpers.planter_config_update_source(None, status), status)

    def test_planter_config_update_source_prefers_config(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
        }
        status = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
            "fertilizer_steps": 180,
            "hysteresis": 4.0,
        }

        self.assertIs(helpers.planter_config_update_source(config, status), config)

    def test_planter_config_update_source_rejects_incomplete_status(self) -> None:
        status = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "target_moisture": 45.0,
            "fertilizer_steps": 120,
            "hysteresis": 4.0,
        }

        self.assertIsNone(helpers.planter_config_update_source(None, status))

    def test_pump_config_set_payload_updates_only_set_level(self) -> None:
        config = {
            "pump_id": 1,
            "level_sensor_modbus_id": 8,
            "low_level_threshold_percent": 20,
            "set_level_percent": 85,
            "max_relay_on_time_s": 600,
            "max_daily_refill_on_time_s": 64800,
            "reservoir_capacity_l": 50.0,
        }

        self.assertEqual(
            helpers.pump_config_set_payload(config, set_level_percent=90),
            {
                "pump_id": 1,
                "level_sensor_modbus_id": 8,
                "low_level_threshold_percent": 20,
                "set_level_percent": 90,
                "max_relay_on_time_s": 600,
                "max_daily_refill_on_time_s": 64800,
                "reservoir_capacity_l": 50.0,
            },
        )

    def test_pump_config_set_payload_defaults_daily_refill_limit(self) -> None:
        config = {
            "pump_id": 1,
            "level_sensor_modbus_id": 8,
            "low_level_threshold_percent": 20,
            "set_level_percent": 85,
            "max_relay_on_time_s": 600,
        }

        self.assertEqual(
            helpers.pump_config_set_payload(config, max_daily_refill_on_time_s=18 * 60 * 60),
            {
                "pump_id": 1,
                "level_sensor_modbus_id": 8,
                "low_level_threshold_percent": 20,
                "set_level_percent": 85,
                "max_relay_on_time_s": 600,
                "max_daily_refill_on_time_s": 64800,
                "reservoir_capacity_l": 0.0,
            },
        )
        payload = helpers.pump_config_set_payload(config)
        self.assertEqual(payload["max_daily_refill_on_time_s"], 0)
        self.assertEqual(payload["reservoir_capacity_l"], 0.0)

    def test_pump_config_update_source_uses_status_when_config_missing(self) -> None:
        status = {
            "pump_id": 2,
            "level_sensor_modbus_id": 0,
            "low_level_threshold_percent": 0,
            "set_level_percent": 0,
            "max_relay_on_time_s": 0,
            "max_daily_refill_on_time_s": 0,
            "reservoir_capacity_l": 0.0,
        }

        self.assertIs(helpers.pump_config_update_source(None, status), status)

    def test_pump_daily_refill_number_entity_is_exposed(self) -> None:
        source = (ROOT / "custom_components/watering_io/number.py").read_text(encoding="utf-8")
        coordinator_source = (ROOT / "custom_components/watering_io/coordinator.py").read_text(encoding="utf-8")

        self.assertIn("PumpMaxDailyRefillOnTimeNumber(coordinator, pump_id)", source)
        self.assertIn('config_key = "max_daily_refill_on_time_s"', source)
        self.assertIn("_attr_native_max_value = 86400", source)
        self.assertIn("max_daily_refill_on_time_s: int | None = None", coordinator_source)
        self.assertIn('payload["max_daily_refill_on_time_s"] = max_daily_refill_on_time_s', coordinator_source)

    def test_reservoir_capacity_number_and_consumption_entities_are_exposed(self) -> None:
        number_source = (ROOT / "custom_components/watering_io/number.py").read_text(encoding="utf-8")
        sensor_source = (ROOT / "custom_components/watering_io/sensor.py").read_text(encoding="utf-8")
        binary_source = (ROOT / "custom_components/watering_io/binary_sensor.py").read_text(encoding="utf-8")
        coordinator_source = (ROOT / "custom_components/watering_io/coordinator.py").read_text(encoding="utf-8")

        self.assertIn("PumpReservoirCapacityNumber(coordinator, pump_id)", number_source)
        self.assertIn('config_key = "reservoir_capacity_l"', number_source)
        self.assertIn("_attr_native_step = 0.1", number_source)
        self.assertIn("reservoir_capacity_l: float | None = None", coordinator_source)
        self.assertIn('payload["reservoir_capacity_l"] = reservoir_capacity_l', coordinator_source)
        self.assertIn('"reservoir_volume_l"', sensor_source)
        self.assertIn('"water_consumed_today_l"', sensor_source)
        self.assertIn('"water_consumption_complete"', binary_source)

    def test_reservoir_safety_clear_button_is_exposed(self) -> None:
        button_source = (ROOT / "custom_components/watering_io/button.py").read_text(encoding="utf-8")
        coordinator_source = (ROOT / "custom_components/watering_io/coordinator.py").read_text(encoding="utf-8")

        self.assertIn("ClearReservoirSafetyFaultsButton(coordinator)", button_source)
        self.assertIn("Clear reservoir safety faults", button_source)
        self.assertIn("async_publish_safety_clear_fault", button_source)
        self.assertIn("cmd/safety/clear_fault", coordinator_source)
        self.assertIn('"reset_refill_today": reset_refill_today', coordinator_source)


if __name__ == "__main__":
    unittest.main()
