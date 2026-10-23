import unittest

from dama_lite.sharepoint import validate_test_name


class SharePointNameTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual("Ecoli 1", validate_test_name("Ecoli 1"))
        self.assertEqual("EXP_ID-AST_23-10", validate_test_name("EXP_ID-AST_23-10"))

    def test_reject_path_traversal_and_confusing_names(self):
        for name in ["", ".", "..", "ABC/", "A\\B", "ABC ", " A", "X\nY", "Z?", "A" * 111]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_test_name(name)


if __name__ == "__main__":
    unittest.main()
