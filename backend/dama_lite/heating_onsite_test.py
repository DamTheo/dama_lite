"""Essai réel TEMPORAIRE du relais GPIO21, uniquement avec opérateur présent.

Ce programme n'autorise jamais le service de chauffe de production.
Il fonctionne sous un service systemd sans redémarrage, avec limite de durée,
journal CSV et ExecStopPost qui force GPIO21 à LOW même sur SIGKILL.
La protection thermique indépendante reste une obligation matérielle.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import signal
import stat
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from .config import Config
from .safe_staging import validate_staging
from .thermal import DS18B20, ThermalController, cpu_temperature

LOG = logging.getLogger(__name__)
AUTH = Path("/etc/dama-lite/heat-test-onsite-approved")
TOKEN = "OPERATOR_PRESENT_INDEPENDENT_CUTOFF_CONFIRMED"
# La présence opérateur ne peut pas être présumée indéfiniment après
# l'installation d'un fichier. Réarmer pour chaque campagne d'essai.
MAX_ARM_AGE_S = 15 * 60
LOG_DIR = Path("/home/damocles/dama-lite-staging/heat-test-logs")
MAX_RUNTIME = 600.0
MAX_TEST_TEMPERATURE = 38.5
MAX_TEST_CPU = 70.0
MIN_RISE_C = 0.15
MIN_RISE_AFTER_S = 180.0


def marker_valid(marker: Path = AUTH) -> bool:
    if marker.is_symlink() or not marker.is_file():
        return False
    meta = marker.stat()
    return (
        meta.st_uid == 0
        and stat.S_IMODE(meta.st_mode) & 0o022 == 0
        and 0 <= time.time() - meta.st_mtime <= MAX_ARM_AGE_S
        and marker.read_text(encoding="ascii").strip() == TOKEN
    )


def safe_preflight(cfg: Config, *, marker: Path = AUTH, sensor=None,
                   cpu_reader=cpu_temperature, status=None) -> dict:
    """Validation sans accès en écriture GPIO."""
    validate_staging(cfg)
    if cfg.heating_enabled or cfg.relay_gpio != 21 or not cfg.relay_active_high:
        raise RuntimeError("Profil de commande relais inattendu.")
    if not marker_valid(marker):
        raise RuntimeError(
            "Autorisation opérateur pour le banc de chauffe absente."
        )
    if status is None:
        with urlopen("http://127.0.0.1:8765/api/status", timeout=3) as response:
            status = json.load(response)
    if status.get("power") != "on" or status.get("tests"):
        if any(t.get("state") == "running" for t in status.get("tests", [])):
            raise RuntimeError("Essai de chauffe interdit : analyses en cours.")
        if status.get("power") != "on":
            raise RuntimeError("Incubateur non disponible.")
    if status.get("thermal", {}).get("heating_enabled"):
        raise RuntimeError("Autre contrôleur thermique déjà autorisé.")
    therm = sensor or DS18B20(cfg.sensor_id)
    temps = [therm.read() for _ in range(3)]
    cpu = cpu_reader()
    if cpu is None or cpu >= cfg.cpu_warning_c:
        raise RuntimeError("CPU absent ou trop chaud avant essai.")
    if any(t >= cfg.setpoint_c or t >= MAX_TEST_TEMPERATURE for t in temps):
        raise RuntimeError("Enceinte déjà trop chaude pour cet essai de montée.")
    if max(temps) - min(temps) > 1.0:
        raise RuntimeError("Sonde DS18B20 instable avant essai.")
    return {
        "sensor_samples_c": [round(t, 3) for t in temps],
        "cpu_c": round(cpu, 3),
        "relay_gpio": cfg.relay_gpio,
        "active_high": cfg.relay_active_high,
        "independent_cutoff_confirmed_by_operator": True,
        "permanent_heater_authorized": False,
    }


def perform(cfg: Config, *, duration_s: int, sensor=None,
            cpu_reader=cpu_temperature) -> dict:
    if duration_s <= 0 or duration_s > MAX_RUNTIME:
        raise ValueError("Durée d'essai autorisée : 1 à 600 secondes.")
    # Le preflight est vérifié à nouveau au plus près de l'activation.
    initial = safe_preflight(cfg, sensor=sensor, cpu_reader=cpu_reader)
    LOG.warning("ESSAI CHAUFFE réel début ; durée max=%ds ; T=%.3f ; CPU=%.2f",
                duration_s, initial["sensor_samples_c"][-1], initial["cpu_c"])
    # No heat-related GPIO is touched until preflight succeeds.
    run_cfg = replace(cfg, heating_enabled=True)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda _sig, _frame: stop.set())

    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    filename = LOG_DIR / ("heat-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".csv")
    if filename.exists():
        raise RuntimeError("Nom de journal de chauffe déjà utilisé.")
    controller: ThermalController | None = None
    started = time.monotonic()
    baseline = initial["sensor_samples_c"][-1]
    last_t = baseline
    peak = baseline
    steps = 0
    fault = None
    with filename.open("x", newline="", encoding="utf-8") as f:
        os.chmod(filename, 0o600)
        writer = csv.writer(f)
        writer.writerow(["elapsed_s", "temperature_c", "cpu_c", "heater_on", "ready", "fault"])
        f.flush()
        try:
            controller = ThermalController(
                run_cfg,
                sensor=sensor if sensor is not None else DS18B20(cfg.sensor_id),
                cpu_reader=cpu_reader,
            )
            while not stop.is_set() and time.monotonic() - started < duration_s:
                controller.tick()
                state = controller.snapshot()
                elapsed = time.monotonic() - started
                t = state["temperature_c"]
                cpu = state["cpu_temperature_c"]
                peak = max(peak, t) if t is not None else peak
                writer.writerow([round(elapsed, 1), t, cpu, int(state["heater_on"]),
                                 int(state["ready"]), state["fault"] or ""])
                f.flush()
                steps += 1
                LOG.info("HEAT_TEST elapsed=%0.1fs chamber=%s cpu=%s relay=%s fault=%s",
                         elapsed, t, cpu, state["heater_on"], state["fault"])
                if state["fault"]:
                    fault = state["fault"]
                    LOG.error("TEST ARRETE : défaut thermique %s", fault)
                    break
                if t is None or cpu is None:
                    fault = "MESURE_MANQUANTE"
                    break
                if t >= MAX_TEST_TEMPERATURE:
                    fault = "LIMITE_D_ESSAI_38_5"
                    LOG.error("TEST ARRETE : température d'essai >=38.5 C.")
                    break
                if cpu >= MAX_TEST_CPU:
                    fault = "LIMITE_CPU_70"
                    LOG.error("TEST ARRETE : CPU d'essai >=70 C.")
                    break
                if t - last_t >= 2.0:
                    fault = "SAUT_SONDE_SUPERIEUR_2C"
                    LOG.error("TEST ARRETE : augmentation non physique de la sonde.")
                    break
                if elapsed >= MIN_RISE_AFTER_S and peak - baseline < MIN_RISE_C:
                    fault = "AUCUNE_MONTEE_MESURABLE"
                    LOG.error("TEST ARRETE : température n'augmente pas après 180s.")
                    break
                last_t = t
                stop.wait(2.0)
        finally:
            # Condition nécessaire mais non suffisante : l'unité systemd
            # exécute également une coupure GPIO indépendante après sortie.
            if controller is not None:
                controller.stop()
            f.flush()
            os.fsync(f.fileno())
            LOG.warning("ESSAI CHAUFFE termine et GPIO21 desactive ; journal=%s", filename)
    result = {
        "log": str(filename), "readings": steps,
        "duration_actual_s": round(time.monotonic() - started, 2),
        "initial_c": baseline, "maximum_c": round(peak, 3),
        "failure": fault, "relay_turned_off_on_exit": True,
    }
    LOG.warning("RESULTAT_THERMIQUE %s", json.dumps(result))
    if fault:
        raise SystemExit(2)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    op = ap.add_mutually_exclusive_group(required=True)
    op.add_argument("--preflight", action="store_true")
    op.add_argument("--run", action="store_true")
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--duration-s", type=int, default=600)
    opts = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(opts.config)
    if opts.preflight:
        print(json.dumps(safe_preflight(cfg), indent=2))
    else:
        print(json.dumps(perform(cfg, duration_s=opts.duration_s), indent=2))


if __name__ == "__main__":
    main()
