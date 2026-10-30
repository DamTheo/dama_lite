"""Composition du runtime matériel et de l'arrêt sécurisé par bouton réel."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
import time

from .cameras import CameraController
from .config import Config
from .lights import LightController
from .sessions import SessionManager
from .sharepoint import SharePointClient, UploadWorker
from .store import Store
from .thermal import ThermalController

LOG = logging.getLogger(__name__)

# Root systemd surveille exclusivement ce chemin sous /run. Le serveur API
# n'a aucun droit root, et n'exécute jamais lui-même systemctl poweroff.
POWER_OFF_REQUEST = Path("/run/dama-lite-poweroff/confirmed")


class DamaLiteService:
    def __init__(self, cfg: Config, *, thermal=None, cameras=None, lights=None,
                 store=None, sharepoint=None):
        self.cfg = cfg
        self._lock = threading.RLock()
        self.state = "starting"
        self.store = store if store is not None else Store(cfg.state_dir)
        self.thermal = thermal if thermal is not None else ThermalController(cfg)
        self.cameras = cameras if cameras is not None else CameraController(cfg.cameras)
        self.lights = lights if lights is not None else LightController(
            cfg.leds_enabled, cfg.led_gpio, cfg.led_brightness
        )
        self.sharepoint = sharepoint if sharepoint is not None else SharePointClient(
            cfg.sharepoint
        )
        self.uploader = UploadWorker(self.store, self.sharepoint)
        self.sessions = SessionManager(
            cfg, self.store, self.thermal, self.cameras, self.lights,
            self.sharepoint,
        )
        self.button = None
        self._closing = False
        self._ui_selected_slot: int | None = None
        self._ui_selected_until = 0.0
        self._shutdown_confirmation_required = False

    def start(self) -> None:
        # Aucun démarrage d'acquisition ou LED ne doit précéder le contrôleur.
        self.thermal.start()
        self.uploader.start()
        self.sessions.start()
        if self.cfg.shutdown_button_gpio is not None:
            from gpiozero import Button
            self.button = Button(
                self.cfg.shutdown_button_gpio, pull_up=True,
                bounce_time=0.1, hold_time=1.2, hold_repeat=False,
            )
            self.button.when_held = self._physical_power_button
        self.state = "on"
        LOG.info("DAMA Lite démarré (chauffe autorisée=%s)",
                 self.cfg.heating_enabled)

    def select_ui_camera(self, slot: int | None) -> None:
        """Repère la préparation sur le bandeau, sans autoriser de test.

        La sélection est éphémère : elle expire seule si le navigateur se
        ferme, perd le réseau ou change de page sans nettoyage.
        """
        if slot is not None and (type(slot) is not int or not 1 <= slot <= 8):
            raise ValueError("Caméra à sélectionner : numéro entre 1 et 8.")
        with self._lock:
            if slot is not None and self.state != "on":
                raise ValueError("Incubateur non disponible.")
            self._ui_selected_slot = slot
            self._ui_selected_until = (
                time.monotonic() + 4.0 if slot is not None else 0.0
            )
        if hasattr(self.cameras, "focus_view"):
            self.cameras.focus_view(slot)

    def ui_selected_camera(self) -> int | None:
        with self._lock:
            if self.state != "on" or time.monotonic() >= self._ui_selected_until:
                return None
            return self._ui_selected_slot

    def shutdown_available(self) -> bool:
        return bool(
            self.cfg.allow_os_shutdown
            and POWER_OFF_REQUEST.parent.is_dir()
            and os.access(POWER_OFF_REQUEST.parent, os.W_OK)
        )

    def _physical_power_button(self) -> None:
        """Un maintien du bouton physique propose aussi une confirmation."""
        with self._lock:
            if self._closing:
                return
            if self.store.running():
                self._shutdown_confirmation_required = True
                LOG.warning("Bouton physique : confirmation requise, tests actifs.")
                return
        try:
            self.request_shutdown(confirmed_active_tests=True)
        except Exception:
            LOG.exception("Arrêt matériel refusé : voie d'extinction inaccessible.")

    def cancel_shutdown_confirmation(self) -> None:
        with self._lock:
            if not self._closing:
                self._shutdown_confirmation_required = False

    def snapshot(self) -> dict:
        thermo = self.thermal.snapshot()
        items = self.sessions.overview()
        states = self.sessions.led_states()
        health = self.sessions.camera_health_states()
        return {
            "power": self.state,
            "thermal": thermo,
            "cameras": [
                {"slot": i, "configured": bool(self.cameras.specs[i].device),
                 "mapping_verified": self.cameras.specs[i].mapping_verified,
                 "connected": self.cameras.ready(i),
                 "led": states[i - 1], "health": health[i - 1],
                 "active_test": next(
                     (t["id"] for t in items
                      if t["camera_slot"] == i and t["state"] == "running"), None
                 )}
                for i in range(1, 9)
            ],
            "tests": items,
            "sharepoint_configured": self.cfg.sharepoint.configured,
            "led_blackout": self.lights.blackout_active,
            "shutdown_available": self.shutdown_available(),
            "shutdown_confirmation_required": self._shutdown_confirmation_required,
            "pending_uploads": self.store.pending_uploads_count(),
            "ui_selected_camera": self.ui_selected_camera(),
            "interval_seconds": self.cfg.camera_interval_s,
            "temperature_start_min_c": self.cfg.start_min_c,
            "setpoint_c": self.cfg.setpoint_c,
        }

    def request_shutdown(self, *, confirmed_active_tests: bool = False) -> dict:
        """Clôture propre puis déclenchement OS, sous confirmation expresse."""
        from .sessions import CannotStart

        with self._lock:
            if self._closing:
                return {"status": "shutting", "ended_tests": 0}
            if not self.shutdown_available():
                raise CannotStart("Extinction Linux non autorisée sur ce Pi.")
            active = self.store.running()
            if active and not confirmed_active_tests:
                self._shutdown_confirmation_required = True
                raise CannotStart(
                    "Expériences actives : confirmer leur fin avant d'éteindre."
                )
            self._closing = True
            self._shutdown_confirmation_required = False
            self.state = "shutting"
            self._ui_selected_slot = None
            self._ui_selected_until = 0.0

        # Sécurité prioritaire avant animation, fichiers et Microsoft Graph.
        self.thermal.stop()
        self.sessions.stop_all(confirmed=True)
        LOG.warning(
            "Arrêt confirmé : %d session(s) clôturée(s), %d photo(s) en attente.",
            len(active), self.store.pending_uploads_count(),
        )
        threading.Thread(
            target=self._poweroff_after_animation,
            name="poweroff-after-safe-close", daemon=True,
        ).start()
        return {"status": "shutting", "ended_tests": len(active)}

    def _poweroff_after_animation(self) -> None:
        started = time.monotonic()
        try:
            # Attend la fin d'une photographie en cours ; aucun PNG tronqué
            # et aucune fausse photo créée. Les expériences sont déjà stoppées.
            self.sessions.close(confirmed_shutdown=True)
            if hasattr(self.cameras, "close"):
                self.cameras.close()
            # Les photos non synchronisées restent dans le spool persistant.
            self.uploader.stop()
            self.store.checkpoint()
            remaining = max(
                0.0, self.cfg.shutdown_animation_s - (time.monotonic() - started)
            )
            if remaining:
                time.sleep(remaining)
            if not self.shutdown_available():
                raise RuntimeError("Passerelle d'extinction systemd indisponible.")
            staging = POWER_OFF_REQUEST.parent / (
                ".request-" + str(os.getpid()) + "-" + str(threading.get_ident())
            )
            try:
                fd = os.open(
                    staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(fd, "w", encoding="ascii") as stream:
                    stream.write("DAMA_LITE_EXTINCTION_CONFIRMEE\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                # Renommage atomique : systemd ne verra jamais une requête
                # partiellement écrite.
                os.replace(staging, POWER_OFF_REQUEST)
            finally:
                staging.unlink(missing_ok=True)
            LOG.warning("Extinction Linux transférée à la passerelle systemd.")
        except Exception:
            LOG.exception("Extinction Linux impossible, chauffage déjà désactivé.")
            self.state = "shutdown_failed"

    def stop(self) -> None:
        with self._lock:
            if self.state == "off":
                return
            self.state = "shutting"
            self._ui_selected_slot = None
            self._ui_selected_until = 0.0
        # Relais coupé AVANT toute opération réseau ou de stockage.
        self.thermal.stop()
        self.sessions.close()
        # Stopper les flux MJPEG persistants avant la fermeture du service.
        if hasattr(self.cameras, "close"):
            self.cameras.close()
        self.uploader.stop()
        self.lights.close()
        if self.button is not None:
            self.button.close()
        self.store.close()
        self.state = "off"
