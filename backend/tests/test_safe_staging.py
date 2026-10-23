"""Tests du verrou anti-actionneur du service d'évaluation."""
import unittest
from dataclasses import replace
from pathlib import Path

from dama_lite.config import CameraSpec, Config, SharePointConfig
from dama_lite.safe_staging import validate_staging


def cfg():
    return Config(
        host="127.0.0.1", port=8765, state_dir=Path("/tmp/staging"),
        ui_dir=Path("/tmp/staging-ui"),
        sensor_id="28-0000006ca681",
        heating_enabled=False, relay_gpio=21, relay_active_high=True,
        setpoint_c=37.0, start_min_c=35.0, hysteresis_c=0.3,
        enclosure_limit_c=41.0, cpu_warning_c=65.0, cpu_cutoff_c=80.0,
        temperature_poll_s=2.0, leds_enabled=False, led_gpio=12,
        led_brightness=0.1, camera_interval_s=300,
        spool_limit_bytes=1024**3,
        cameras=tuple(CameraSpec(slot=i, device=None) for i in range(1, 9)),
        sharepoint=SharePointConfig(), shutdown_button_gpio=None,
        allow_os_shutdown=False, shutdown_animation_s=4.8,
    )


class SafeStagingTests(unittest.TestCase):
    def test_safe_profile_passes(self):
        validate_staging(cfg())

    def test_unsafe_actuators_fail_before_backend_starts(self):
        for changed in (
            {"heating_enabled": True},
            {"leds_enabled": True},
            {"allow_os_shutdown": True},
            {"shutdown_button_gpio": 16},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(RuntimeError):
                    validate_staging(replace(cfg(), **changed))


if __name__ == "__main__":
    unittest.main()
