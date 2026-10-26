"""Pilote LED isolé du service Graph et du relais GPIO21.

Ce module contrôle EXCLUSIVEMENT 64 pixels GPIO12 à 10 % maximum et
requiert une qualification physique explicite avant de démarrer comme
service. Aucune commande de chauffe, de relais ou de GPIO21.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import signal
import stat
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .lights import LightController

LOG = logging.getLogger(__name__)
VALIDATION_MARKER = Path("/etc/dama-lite/leds-qualified")
VALIDATION_TEXT = "LED_GPIO12_64_10PCT_OPERATOR_AUTHORIZED"
STATUS_URL = "http://127.0.0.1:8765/api/status"


def safety_confirmed(path: Path = VALIDATION_MARKER) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    meta = path.stat()
    return (
        meta.st_uid == 0
        and not stat.S_IMODE(meta.st_mode) & 0o022
        and path.read_text(encoding="ascii").strip() == VALIDATION_TEXT
    )


def states_from_snapshot(data: dict) -> list[str]:
    """L'état UVC reste indépendant du seuil de démarrage de l'incubateur."""
    cams = data.get("cameras", [])
    if data.get("power") != "on" or len(cams) != 8:
        return ["off"] * 8
    if data.get("thermal", {}).get("fault"):
        return ["fault"] * 8
    result = []
    for cam in cams:
        if not cam.get("configured"):
            result.append("off")
        elif not cam.get("connected"):
            result.append("fault")
        elif cam.get("health") == "fault":
            result.append("fault")
        elif cam.get("health") == "running":
            result.append("running")
        else:
            result.append("available")
    return result


def should_hold_previous(
    last_valid_at: float | None, now: float, grace_seconds: float = 3.0
) -> bool:
    """Évite le clignotement en cas de timeout HTTP isolé.

    Au-delà de 3 s sans état valide, les LED reviennent à OFF.
    Un blackout photo reçu correctement est appliqué immédiatement.
    """
    return last_valid_at is not None and now - last_valid_at < grace_seconds


def gentle_pulse_factor(elapsed: float, cycle_seconds: float = 3.6) -> float:
    """Respiration sinusoïdale 35–100 % d'une luminosité plafonnée à 10 %."""
    if cycle_seconds <= 0:
        raise ValueError("Période de pulsation invalide.")
    return 0.675 + 0.325 * math.cos(2.0 * math.pi * elapsed / cycle_seconds)


def selected_available_slot(snapshot: dict, states: list[str]) -> int | None:
    """Repère la caméra visualisée, quel que soit son état (vert/jaune/rouge).

    L'extinction pour une photo et l'arrêt machine restent prioritaires.
    Le nom historique de la fonction est conservé pour les anciens tests.
    """
    slot = snapshot.get("ui_selected_camera")
    if type(slot) is not int or not 1 <= slot <= 8:
        return None
    if snapshot.get("power") != "on" or snapshot.get("led_blackout"):
        return None
    return slot


