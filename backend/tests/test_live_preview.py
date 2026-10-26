import unittest
from dama_lite.live_preview import (
    FRAME_INTERVAL_S, JpegParser, LivePreviewManager, MAX_FRAME_BYTES,
    STALL_TIMEOUT_S,
)


class ParserTests(unittest.TestCase):
    def test_jpeg_split_and_coalesced_transport_chunks(self):
        parser = JpegParser()
        a = b"\xff\xd8frame_a\xff\xd9"
        b = b"\xff\xd8frame_b\xff\xd9"
        self.assertEqual([], parser.feed(b"header" + a[:4]))
        self.assertEqual([a, b], parser.feed(a[4:] + b + b"tail"))
        self.assertEqual([], parser.feed(b"garbage"))

    def test_large_invalid_frame_dropped_without_memory_leak(self):
        parser = JpegParser()
        parser.feed(b"\xff\xd8" + b"A" * (MAX_FRAME_BYTES + 5))
        self.assertEqual(0, len(parser.buffer))

    def test_stream_reads_camera_mjpg_without_transcoding(self):
        command = LivePreviewManager.ffmpeg_command("/dev/v4l/by-path/video0")
        self.assertIn("640x480", command)
        self.assertIn("mjpeg", command)
        self.assertEqual("copy", command[command.index("-c:v") + 1])
        self.assertEqual("pipe:1", command[-1])

    def test_all_native_ten_fps_frames_can_pass_without_artificial_drop(self):
        # L'entrée FFmpeg limite déjà la cadence à 10 i/s : le worker ne
        # doit pas jeter une image sur deux avant diffusion aux clients.
        self.assertEqual(0.0, FRAME_INTERVAL_S)
        self.assertLessEqual(STALL_TIMEOUT_S, 5.0)
        command = LivePreviewManager.ffmpeg_command("/dev/v4l/by-path/video0")
        self.assertEqual("10", command[command.index("-framerate") + 1])

    def test_photo_slot_releases_after_completion(self):
        preview = LivePreviewManager()
        preview.suspend_for_photo(1)
        with self.assertRaisesRegex(Exception, "déjà"):
            preview.suspend_for_photo(1)
        preview.resume_after_photo(1)
        preview.suspend_for_photo(1)
        preview.resume_after_photo(1)
        preview.close()
        with self.assertRaisesRegex(Exception, "arrêt"):
            preview.suspend_for_photo(1)




class SharedPreviewTests(unittest.TestCase):
    def test_multiple_subscribers_and_warm_reconnect_use_one_uvc_open(self):
        import threading
        import time
        from unittest.mock import patch

        class FakeProcess:
            stdout = None
            returncode = None
            def __init__(self):
                self.terminated = False
            def poll(self):
                return 0 if self.terminated else None
            def terminate(self):
                self.terminated = True
            def kill(self):
                self.terminated = True
            def wait(self, timeout=None):
                return 0

        manager = LivePreviewManager()
        def reader_holds_until_stop(slot, session):
            session.stop.wait(timeout=4.0)

        with patch(
            "dama_lite.live_preview.subprocess.Popen",
            side_effect=lambda *a, **k: FakeProcess(),
        ) as spawn, patch.object(manager, "_read_loop", side_effect=reader_holds_until_stop):
            with manager.open(5, "/dev/v4l/by-path/fake-5") as first:
                with manager.open(5, "/dev/v4l/by-path/fake-5") as second:
                    self.assertEqual(1, spawn.call_count)
                    self.assertEqual(2, manager._streams[5].clients)
                    # Un nouvel abonné récupère l'image cache immédiatement.
                    session = manager._streams[5]
                    with session.condition:
                        session.last_frame = b"\xff\xd8test\xff\xd9"
                        session.frame_at = time.monotonic()
                        session.seq += 1
                        session.condition.notify_all()
                    self.assertEqual(b"\xff\xd8test\xff\xd9", next(first))
                    self.assertEqual(b"\xff\xd8test\xff\xd9", next(second))
            with manager.open(5, "/dev/v4l/by-path/fake-5"):
                self.assertEqual(1, spawn.call_count)
            # Une photographie force la libération V4L2 et la réouverture.
            manager.suspend_for_photo(5)
            with self.assertRaisesRegex(Exception, "Photographie"):
                with manager.open(5, "/dev/v4l/by-path/fake-5"):
                    pass
            manager.resume_after_photo(5)
            with manager.open(5, "/dev/v4l/by-path/fake-5"):
                self.assertEqual(2, spawn.call_count)
            manager.close()

    def test_no_usb_photo_interference_from_preview(self):
        from unittest.mock import patch
        manager = LivePreviewManager()
        manager.suspend_for_photo(3)
        with self.assertRaisesRegex(Exception, "Photographie"):
            with manager.open(3, "/dev/v4l/by-path/fake-3"):
                pass
        manager.resume_after_photo(3)
        manager.close()

if __name__ == "__main__":
    unittest.main()
