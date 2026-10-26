"""Active uniquement l'arrêt Linux du staging, sans toucher au GPIO.

Aucun secret dans le JSON ou les logs. Activation atomique avec backup.
À exécuter APRÈS installation du fichier root d'autorisation et de la
passerelle systemd poweroff.path. N'éteint jamais la machine lui-même.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .safe_staging import STAGING_CONFIG, shutdown_approved, validate_staging


def enable_shutdown(config_path: Path = STAGING_CONFIG) -> Path:
    if config_path.resolve() != STAGING_CONFIG.resolve():
        raise ValueError("Seul le fichier de staging courant est autorisé.")
    before = Config.load(config_path)
    validate_staging(before)
    if before.heating_enabled or before.leds_enabled:
        raise ValueError("Le staging doit garder chauffe et LEDs internes OFF.")
    if not shutdown_approved():
        raise ValueError("Autorisation d'extinction root absente.")
    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", "dama-lite-poweroff.path"],
        check=False, capture_output=True, timeout=8,
    )
    if result.returncode != 0:
        raise RuntimeError("Service de surveillance d'extinction non actif.")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["allow_os_shutdown"] = True
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config_path.with_name(config_path.name + ".backup-shutdown-" + stamp)
    fd, temp_path = tempfile.mkstemp(
        prefix=".shutdown-config-", suffix=".json", dir=config_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(raw, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, 0o600)
        after = Config.load(Path(temp_path))
        validate_staging(after)
        if not after.allow_os_shutdown or after.heating_enabled or after.leds_enabled:
            raise RuntimeError("Incohérence : une sortie GPIO serait activée.")
        backup.write_bytes(config_path.read_bytes())
        backup.chmod(0o600)
        os.replace(temp_path, config_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-staging", action="store_true", required=True)
    opts = parser.parse_args()
    if opts.enable_staging:
        backup = enable_shutdown()
        print("Extinction Linux autorisée sur l'interface tactile.")
        print("Configuration initiale sauvegardée dans :", backup)
        print("Chauffage et commande LED interne restent désactivés.")


if __name__ == "__main__":
    main()
