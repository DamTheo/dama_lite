"""Découverte USB et appairage EXPLICITE en configuration de staging.

Aucun remappage à chaud ni pendant une expérience, pour ne jamais mélanger
les séries de photos de deux positions physiques différentes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, ConfigError
from .safe_staging import STAGING_CONFIG, validate_staging


def discover_uvc_links(root: Path = Path("/dev/v4l/by-path")) -> list[str]:
    if not root.is_dir():
        return []
    result = []
    for link in root.iterdir():
        if not (link.is_symlink()
                and "-usb-" in link.name
                and link.name.endswith("-video-index0")):
            continue
        # Éliminer les codecs de la plateforme et les liens obsolètes.
        if link.exists() and link.resolve().name.startswith("video"):
            result.append(str(link))
    return sorted(result)


def reserve_observed_usb_ports(
    detected: list[str], ports: list[str],
) -> list[str]:
    """Réserve uniquement des chemins by-path USB physiquement constatés.

    Les ports peuvent être temporairement inaccessibles (hub en défaut).
    Cette fonction n'ouvre pas de webcam, et ne déclenche aucun reset USB.
    Toute réservation est explicite, jamais à chaud ni au runtime.
    """
    if not ports:
        return sorted(detected)
    if not detected:
        raise ValueError("Impossible de déterminer la racine USB sans caméra détectée.")
    pattern = re.compile(
        r"(?P<before>/dev/v4l/by-path/[^/]+-usb-0:)"
        r"(?P<port>[0-9]+(?:\.[0-9]+)+)"
        r"(?P<after>:[0-9]+\.[0-9]+-video-index0)"
    )
    matches = [pattern.fullmatch(d) for d in detected]
    if any(m is None for m in matches):
        raise ValueError("Impossible de dériver un chemin USB vidéo fiable.")
    bases = {(m.group("before"), m.group("after")) for m in matches if m}
    if len(bases) != 1:
        raise ValueError("Plusieurs contrôleurs USB : fournir une association explicite.")
    before, after = next(iter(bases))
    if any(not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,4}", p) for p in ports):
        raise ValueError("Port USB invalide : utiliser par exemple 1.1.3.")
    all_links = sorted(set(detected) | {before + port + after for port in ports})
    if len(all_links) > 8:
        raise ValueError("Plus de huit caméras : appairage refusé.")
    return all_links


def propose_slot_mapping(
    old_slots: dict[int, str | None], detected: list[str],
) -> dict[int, str | None]:
    """Conserver les ports encore présents, attribuer le reste dans l'ordre.

    Réaffectation seulement par la commande manuelle --apply en staging,
    jamais automatiquement au runtime lorsque les tests ont commencé.
    """
    if len(detected) > 8 or len(set(detected)) != len(detected):
        raise ValueError("Il faut entre 0 et 8 ports USB vidéo uniques.")
    # Conserver les associations existantes si l'emplacement USB est présent.
    kept = {
        slot: old_slots.get(slot)
        for slot in range(1, 9)
        if old_slots.get(slot) in detected
    }
    remaining = [dev for dev in detected if dev not in kept.values()]
    result: dict[int, str | None] = {}
    for slot in range(1, 9):
        result[slot] = kept.get(slot)
        if result[slot] is None and remaining:
            result[slot] = remaining.pop(0)
    return result


def _historical_test_count(database: Path) -> int:
    if not database.exists():
        return 0
    # Lecture seule ; ne crée pas le fichier SQLite.
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM tests").fetchone()[0])
    finally:
        connection.close()


def apply_staging_mapping(config_path: Path, mapping: dict[int, str | None]) -> str:
    if config_path.resolve() != STAGING_CONFIG.resolve():
        raise ValueError("Écriture autorisée uniquement dans config.staging.json.")
    cfg = Config.load(config_path)
    validate_staging(cfg)
    if cfg.sharepoint.configured:
        raise ValueError("Ne pas réappairer après activation de Microsoft Graph.")
    if _historical_test_count(cfg.state_dir / "dama-lite.db") > 0:
        raise ValueError("Historique existant : appairage manuel contrôlé obligatoire.")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    for entry in raw["cameras"]:
        entry["device"] = mapping[int(entry["slot"])]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config_path.with_name(config_path.name + f".backup-{stamp}")
    backup.write_bytes(config_path.read_bytes())
    backup.chmod(0o600)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".dama-lite-camera-map-", suffix=".json",
        dir=config_path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(raw, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, config_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    # Relecture structurée pour vérifier les chemins uniques et les slots 1–8.
    Config.load(config_path)
    return str(backup)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identifier les caméras USB et suggérer un appairage stable."
    )
    parser.add_argument("--config", default=str(STAGING_CONFIG))
    parser.add_argument("--apply", action="store_true",
                        help="Mettre à jour UNIQUEMENT le staging, avec sauvegarde.")
    parser.add_argument("--reserve-offline-ports", default="",
                        help="Ports UVC déjà observés mais actuellement hors ligne, séparés par virgules (ex. 1.1.1,1.1.2).")
    args = parser.parse_args()
    cfg_path = Path(args.config)
    cfg = Config.load(cfg_path)
    detected = discover_uvc_links()
    current = {s.slot: s.device for s in cfg.cameras}
    expected_ports = [
        part.strip() for part in args.reserve_offline_ports.split(",") if part.strip()
    ]
    candidates = reserve_observed_usb_ports(detected, expected_ports)
    proposed = propose_slot_mapping(current, candidates)
    result = {
        "observed_usb_video_paths": detected,
        "reserved_offline_paths": [p for p in candidates if p not in detected],
        "current_slots": current,
        "proposed_slots": proposed,
        "changes": {
            slot: {"old": current[slot], "new": proposed[slot]}
            for slot in range(1, 9) if current[slot] != proposed[slot]
        },
        "applied": False,
        "note": "Vérifier visuellement chaque emplacement avant les tests réels.",
    }
    if args.apply:
        if not detected:
            raise RuntimeError("Aucune webcam USB détectée : aucun changement.")
        result["backup"] = apply_staging_mapping(cfg_path, proposed)
        result["applied"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
