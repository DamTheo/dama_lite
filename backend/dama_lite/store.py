"""SQLite transactionnel : état des tests, photos et file d'upload conservés au reboot."""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "spool").mkdir(parents=True, exist_ok=True)
        self.spool_dir = state_dir / "spool"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(state_dir / "dama-lite.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        with self._lock, self._db:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS tests (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    camera_slot INTEGER NOT NULL CHECK(camera_slot BETWEEN 1 AND 8),
                    folder_id TEXT NOT NULL,
                    folder_url TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ended_at TEXT,
                    images_count INTEGER NOT NULL DEFAULT 0,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    test_id TEXT NOT NULL REFERENCES tests(id),
                    sequence INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    taken_at TEXT NOT NULL,
                    enclosure_temp REAL,
                    cpu_temp REAL,
                    byte_size INTEGER NOT NULL,
                    uploaded INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    retry_after REAL NOT NULL DEFAULT 0,
                    error TEXT,
                    uploaded_at TEXT,
                    UNIQUE(test_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS images_pending
                    ON images(uploaded, retry_after, taken_at);
            """)
            # Migration non destructive pour les bases déjà créées.
            existing = {row["name"] for row in self._db.execute("PRAGMA table_info(tests)")}
            if "acknowledged" not in existing:
                self._db.execute(
                    "ALTER TABLE tests ADD COLUMN acknowledged INTEGER NOT NULL DEFAULT 0"
                )
            # Un reboot ne doit pas relancer automatiquement une expérience interrompue.
            self._db.execute(
                "UPDATE tests SET state='interrupted', ended_at=?, "
                "error='Redémarrage : reprise manuelle nécessaire' WHERE state='running'",
                (utc_now(),),
            )

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self._db.execute(sql, params).fetchall()]

    def new_test(self, name: str, slot: int, folder_id: str, folder_url: str | None) -> dict:
        item = {
            "id": str(uuid4()), "name": name, "camera_slot": slot,
            "folder_id": folder_id, "folder_url": folder_url,
            "state": "running", "created_at": utc_now(),
        }
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO tests(id,name,camera_slot,folder_id,folder_url,state,created_at)"
                "VALUES(:id,:name,:camera_slot,:folder_id,:folder_url,:state,:created_at)",
                item,
            )
        return item

    def tests(self, limit: int = 40) -> list[dict]:
        return self._rows(
            "SELECT t.*, (SELECT COUNT(*) FROM images i WHERE i.test_id=t.id "
            "AND uploaded=0) AS pending_uploads, "
            "(SELECT COUNT(*) FROM images i WHERE i.test_id=t.id "
            "AND uploaded=0 AND error IS NOT NULL) AS upload_errors FROM tests t "
            "ORDER BY created_at DESC LIMIT ?", (limit,),
        )

    def running(self) -> list[dict]:
        return self._rows("SELECT * FROM tests WHERE state='running'")

    def has_name(self, name: str) -> bool:
        return bool(self._rows("SELECT 1 FROM tests WHERE name=? LIMIT 1", (name,)))

    def last_camera_test(self, slot: int) -> dict | None:
        results = self._rows(
            "SELECT * FROM tests WHERE camera_slot=? ORDER BY created_at DESC LIMIT 1",
            (slot,),
        )
        return results[0] if results else None

    def needs_ack(self, slot: int) -> bool:
        latest = self.last_camera_test(slot)
        return bool(latest and latest["state"] in {"fault", "interrupted"}
                    and not latest["acknowledged"])

    def ack_camera(self, slot: int) -> bool:
        with self._lock, self._db:
            latest = self.last_camera_test(slot)
            if latest is None or not self.needs_ack(slot):
                return False
            self._db.execute(
                "UPDATE tests SET acknowledged=1 WHERE id=?", (latest["id"],)
            )
            return True

    def upload_problem_slots(self) -> set[int]:
        return {row["camera_slot"] for row in self._rows(
            "SELECT DISTINCT t.camera_slot FROM tests t "
            "JOIN images i ON i.test_id=t.id "
            "WHERE i.uploaded=0 AND i.error IS NOT NULL"
        )}

    def set_state(self, test_id: str, state: str, error: str | None = None) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE tests SET state=?, error=?, ended_at=? WHERE id=?",
                (state, error, utc_now(), test_id),
            )

    def next_sequence(self, test_id: str) -> int:
        rows = self._rows(
            "SELECT COALESCE(MAX(sequence), -1)+1 AS number FROM images WHERE test_id=?",
            (test_id,),
        )
        return rows[0]["number"]

    def add_image(
        self, test_id: str, seq: int, filename: str, path: Path, size: int,
        enclosure_temp: float | None, cpu_temp: float | None,
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO images(id,test_id,sequence,filename,path,taken_at,"
                "enclosure_temp,cpu_temp,byte_size) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), test_id, seq, filename, str(path), utc_now(),
                 enclosure_temp, cpu_temp, size),
            )
            self._db.execute(
                "UPDATE tests SET images_count=images_count+1 WHERE id=?", (test_id,)
            )

    def due_uploads(self, limit: int = 5) -> list[dict]:
        return self._rows(
            "SELECT i.*, t.folder_id FROM images i JOIN tests t ON t.id=i.test_id "
            "WHERE i.uploaded=0 AND i.retry_after<=? "
            "ORDER BY i.taken_at LIMIT ?",
            (time.time(), limit),
        )

    def mark_uploaded(self, image_id: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE images SET uploaded=1, error=NULL, uploaded_at=? WHERE id=?",
                (utc_now(), image_id),
            )

    def mark_upload_failure(self, image_id: str, attempts: int, error: str) -> None:
        retry_s = min(300, 5 * 2 ** min(attempts, 6))
        with self._lock, self._db:
            self._db.execute(
                "UPDATE images SET attempts=?, retry_after=?, error=? WHERE id=?",
                (attempts, time.time() + retry_s, error[:1000], image_id),
            )

    def pending_uploads_count(self) -> int:
        return self._rows(
            "SELECT COUNT(*) AS total FROM images WHERE uploaded=0"
        )[0]["total"]

    def checkpoint(self) -> None:
        """Checkpoint SQLite après stabilisation des écritures photo."""
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def pending_bytes(self) -> int:
        result = self._rows(
            "SELECT COALESCE(SUM(byte_size),0) AS total FROM images WHERE uploaded=0"
        )
        return result[0]["total"]

    def close(self) -> None:
        with self._lock:
            self._db.close()
