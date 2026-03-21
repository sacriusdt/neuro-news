import unittest

from neuro_news.ingest import build_unique_key, canonicalize_url


class TestDedup(unittest.TestCase):
    def test_canonicalize_url(self):
        self.assertEqual(
            canonicalize_url("HTTP://Example.com/path/?q=1#frag"),
            "http://example.com/path",
        )

    def test_unique_key_prefers_guid(self):
        key1 = build_unique_key("guid-1", "http://a.com", "Title", "2024-01-01")
        key2 = build_unique_key("guid-1", "http://b.com", "Other", "2024-02-01")
        self.assertEqual(key1, key2)


if __name__ == "__main__":
    unittest.main()
