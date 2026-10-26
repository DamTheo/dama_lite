"""Acquisition et aperçu V4L2 sérialisés dans un processus jetable.

Une caméra UVC ou OpenCV peut bloquer dans du code natif. Ne jamais effectuer
l'ouverture USB dans le contrôleur du chauffage : le worker isolé est tué au
bout du délai maximal et la session reçoit une erreur tracée.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from contextlib import contextmanager

from .live_preview import LivePreviewManager, LivePreviewError

from .config import CameraSpec

LOG = logging.getLogger(__name__)
PREVIEW_TIMEOUT_S = 10
PHOTO_TIMEOUT_S = 15


class CameraError(RuntimeError):
    pass


class CameraController:
    def __init__(self, cameras: tuple[CameraSpec, ...]):
        self.specs = {spec.slot: spec for spec in cameras}
        self._usb_lock = threading.Lock()
        self._live = LivePreviewManager()

    def focus_view(self, slot: int | None) -> None:
        """Libérer les anciennes prévisualisations au changement de caméra."""
        self._live.set_focus(slot)

    def ready(self, slot: int) -> bool:
        spec = self.specs.get(slot)
        return bool(spec and spec.device and Path(spec.device).exists())

    def _capture(self, slot: int, preview: bool) -> bytes:
        spec = self.specs.get(slot)
        if spec is None or not self.ready(slot) or spec.device is None:
            raise CameraError(f"Caméra {slot} absente ou non configurée")
        # Un aperçu ne doit pas se mettre en file d'attente et retarder les
        # photos des expériences. Les captures ont un droit prioritaire.
        acquired = self._usb_lock.acquire(
            blocking=False
        ) if preview else self._usb_lock.acquire(timeout=20)
        if not acquired:
            raise CameraError(
                "Bus USB occupé, réessayer l'aperçu."
                if preview else "Bus USB inaccessible : photo non effectuée."
            )
        try:
            timeout = PREVIEW_TIMEOUT_S if preview else PHOTO_TIMEOUT_S
            command = [
                sys.executable, "-m", "dama_lite.camera_worker",
                "--device", spec.device,
                "--width", str(spec.width),
                "--height", str(spec.height),
                "--pixel-format", spec.pixel_format,
            ]
            if preview:
                command.append("--preview")
            try:
                result = subprocess.run(
                    command, capture_output=True, check=False, timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise CameraError(
                    f"Caméra {slot} figée : acquisition interrompue après "
                    f"{timeout} secondes."
                ) from exc
            except OSError as exc:
                raise CameraError(f"Worker caméra introuvable : {exc}") from exc
            if result.returncode != 0:
                error = result.stderr.decode("utf-8", errors="replace")[-350:]
                raise CameraError(
                    f"Caméra {slot} en erreur ({result.returncode}) : "
                    f"{error or 'sortie worker absente'}"
                )
            signature = b"\xff\xd8" if preview else b"\x89PNG\r\n\x1a\n"
            if not result.stdout.startswith(signature):
                raise CameraError(
                    f"Caméra {slot} : image encodée absente ou invalide."
                )
            return result.stdout
        finally:
            self._usb_lock.release()

    def photo(self, slot: int) -> bytes:
        if not self.ready(slot):
            raise CameraError(f"Caméra {slot} absente ou non configurée.")
        # Empêcher un réouverture UVC tant que l'image PNG est en cours.
        try:
            self._live.suspend_for_photo(slot)
        except LivePreviewError as exc:
            raise CameraError(str(exc)) from exc
        try:
            # Deux essais maximum face aux erreurs UVC transitoires, sans
            # remplacer une photo manquante par une fausse mesure. Si les
            # deux acquisitions échouent, SessionManager signale le défaut.
            for attempt in range(2):
                try:
                    return self._capture(slot, preview=False)
                except CameraError as exc:
                    if attempt == 1:
                        raise
                    LOG.warning(
                        "Photo UVC caméra %s : premier essai interrompu (%s), "
                        "une nouvelle acquisition sera tentée.", slot, exc
                    )
                    time.sleep(0.75)
            raise CameraError(f"Caméra {slot} : image indisponible.")
        finally:
            self._live.resume_after_photo(slot)

    @contextmanager
    def stream(self, slot: int):
        spec = self.specs.get(slot)
        if spec is None or not self.ready(slot) or not spec.device:
            raise CameraError(f"Caméra {slot} absente ou non configurée.")
        try:
            with self._live.open(slot, spec.device) as frames:
                yield frames
        except LivePreviewError as exc:
            raise CameraError(str(exc)) from exc

    def close(self) -> None:
        self._live.close()

    def preview(self, slot: int) -> bytes:
        return self._capture(slot, preview=True)
