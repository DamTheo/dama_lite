"""8 sessions d'acquisition indépendantes, une file de captures USB sérialisée."""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import Config
from .sharepoint import SharePointClient, validate_test_name

LOG = logging.getLogger(__name__)


class CannotStart(RuntimeError):
    pass


class SessionManager:
    def __init__(self, cfg: Config, store, thermal, cameras, lights,
                 sharepoint: SharePointClient):
        self.cfg = cfg
        self.store = store
        self.thermal = thermal
        self.cameras = cameras
        self.lights = lights
        self.sharepoint = sharepoint
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._due: dict[str, float] = {}
        self._busy: set[str] = set()
        # Une réservation Graph peut être lente. Ne pas retenir _lock sur le
        # réseau, mais interdire deux créations simultanées pour le même slot.
        self._reserving_slots: set[int] = set()
        self._reserving_names: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photo")
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()

    def _check_can_start(self, slot: int, name: str) -> None:
        if self._stop.is_set():
            raise CannotStart("Machine en cours d'extinction.")
        if not self.cameras.ready(slot):
            raise CannotStart(f"Caméra {slot} absente ou non configurée.")
        state = self.thermal.snapshot()
        if not state["ready"]:
            detail = state["fault"] or (
                "Chauffage non validé" if not state["heating_enabled"]
                else "Enceinte sous 35 °C"
            )
            raise CannotStart(f"Nouvelle analyse impossible : {detail}.")
        if any(s["camera_slot"] == slot for s in self.store.running()):
            raise CannotStart(f"La caméra {slot} est déjà utilisée.")
        if self.store.needs_ack(slot):
            raise CannotStart(
                "Dernier défaut de caméra non acquitté : vérifier puis acquitter."
            )
        if self.store.has_name(name):
            raise CannotStart("Nom de test déjà utilisé : choisir un nom unique.")

    def new_test(self, slot: int, name: str) -> dict:
        name = validate_test_name(name)
        if slot not in range(1, 9):
            raise CannotStart("Caméra inexistante.")
        with self._lock:
            self._check_can_start(slot, name)
            if slot in self._reserving_slots:
                raise CannotStart(f"Caméra {slot} en cours de préparation.")
            if name in self._reserving_names:
                raise CannotStart("Un test avec ce nom est déjà en préparation.")
            self._reserving_slots.add(slot)
            self._reserving_names.add(name)
        try:
            # Réseau hors verrou : les autres caméras, l'écran et l'extinction
            # continuent à répondre pendant l'appel Microsoft Graph.
            folder_id, folder_url = self.sharepoint.reserve_folder(name)
            with self._lock:
                # Une panne/une chute thermique après l'appel Graph interdit
                # toujours le lancement : ne jamais ignorer le seuil réel.
                self._check_can_start(slot, name)
                item = self.store.new_test(name, slot, folder_id, folder_url)
                self._due[item["id"]] = time.monotonic()
                LOG.info("Analyse démarrée : %s, caméra %s", name, slot)
                return item
        except CannotStart:
            LOG.warning(
                "Préparation annulée pour %s ; si le dossier SharePoint a déjà "
                "été créé, vérifier son éventuelle absence de photos.", name
            )
            raise
        finally:
            with self._lock:
                self._reserving_slots.discard(slot)
                self._reserving_names.discard(name)

    def acknowledge_camera(self, slot: int) -> None:
        if slot not in range(1, 9):
            raise CannotStart("Caméra inexistante.")
        with self._lock:
            if not self.cameras.ready(slot):
                raise CannotStart("Caméra absente : impossible d'acquitter.")
            if self.thermal.snapshot()["fault"]:
                raise CannotStart("Corriger d'abord le défaut thermique.")
            if any(s["camera_slot"] == slot for s in self.store.running()) or slot in self._reserving_slots:
                raise CannotStart("Impossible d'acquitter une caméra en cours d'utilisation.")
            if not self.store.ack_camera(slot):
                raise CannotStart("Aucun défaut de caméra à acquitter.")

    def stop_test(self, test_id: str) -> None:
        with self._lock:
            match = next((x for x in self.store.running() if x["id"] == test_id), None)
            if not match:
                raise CannotStart("Test inexistant ou déjà arrêté.")
            self._due.pop(test_id, None)
            self.store.set_state(test_id, "stopped")
            LOG.info("Analyse arrêtée : %s", match["name"])

    def stop_all(self) -> None:
        with self._lock:
            self._stop.set()
            self._due.clear()
            for test in self.store.running():
                self.store.set_state(
                    test["id"], "interrupted", "Extinction : acquisition interrompue"
                )

    def overview(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            items = self.store.tests(limit=40)
            for test in items:
                due = self._due.get(test["id"])
                test["next_photo_seconds"] = (
                    max(0, round(due - now)) if due is not None else None
                )
            return items

    def led_states(self) -> list[str]:
        state = self.thermal.snapshot()
        slots = {s["camera_slot"]: s for s in self.store.tests(limit=100000)
                 if s["state"] == "running"}
        # Un défaut sur la dernière session de ce slot reste visible jusqu'au
        # prochain test / acquittement ; une caméra absente est un défaut si configurée.
        faults = {slot for slot in range(1, 9) if self.store.needs_ack(slot)}
        upload_faults = self.store.upload_problem_slots()
        result = []
        for slot in range(1, 9):
            if state["fault"] and self.cameras.specs[slot].device:
                result.append("fault")
            elif slot in upload_faults:
                result.append("fault")
            elif slot in slots or slot in self._reserving_slots:
                result.append("running")
            elif slot in faults:
                result.append("fault")
            elif self.cameras.specs[slot].device and not self.cameras.ready(slot):
                result.append("fault")
            elif self.cameras.ready(slot) and state["ready"]:
                result.append("available")
            else:
                result.append("off")
        return result

    def _loop(self) -> None:
        while not self._stop.wait(0.5):
            try:
                now = time.monotonic()
                with self._lock:
                    active = {s["id"] for s in self.store.running()}
                    for sid, due in list(self._due.items()):
                        if sid not in active:
                            self._due.pop(sid, None)
                            continue
                        if now >= due and sid not in self._busy:
                            self._busy.add(sid)
                            # Ne pas générer artificiellement de photos manquées.
                            self._due[sid] = max(due + self.cfg.camera_interval_s,
                                                 now + self.cfg.camera_interval_s)
                            self._executor.submit(self._capture, sid)
                self.lights.update(self.led_states())
            except Exception:
                LOG.exception("Erreur planificateur")

    def _capture(self, sid: str) -> None:
        try:
            match = next((s for s in self.store.running() if s["id"] == sid), None)
            if not match:
                return
            if self.store.pending_bytes() >= self.cfg.spool_limit_bytes:
                raise RuntimeError("File locale de photos pleine : acquisitions suspendues.")
            seq = self.store.next_sequence(sid)
            slot = match["camera_slot"]
            # Aucun éclairage LED de statut ne doit fausser la colorimétrie.
            self.lights.blackout_on()
            try:
                png = self.cameras.photo(slot)
            finally:
                self.lights.blackout_off()
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Flux caméra : image non PNG.")
            if self.store.pending_bytes() + len(png) > self.cfg.spool_limit_bytes:
                raise RuntimeError("Limite de stockage local dépassée.")
            taken = datetime.now(timezone.utc)
            started = datetime.fromisoformat(match["created_at"])
            elapsed_minutes = round((taken - started).total_seconds() / 60)
            filename = (
                f"{taken.strftime('%Y%m%d_%H%M%S_%f')[:-3]}"
                f"_t{elapsed_minutes:04d}min_n{seq:04d}.png"
            )
            destination = self.store.spool_dir / f"{uuid4().hex}.png"
            staging = destination.with_suffix(".tmp")
            try:
                with staging.open("xb") as handle:
                    handle.write(png)
                    handle.flush()
                    os.fsync(handle.fileno())
                staging.replace(destination)
            finally:
                staging.unlink(missing_ok=True)
            state = self.thermal.snapshot()
            self.store.add_image(
                sid, seq, filename, destination, len(png),
                state["temperature_c"], state["cpu_temperature_c"],
            )
            LOG.info("Caméra %d, test %s, image %d acquise", slot, match["name"], seq)
        except Exception as exc:
            LOG.exception("Capture impossible pour %s : %s", sid, exc)
            with self._lock:
                self._due.pop(sid, None)
                if any(s["id"] == sid for s in self.store.running()):
                    self.store.set_state(sid, "fault", str(exc))
        finally:
            with self._lock:
                self._busy.discard(sid)

    def close(self) -> None:
        self.stop_all()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._executor.shutdown(wait=True, cancel_futures=True)
