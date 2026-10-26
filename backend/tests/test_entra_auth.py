"""Authentification Entra simulée : aucun accès réseau ni clé publiée."""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dama_lite.config import SharePointConfig
from dama_lite.sharepoint import SharePointClient, SharePointError


class AuthTests(unittest.TestCase):
    def test_client_secret_loaded_from_private_file_only(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "entra.secret"
            key.write_text("secret-for-local-test\n", encoding="utf-8")
            key.chmod(0o600)
            cfg = SharePointConfig(
                tenant_id="tenant", client_id="client", drive_id="drive",
                client_secret_path=str(key),
            )
            app = MagicMock()
            app.acquire_token_for_client.return_value = {"access_token": "example"}
            msal = types.ModuleType("msal")
            msal.ConfidentialClientApplication = MagicMock(return_value=app)
            with patch.dict(sys.modules, {"msal": msal}):
                self.assertEqual("example", SharePointClient(cfg)._token())
            credentials = msal.ConfidentialClientApplication.call_args.kwargs
            self.assertEqual("secret-for-local-test", credentials["client_credential"])
            self.assertEqual("client", credentials["client_id"])

    def test_reject_secret_with_open_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "entra.secret"
            key.write_text("example", encoding="utf-8")
            key.chmod(0o644)
            cfg = SharePointConfig(
                tenant_id="tenant", client_id="client", drive_id="drive",
                client_secret_path=str(key),
            )
            msal = types.ModuleType("msal")
            msal.ConfidentialClientApplication = MagicMock()
            with patch.dict(sys.modules, {"msal": msal}):
                with self.assertRaisesRegex(SharePointError, "chmod 600"):
                    SharePointClient(cfg)._token()


if __name__ == "__main__":
    unittest.main()


class GraphEnvOauthTests(unittest.TestCase):
    def test_client_credentials_cached_without_exposing_secret(self):
        from unittest.mock import patch
        import tempfile
        from pathlib import Path
        from dama_lite.config import SharePointConfig
        from dama_lite.sharepoint import SharePointClient

        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "graph.env"
            file.write_text(
                "MS_TENANT_ID=tenant\nMS_CLIENT_ID=client\n"
                "MS_CLIENT_SECRET=private-test-value\nMS_DRIVE_ID=drive\n",
                encoding="utf-8",
            )
            file.chmod(0o600)
            cfg = SharePointConfig(
                tenant_id="tenant", client_id="client",
                drive_id="drive", graph_env_path=str(file),
            )
            reply = MagicMock()
            reply.ok = True
            reply.json.return_value = {
                "access_token": "token-test", "expires_in": 3600
            }
            with patch("requests.post", return_value=reply) as request:
                client = SharePointClient(cfg)
                self.assertEqual("token-test", client._token())
                self.assertEqual("token-test", client._token())
            self.assertEqual(1, request.call_count)
            self.assertEqual(
                "private-test-value",
                request.call_args.kwargs["data"]["client_secret"],
            )
