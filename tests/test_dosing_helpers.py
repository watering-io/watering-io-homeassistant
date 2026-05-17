from __future__ import annotations

from datetime import datetime, timezone
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
            "device_id": "esp32-001",
            "planter_id": 3,
            "last_dosing_ms": 18500,
            "total_dosing_ms": 842000,
            "last_dosing_unix": 1778879536,
            "last_event_id": 1234,
        }

        self.assertEqual(helpers.extract_planter_id(payload), "3")
        self.assertEqual(helpers.milliseconds_to_seconds(payload["total_dosing_ms"]), 842)
        self.assertEqual(helpers.milliseconds_to_seconds(payload["last_dosing_ms"]), 18.5)
        self.assertEqual(
            helpers.unix_to_utc_datetime(payload["last_dosing_unix"]),
            datetime.fromtimestamp(1778879536, tz=timezone.utc),
        )
        self.assertEqual(
            helpers.total_water_ml(payload["total_dosing_ms"], const.DEFAULT_PUMP_1_FLOW_ML_PER_S),
            842,
        )

    def test_extract_planter_id_accepts_new_payload_key(self) -> None:
        self.assertEqual(helpers.extract_planter_id({"planter_id": 3}), "3")

    def test_total_dosing_ms_converts_to_seconds(self) -> None:
        payload = {"total_dosing_ms": 842000}

        self.assertEqual(helpers.milliseconds_to_seconds(payload["total_dosing_ms"]), 842)

    def test_last_dosing_ms_converts_to_seconds(self) -> None:
        payload = {"last_dosing_ms": "18500"}

        self.assertEqual(helpers.milliseconds_to_seconds(payload["last_dosing_ms"]), 18.5)

    def test_last_dosing_unix_converts_to_utc_datetime(self) -> None:
        payload = {"last_dosing_unix": 1778879536}

        self.assertEqual(
            helpers.unix_to_utc_datetime(payload["last_dosing_unix"]),
            datetime.fromtimestamp(1778879536, tz=timezone.utc),
        )

    def test_total_water_uses_default_pump_flow(self) -> None:
        payload = {"total_dosing_ms": 842000}

        self.assertEqual(
            helpers.total_water_ml(payload["total_dosing_ms"], const.DEFAULT_PUMP_1_FLOW_ML_PER_S),
            842,
        )

    def test_total_water_uses_configured_pump_flow(self) -> None:
        payload = {"total_dosing_ms": 842000}

        self.assertEqual(helpers.total_water_ml(payload["total_dosing_ms"], 1.5), 1263)

    def test_invalid_values_return_none(self) -> None:
        self.assertIsNone(helpers.milliseconds_to_seconds("not-a-number"))
        self.assertIsNone(helpers.unix_to_utc_datetime("not-a-timestamp"))
        self.assertIsNone(helpers.total_water_ml("not-a-number", 1.0))


if __name__ == "__main__":
    unittest.main()
