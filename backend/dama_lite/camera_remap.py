"""Réaffectation USB des huit caméras aux emplacements physiques indiqués.

Préserve tous les autres paramètres (SharePoint Entra, chauffe OFF,
GPIO12, CAM5–CAM8), et applique le plan uniquement au staging du Pi.
Utilise /dev/v4l/by-path, jamais /dev/videoX ni by-id : les huit UC60
partagent le même numéro de série, donc by-id n'est PAS une identité.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .safe_staging import STAGING_CONFIG, validate_staging

# Nouvelle observation opérateur datée du 30/10/2026, deux hubs fonctionnels.
USB_PORT_FOR_LOGICAL_SLOT = {
    # Opérateur 30/10 : anciens 1->5, 2->6, 3->7, 4->8,
    # 5->4, 6->3, 7->1, 8->1 (ambigu, physique 2 non identifié).
    1: "1.1.3",  # ancienne tuile 7, physique 1
    2: "1.1.4",  # ancienne tuile 8, PROVISOIRE / non vérifié
    3: "1.1.2",  # ancienne tuile 6, physique 3
    4: "1.1.1",  # ancienne tuile 5, physique 4
    5: "1.2.4",  # ancienne tuile 1, physique 5
    6: "1.2.3",  # ancienne tuile 2, physique 6
    7: "1.2.2",  # ancienne tuile 3, physique 7
    8: "1.2.1",  # ancienne tuile 4, physique 8
}
UNVERIFIED_SLOTS = frozenset({2})
PORT_RE = re.compile(r"-usb-0:(1\.[12]\.[1-4]):1\.0-video-index0$")

def usb_port(device: str | None) -> str | None:
    if not isinstance(device, str):
        return None
    match = PORT_RE.search(device)
    return match.group(1) if match else None


def remap_staging(raw: dict) -> dict:
    """Retourne une copie sans changer aucune autre clé de configuration."""
    if type(raw) is not dict:
        raise ValueError("Configuration JSON incorrecte.")
    items = raw.get("cameras")
    if not isinstance(items, list) or len(items) != 8:
        raise ValueError("Huit emplacements caméra sont obligatoires.")
    by_slot = {item.get("slot"): item for item in items if isinstance(item, dict)}
    if set(by_slot) != set(range(1, 9)):
        raise ValueError("Slots caméra invalides ou dupliqués.")
    port_devices = {}
    for slot in range(1, 9):
        path = by_slot[slot].get("device")
        port = usb_port(path)
        if port is None or port in port_devices:
            raise ValueError(
                "Chemins USB persistants des huit caméras invalides."
            )
        port_devices[port] = path
    if set(port_devices) != set(USB_PORT_FOR_LOGICAL_SLOT.values()):
        raise ValueError("Topologie USB inattendue : aucun remappage automatique.")
    result = json.loads(json.dumps(raw))
    for item in result["cameras"]:
        item["device"] = port_devices[USB_PORT_FOR_LOGICAL_SLOT[item["slot"]]]
        item["mapping_verified"] = item["slot"] not in UNVERIFIED_SLOTS
    all_devices = [x["device"] for x in result["cameras"] if x.get("device")]
    if len(set(all_devices)) != len(all_devices):
        raise ValueError("Le remappage créerait deux caméras sur un même port.")
    # Configuration Entra, thermique et GPIO laissée inchangée.
    return result


def apply_staging(path: Path = STAGING_CONFIG) -> Path | None:
    if path.resolve() != STAGING_CONFIG.resolve():
        raise ValueError("Modification interdite hors du staging DAMA Lite.")
    before_cfg = Config.load(path)
    validate_staging(before_cfg)
    if before_cfg.heating_enabled or before_cfg.leds_enabled:
        raise ValueError("Remappage interdit si GPIO matériel actif dans ce service.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    after = remap_staging(raw)
    if after == raw:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(path.name + ".camera-map-backup-" + stamp)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".camera-remap-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(after, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp_path, 0o600)
        after_cfg = Config.load(Path(tmp_path))
        validate_staging(after_cfg)
        if (
            after_cfg.heating_enabled != before_cfg.heating_enabled
            or after_cfg.leds_enabled != before_cfg.leds_enabled
            or after_cfg.sharepoint != before_cfg.sharepoint
            or after_cfg.allow_os_shutdown != before_cfg.allow_os_shutdown
        ):
            raise RuntimeError("Modification non caméra détectée.")
        backup.write_bytes(path.read_bytes())
        backup.chmod(0o600)
        os.replace(tmp_path, path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Remapper CAM1–CAM4 en sécurité.")
    parser.add_argument("--apply-staging", action="store_true")
    args = parser.parse_args()
    if not args.apply_staging:
        print(json.dumps(USB_PORT_FOR_LOGICAL_SLOT, indent=2))
        print("Mode lecture seule. Passer --apply-staging pour appliquer.")
        return
    backup = apply_staging()
    if backup is None:
        print("Les huit emplacements sont deja correctement associes.")
    else:
        print("Affectation mise à jour ; sauvegarde conservée : " + str(backup))
    print("CAM1:1.1.3, CAM2:1.1.4 (PROVISOIRE), CAM3:1.1.2, CAM4:1.1.1.")
    print("CAM5:1.2.4, CAM6:1.2.3, CAM7:1.2.2, CAM8:1.2.1.")
    print("CAM2 : analyses bloquees tant que la position physique est non verifiee.")
    print("Entra, SharePoint, chauffe et LED inchanges.")


if __name__ == "__main__":
    main()
