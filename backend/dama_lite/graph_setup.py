"""Configurer SharePoint depuis le fichier Entra EXISTANT sur Incub-resa.

Aucune copie de secret. Ne modifie ni chauffage, ni LED, ni GPIO.
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, ConfigError
from .entra_env import read_graph_env
from .safe_staging import STAGING_CONFIG, validate_staging
from .sharepoint import SharePointClient

DEFAULT_GRAPH_ENV = "/etc/dama-lite/graph.env"


def enable_existing_graph(staging_path: Path, env_path: str) -> Path:
    if staging_path.resolve() != STAGING_CONFIG.resolve():
        raise ConfigError("Modifier uniquement la configuration staging existante.")
    keys = read_graph_env(env_path)
    cfg = Config.load(staging_path)
    validate_staging(cfg)
    raw = json.loads(staging_path.read_text(encoding="utf-8"))
    sp = raw.setdefault("sharepoint", {})
    if any(sp.get(k) for k in (
        "tenant_id", "client_id", "drive_id",
        "private_key_path", "public_cert_path", "client_secret_path",
    )):
        raise ConfigError("Une autre authentification Entra est déjà configurée.")
    sp["graph_env_path"] = env_path
    backup = staging_path.with_name(
        staging_path.name + ".backup-entra-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    # Tester la configuration avant d'écraser le fichier utilisé par systemd.
    fd, tmpname = tempfile.mkstemp(
        prefix=".graph-config-", suffix=".json", dir=staging_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(raw, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmpname, 0o600)
        proposed = Config.load(Path(tmpname))
        validate_staging(proposed)
        if not proposed.sharepoint.configured:
            raise ConfigError("SharePoint incomplet après configuration.")
        backup.write_bytes(staging_path.read_bytes())
        backup.chmod(0o600)
        os.replace(tmpname, staging_path)
    finally:
        Path(tmpname).unlink(missing_ok=True)
    return backup


def validation_png() -> bytes:
    """Un pixel RGB vert explicitement réservé aux vérifications, sans caméra."""
    def chunk(name: bytes, payload: bytes) -> bytes:
        body = name + payload
        return (
            struct.pack(">I", len(payload)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\xff\x00"))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Associer les identifiants Entra existants ou vérifier SharePoint."
    )
    ap.add_argument("--config", default=str(STAGING_CONFIG))
    ap.add_argument("--env", default=DEFAULT_GRAPH_ENV)
    options = ap.add_mutually_exclusive_group(required=True)
    options.add_argument("--configure", action="store_true")
    options.add_argument("--verify", action="store_true")
    options.add_argument("--write-probe", action="store_true",
                         help="Créer un dossier de vérification et un PNG 1px, jamais une analyse.")
    args = ap.parse_args()
    config_file = Path(args.config)
    if args.configure:
        backup = enable_existing_graph(config_file, args.env)
        print("Configuration Entra reliée au fichier privé existant.")
        print("Sauvegarde:", backup)
        return
    cfg = Config.load(config_file)
    validate_staging(cfg)
    if not cfg.sharepoint.configured:
        raise ConfigError("Authentification Entra non configurée.")
    client = SharePointClient(cfg.sharepoint)
    result = client.verify_read_only()
    if args.write_probe:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder_name = "DAMA-Lite-Verification-" + stamp
        folder_id, web_url = client.reserve_folder(folder_name)
        client.upload(folder_id, "verification_ecriture.png", validation_png())
        print(json.dumps({
            "graph_authenticated": True,
            **result,
            "writes_performed": True,
            "test_folder": folder_name,
            "verification_image": "verification_ecriture.png",
            "url": web_url,
        }, ensure_ascii=False))
    else:
        print(json.dumps(
            {"graph_authenticated": True, **result, "writes_performed": False},
            ensure_ascii=False,
        ))


if __name__ == "__main__":
    main()
