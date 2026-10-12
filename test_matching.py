import unittest
from unittest.mock import patch, Mock
from matching import expand_queries, rank_jobs, deduplicate, contains


class MatchingTests(unittest.TestCase):
    def test_arbeitsagentur_empty_response_is_not_failure(self):
        from sources import arbeitsagentur
        session = Mock()
        session.headers = {}
        session.get.return_value.json.return_value = {"maxErgebnisse": 0}
        with patch("requests.Session", return_value=session):
            self.assertEqual(arbeitsagentur("x", "Germany", 7, 20, False), ([], []))

    def test_expansion_includes_assistant_and_german_roles(self):
        queries = expand_queries("Junior project manager", "solar")
        self.assertEqual(len(queries), 6)
        self.assertTrue(any("Projektassistenz" in q for q in queries))
        self.assertFalse(any("renewable" in q for q in queries))

    def test_unrelated_title_does_not_win_over_german_match(self):
        rows = [{"title": "Restaurant manager", "description": "Solar panels on our restaurant"},
                {"title": "Projektkoordinator Photovoltaik", "description": "Solaranlagen"}]
        ranked, _ = rank_jobs(rows, "Project manager", "solar", "Any")
        self.assertEqual(ranked[0]["title"], rows[1]["title"])
        self.assertIn("Related role in title", ranked[0]["fit_note"])

    def test_senior_filter_keeps_unknown_and_junior(self):
        rows = [{"title": t} for t in ["Senior Project Manager", "Junior Project Manager", "Projektleiter"]]
        ranked, rejected = rank_jobs(rows, "Project manager", "", "Junior / entry level", True)
        self.assertEqual(rejected, 1)
        self.assertEqual(len(ranked), 2)

    def test_tracking_urls_merge_and_keep_sources(self):
        rows = [{"job_url": "https://example.com/job?id=1&utm_source=a", "site": "indeed"},
                {"job_url": "https://example.com/job?id=1&utm_source=b", "site": "linkedin", "description": "Details"}]
        result = deduplicate(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sources"], "indeed, linkedin")
        self.assertEqual(result[0]["description"], "Details")

    def test_identity_merge_preserves_distinct_locations(self):
        rows = [{"title": "Projektmanager", "company": "Example", "location": place, "job_url": "https://example.com/" + str(i)} for i, place in enumerate(["Berlin", "Berlin", "Hamburg"])]
        self.assertEqual(len(deduplicate(rows)), 2)
        self.assertEqual(len(deduplicate([{"title": "A"}, {"title": "A"}])), 2)

    def test_expired_and_remote_unknown_filters(self):
        rows = [{"title": "A", "date_posted": "2020-01-01", "is_remote": True},
                {"title": "B", "is_remote": None}, {"title": "C", "is_remote": True}]
        ranked, rejected = rank_jobs(rows, "C", "", "Any", days=7, remote=True)
        self.assertEqual([r["title"] for r in ranked], ["C"])
        self.assertEqual(rejected, 2)
        self.assertIn("Posting date unknown", ranked[0]["fit_note"])

    def test_skill_word_boundaries(self):
        self.assertFalse(contains("JavaScript", "Java"))
        self.assertTrue(contains("PV-Anlagen", "PV"))


if __name__ == "__main__":
    unittest.main()
