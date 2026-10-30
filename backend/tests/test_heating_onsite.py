import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from dama_lite.config import Config
from dama_lite.heating_onsite_test import (
    marker_valid, safe_preflight, MAX_RUNTIME, MAX_TEST_TEMPERATURE
)


class Sensor:
    def read(self): return 22.0


def config():
    with tempfile.TemporaryDirectory() as root:
        p = Path(root) / "config.json"
        p.write_text('{"heating_enabled":false}')
        return Config.load(p)


class CommissioningGuardTests(unittest.TestCase):
    def test_marker_must_be_root_owned_and_non_writable(self):
        marker = Mock()
        marker.is_symlink.return_value = False
        marker.is_file.return_value = True
        marker.stat.return_value = Mock(st_uid=0, st_mode=0o100644)
        marker.read_text.return_value = "OPERATOR_PRESENT_INDEPENDENT_CUTOFF_CONFIRMED"
        self.assertTrue(marker_valid(marker))
        marker.stat.return_value = Mock(st_uid=0, st_mode=0o100666)
        self.assertFalse(marker_valid(marker))

    def test_no_marker_blocks_every_gpio_operation(self):
        with patch("dama_lite.heating_onsite_test.marker_valid", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Autorisation opérateur"):
                safe_preflight(config(), sensor=Sensor(),
                               cpu_reader=lambda: 42.0,
                               status={"power":"on", "tests":[], "thermal":{"heating_enabled":False}})

    def test_live_experiment_blocks_commissioning(self):
        with patch("dama_lite.heating_onsite_test.marker_valid", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "analyses en cours"):
                safe_preflight(config(), sensor=Sensor(), cpu_reader=lambda: 42.0,
                               status={"power":"on", "tests":[{"state":"running"}],
                                       "thermal":{"heating_enabled":False}})

    def test_authorized_no_active_test_passes_dry_guard(self):
        with patch("dama_lite.heating_onsite_test.marker_valid", return_value=True):
            report = safe_preflight(config(), sensor=Sensor(),
                                    cpu_reader=lambda: 44.0,
                                    status={"power":"on", "tests":[],
                                            "thermal":{"heating_enabled":False}})
        self.assertEqual([22.0, 22.0, 22.0], report["sensor_samples_c"])
        self.assertFalse(report["permanent_heater_authorized"])
        self.assertEqual(MAX_TEST_TEMPERATURE, 38.5)
        self.assertEqual(MAX_RUNTIME, 600.0)


if __name__ == "__main__":
    unittest.main()
