import json
import tempfile
import unittest
from pathlib import Path

from dama_lite.config import Config, ConfigError, SHAREPOINT_ROOT


def load(data):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return Config.load(path)


class ConfigTests(unittest.TestCase):
    def test_default_heater_off_and_eight_slots(self):
        cfg = load({})
        self.assertFalse(cfg.heating_enabled)
        self.assertEqual(8, len(cfg.cameras))
        self.assertEqual(37.0, cfg.setpoint_c)
        self.assertEqual(35.0, cfg.start_min_c)
        self.assertEqual(300, cfg.camera_interval_s)
        self.assertEqual(SHAREPOINT_ROOT, cfg.sharepoint.folder_root)

    def test_reject_remote_listener(self):
        with self.assertRaises(ConfigError):
            load({"host": "0.0.0.0"})

    def test_reject_same_camera_twice(self):
        cameras = [{"slot": x, "device": "/dev/v4l/by-path/camera"} for x in range(1, 9)]
        with self.assertRaises(ConfigError):
            load({"cameras": cameras})

    def test_reject_conflicting_gpio(self):
        with self.assertRaises(ConfigError):
            load({"shutdown_button_gpio": 21})

    def test_reject_non_contract_sharepoint_structure(self):
        with self.assertRaises(ConfigError):
            load({"sharepoint": {"folder_root": SHAREPOINT_ROOT + "/camera1"}})


if __name__ == "__main__":
    unittest.main()
