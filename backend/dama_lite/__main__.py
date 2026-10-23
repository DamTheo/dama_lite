"""Point d'entrée : python -m dama_lite --config /etc/dama-lite/config.json."""
from __future__ import annotations

import argparse
import logging
import signal
import threading

from .config import Config
from .server import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="DAMA Lite — serveur incubateur")
    parser.add_argument("--config", required=True, help="Chemin vers config.json")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.load(args.config)
    # systemd SIGTERM est traité par interruption du serveur HTTP ;
    # la fermeture du service coupe d'abord le chauffage.
    run_server(cfg)


if __name__ == "__main__":
    main()
