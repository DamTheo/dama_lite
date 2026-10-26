"""Essai de huit flux UVC via l'API locale sans lancer d'analyse.

L'image n'est ni enregistrée ni envoyée à Microsoft 365.
Aucun GPIO, aucune chauffe. Fonctionne sur le service staging déjà actif.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import json
import time


def inspect_stream(slot: int, seconds: float, port: int = 8765) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", port=port, timeout=4.0)
    start = time.monotonic()
    frames = 0
    first = None
    pending = b""
    detail = None
    status = None
    bytes_received = 0
    try:
        conn.request("GET", f"/api/cameras/{slot}/stream")
        response = conn.getresponse()
        status = response.status
        if status != 200:
            detail = f"HTTP {status}"
        else:
            # Count multipart part headers; they cannot occur in an ordinary
            # valid JPEG bitstream. A chunk can split a marker across reads.
            marker = b"Content-Type: image/jpeg"
            deadline = start + seconds
            while time.monotonic() < deadline:
                try:
                    chunk = response.read(16 * 1024)
                except (OSError, TimeoutError) as exc:
                    detail = type(exc).__name__
                    break
                if not chunk:
                    detail = "Flux fermé prématurément"
                    break
                bytes_received += len(chunk)
                combined = pending + chunk
                count = combined.count(marker)
                frames += count
                if count and first is None:
                    first = round(time.monotonic() - start, 3)
                pending = combined[-len(marker) + 1:]
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        detail = type(exc).__name__
    finally:
        conn.close()
    elapsed = round(time.monotonic() - start, 2)
    return {
        "slot": slot,
        "http_status": status,
        "frames": frames,
        "first_frame_s": first,
        "elapsed_s": elapsed,
        "fps": round(frames / elapsed, 2) if elapsed else 0.0,
        "bytes": bytes_received,
        "error": detail,
    }


def measure(slots: list[int], seconds: float, port: int = 8765) -> list[dict]:
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(slots)
    ) as pool:
        futures = [
            pool.submit(inspect_stream, slot, seconds, port) for slot in slots
        ]
        return sorted((f.result() for f in futures), key=lambda r: r["slot"])


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Contrôler 1–8 flux vidéo en parallèle sans sauvegarder d'images."
    )
    ap.add_argument("--seconds", type=float, default=7.0)
    ap.add_argument("--slots", default="1,2,3,4,5,6,7,8")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    slots = [int(s) for s in args.slots.split(",")]
    if not slots or len(set(slots)) != len(slots) or any(not 1 <= s <= 8 for s in slots):
        ap.error("Indiquer des numéros de caméras uniques entre 1 et 8.")
    if not 2.0 <= args.seconds <= 45.0:
        ap.error("Durée comprise entre 2 et 45 secondes.")
    data = measure(slots, args.seconds, args.port)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if any(item["http_status"] != 200 or item["frames"] < 2 for item in data):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
