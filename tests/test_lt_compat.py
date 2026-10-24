import unittest

from core.lt_compat import has_metadata, torrent_name, list_files


class FakeInfoV1:
    def file_at(self, i):
        class E:
            path = "a.txt"
            size = 10
        return E()
    def num_files(self):
        return 1
    def name(self):
        return "torrent1"


class FakeHandle:
    def __init__(self, info=None, has_meta=True):
        self._info = info
        self._has_meta = has_meta
    def has_metadata(self):
        return self._has_meta
    def get_torrent_info(self):
        return self._info
    def status(self):
        class S:
            name = "fromstatus"
            has_metadata = True
        return S()


class LtCompatTests(unittest.TestCase):
    def test_has_metadata_true(self):
        h = FakeHandle(has_meta=True)
        self.assertTrue(has_metadata(h))

    def test_has_metadata_none(self):
        self.assertFalse(has_metadata(None))

    def test_torrent_name_from_info(self):
        info = FakeInfoV1()
        h = FakeHandle(info=info)
        self.assertEqual(torrent_name(h, info), "torrent1")

    def test_list_files_v1(self):
        info = FakeInfoV1()
        self.assertEqual(list_files(info), [("a.txt", 10)])

    def test_list_files_none(self):
        self.assertEqual(list_files(None), [])


if __name__ == "__main__":
    unittest.main()
