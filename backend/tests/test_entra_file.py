"""Tests du fichier MS_* : aucun secret réel ni requête réseau."""
import json
import tempfile
import unittest
from pathlib import Path

from dama_lite.config import Config, ConfigError
from dama_lite.entra_env import read_graph_env


class EntrafileTests(unittest.TestCase):
    def test_staging_config_loads_ids_but_not_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "graph.env"
            env.write_text(
                "MS_TENANT_ID=t-test\nMS_CLIENT_ID=c-test\n"
                "MS_CLIENT_SECRET=s-test-secret\n"
                "MS_DRIVE_ID=d-test\nMS_FOLDER_ID=f-test\n",
                encoding="utf-8",
            )
            env.chmod(0o600)
            cfg_file = Path(tmp) / "config.json"
            cfg_file.write_text(
                json.dumps({"sharepoint": {"graph_env_path": str(env)}}),
                encoding="utf-8",
            )
            config = Config.load(cfg_file)
            self.assertTrue(config.sharepoint.configured)
            self.assertEqual("d-test", config.sharepoint.drive_id)
            self.assertEqual("f-test", config.sharepoint.graph_folder_id)
            self.assertNotIn("s-test-secret", repr(config))
            self.assertEqual("s-test-secret", read_graph_env(str(env))["MS_CLIENT_SECRET"])

    def test_reject_world_readable_auth_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "graph.env"
            env.write_text(
                "MS_TENANT_ID=t\nMS_CLIENT_ID=c\nMS_CLIENT_SECRET=secret\n"
                "MS_DRIVE_ID=d\n", encoding="utf-8",
            )
            env.chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "chmod 600"):
                read_graph_env(str(env))

    def test_missing_required_field_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "graph.env"
            env.write_text("MS_CLIENT_SECRET=secret\n", encoding="utf-8")
            env.chmod(0o600)
            with self.assertRaisesRegex(ConfigError, "incomplet"):
                read_graph_env(str(env))


if __name__ == "__main__":
    unittest.main()
