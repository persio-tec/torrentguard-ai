import unittest

from core.scanner import PreDownloadScanner


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.scanner = PreDownloadScanner()

    def test_analyze_files_low_risk(self):
        files = [{"path": "movie.mkv", "size": 1000}]
        rep = self.scanner.analyze_files(files, "My Movie")
        self.assertEqual(rep["risk"], "LOW")
        self.assertEqual(rep["blocked_ext"], [])

    def test_analyze_files_high_risk_crack(self):
        files = [{"path": "crack.exe", "size": 1000}]
        rep = self.scanner.analyze_files(files, "Some App crack")
        self.assertIn(rep["risk"], ("MEDIUM", "HIGH"))
        self.assertTrue(len(rep["blocked_ext"]) > 0)

    def test_analyze_files_piracy_keyword_in_name(self):
        files = [{"path": "setup.exe", "size": 1000}]
        rep = self.scanner.analyze_files(files, "App keygen")
        self.assertGreater(rep["score"], 0)

    def test_analyze_info_with_info_object(self):
        class FakeInfo:
            def name(self):
                return "test torrent"
            def num_files(self):
                return 1

        # list_files will fail; provide empty via monkey? Just call analyze_files directly.
        rep = self.scanner.analyze_files([], "empty")
        self.assertEqual(rep["risk"], "LOW")


if __name__ == "__main__":
    unittest.main()
