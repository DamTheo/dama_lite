"""Tests de qualification du relais — aucun matériel activé."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from dama_lite.config import Config
from dama_lite.heat_qualification import (
    MARKER_TEXT, QualificationError, validate_before_heating
)


class FakeSensor:
    def __init__(self, values):
        self.values = iter(values)

    def read(self):
        return next(self.values)


class QualificationTests(unittest.TestCase):
    def test_refuse_staging_even_with_marker(self):
        with tempfile.TemporaryDirectory() as root:
            config_file = Path(root) / "config.json"
            config_file.write_text("{}")
            cfg = Config.load(config_file)
            with self.assertRaisesRegex(QualificationError, "n'active pas"):
                validate_before_heating(cfg)

    def test_refuse_heating_without_independent_cutoff(self):
        with tempfile.TemporaryDirectory() as root:
            config_file = Path(root) / "config.json"
            config_file.write_text('{"heating_enabled":true}')
            cfg = Config.load(config_file)
            with self.assertRaisesRegex(QualificationError, "interdite"):
                validate_before_heating(cfg, marker=Path(root) / "absent")

    def test_ready_guard_never_commands_real_relay(self):
        with tempfile.TemporaryDirectory() as root:
            config_file = Path(root) / "config.json"
            config_file.write_text('{"heating_enabled":true}')
            cfg = Config.load(config_file)
            marker = Path(root) / "heating-qualified"
            marker.write_text(MARKER_TEXT)
            marker.chmod(0o600)
            with patch("dama_lite.heat_qualification.os.geteuid", return_value=0):
                # stat() returns ownership of the CI user; replace only
                # marker_valid, not the expected sensor and CPU guards.
                with patch("dama_lite.heat_qualification.marker_valid", return_value=True):
                    result = validate_before_heating(
                        cfg, marker=marker,
                        sensor=FakeSensor([22.1, 22.2, 22.2]),
                        cpu_reader=lambda: 41.0,
                    )
            self.assertEqual(21, result["relay_gpio"])
            self.assertFalse(result["heating_commanded"])


if __name__ == "__main__":
    unittest.main()
