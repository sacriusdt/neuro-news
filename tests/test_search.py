import tempfile
import unittest

from neuro_news.db import connect, init_db
from neuro_news.search import SearchFilters, search_articles


class TestSearch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = tmp.name
        tmp.close()
        conn = connect(self.db_path)
        init_db(conn)
        conn.execute(
            "INSERT INTO feeds (title, url, category, country) VALUES (?, ?, ?, ?)",
            ("Gaming Feed", "http://example.com/rss", "Gaming", "United States"),
        )
        feed_id = conn.execute("SELECT id FROM feeds WHERE url=?", ("http://example.com/rss",)).fetchone()[0]
        conn.execute(
            "INSERT INTO feed_subcategories (feed_id, subcategory) VALUES (?, ?)",
            (feed_id, "Video Games"),
        )
        conn.execute(
            """
            INSERT INTO articles (feed_id, guid, url, title, summary, published_at, fetched_at, unique_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed_id,
                "guid-1",
                "http://example.com/article",
                "New gaming release",
                "A big gaming story",
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00",
                "key-1",
            ),
        )
        conn.commit()
        conn.close()

    def test_search_with_filters(self):
        filters = SearchFilters(
            categories=["Gaming"],
            subcategories=["Video Games"],
            countries=["Etats-Unis"],
        )
        results = search_articles(self.db_path, "gaming", filters, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["feed_title"], "Gaming Feed")


if __name__ == "__main__":
    unittest.main()
