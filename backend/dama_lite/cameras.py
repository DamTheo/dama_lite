"""USB V4L2 : chemins persistants, acquisition et aperçu sérialisés.

L'aperçu n'ouvre jamais une caméra en même temps qu'une photographie. Le verrou
est global pour éviter de saturer le bus USB2 et les hubs partagés du Pi 4.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from .config import CameraSpec

LOG = logging.getLogger(__name__)


class CameraError(RuntimeError):
    pass


class CameraController:
    def __init__(self, cameras: tuple[CameraSpec, ...]):
        self.specs = {spec.slot: spec for spec in cameras}
        self._usb_lock = threading.RLock()

    def ready(self, slot: int) -> bool:
        spec = self.specs.get(slot)
        return bool(spec and spec.device and Path(spec.device).exists())

    def _capture(self, slot: int, preview: bool) -> bytes:
        spec = self.specs.get(slot)
        if spec is None or not self.ready(slot) or spec.device is None:
            raise CameraError(f"Caméra {slot} absente ou non configurée")
        try:
            import cv2
        except ImportError as exc:
            raise CameraError("OpenCV (python3-opencv) non installé") from exc
        # L'index video-index0 correspond au flux image; index1 peut porter
        # uniquement des métadonnées UVC.
        with self._usb_lock:
            cap = cv2.VideoCapture(spec.device, cv2.CAP_V4L2)
            try:
                if not cap.isOpened():
                    raise CameraError(f"Impossible d'ouvrir la caméra {slot}")
                # La webcam UC60 observée sur Incub-resa prend en charge MJPG
                # en 1280x720. MJPG réduit la bande passante des hubs USB.
                requested_fourcc = cv2.VideoWriter_fourcc(*spec.pixel_format)
                cap.set(cv2.CAP_PROP_FOURCC, requested_fourcc)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, spec.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, spec.height)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                frame = None
                for _ in range(3):
                    ok, candidate = cap.read()
                    if ok and candidate is not None:
                        frame = candidate
                if frame is None:
                    raise CameraError(f"Image indisponible pour la caméra {slot}")
                actual_height, actual_width = frame.shape[:2]
                if (actual_width, actual_height) != (spec.width, spec.height):
                    raise CameraError(
                        f"Résolution inattendue caméra {slot} : "
                        f"{actual_width}x{actual_height} au lieu de "
                        f"{spec.width}x{spec.height}."
                    )
                if preview:
                    height, width = frame.shape[:2]
                    if width > 800:
                        frame = cv2.resize(frame, (800, round(height * 800 / width)))
                ext = ".jpg" if preview else ".png"
                args = [int(cv2.IMWRITE_JPEG_QUALITY), 80] if preview else [
                    int(cv2.IMWRITE_PNG_COMPRESSION), 3
                ]
                success, encoded = cv2.imencode(ext, frame, args)
                if not success:
                    raise CameraError(f"Encodage {ext} impossible")
                return encoded.tobytes()
            finally:
                cap.release()

    def photo(self, slot: int) -> bytes:
        return self._capture(slot, preview=False)

    def preview(self, slot: int) -> bytes:
        return self._capture(slot, preview=True)
