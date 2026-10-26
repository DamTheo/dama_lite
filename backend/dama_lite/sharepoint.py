"""Transfert Microsoft Graph par certificat et dossier DIRECT par nom de test.

Aucun secret SharePoint dans ce dépôt. La création du dossier distant est
obligatoire avant le début d'une analyse ; les images sont mises en attente
sur disque seulement après cette réservation.
"""
from __future__ import annotations

import logging
import re
import stat
import threading
import time
from pathlib import Path
from urllib.parse import quote

from .config import SharePointConfig
from .entra_env import read_graph_env

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
        self._drive_verified = False
        self._graph_access_token: str | None = None
        self._graph_token_expiry: float = 0.0

    def _token(self) -> str:
        if not self.cfg.configured:
            raise SharePointError("SharePoint non configuré : impossible de démarrer une analyse.")
        if self.cfg.graph_env_path:
            # Client credentials Entra via HTTPS, depuis le fichier local 0600.
            # Cette voie évite d'installer MSAL dans le Python système du Pi.
            import requests

            with self._lock:
                if self._graph_access_token and time.monotonic() < self._graph_token_expiry:
                    return self._graph_access_token
                keys = read_graph_env(self.cfg.graph_env_path)
                endpoint = (
                    "https://login.microsoftonline.com/"
                    + quote(self.cfg.tenant_id, safe="")
                    + "/oauth2/v2.0/token"
                )
                try:
                    reply = requests.post(
                        endpoint,
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self.cfg.client_id,
                            "client_secret": keys["MS_CLIENT_SECRET"],
                            "scope": "https://graph.microsoft.com/.default",
                        },
                        timeout=(10, 25),
                    )
                except requests.RequestException as exc:
                    raise SharePointError(
                        "Connexion à Microsoft Entra impossible."
                    ) from exc
                if not reply.ok:
                    try:
                        code = reply.json().get("error", "auth_failed")
                    except ValueError:
                        code = "auth_failed"
                    raise SharePointError(
                        f"Microsoft Entra HTTP {reply.status_code} ({code})."
                    )
                try:
                    reply_data = reply.json()
                    token = reply_data["access_token"]
                    expires = int(reply_data.get("expires_in", 3600))
                except (KeyError, ValueError, TypeError) as exc:
                    raise SharePointError(
                        "Réponse Microsoft Entra invalide."
                    ) from exc
                if not isinstance(token, str) or not token:
                    raise SharePointError("Microsoft Entra : jeton absent.")
                self._graph_access_token = token
                self._graph_token_expiry = (
                    time.monotonic() + max(5, expires - 120)
                )
                return token
        with self._lock:
            if self._app is None:
                from msal import ConfidentialClientApplication

                if self.cfg.graph_env_path:
                    # Le secret existant reste dans le fichier 0600 du Pi.
                    # Ne jamais le recopier dans le JSON ou la télémétrie.
                    credential = read_graph_env(
                        self.cfg.graph_env_path
                    )["MS_CLIENT_SECRET"]
                elif self.cfg.client_secret_path:
                    # La valeur du secret n'est jamais présente en JSON,
                    # argument CLI, URL, log ni Git. Seul son chemin est configuré.
                    secret_file = Path(self.cfg.client_secret_path)
                    if not secret_file.is_file():
                        raise SharePointError(
                            "Fichier local du secret Microsoft Entra introuvable."
                        )
                    if stat.S_IMODE(secret_file.stat().st_mode) & 0o077:
                        raise SharePointError(
                            "Permissions du secret Entra trop larges : chmod 600 requis."
                        )
                    credential = secret_file.read_text(encoding="utf-8").strip()
                    if not credential:
                        raise SharePointError("Secret Microsoft Entra vide.")
                else:
                    private = Path(self.cfg.private_key_path)
                    certificate = Path(self.cfg.public_cert_path)
                    if not private.is_file() or not certificate.is_file():
                        raise SharePointError("Certificats SharePoint absents sur le Pi.")
                    # MSAL >=1.35 utilise le certificat public pour SHA-256.
                    credential = {
                        "public_certificate": certificate.read_text(encoding="utf-8"),
                        "private_key": private.read_text(encoding="utf-8"),
                    }
                self._app = ConfidentialClientApplication(
                    client_id=self.cfg.client_id,
                    authority=f"https://login.microsoftonline.com/{self.cfg.tenant_id}",
                    client_credential=credential,
                )
            result = self._app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"],
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
                # Recréer le client pour éviter de reprendre un jeton 401
                # mis en cache. Le flux client_credentials n'a pas de RT.
                with self._lock:
                    self._app = None
                    self._graph_access_token = None
                    self._graph_token_expiry = 0.0
                token = self._token()
                continue
            if response.status_code == 409:
                raise NameConflict("Un dossier de ce nom existe déjà dans DAMA-Lite.")
            if not response.ok:
                raise SharePointError(
                    f"Graph HTTP {response.status_code}: {response.text[:400]}"
                )
            return response.json() if response.content else {}
        raise SharePointError("Authentification Graph refusée après renouvellement.")

    def _verify_drive(self) -> None:
        if self._drive_verified:
            return
        with self._lock:
            if self._drive_verified:
                return
            drive = quote(self.cfg.drive_id, safe="")
            metadata = self._request("GET", f"{BASE}/drives/{drive}")
            if metadata.get("name") != self.cfg.expected_drive_name:
                raise SharePointError(
                    "Mauvaise bibliothèque Microsoft Graph : l'ID choisi "
                    "ne pointe pas vers R&D Biologie."
                )
            self._drive_verified = True

    def _resolve_root_folder(self) -> dict:
        self._verify_drive()
        root = quote(self.cfg.folder_root, safe="/")
        drive = quote(self.cfg.drive_id, safe="")
        item = self._request(
            "GET", f"{BASE}/drives/{drive}/root:/{root}"
        )
        if not item.get("id"):
            raise SharePointError("Dossier DAMA-Lite introuvable dans SharePoint.")
        if item.get("name") and item["name"] != "DAMA-Lite":
            raise SharePointError("Le dossier Graph cible n'est pas DAMA-Lite.")
        if self.cfg.graph_folder_id and item["id"] != self.cfg.graph_folder_id:
            raise SharePointError(
                "Le dossier Graph ne correspond pas à MS_FOLDER_ID : "
                "aucune écriture n'est autorisée."
            )
        return item

    def verify_read_only(self) -> dict[str, str | bool]:
        """Authentifie et valide le chemin exact sans aucune création."""
        root_item = self._resolve_root_folder()
        return {
            "drive_verified": True,
            "folder_name": root_item.get("name", "DAMA-Lite"),
            "folder_matches_env": (
                not self.cfg.graph_folder_id
                or root_item["id"] == self.cfg.graph_folder_id
            ),
        }

    def reserve_folder(self, name: str) -> tuple[str, str | None]:
        name = validate_test_name(name)
        root_item = self._resolve_root_folder()
        drive = quote(self.cfg.drive_id, safe="")
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
        self._verify_drive()
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
