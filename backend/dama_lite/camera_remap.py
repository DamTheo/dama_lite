"""Réaffectation USB CAM1–CAM4 sur les emplacements physiques indiqués.

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

# USB observé sur Incub-resa le 26 octobre 2026 (hub Linux 1-1.2).
# D'après le retour opérateur : ancien CAM2=physique 1,
# ancien CAM1=physique 3, ancien CAM3=physique 4.
# Le port 1.2.3, ancien CAM4 (HTTP 503), reste le seul candidat pour
# CAM2 : il doit être confirmé visuellement APRÈS déblocage des flux.
USB_PORT_FOR_LOGICAL_SLOT = {
    1: "1.2.4",
    2: "1.2.3",  # À CONFIRMER visuellement, ne pas l'affirmer comme validé.
    3: "1.2.2",
    4: "1.2.1",
}
PORT_RE = re.compile(r"-usb-0:(1\.2\.[1-4]):1\.0-video-index0$")


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
    for slot in range(1, 5):
        path = by_slot[slot].get("device")
        port = usb_port(path)
        if port is None or port in port_devices:
            raise ValueError(
                "Chemins persistants des quatre webcams du premier hub invalides."
            )
        port_devices[port] = path
    if set(port_devices) != set(USB_PORT_FOR_LOGICAL_SLOT.values()):
        raise ValueError("Topologie USB inattendue : aucun remappage automatique.")
    result = json.loads(json.dumps(raw))
    for item in result["cameras"]:
        if 1 <= item["slot"] <= 4:
            item["device"] = port_devices[USB_PORT_FOR_LOGICAL_SLOT[item["slot"]]]
    all_devices = [x["device"] for x in result["cameras"] if x.get("device")]
    if len(set(all_devices)) != len(all_devices):
        raise ValueError("Le remappage créerait deux caméras sur un même port.")
    # CAM5–CAM8 et secrets Entra laissés inchangés à l'octet logique près.
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
        print("Les quatre emplacements étaient déjà correctement associés.")
    else:
        print("Affectation mise à jour ; sauvegarde conservée : " + str(backup))
    print("CAM1=USB1.2.4, CAM3=USB1.2.2, CAM4=USB1.2.1.")
    print("CAM2=USB1.2.3 : emplacement encore à confirmer visuellement.")
    print("CAM5–CAM8, Entra, chauffe et LED inchangés.")


if __name__ == "__main__":
    main()
