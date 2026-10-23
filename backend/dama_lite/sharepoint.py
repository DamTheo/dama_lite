"""Transfert Microsoft Graph par certificat et dossier DIRECT par nom de test.

Aucun secret SharePoint dans ce dépôt. La création du dossier distant est
obligatoire avant le début d'une analyse ; les images sont mises en attente
sur disque seulement après cette réservation.
"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote

from .config import SharePointConfig

LOG = logging.getLogger(__name__)
BASE = "https://graph.microsoft.com/v1.0"


class SharePointError(RuntimeError):
    pass


class NameConflict(SharePointError):
    pass


def validate_test_name(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 110:
        raise ValueError("Le nom du test doit contenir 1 à 110 caractères.")
    if value != value.strip(" .") or value in {".", ".."}:
        raise ValueError("Le nom du test ne doit pas commencer/finir par un espace ou un point.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', value):
        raise ValueError("Le nom du test contient un caractère interdit par SharePoint.")
    if value.lower() in {"con", "prn", "aux", "nul"}:
        raise ValueError("Nom de test réservé.")
    return value


class SharePointClient:
    def __init__(self, cfg: SharePointConfig):
        self.cfg = cfg
        self._app = None
        self._lock = threading.RLock()

    def _token(self, refresh: bool = False) -> str:
        if not self.cfg.configured:
            raise SharePointError("SharePoint non configuré : impossible de démarrer une analyse.")
        with self._lock:
            if self._app is None:
                from msal import ConfidentialClientApplication

                private = Path(self.cfg.private_key_path)
                certificate = Path(self.cfg.public_cert_path)
                if not private.is_file() or not certificate.is_file():
                    raise SharePointError("Certificats SharePoint absents sur le Pi.")
                fingerprint = subprocess.run(
                    ["openssl", "x509", "-in", str(certificate), "-noout",
                     "-fingerprint", "-sha1"],
                    check=True, capture_output=True, text=True, timeout=8,
                ).stdout.strip().split("=", 1)[-1].replace(":", "")
                self._app = ConfidentialClientApplication(
                    client_id=self.cfg.client_id,
                    authority=f"https://login.microsoftonline.com/{self.cfg.tenant_id}",
                    client_credential={
                        "thumbprint": fingerprint,
                        "private_key": private.read_text(encoding="utf-8"),
                    },
                )
            result = self._app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"],
                force_refresh=refresh,
            )
            if not result.get("access_token"):
                raise SharePointError(
                    f"Authentification Microsoft Graph impossible : {result.get('error', 'unknown')}"
                )
            return result["access_token"]

    def _request(self, method: str, url: str, *, json_body=None, data=None):
        import requests

        token = self._token()
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {token}"}
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            if data is not None:
                headers["Content-Type"] = "image/png"
            try:
                response = requests.request(
                    method, url, headers=headers, json=json_body, data=data,
                    timeout=(10, 60),
                )
            except requests.RequestException as exc:
                raise SharePointError(f"Réseau Graph indisponible : {exc}") from exc
            if response.status_code == 401 and attempt == 0:
                token = self._token(refresh=True)
                continue
            if response.status_code == 409:
                raise NameConflict("Un dossier de ce nom existe déjà dans DAMA-Lite.")
            if not response.ok:
                raise SharePointError(
                    f"Graph HTTP {response.status_code}: {response.text[:400]}"
                )
            return response.json() if response.content else {}
        raise SharePointError("Authentification Graph refusée après renouvellement.")

    def reserve_folder(self, name: str) -> tuple[str, str | None]:
        name = validate_test_name(name)
        root = quote(self.cfg.folder_root, safe="/")
        drive = quote(self.cfg.drive_id, safe="")
        root_item = self._request(
            "GET", f"{BASE}/drives/{drive}/root:/{root}"
        )
        if not root_item.get("id"):
            raise SharePointError("Dossier DAMA-Lite introuvable dans SharePoint.")
        result = self._request(
            "POST",
            f"{BASE}/drives/{drive}/items/{quote(root_item['id'], safe='')}/children",
            json_body={
                "name": name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            },
        )
        if result.get("name") != name or not result.get("id"):
            raise SharePointError("Nom ou identifiant distant inattendu après création du test.")
        return result["id"], result.get("webUrl")

    def upload(self, folder_id: str, filename: str, content: bytes) -> None:
        if not filename.endswith(".png") or "/" in filename or "\\" in filename:
            raise SharePointError("Nom de fichier invalide.")
        drive = quote(self.cfg.drive_id, safe="")
        folder = quote(folder_id, safe="")
        target = quote(filename, safe="")
        self._request(
            "PUT",
            f"{BASE}/drives/{drive}/items/{folder}:/{target}:/content",
            data=content,
        )


class UploadWorker:
    def __init__(self, store, client: SharePointClient):
        self.store = store
        self.client = client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sharepoint")
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            for item in self.store.due_uploads(limit=4):
                if self._stop.is_set():
                    break
                try:
                    content = Path(item["path"]).read_bytes()
                    self.client.upload(item["folder_id"], item["filename"], content)
                    # Toujours confirmer en base AVANT suppression du fichier local.
                    self.store.mark_uploaded(item["id"])
                    try:
                        Path(item["path"]).unlink(missing_ok=True)
                    except OSError:
                        LOG.warning("Nettoyage local reporté pour %s", item["filename"])
                    LOG.info("Photo synchronisée : %s", item["filename"])
                except Exception as exc:
                    LOG.warning("Envoi SharePoint reporté (%s) : %s", item["filename"], exc)
                    self.store.mark_upload_failure(
                        item["id"], int(item["attempts"]) + 1, str(exc)
                    )
            self._stop.wait(2)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
