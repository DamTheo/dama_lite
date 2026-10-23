import tempfile
import unittest
from pathlib import Path

from dama_lite.interlocks import legacy_gpio_processes


class InterlockTests(unittest.TestCase):
    def test_lists_only_explicit_legacy_gpio_owners(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for pid, args in {
                "123": [b"/usr/bin/python3", b"/home/damocles/Programme_complet.py"],
                "124": [b"python3", b"/home/damocles/temperature.py"],
                "125": [b"python3", b"/home/damocles/Test_LED.py"],
            }.items():
                proc = root / pid
                proc.mkdir()
                (proc / "cmdline").write_bytes(b"\0".join(args) + b"\0")
            self.assertEqual(
                [{"pid": 123, "program": "Programme_complet.py"},
                 {"pid": 125, "program": "Test_LED.py"}],
                legacy_gpio_processes(root),
            )


if __name__ == "__main__":
    unittest.main()