class StatusCache:
    """La récupération HTTP ne doit jamais bloquer l'horloge des NeoPixels."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot: dict | None = None
        self._received_at: float | None = None

    def publish(self, snapshot: dict, received_at: float) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._received_at = received_at

    def read(self, now: float) -> dict | None:
        with self._lock:
            if not should_hold_previous(self._received_at, now):
                return None
            return self._snapshot


def poll_status(cache: StatusCache, stopped: threading.Event) -> None:
    unreachable = False
    while not stopped.is_set():
        try:
            with urlopen(STATUS_URL, timeout=1.25) as reply:
                snapshot = json.load(reply)
            if not isinstance(snapshot, dict):
                raise ValueError("Réponse HTTP invalide.")
            cache.publish(snapshot, time.monotonic())
            if unreachable:
                LOG.info("Communication avec le contrôleur rétablie.")
            unreachable = False
        except (URLError, OSError, ValueError, TypeError, TimeoutError):
            if not unreachable:
                LOG.warning("Statut local temporairement inaccessible.")
                unreachable = True
        stopped.wait(0.35)


class PulseAnimator:
    """Phase monotone, départ à plein vert et extinction progressive."""

    def __init__(self):
        self.selected: int | None = None
        self.started_at = 0.0
        self.fading_slot: int | None = None
        self.fade_started_at = 0.0
        self.fade_from = 1.0

    def frame(self, selected: int | None, now: float) -> tuple[int | None, float]:
        if selected is not None:
            if selected != self.selected:
                self.selected = selected
                self.started_at = now
                self.fading_slot = None
            return selected, gentle_pulse_factor(now - self.started_at)
        if self.selected is not None:
            self.fading_slot = self.selected
            self.fade_from = gentle_pulse_factor(now - self.started_at)
            self.fade_started_at = now
            self.selected = None
        if self.fading_slot is not None:
            fraction = min(1.0, (now - self.fade_started_at) / 0.4)
            if fraction >= 1.0:
                self.fading_slot = None
                return None, 1.0
            eased = fraction * fraction * (3.0 - 2.0 * fraction)
            return self.fading_slot, self.fade_from + (1.0 - self.fade_from) * eased
        return None, 1.0


def run_polling(controller: LightController, stopped: threading.Event) -> None:
    cache = StatusCache()
    animator = PulseAnimator()
    reader = threading.Thread(
        target=poll_status, args=(cache, stopped),
        name="led-status-http", daemon=True,
    )
    reader.start()
    old_states: list[str] | None = None
    old_selected: int | None = None
    try:
        # Rendu 25 Hz : aucune attente HTTP, horloge time.monotonic.
        while not stopped.wait(0.04):
            now = time.monotonic()
            snapshot = cache.read(now)
            if snapshot is None:
                states = ["off"] * 8
                selected = None
            else:
                states = (
                    ["off"] * 8 if snapshot.get("led_blackout")
                    else states_from_snapshot(snapshot)
                )
                selected = selected_available_slot(snapshot, states)
                # Même un emplacement déconnecté doit pouvoir être repéré :
                # son groupe rouge respire pendant que l'opérateur regarde
                # la caméra, sans prétendre qu'elle est fonctionnelle.
                if selected is not None and states[selected - 1] == "off":
                    states[selected - 1] = "fault"
            if states != old_states or selected != old_selected:
                LOG.info(
                    "LED GPIO12 : %s ; repérage=%s",
                    ",".join(states), selected,
                )
                old_states = list(states)
                old_selected = selected
            if snapshot is not None and snapshot.get("led_blackout"):
                animator.frame(None, now)
                controller.update(states)
                continue
            slot, factor = animator.frame(selected, now)
            if slot is not None and states[slot - 1] == "off":
                slot, factor = None, 1.0
            controller.update(states, pulse_slot=slot, pulse_factor=factor)
    finally:
        stopped.set()
        reader.join(timeout=2.0)


def selftest(controller: LightController, delay: float = 0.25) -> None:
    """Huit groupes successifs à 10 %, puis tous éteints, sans chauffe."""
    if not 0.1 <= delay <= 1.0:
        raise ValueError("L'essai doit rester bref (100–1000 ms/position).")
    try:
        for slot in range(8):
            state = ["off"] * 8
            state[slot] = "available"
            controller.update(state)
            time.sleep(delay)
    finally:
        controller.update(["off"] * 8)


def main() -> None:
    parser = argparse.ArgumentParser(description="LED GPIO12 uniquement.")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--run-service", action="store_true")
    args = parser.parse_args()
    if args.selftest == args.run_service:
        parser.error("Choisir un seul mode.")
    if args.run_service and not safety_confirmed():
        parser.error("Autorisation opérateur pour les LED GPIO12 non enregistrée.")
    logging.basicConfig(level=logging.INFO)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    leds = LightController(enabled=True, gpio=12, brightness=0.10)
    try:
        if args.selftest:
            selftest(leds)
        else:
            run_polling(leds, stopped)
    finally:
        leds.close()
        LOG.info("LED GPIO12 éteintes, aucune commande de chauffage.")


if __name__ == "__main__":
    main()
