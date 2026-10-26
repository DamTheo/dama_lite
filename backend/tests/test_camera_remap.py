"""Vérification de l'affectation USB, sans caméra ni secret Graph réel."""
import unittest
from dama_lite.camera_remap import remap_staging, usb_port


def make_raw():
    prefix = "/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:"
    order = [2, 4, 1, 3]
    cameras = [
        {"slot": idx, "device": prefix + f"1.2.{port}:1.0-video-index0",
         "width": 1280, "height": 720, "pixel_format": "MJPG"}
        for idx, port in enumerate(order, 1)
    ]
    cameras.extend(
        {"slot": idx, "device": prefix + f"1.1.{idx - 4}:1.0-video-index0"}
        for idx in range(5, 9)
    )
    return {
        "cameras": cameras, "heating_enabled": False,
        "leds_enabled": False, "allow_os_shutdown": True,
        "sharepoint": {"graph_env_path": "/etc/dama-lite/graph.env"},
    }


class MappingTests(unittest.TestCase):
    def test_old_slot_labels_to_unique_persistent_usb_paths(self):
        original = make_raw()
        revised = remap_staging(original)
        expected = ["1.2.4", "1.2.3", "1.2.2", "1.2.1"]
        self.assertEqual(expected, [
            usb_port(c["device"]) for c in revised["cameras"][:4]
        ])
        self.assertEqual(8, len({
            c["device"] for c in revised["cameras"]
        }))
        self.assertEqual(original["cameras"][4:], revised["cameras"][4:])
        self.assertEqual(original["sharepoint"], revised["sharepoint"])
        self.assertFalse(revised["heating_enabled"])
        self.assertFalse(revised["leds_enabled"])
        self.assertEqual(original, make_raw())
        self.assertEqual(revised, remap_staging(revised))

    def test_reject_duplicate_or_unexpected_hub(self):
        value = make_raw()
        value["cameras"][0]["device"] = value["cameras"][1]["device"]
        with self.assertRaisesRegex(ValueError, "invalides"):
            remap_staging(value)
        value = make_raw()
        value["cameras"][0]["device"] = value["cameras"][0]["device"].replace(
            "1.2.2:", "1.1.2:")
        with self.assertRaisesRegex(ValueError, "invalides"):
            remap_staging(value)

    def test_usb_by_id_is_not_a_reliable_identity_for_uc60(self):
        self.assertIsNone(usb_port(
            "/dev/v4l/by-id/usb-DSJ_UC60_Video_200901010001-video-index0"
        ))


if __name__ == "__main__":
    unittest.main()
