"""Contrat Microsoft Graph hors réseau : l'identité de la bibliothèque est obligatoire."""
import unittest
from urllib.parse import quote

from dama_lite.config import SHAREPOINT_ROOT, SharePointConfig
from dama_lite.sharepoint import NameConflict, SharePointClient, SharePointError


def configured():
    return SharePointConfig(
        tenant_id="placeholder", client_id="placeholder",
        drive_id="drive-rd", private_key_path="/unused/private",
        public_cert_path="/unused/public",
    )


class FakeGraph(SharePointClient):
    def __init__(self):
        super().__init__(configured())
        self.calls = []
        self.drive_name = "R&D Biologie"

    def _request(self, method, url, *, json_body=None, data=None):
        self.calls.append((method, url, json_body, data))
        if url.endswith("/drives/drive-rd"):
            return {"name": self.drive_name}
        if method == "GET":
            return {"id": "DAMA_LITE_ROOT", "name": "DAMA-Lite"}
        if method == "POST":
            if json_body["@microsoft.graph.conflictBehavior"] != "fail":
                raise AssertionError("Le nom du dossier doit rester EXACT.")
            return {"id": "TEST_FOLDER", "name": json_body["name"],
                    "webUrl": "https://example.invalid/test"}
        if method == "PUT":
            return {"id": "image-id"}
        raise AssertionError("Méthode Graph inattendue")


class GraphContractTests(unittest.TestCase):
    def test_single_directory_per_test_inside_r_and_d_biologie(self):
        g = FakeGraph()
        folder_id, url = g.reserve_folder("Ecoli-01")
        self.assertEqual("TEST_FOLDER", folder_id)
        self.assertEqual("https://example.invalid/test", url)
        self.assertEqual(3, len(g.calls))
        self.assertEqual(("GET", "GET", "POST"), tuple(c[0] for c in g.calls))
        self.assertIn(
            "/root:/" + quote(SHAREPOINT_ROOT, safe="/"), g.calls[1][1]
        )
        self.assertEqual("Ecoli-01", g.calls[2][2]["name"])
        self.assertNotIn("camera", g.calls[2][1].lower())
        self.assertNotIn("camera", g.calls[2][2]["name"].lower())
        g.upload(folder_id, "photo.png", b"\x89PNG\r\n\x1a\n")
        self.assertEqual(4, len(g.calls))  # Drive vérifié une fois seulement.
        self.assertIn("TEST_FOLDER:/photo.png:/content", g.calls[3][1])
        self.assertEqual(b"\x89PNG\r\n\x1a\n", g.calls[3][3])

    def test_graph_env_folder_id_must_match_exact_target(self):
        g = FakeGraph()
        from dataclasses import replace
        g.cfg = replace(g.cfg, graph_folder_id="ANOTHER_FOLDER")
        with self.assertRaisesRegex(SharePointError, "MS_FOLDER_ID"):
            g.reserve_folder("AnyTest")
        self.assertEqual(["GET", "GET"], [c[0] for c in g.calls])

    def test_readonly_verify_creates_no_dossier(self):
        g = FakeGraph()
        result = g.verify_read_only()
        self.assertEqual("DAMA-Lite", result["folder_name"])
        self.assertEqual(["GET", "GET"], [c[0] for c in g.calls])

    def test_wrong_library_is_refused_before_test_folder(self):
        g = FakeGraph()
        g.drive_name = "Documents"
        with self.assertRaisesRegex(SharePointError, "R&D Biologie"):
            g.reserve_folder("Ecoli-01")
        self.assertEqual(1, len(g.calls))
        self.assertEqual("GET", g.calls[0][0])


if __name__ == "__main__":
    unittest.main()
