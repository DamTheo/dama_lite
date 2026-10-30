"""Commandes bornées pour l'ESSAI de chauffe local, jamais la production.

Le contrôleur web (damocles, sans root) ne commande pas GPIO21.
Il demande une action START/STOP via /run ; un service systemd root,
possédant uniquement le droit de démarrer/arrêter l'unité de test fixe,
interprète la demande. Le script de test revalide les protections,
la présence d'une autorisation opérateur root et limite l'essai à 10 min.

Sans cette autorisation root, le bouton tactile reste non actionnable.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from .config import Config
from .heating_onsite_test import LOG_DIR, marker_valid, safe_preflight
from .safe_staging import validate_staging

REQUEST = Path("/run/dama-lite-heat-control/request")
PATH_UNIT = "dama-lite-heat-control.path"
TEST_UNIT = "dama-lite-heat-test.service"


def _systemd_properties() -> dict[str, str]:
    try:
        cp = subprocess.run(
            ["/usr/bin/systemctl", "show", TEST_UNIT,
             "--property=ActiveState,SubState,Result"],
            capture_output=True, text=True, timeout=1.8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if cp.returncode != 0:
        return {}
    return dict(
        line.split("=", 1) for line in cp.stdout.splitlines()
        if "=" in line
    )


def _path_ready() -> bool:
    if not REQUEST.parent.is_dir() or not os.access(REQUEST.parent, os.W_OK):
        return False
    try:
        cp = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "--quiet", PATH_UNIT],
            timeout=1.5, check=False, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return cp.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _last_record() -> dict[str, Any] | None:
    """Dernier enregistrement d'essai ; ne jamais l'assimiler au présent."""
    try:
        latest = max(LOG_DIR.glob("heat-*.csv"), default=None)
        if latest is None or not latest.is_file() or latest.is_symlink():
            return None
        if latest.stat().st_size > 512_000:
            return None
        with latest.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        line = rows[-1]
        return {
            "file": latest.name,
            "elapsed_s": float(line["elapsed_s"]),
            "temperature_c": float(line["temperature_c"]),
            "cpu_c": float(line["cpu_c"]),
            "relay_command_on": line["heater_on"] == "1",
            "fault": line.get("fault") or None,
        }
    except (OSError, ValueError, KeyError, csv.Error):
        return None


class HeatTestPanel:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock = threading.RLock()

    def snapshot(self) -> dict:
        props = _systemd_properties()
        phase = props.get("ActiveState", "unknown")
        return {
            "gateway_ready": _path_ready(),
            "operator_armed": marker_valid(),
            "phase": phase,
            "active": phase in {"active", "activating"},
            "result": props.get("Result", "unknown"),
            "request_pending": REQUEST.is_file(),
            "max_duration_s": 600,
            "max_chamber_c": 38.5,
            "last_record": _last_record(),
        }

    def _request(self, action: str) -> None:
        """Publication atomique, un nom de service systemd fixé côté root."""
        if action not in {"START", "STOP"}:
            raise ValueError("Commande d'essai inconnue.")
        with self._lock:
            if not _path_ready():
                raise ValueError("Passerelle de chauffe non installée ou inactive.")
            fd, tmp = tempfile.mkstemp(
                dir=REQUEST.parent, prefix=".heat-request-", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="ascii") as f:
                    f.write(action + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmp, 0o600)
                os.replace(tmp, REQUEST)
            finally:
                Path(tmp).unlink(missing_ok=True)

    def start(self, *, confirmed_present: bool, confirmed_cutoff: bool,
              machine_power: str, running_tests: list) -> dict:
        from .sessions import CannotStart
        if type(confirmed_present) is not bool or not confirmed_present:
            raise ValueError("Confirmer la présence de l'opérateur.")
        if type(confirmed_cutoff) is not bool or not confirmed_cutoff:
            raise ValueError("Confirmer le coupe-circuit indépendant.")
        if machine_power != "on" or running_tests:
            raise CannotStart(
                "Démarrage interdit : machine arrêtée ou expérience en cours."
            )
        if not _path_ready():
            raise CannotStart("Service d'essai thermique non installé.")
        if not marker_valid():
            raise CannotStart(
                "Essai non armé : autorisation opérateur root absente."
            )
        if not self.cfg.relay_active_high or self.cfg.relay_gpio != 21:
            raise CannotStart("Polarité ou position du relais non qualifiée.")
        validate_staging(self.cfg)
        snap = self.snapshot()
        if snap["active"] or snap["request_pending"]:
            raise CannotStart("Un essai de chauffe est déjà engagé.")
        try:
            # Lecture réelle des capteurs, mais jamais d'accès GPIO ici.
            safe_preflight(
                self.cfg,
                status={
                    "power": machine_power,
                    "tests": running_tests,
                    "thermal": {"heating_enabled": False},
                },
            )
        except Exception as exc:
            raise CannotStart(f"Précontrôle refusé : {exc}") from exc
        self._request("START")
        return {"status": "requested", "action": "start"}

    def stop(self) -> dict:
        # Un arrêt peut toujours être demandé sans présence ni qualification.
        self._request("STOP")
        return {"status": "requested", "action": "stop"}
