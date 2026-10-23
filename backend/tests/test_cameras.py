import subprocess
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dama_lite.cameras import CameraController, CameraError
from dama_lite.config import CameraSpec


class CameraTests(unittest.TestCase):
    def setUp(self):
        camera = CameraSpec(
            1, "/dev/v4l/by-path/usb-fake-video-index0",
            1280, 720, "MJPG",
        )
        self.driver = CameraController((camera,))

    def test_worker_returns_png_and_uses_mjpg(self):
        self.driver.ready = lambda slot: True
        payload = SimpleNamespace(
            returncode=0, stdout=b"\x89PNG\r\n\x1a\nframe", stderr=b""
        )
        with patch("dama_lite.cameras.subprocess.run", return_value=payload) as runner:
            image = self.driver.photo(1)
        self.assertEqual(payload.stdout, image)
        args = runner.call_args.args[0]
        self.assertIn("dama_lite.camera_worker", args)
        self.assertIn("MJPG", args)
        self.assertEqual(15, runner.call_args.kwargs["timeout"])

    def test_native_hang_isolation(self):
        self.driver.ready = lambda slot: True
        with patch("dama_lite.cameras.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("uvc", 10)):
            with self.assertRaisesRegex(CameraError, "figée"):
                self.driver.preview(1)
        # Le verrou est libéré, le prochain essai reste possible.
        self.assertFalse(self.driver._usb_lock.locked())

    def test_preview_never_waits_behind_photo(self):
        self.driver.ready = lambda slot: True
        self.driver._usb_lock.acquire()
        try:
            with self.assertRaisesRegex(CameraError, "occupé"):
                self.driver.preview(1)
        finally:
            self.driver._usb_lock.release()

    def test_unrecognized_image_rejected(self):
        self.driver.ready = lambda slot: True
        result = SimpleNamespace(returncode=0, stdout=b"not-image", stderr=b"")
        with patch("dama_lite.cameras.subprocess.run", return_value=result):
            with self.assertRaisesRegex(CameraError, "invalide"):
                self.driver.photo(1)


if __name__ == "__main__":
    unittest.main()
