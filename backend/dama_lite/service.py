"""Composition du runtime matériel et de l'arrêt sécurisé par bouton réel."""
from __future__ import annotations

import logging
import subprocess
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
            self.button.when_held = self.request_shutdown
        self.state = "on"
        LOG.info("DAMA Lite démarré (chauffe autorisée=%s)",
                 self.cfg.heating_enabled)

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
            "interval_seconds": self.cfg.camera_interval_s,
            "temperature_start_min_c": self.cfg.start_min_c,
            "setpoint_c": self.cfg.setpoint_c,
        }

    def request_shutdown(self) -> None:
        with self._lock:
            if self._closing:
                return
            self._closing = True
            self.state = "shutting"
        LOG.warning("Extinction demandée : sécurisation des résistances et sessions.")
        # La sécurité thermique ne dépend pas de l'animation du navigateur.
        self.thermal.stop()
        self.sessions.stop_all()
        # Les photos déjà acquises restent dans la file locale si la
        # synchronisation Graph ne peut se terminer avant le poweroff.
        threading.Thread(
            target=self._poweroff_after_animation, name="poweroff", daemon=True
        ).start()

    def _poweroff_after_animation(self) -> None:
        time.sleep(self.cfg.shutdown_animation_s)
        if self.cfg.allow_os_shutdown:
            try:
                subprocess.run(["/usr/bin/systemctl", "poweroff"],
                               timeout=20, check=True)
            except Exception:
                LOG.exception("Échec extinction OS, chauffage déjà désactivé.")
                self.state = "shutdown_failed"
        else:
            LOG.warning("Arrêt OS désactivé : profil de développement.")
            self.state = "shutdown_disabled"

    def stop(self) -> None:
        with self._lock:
            if self.state == "off":
                return
            self.state = "shutting"
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
