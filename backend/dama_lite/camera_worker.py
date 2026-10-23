"""Worker UVC éphémère — seul processus qui importe OpenCV et ouvre /dev/video*.

Ne commande JAMAIS le chauffage, les LED, le bouton ni SharePoint.
Les octets JPG/PNG sont écrits sur stdout; diagnostics sur stderr.
"""
from __future__ import annotations

import argparse
import sys


def capture(device: str, width: int, height: int,
            pixel_format: str, preview: bool) -> bytes:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Installer python3-opencv sur le Pi.") from exc

    camera = cv2.VideoCapture(device, cv2.CAP_V4L2)
    try:
        if not camera.isOpened():
            raise RuntimeError(f"Ouverture impossible : {device}")
        camera.set(
            cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pixel_format)
        )
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        frame = None
        for _ in range(3):
            ok, sample = camera.read()
            if ok and sample is not None:
                frame = sample
        if frame is None:
            raise RuntimeError("Aucune trame valide.")
        actual_height, actual_width = frame.shape[:2]
        if (actual_width, actual_height) != (width, height):
            raise RuntimeError(
                f"Dimensions {actual_width}x{actual_height}, "
                f"attendu {width}x{height}."
            )
        if preview and width > 800:
            frame = cv2.resize(
                frame, (800, round(actual_height * 800 / actual_width))
            )
        ext = ".jpg" if preview else ".png"
        encoding = (
            [int(cv2.IMWRITE_JPEG_QUALITY), 80] if preview
            else [int(cv2.IMWRITE_PNG_COMPRESSION), 3]
        )
        ok, encoded = cv2.imencode(ext, frame, encoding)
        if not ok:
            raise RuntimeError("Impossible d'encoder la photographie.")
        return encoded.tobytes()
    finally:
        camera.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture caméra isolée")
    parser.add_argument("--device", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--pixel-format", choices=["MJPG", "YUYV"], default="MJPG")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        image = capture(
            args.device, args.width, args.height, args.pixel_format, args.preview
        )
        sys.stdout.buffer.write(image)
        sys.stdout.buffer.flush()
        return 0
    except Exception as exc:
        print(f"UVC worker : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
