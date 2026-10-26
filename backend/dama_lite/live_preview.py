"""Aperçu UVC partagé, sans réouverture à chaque changement d'écran.

Un seul FFmpeg par caméra sert plusieurs clients HTTP simultanés ; le dernier
JPEG est diffusé sans décodage, réencodage ni allocation d'une file vidéo.
Un lecteur qui revient sous 2 s réutilise le même UVC (délai quasi nul).

Une photo scientifique ferme d'abord FFmpeg puis libère le port UVC :
la qualité PNG et le verrouillage thermique restent inchangés.
Ce module ne commande aucun GPIO et n'accède pas à SharePoint.
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
# Les UC60 sont déjà configurées à 10 images/s dans FFmpeg.
# Ne pas jeter arbitrairement une image sur deux sur le Pi : le client
# partage la dernière image complète, sans file susceptible d'accumuler
# du retard. Le cap USB reste 10 Hz, le débit matériel n'augmente pas.
FRAME_INTERVAL_S = 0.0
STALL_TIMEOUT_S = 5.0
WARM_IDLE_S = 2.0
MAX_PARALLEL_PREVIEWS = 3  # Éviter huit flux vidéo concurrents sur un bus USB2.

class LivePreviewError(RuntimeError):
    pass


class JpegParser:
    """Trames MJPEG découpées arbitrairement par stdout, sans copie inutile."""
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
            if end + 2 <= MAX_FRAME_BYTES:
                frames.append(bytes(self.buffer[:end + 2]))
            del self.buffer[:end + 2]


@dataclass
class _Stream:
    proc: subprocess.Popen
    stop: threading.Event = field(default_factory=threading.Event)
    terminate_lock: threading.Lock = field(default_factory=threading.Lock)
    condition: threading.Condition = field(default_factory=threading.Condition)
    last_frame: bytes | None = None
    frame_at: float = 0.0
    seq: int = 0
    error: str | None = None
    clients: int = 0
    idle_since: float | None = None
    worker: threading.Thread | None = None


def stop_process(session: _Stream) -> None:
    """Termine FFmpeg et libère V4L2, même si un lecteur HTTP se bloque."""
    with session.terminate_lock:
        session.stop.set()
        with session.condition:
            session.condition.notify_all()
        if session.proc.poll() is None:
            try:
                session.proc.terminate()
                session.proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                session.proc.kill()
                try:
                    session.proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    LOG.error("FFmpeg UVC ne répond pas au SIGKILL.")
            except ProcessLookupError:
                pass
        if session.proc.stdout:
            try:
                session.proc.stdout.close()
            except (OSError, ValueError):
                pass


class LivePreviewManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._streams: dict[int, _Stream] = {}
        self._photo_slots: set[int] = set()
        self._closed = False

    @staticmethod
    def ffmpeg_command(device: str) -> list[str]:
        # Le format MJPG est supporté matériellement par les huit UC60.
        return [
            "/usr/bin/ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-fflags", "nobuffer",
            "-f", "video4linux2", "-input_format", "mjpeg",
            "-video_size", "640x480", "-framerate", "10",
            "-i", device, "-an", "-c:v", "copy", "-f", "mjpeg", "pipe:1",
        ]

    @contextmanager
    def open(self, slot: int, device: str) -> Iterator[Iterator[bytes]]:
        """Un FFmpeg par caméra, même si Chromium reconnecte deux fois."""
        with self._lock:
            if self._closed:
                raise LivePreviewError("Contrôleur vidéo à l'arrêt.")
            if slot in self._photo_slots:
                raise LivePreviewError("Photographie scientifique en cours.")
            session = self._streams.get(slot)
            if session is not None and (
                session.stop.is_set() or session.error
                or session.proc.poll() is not None
            ):
                self._streams.pop(slot, None)
                stop_process(session)
                session = None
            if session is None:
                if len(self._streams) >= MAX_PARALLEL_PREVIEWS:
                    idle = [
                        (s.idle_since or 0.0, old_slot, s)
                        for old_slot, s in self._streams.items()
                        if s.clients == 0
                    ]
                    if not idle:
                        raise LivePreviewError(
                            "Trop d'aperçus actifs : fermer une autre vue."
                        )
                    _, old_slot, old = min(idle)
                    self._streams.pop(old_slot, None)
                    stop_process(old)
                try:
                    proc = subprocess.Popen(
                        self.ffmpeg_command(device),
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, bufsize=0, close_fds=True,
                    )
                except OSError as exc:
                    raise LivePreviewError("FFmpeg indisponible.") from exc
                session = _Stream(proc=proc)
                self._streams[slot] = session
                session.worker = threading.Thread(
                    target=self._read_loop, args=(slot, session),
                    daemon=True, name=f"uvc-live-{slot}",
                )
                session.worker.start()
            session.clients += 1
            session.idle_since = None
        try:
            yield self._frames(session, slot)
        finally:
            with self._lock:
                session.clients = max(0, session.clients - 1)
                if session.clients == 0:
                    session.idle_since = time.monotonic()
            # La lecture UVC reste chaude seulement 2 s, puis le worker ferme.

    def _frames(self, session: _Stream, slot: int) -> Iterator[bytes]:
        seen = -1
        while True:
            data = None
            with session.condition:
                if session.stop.is_set():
                    raise LivePreviewError(
                        session.error or f"Caméra {slot} : flux fermé."
                    )
                if session.error:
                    raise LivePreviewError(session.error)
                if session.last_frame is not None and (
                    seen < 0 or session.seq > seen
                ) and time.monotonic() - session.frame_at < 1.5:
                    data = session.last_frame
                    seen = session.seq
                else:
                    session.condition.wait(timeout=0.35)
            if data is not None:
                yield data

    def _read_loop(self, slot: int, session: _Stream) -> None:
        error = None
        parser = JpegParser()
        last_received = time.monotonic()
        total_frames = 0
        stdout = session.proc.stdout
        try:
            if stdout is None:
                raise LivePreviewError("Tube de capture UVC absent.")
            while not session.stop.is_set():
                with self._lock:
                    expired = (
                        session.clients == 0
                        and session.idle_since is not None
                        and time.monotonic() - session.idle_since >= WARM_IDLE_S
                    )
                if expired:
                    break
                if session.proc.poll() is not None:
                    raise LivePreviewError(
                        f"Caméra {slot} : FFmpeg terminé "
                        f"(code {session.proc.returncode})."
                    )
                ready, _, _ = select.select([stdout], [], [], 0.25)
                if ready:
                    chunk = os.read(stdout.fileno(), 65536)
                    if not chunk:
                        raise LivePreviewError(
                            f"Caméra {slot} : USB a fermé le flux MJPEG."
                        )
                    for frame in parser.feed(chunk):
                        now = time.monotonic()
                        last_received = now
                        total_frames += 1
                        # Toute image MJPEG valide a sa chance d'être
                        # affichée ; l'ancien filtre temporel de 120 ms
                        # écartait ~40 % des images d'une source à 10 Hz.
                        # Les lecteurs lents sautent naturellement les
                        # anciennes images, pas les plus récentes.
                        with session.condition:
                            session.last_frame = frame
                            session.frame_at = now
                            session.seq += 1
                            session.condition.notify_all()
                if time.monotonic() - last_received > STALL_TIMEOUT_S:
                    raise LivePreviewError(
                        f"Caméra {slot} : aucune image USB depuis 5 secondes."
                    )
        except (OSError, ValueError, LivePreviewError) as exc:
            if not session.stop.is_set():
                error = str(exc)
                LOG.warning("Flux UVC %d interrompu : %s", slot, error)
        finally:
            with session.condition:
                session.error = error
                session.stop.set()
                session.condition.notify_all()
            with self._lock:
                if self._streams.get(slot) is session:
                    self._streams.pop(slot, None)
            stop_process(session)

    def suspend_for_photo(self, slot: int) -> None:
        """Libération synchrone du port caméra AVANT une photo scientifique."""
        with self._lock:
            if self._closed:
                raise LivePreviewError("Contrôleur vidéo arrêté.")
            if slot in self._photo_slots:
                raise LivePreviewError("Photographie déjà en cours.")
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
