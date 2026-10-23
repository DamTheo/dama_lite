"""Flux vidéo quasi-direct en MJPEG UVC, sans décodage ni encodage Python.

Le processus FFmpeg est isolé, ouvert une seule fois quand un utilisateur
visualise une caméra. Le navigateur reçoit un multipart MJPEG continu.
L'acquisition PNG scientifique reste indépendante et PRIORITAIRE : on tue
le flux d'aperçu avant de rouvrir la caméra à sa résolution expérimentale.

Aucun contrôle du chauffage ni des GPIO, aucun accès Graph dans ce module.
"""
from __future__ import annotations

import logging
import os
import select
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

LOG = logging.getLogger(__name__)
SOI = b"\xff\xd8"
EOI = b"\xff\xd9"
MAX_FRAME_BYTES = 3 * 1024 * 1024
FRAME_INTERVAL_S = 0.12  # maximum ~8 images/s à l'écran
STALL_TIMEOUT_S = 8.0


class LivePreviewError(RuntimeError):
    pass


class JpegParser:
    """Reconstitue les JPEG à partir de blocs stdout arbitrairement découpés."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames: list[bytes] = []
        while True:
            start = self.buffer.find(SOI)
            if start < 0:
                self.buffer.clear()
                return frames
            if start:
                del self.buffer[:start]
            end = self.buffer.find(EOI, 2)
            if end < 0:
                if len(self.buffer) > MAX_FRAME_BYTES:
                    self.buffer.clear()
                return frames
            if end + len(EOI) > MAX_FRAME_BYTES:
                del self.buffer[:end + len(EOI)]
                continue
            frames.append(bytes(self.buffer[:end + len(EOI)]))
            del self.buffer[:end + len(EOI)]


@dataclass
class _Stream:
    proc: subprocess.Popen
    stop: threading.Event = field(default_factory=threading.Event)
    terminate_lock: threading.Lock = field(default_factory=threading.Lock)


def stop_process(session: _Stream) -> None:
    """Termine FFmpeg sans attendre une webcam bloquée en ioctl."""
    with session.terminate_lock:
        session.stop.set()
        if session.proc.poll() is None:
            try:
                session.proc.terminate()
                session.proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                session.proc.kill()
                try:
                    session.proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    LOG.error("Worker MJPEG non réinitialisé après SIGKILL.")
            except ProcessLookupError:
                pass
        if session.proc.stdout:
            try:
                session.proc.stdout.close()
            except OSError:
                pass


class LivePreviewManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._streams: dict[int, _Stream] = {}
        self._photo_slots: set[int] = set()
        self._closed = False

    @staticmethod
    def ffmpeg_command(device: str) -> list[str]:
        return [
            "/usr/bin/ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer",
            "-f", "video4linux2", "-input_format", "mjpeg",
            "-video_size", "640x480", "-framerate", "10",
            "-i", device,
            "-an", "-c:v", "copy", "-f", "mjpeg", "pipe:1",
        ]

    @contextmanager
    def open(self, slot: int, device: str) -> Iterator[Iterator[bytes]]:
        """Un client par caméra ; la session est libérée en quittant le contexte."""
        with self._lock:
            if self._closed:
                raise LivePreviewError("Contrôleur vidéo à l'arrêt.")
            if slot in self._photo_slots:
                raise LivePreviewError("Photographie scientifique en cours.")
            if slot in self._streams:
                raise LivePreviewError("Aperçu déjà ouvert sur cette caméra.")
            try:
                proc = subprocess.Popen(
                    self.ffmpeg_command(device),
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0, close_fds=True,
                )
            except OSError as exc:
                raise LivePreviewError(f"Impossible de lancer FFmpeg : {exc}") from exc
            session = _Stream(proc=proc)
            self._streams[slot] = session
        try:
            yield self._frames(session, slot)
        finally:
            with self._lock:
                if self._streams.get(slot) is session:
                    self._streams.pop(slot, None)
            stop_process(session)

    def _frames(self, session: _Stream, slot: int) -> Iterator[bytes]:
        stdout = session.proc.stdout
        if stdout is None:
            raise LivePreviewError("Sortie vidéo MJPEG absente.")
        parser = JpegParser()
        last_packet = time.monotonic()
        last_frame_sent = 0.0
        while not session.stop.is_set():
            if session.proc.poll() is not None:
                raise LivePreviewError(
                    f"Caméra {slot} : flux FFmpeg interrompu "
                    f"(code {session.proc.returncode})."
                )
            try:
                readable, _, _ = select.select([stdout], [], [], 0.4)
                if readable:
                    chunk = os.read(stdout.fileno(), 65536)
                    if not chunk:
                        raise LivePreviewError("Flux MJPEG fermé par le périphérique.")
                    frames = parser.feed(chunk)
                    for frame in frames:
                        now = time.monotonic()
                        last_packet = now
                        if now - last_frame_sent >= FRAME_INTERVAL_S:
                            yield frame
                            last_frame_sent = now
            except (OSError, ValueError) as exc:
                raise LivePreviewError(
                    f"Caméra {slot} : lecture du flux indisponible ({exc})."
                ) from exc
            if time.monotonic() - last_packet > STALL_TIMEOUT_S:
                raise LivePreviewError(f"Caméra {slot} : flux figé depuis 8 secondes.")

    def suspend_for_photo(self, slot: int) -> None:
        """Les photos à pleine résolution reprennent la propriété du port UVC."""
        with self._lock:
            if self._closed:
                raise LivePreviewError("Contrôleur vidéo arrêté.")
            if slot in self._photo_slots:
                raise LivePreviewError("Une photographie est déjà en cours.")
            self._photo_slots.add(slot)
            session = self._streams.pop(slot, None)
        if session is not None:
            stop_process(session)

    def resume_after_photo(self, slot: int) -> None:
        with self._lock:
            self._photo_slots.discard(slot)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            sessions = list(self._streams.values())
            self._streams.clear()
        for session in sessions:
            stop_process(session)
