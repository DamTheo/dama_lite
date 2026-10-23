"""Vérification USB sans GPIO ni SharePoint, avec mesures réelles sur Pi 4.

Démarre un flux natif MJPEG, prend un PNG haute résolution qui préempte
ce flux, puis vérifie que le MJPEG peut être réouvert. Aucune image conservée.
Exécuter lorsque l'API staging est arrêtée, pour éviter deux propriétaires UVC.
"""
from __future__ import annotations

import argparse
import json
import struct
import time
from pathlib import Path

from .cameras import CameraController
from .config import Config
from .safe_staging import validate_staging


def check_camera(cfg: Config, slot: int) -> dict:
    validate_staging(cfg)
    ctrl = CameraController(cfg.cameras)
    times = {}
    try:
        if not ctrl.ready(slot):
            raise RuntimeError(f"Caméra {slot} physiquement indisponible.")
        started = time.monotonic()
        with ctrl.stream(slot) as frames:
            first = next(frames)
            times["first_frame_ms"] = round(1000 * (time.monotonic() - started))
            if not first.startswith(b"\xff\xd8"):
                raise RuntimeError("Première image MJPEG invalide.")
            start_photo = time.monotonic()
            png = ctrl.photo(slot)
            times["photo_ms"] = round(1000 * (time.monotonic() - start_photo))
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) < 24:
                raise RuntimeError("Photographie PNG invalide.")
            width, height = struct.unpack(">II", png[16:24])
            times["photo_pixels"] = [width, height]
            times["photo_bytes"] = len(png)
        resumed = time.monotonic()
        with ctrl.stream(slot) as frames:
            frame = next(frames)
            if not frame.startswith(b"\xff\xd8"):
                raise RuntimeError("Flux MJPEG impossible après photographie.")
            times["resume_ms"] = round(1000 * (time.monotonic() - resumed))
        times["ok"] = True
        return times
    finally:
        ctrl.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--slot", type=int, required=True, choices=range(1, 9))
    args = ap.parse_args()
    cfg = Config.load(Path(args.config))
    print(json.dumps(check_camera(cfg, args.slot), ensure_ascii=False))


if __name__ == "__main__":
    main()
