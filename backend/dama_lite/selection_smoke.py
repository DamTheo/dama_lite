"""Essai local sans chauffe de l'indicateur LED de caméra sélectionnée.

Appelle uniquement /api/selection et /api/status. Ne lance aucune analyse
et n'accède pas à SharePoint. Remet toujours la sélection à null en fin.
"""
from __future__ import annotations

import argparse
import json
import time
from urllib.request import Request, urlopen


ROOT = "http://127.0.0.1:8765"


def selection(camera: int | None) -> dict:
    request = Request(
        ROOT + "/api/selection",
        data=json.dumps({"camera": camera}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def current_status() -> dict:
    with urlopen(ROOT + "/api/status", timeout=3) as response:
        return json.load(response)


def smoke(slot: int, duration: float, *, allow_disconnected: bool = False) -> dict:
    before = current_status()
    if before["thermal"]["heating_enabled"] or before["thermal"]["heater_on"]:
        raise RuntimeError("Essai réservé au staging : chauffe doit être désactivée.")
    if not before["cameras"][slot - 1]["connected"] and not allow_disconnected:
        raise RuntimeError("Caméra sélectionnée déconnectée.")
    try:
        changed = selection(slot)
        if changed["selected"] != slot:
            raise AssertionError("Échec signal de sélection.")
        time.sleep(duration)
        observed = current_status()
        if observed["ui_selected_camera"] != slot:
            raise AssertionError("Sélection expirée ou non transmise.")
        return {
            "camera": slot,
            "backend_selection": observed["ui_selected_camera"],
            "camera_health": observed["cameras"][slot - 1]["health"],
            "heater_on": observed["thermal"]["heater_on"],
            "heating_enabled": observed["thermal"]["heating_enabled"],
            "status": "ok",
        }
    finally:
        selection(None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=3, choices=range(1, 9))
    parser.add_argument("--seconds", type=float, default=1.5)
    parser.add_argument(
        "--allow-disconnected", action="store_true",
        help="Tester le repérage rouge sans prétendre que l'USB fonctionne.",
    )
    args = parser.parse_args()
    if not 0.1 <= args.seconds <= 3.0:
        parser.error("0,1 à 3 secondes, sans dépassement du TTL.")
    print(json.dumps(smoke(
        args.camera, args.seconds,
        allow_disconnected=args.allow_disconnected,
    ), ensure_ascii=False))


if __name__ == "__main__":
    main()
