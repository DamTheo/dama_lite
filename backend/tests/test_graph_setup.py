import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dama_lite.config import Config, ConfigError
from dama_lite.graph_setup import enable_existing_graph


class ExistingEntraTests(unittest.TestCase):
    def test_configure_only_authorized_staging_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = root / "graph.env"
            env.write_text(
                "MS_TENANT_ID=tenant\nMS_CLIENT_ID=client\n"
                "MS_CLIENT_SECRET=unused-test-secret\nMS_DRIVE_ID=drive\n"
                "MS_FOLDER_ID=dama-folder\n", encoding="utf-8",
            )
            env.chmod(0o600)
            cfg = root / "config.staging.json"
            cfg.write_text('{"heating_enabled":false,"leds_enabled":false}',
                           encoding="utf-8")
            cfg.chmod(0o600)
            with patch("dama_lite.graph_setup.STAGING_CONFIG", cfg):
                backup = enable_existing_graph(cfg, str(env))
            self.assertTrue(backup.exists())
            got = Config.load(cfg)
            self.assertTrue(got.sharepoint.configured)
            self.assertEqual("drive", got.sharepoint.drive_id)
            self.assertNotIn("unused-test-secret", cfg.read_text())
            self.assertFalse(got.heating_enabled)
            self.assertFalse(got.leds_enabled)

    def test_other_config_cannot_be_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = root / "other.json"
            cfg.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "staging"):
                enable_existing_graph(cfg, str(root / "graph.env"))


if __name__ == "__main__":
    unittest.main()
