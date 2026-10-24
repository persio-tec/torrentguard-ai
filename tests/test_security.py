import hashlib
import os
import tempfile
import unittest

from core.security import SecurityManager


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # redirect CONFIG_DIR
        import core.security as sec
        self.orig_config_dir = sec.CONFIG_DIR
        sec.CONFIG_DIR = __import__("pathlib").Path(self.tmp)
        sec.KEY_FILE = sec.CONFIG_DIR / "security.key"
        sec.VAULT_FILE = sec.CONFIG_DIR / "vault.enc"
        sec.VIRUS_DB = sec.CONFIG_DIR / "virus_db.json"
        self.mgr = SecurityManager()

    def tearDown(self):
        import core.security as sec
        sec.CONFIG_DIR = self.orig_config_dir

    def test_sha256(self):
        p = os.path.join(self.tmp, "f.txt")
        with open(p, "wb") as f:
            f.write(b"abc")
        h = self.mgr.sha256(p)
        self.assertEqual(h, hashlib.sha256(b"abc").hexdigest())

    def test_sha256_missing(self):
        self.assertIsNone(self.mgr.sha256("/no/such/file"))

    def test_scan_file_clean(self):
        p = os.path.join(self.tmp, "readme.txt")
        with open(p, "wb") as f:
            f.write(b"hello")
        res = self.mgr.scan_file(p)
        self.assertTrue(res["safe"])

    def test_scan_file_suspicious_name(self):
        p = os.path.join(self.tmp, "crack.exe")
        with open(p, "wb") as f:
            f.write(b"x")
        res = self.mgr.scan_file(p)
        self.assertFalse(res["safe"])

    def test_encrypt_decrypt(self):
        enc = self.mgr.encrypt("segredo")
        self.assertEqual(self.mgr.decrypt(enc), "segredo")


if __name__ == "__main__":
    unittest.main()
