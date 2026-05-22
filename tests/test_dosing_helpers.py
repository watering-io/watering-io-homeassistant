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
    def test_new_planter_status_payload_dosing_fields(self) -> None:
        payload = {
            "device_id": "watering-001122334455",
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

    def test_extract_planter_unique_id_from_schema(self) -> None:
        self.assertEqual(
            helpers.extract_planter_unique_id({"unique_id": "watering-001122334455_planter_3"}),
            "watering-001122334455_planter_3",
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

    def test_planter_config_set_payload_updates_only_target_moisture(self) -> None:
        config = {
            "planter_id": 3,
            "enabled": True,
            "sensor_modbus_id": 1,
            "valve_route": 5,
            "target_moisture": 45.0,
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
                "hysteresis": 4.0,
            },
        )

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
                "hysteresis": 4.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
