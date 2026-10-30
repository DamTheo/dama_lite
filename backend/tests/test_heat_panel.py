"""Aucun cas de test ne déclenche un GPIO ni un systemctl start réel."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dama_lite.config import Config
from dama_lite.heat_panel import HeatTestPanel, _last_record
from dama_lite.sessions import CannotStart


def config():
    with tempfile.TemporaryDirectory() as folder:
        p = Path(folder) / "config.json"
        p.write_text('{"heating_enabled":false,"leds_enabled":false}',
                     encoding="utf-8")
        return Config.load(p)


class HeatPanelTests(unittest.TestCase):
    def setUp(self):
        self.panel = HeatTestPanel(config())

    def test_no_operator_authorization_denies_start(self):
        with patch("dama_lite.heat_panel._path_ready", return_value=True), \
             patch("dama_lite.heat_panel.marker_valid", return_value=False):
            with self.assertRaisesRegex(CannotStart, "autorisation"):
                self.panel.start(
                    confirmed_present=True, confirmed_cutoff=True,
                    machine_power="on", running_tests=[],
                )

    def test_confirmation_must_be_true_and_bool(self):
        for presence in (False, 1, "oui", None):
            with self.assertRaises(ValueError):
                self.panel.start(
                    confirmed_present=presence, confirmed_cutoff=True,
                    machine_power="on", running_tests=[],
                )

    def test_do_not_start_while_experiment_running(self):
        with self.assertRaisesRegex(CannotStart, "expérience"):
            self.panel.start(
                confirmed_present=True, confirmed_cutoff=True,
                machine_power="on", running_tests=[{"state": "running"}],
            )

    def test_no_gpio_in_start_confirmation(self):
        with patch("dama_lite.heat_panel._path_ready", return_value=True), \
             patch("dama_lite.heat_panel.marker_valid", return_value=True), \
             patch("dama_lite.heat_panel.safe_preflight",
                   return_value={"sensor_samples_c": [21.5] * 3}), \
             patch.object(self.panel, "snapshot",
                          return_value={"active": False, "request_pending": False}), \
             patch.object(self.panel, "_request") as request:
            result = self.panel.start(
                confirmed_present=True, confirmed_cutoff=True,
                machine_power="on", running_tests=[],
            )
            self.assertEqual("requested", result["status"])
            request.assert_called_once_with("START")

    def test_stop_does_not_require_heat_authorization(self):
        with patch.object(self.panel, "_request") as request:
            self.panel.stop()
            request.assert_called_once_with("STOP")


if __name__ == "__main__":
    unittest.main()
