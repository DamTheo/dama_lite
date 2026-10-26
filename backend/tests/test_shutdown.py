"""Arrêt OS testé sans demander au noyau d'éteindre le Pi."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from dama_lite.config import Config
from dama_lite.service import DamaLiteService
from dama_lite.sessions import CannotStart
from dama_lite.safe_staging import validate_staging


class FakeThermal:
    def __init__(self):
        self.stopped = False
    def stop(self):
        self.stopped = True
    def snapshot(self):
        return {"ready": False, "heating_enabled": False, "heater_on": False,
                "fault": None, "temperature_c": 22, "cpu_temperature_c": 39}


class FakeCameras:
    def __init__(self, cams):
        self.specs = {c.slot: c for c in cams}
    def ready(self, n):
        return True
    def close(self):
        pass


class FakeLights:
    blackout_active = False
    def close(self):
        pass


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        cfg_path = folder / "config.json"
        cfg_path.write_text(
            '{"state_dir": "' + str(folder / "db") +
            '", "heating_enabled": false, "leds_enabled": false}',
            encoding="utf-8",
        )
        self.cfg = Config.load(cfg_path)
        self.thermal = FakeThermal()
        self.svc = DamaLiteService(
            self.cfg, thermal=self.thermal,
            cameras=FakeCameras(self.cfg.cameras), lights=FakeLights(),
        )
        self.svc.state = "on"

    def tearDown(self):
        self.svc.sessions.close()
        self.svc.uploader.stop()
        self.svc.store.close()
        self.tmp.cleanup()

    def test_no_shutdown_if_os_gateway_unavailable(self):
        self.assertFalse(self.svc.shutdown_available())
        with self.assertRaisesRegex(CannotStart, "non autorisée"):
            self.svc.request_shutdown(confirmed_active_tests=True)
        self.assertFalse(self.thermal.stopped)
        self.assertEqual("on", self.svc.state)

    def test_confirmation_required_with_running_test(self):
        item = self.svc.store.new_test("ACTIVE", 1, "fake-folder", None)
        # Simuler la disponibilité d'une passerelle sans déclencher d'arrêt
        # ni écrire de marqueur sous /run.
        with patch.object(self.svc, "shutdown_available", return_value=True):
            with self.assertRaisesRegex(CannotStart, "confirmer"):
                self.svc.request_shutdown(confirmed_active_tests=False)
        self.assertTrue(self.svc._shutdown_confirmation_required)
        self.assertFalse(self.thermal.stopped)
        self.svc.cancel_shutdown_confirmation()
        self.assertFalse(self.svc._shutdown_confirmation_required)
        self.assertEqual("running", self.svc.store.running()[0]["state"])

    def test_physical_button_requires_confirmation(self):
        self.svc.store.new_test("ACTIVE-PHYSICAL", 1, "folder", None)
        self.svc._physical_power_button()
        self.assertTrue(self.svc.snapshot()["shutdown_confirmation_required"])
        self.assertFalse(self.thermal.stopped)

    def test_root_owned_read_only_operator_marker(self):
        from dama_lite.safe_staging import shutdown_approved
        from unittest.mock import Mock
        marker = Mock()
        marker.is_symlink.return_value = False
        marker.is_file.return_value = True
        marker.stat.return_value = Mock(st_uid=0, st_mode=0o100644)
        marker.read_text.return_value = "DAMA_LITE_UI_POWER_OFF_AUTHORIZED"
        self.assertTrue(shutdown_approved(marker))
        marker.stat.return_value = Mock(st_uid=0, st_mode=0o100666)
        self.assertFalse(shutdown_approved(marker))

    def test_staging_rejects_heat_even_if_poweroff_allowed(self):
        cfg = replace(self.cfg, allow_os_shutdown=True, heating_enabled=True)
        with patch("dama_lite.safe_staging.shutdown_approved", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "chauffage"):
                validate_staging(cfg)


if __name__ == "__main__":
    unittest.main()
