"""HTTP local sans exposition réseau ; fichiers du frontend et API tactile."""
from __future__ import annotations

import fcntl
import itertools
import json
import logging
import mimetypes
import re
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .cameras import CameraError
from .config import Config
from .interlocks import ensure_gpio_exclusive
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
            # Pas de connexion HTTP/1.1 persistante : sinon les connexions
            # ouvertes de Chromium empêchent l'arrêt propre de systemd.
            self.send_header("Connection", "close")
            self.close_connection = True
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")
            try:
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # Une ancienne requête d'aperçu a été annulée par le navigateur.
                # Ne jamais envoyer un second HTTP 503 après avoir écrit le 200.
                LOG.debug("Client HTTP déconnecté avant fin de transmission.")

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
                live = re.fullmatch(r"/api/cameras/([1-8])/stream", path)
                if live:
                    if service.state != "on":
                        self._error(503, "Incubateur en cours d'arrêt.")
                        return
                    slot = int(live.group(1))
                    # FFmpeg recopie directement les images MJPEG USB, sans
                    # décoder, réencoder ni rouvrir la webcam à chaque trame.
                    # Les LED de statut restent visibles pendant l'aperçu ;
                    # elles sont éteintes uniquement lors des PNG scientifiques.
                    with service.cameras.stream(slot) as frames:
                        first = next(frames)
                        self.send_response(200)
                        self.send_header(
                            "Content-Type",
                            "multipart/x-mixed-replace; boundary=dama_frame",
                        )
                        self.send_header("Connection", "close")
                        self.send_header("Cache-Control", "no-store, no-cache")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.close_connection = True
                        self.end_headers()
                        try:
                            for jpeg in itertools.chain((first,), frames):
                                payload = (
                                    b"--dama_frame\r\nContent-Type: image/jpeg\r\n"
                                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                                    + jpeg + b"\r\n"
                                )
                                self.wfile.write(payload)
                                self.wfile.flush()
                                if service.state != "on":
                                    break
                        except (BrokenPipeError, ConnectionResetError):
                            LOG.debug("Client de prévisualisation déconnecté.")
                        except CameraError as exc:
                            # En multipart les en-têtes HTTP sont déjà partis ;
                            # ne jamais écrire une deuxième réponse JSON 503.
                            LOG.warning("Fin flux caméra %d : %s", slot, exc)
                        return

                match = re.fullmatch(r"/api/cameras/([1-8])/preview", path)
                if match:
                    if service.state != "on":
                        self._error(503, "Incubateur en cours d'arrêt.")
                        return
                    # Le retour vidéo ne doit pas contaminer les images avec
                    # la lumière verte/jaune/rouge du bandeau NeoPixel.
                    service.lights.blackout_on()
                    try:
                        jpg = service.cameras.preview(int(match.group(1)))
                    finally:
                        service.lights.blackout_off()
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
            except CameraError as exc:
                LOG.warning("Aperçu non disponible (%s) : %s", path, exc)
                self._error(503, str(exc))
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
                acknowledge = re.fullmatch(r"/api/cameras/([1-8])/ack", path)
                if acknowledge:
                    service.sessions.acknowledge_camera(int(acknowledge.group(1)))
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
            # React interroge l'état chaque seconde ; éviter plusieurs
            # millions d'entrées de journal et l'usure inutile de la carte SD.
            if self.path.startswith("/api/status") or self.path.startswith("/api/health"):
                return
            LOG.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def run_server(config: Config) -> None:
    # Empêche deux instances de DAMA Lite de piloter simultanément GPIO21.
    # L'ancien Programme_complet.py n'utilise pas ce verrou : son éventuelle
    # tâche de démarrage doit être neutralisée APRÈS audit, lors du déploiement.
    config.state_dir.mkdir(parents=True, exist_ok=True)
    with (config.state_dir / "runtime.lock").open("a") as process_lock:
        try:
            fcntl.flock(process_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Un autre contrôleur DAMA Lite est déjà actif.") from exc

        # Interdire la double commande GPIO avec les scripts historiques.
        ensure_gpio_exclusive(config.heating_enabled, config.leds_enabled)
        service = DamaLiteService(config)
        server = ThreadingHTTPServer((config.host, config.port), make_handler(service))
        # Les requêtes HTTP sont jetables. Ne pas bloquer la coupure du
        # chauffage derrière une connexion Chromium laissée ouverte.
        server.daemon_threads = True
        server.block_on_close = False

        def shutdown_signal(signum, _frame):
            LOG.warning("Signal OS %s : arrêt contrôlé", signum)
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, shutdown_signal)
        signal.signal(signal.SIGINT, shutdown_signal)
        try:
            service.start()
            LOG.info("Interface locale : http://%s:%d", config.host, config.port)
            server.serve_forever(poll_interval=0.5)
        finally:
            # Toujours couper le relais avant toute attente de fermeture
            # des sockets HTTP ou de terminaison des handlers.
            try:
                service.stop()
            finally:
                server.server_close()
