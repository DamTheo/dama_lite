import tempfile
import unittest
from pathlib import Path

from dama_lite.store import Store


class StoreTests(unittest.TestCase):
    def test_session_persists_and_reboot_interrupts(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            db = Store(state)
            item = db.new_test("Ecoli-01", 1, "folder-id", None)
            image = db.spool_dir / "frame.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n")
            db.add_image(item["id"], 0, "image.png", image, 8, 37, 42)
            self.assertEqual(8, db.pending_bytes())
            self.assertEqual(1, len(db.due_uploads()))
            db.close()
            db = Store(state)
            self.assertEqual("interrupted", db.tests()[0]["state"])
            self.assertEqual(1, db.tests()[0]["pending_uploads"])
            db.mark_uploaded(db.due_uploads()[0]["id"])
            self.assertEqual(0, db.pending_bytes())
            db.close()


if __name__ == "__main__":
    unittest.main()
