import unittest
from dama_lite.live_preview import JpegParser, LivePreviewManager, MAX_FRAME_BYTES


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


if __name__ == "__main__":
    unittest.main()
