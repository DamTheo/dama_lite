"""Le contrôle de chauffe doit rester 100 % non énergisant."""
import tempfile
import unittest
from pathlib import Path

from dama_lite.config import Config
from dama_lite.thermal_preflight import run_preflight


class Sensor:
    def read(self):
        return 20.5


def config():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "config.json"
        path.write_text('{"heating_enabled":false}', encoding="utf-8")
        return Config.load(path)


class PreflightTests(unittest.TestCase):
    def test_real_sensor_mode_uses_only_simulated_relay(self):
        result = run_preflight(
            config(), sensor=Sensor(), cpu=43.0, cutoff_verified=False
        )
        self.assertEqual([20.5] * 5, result["sensor_samples_c"])
        self.assertTrue(result["simulated_heater_on"])
        self.assertFalse(result["relay_physically_energized"])
        self.assertFalse(result["physical_heating_test_permitted"])
        self.assertFalse(result["simulated_ready"])
        self.assertEqual(37, result["limits_c"]["target"])
        self.assertEqual(35, result["limits_c"]["start"])
        self.assertEqual(41, result["limits_c"]["chamber_cutoff"])

    def test_marker_does_not_auto_qualify_real_pulse(self):
        result = run_preflight(
            config(), sensor=Sensor(), cpu=40.0, cutoff_verified=True
        )
        self.assertFalse(result["relay_physically_energized"])
        self.assertFalse(result["physical_heating_test_permitted"])


if __name__ == "__main__":
    unittest.main()
