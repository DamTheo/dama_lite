"""HTTP local sans exposition réseau ; fichiers du frontend et API tactile."""
from __future__ import annotations

import json
import logging
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import Config
from .service import DamaLiteService
from .sessions import CannotStart
from .sharepoint import NameConflict, SharePointError

LOG = logging.getLogger(__name__)


def make_handler(service: DamaLiteService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DamaLite/0.1"
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, data: bytes, mime: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code: int, payload: dict) -> None:
            self._send(
                code, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _error(self, code: int, message: str) -> None:
            self._json(code, {"error": message})

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    self._json(200, {"status": service.state})
                    return
                if path == "/api/status":
                    self._json(200, service.snapshot())
                    return
                match = re.fullmatch(r"/api/cameras/([1-8])/preview", path)
                if match:
                    if service.state != "on":
                        self._error(503, "Incubateur en cours d'arrêt.")
                        return
                    jpg = service.cameras.preview(int(match.group(1)))
                    self._send(200, jpg, "image/jpeg")
                    return
                if path.startswith("/api/"):
                    self._error(404, "Endpoint inconnu.")
                    return
                root = service.cfg.ui_dir.resolve()
                target = (root / unquote(path).lstrip("/")).resolve()
                if not target.is_relative_to(root):
                    self._error(403, "Accès interdit.")
                    return
                if path == "/":
                    target = root / "index.html"
                if not target.is_file():
                    self._error(404, "Frontend non construit (ui/dist absent).")
                    return
                mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self._send(200, target.read_bytes(), mime)
            except Exception as exc:
                LOG.exception("GET %s : %s", path, exc)
                self._error(503, str(exc))

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            try:
                # Même origine seulement : aucun CORS autorisé. Refuser les
                # formulaires cross-site simples et les POST non JSON.
                origin = self.headers.get("Origin")
                if origin and origin not in {
                    f"http://127.0.0.1:{service.cfg.port}",
                    f"http://localhost:{service.cfg.port}",
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                }:
                    self._error(403, "Origine interdite.")
                    return
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self._error(415, "Content-Type application/json obligatoire.")
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 4096:
                    self._error(413, "Requête trop volumineuse.")
                    return
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    self._error(400, "Corps JSON invalide.")
                    return
                if path == "/api/tests":
                    if service.state != "on":
                        raise CannotStart("Machine non disponible.")
                    slot = body.get("camera")
                    if type(slot) is not int:
                        raise ValueError("Numéro de caméra incorrect.")
                    item = service.sessions.new_test(slot, body.get("name"))
                    self._json(201, {"test": item})
                    return
                match = re.fullmatch(r"/api/tests/([a-f0-9-]{36})/stop", path)
                if match:
                    service.sessions.stop_test(match.group(1))
                    self._json(200, {"ok": True})
                    return
                if path == "/api/shutdown":
                    service.request_shutdown()
                    self._json(202, {"status": "shutting"})
                    return
                self._error(404, "Endpoint inconnu.")
            except NameConflict as exc:
                self._error(409, str(exc))
            except (ValueError, CannotStart) as exc:
                self._error(400, str(exc))
            except SharePointError as exc:
                self._error(503, str(exc))
            except Exception:
                LOG.exception("POST %s impossible", path)
                self._error(500, "Erreur interne : consulter les journaux du Pi.")

        def log_message(self, fmt: str, *args) -> None:
            LOG.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def run_server(config: Config) -> None:
    service = DamaLiteService(config)
    service.start()
    server = ThreadingHTTPServer((config.host, config.port), make_handler(service))
    server.daemon_threads = True
    try:
        LOG.info("Interface locale : http://%s:%d", config.host, config.port)
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        service.stop()
