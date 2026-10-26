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


def gentle_pulse_factor(timestamp: float, cycle_seconds: float = 2.8) -> float:
    """Respiration douce de 18 à 100 % du vert (NeoPixel limité à 10 %)."""
    return 0.59 + 0.41 * math.cos(2.0 * math.pi * timestamp / cycle_seconds)


def selected_available_slot(snapshot: dict, states: list[str]) -> int | None:
    """Priorité : défaut rouge / test jaune / blackout avant repérage vert."""
    slot = snapshot.get("ui_selected_camera")
    if type(slot) is not int or not 1 <= slot <= 8:
        return None
    if snapshot.get("led_blackout") or states[slot - 1] != "available":
        return None
    return slot


def run_polling(controller: LightController, stopped: threading.Event) -> None:
    last_states: list[str] | None = None
    last_selected: int | None = None
    statuses = ["off"] * 8
    selected = None
    last_valid_at: float | None = None
    next_poll = 0.0
    unreachable = False
    # Le rendu visuel (~8 Hz) est découplé du statut réseau (~1,6 Hz)
    # pour éviter de multiplier les requêtes HTTP durant la pulsation.
    while not stopped.wait(0.12):
        now = time.monotonic()
        if now >= next_poll:
            next_poll = now + 0.60
            try:
                with urlopen(STATUS_URL, timeout=1.5) as reply:
                    snapshot = json.load(reply)
                statuses = (
                    ["off"] * 8 if snapshot.get("led_blackout")
                    else states_from_snapshot(snapshot)
                )
                selected = selected_available_slot(snapshot, statuses)
                last_valid_at = time.monotonic()
                if unreachable:
                    LOG.info("Connexion locale au contrôleur rétablie.")
                unreachable = False
            except (URLError, OSError, ValueError, TypeError, TimeoutError):
                if not should_hold_previous(last_valid_at, time.monotonic()):
                    if not unreachable:
                        LOG.warning("Statut local indisponible depuis 3 s : LED éteintes.")
                        unreachable = True
                    statuses = ["off"] * 8
                    selected = None
        if statuses != last_states or selected != last_selected:
            LOG.info(
                "LED GPIO12 (8 x 8, 10%%): %s ; repérage=%s",
                ",".join(statuses), selected,
            )
            last_states = list(statuses)
            last_selected = selected
            controller.update(
                statuses, pulse_slot=selected,
                pulse_factor=gentle_pulse_factor(now) if selected is not None else 1.0,
            )
        elif selected is not None:
            controller.update(
                statuses, pulse_slot=selected,
                pulse_factor=gentle_pulse_factor(now),
            )


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
