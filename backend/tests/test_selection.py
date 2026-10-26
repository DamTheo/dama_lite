"""Sélection tactile : expiration autonome et aucun effet sur la chauffe."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dama_lite.config import Config
from dama_lite.service import DamaLiteService


class FakeThermal:
    def start(self): pass
    def snapshot(self):
        return {
            "temperature_c": 22.0, "cpu_temperature_c": 43.0,
            "fault": None, "heater_on": False, "heating_enabled": False,
            "ready": False,
        }
    def stop(self): pass


class FakeCamera:
    def __init__(self, specs):
        self.specs = {s.slot: s for s in specs}
    def ready(self, slot): return True


class FakeLights:
    blackout_active = False
    def close(self): pass


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        c = self.path / "config.json"
        c.write_text('{"heating_enabled":false,"leds_enabled":false}', encoding="utf-8")
        cfg = Config.load(c)
        self.svc = DamaLiteService(
            cfg, thermal=FakeThermal(), cameras=FakeCamera(cfg.cameras),
            lights=FakeLights(),
        )
        self.svc.state = "on"

    def tearDown(self):
        self.svc.uploader.stop()
        self.svc.sessions.close()
        self.svc.store.close()
        self.tmp.cleanup()

    def test_selection_and_expiration(self):
        with patch("dama_lite.service.time.monotonic", return_value=100.0):
            self.svc.select_ui_camera(6)
            self.assertEqual(6, self.svc.ui_selected_camera())
            self.assertEqual(6, self.svc.snapshot()["ui_selected_camera"])
        with patch("dama_lite.service.time.monotonic", return_value=103.99):
            self.assertEqual(6, self.svc.ui_selected_camera())
        with patch("dama_lite.service.time.monotonic", return_value=104.0):
            self.assertIsNone(self.svc.ui_selected_camera())

    def test_clear_and_invalid_slots(self):
        for value in (True, 0, 9, "2"):
            with self.assertRaises(ValueError):
                self.svc.select_ui_camera(value)
        self.svc.select_ui_camera(2)
        self.svc.select_ui_camera(None)
        self.assertIsNone(self.svc.ui_selected_camera())
        self.assertFalse(self.svc.snapshot()["thermal"]["heating_enabled"])


if __name__ == "__main__":
    unittest.main()
