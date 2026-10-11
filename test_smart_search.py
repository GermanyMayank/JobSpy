import unittest
from smart_search import assess_seniority, expand_queries, rank_jobs

class SmartSearchTests(unittest.TestCase):
    def test_solar_search_expands_across_languages(self):
        queries = expand_queries("Junior Project manager", "solar")
        self.assertIn("projektmanager Photovoltaik", queries)
        self.assertTrue(any("project coordinator" in q for q in queries))
        self.assertFalse(any("junior" in q.lower() for q in queries))

    def test_unknown_role_is_preserved(self):
        self.assertEqual(expand_queries("Acoustic consultant", ""), ["acoustic consultant"])

    def test_german_role_is_not_automatically_senior(self):
        self.assertFalse(assess_seniority("Projektleiter Photovoltaik", "", "Junior / entry level")[1])

    def test_experience_mismatch_is_detected(self):
        self.assertTrue(assess_seniority("Senior Project Manager", "", "Junior / entry level")[1])
        self.assertTrue(assess_seniority("Projektmanager", "Mindestens 5 Jahre Berufserfahrung", "Junior / entry level")[1])
        self.assertFalse(assess_seniority("Junior Project Manager", "", "Junior / entry level")[1])

    def test_empty_results_do_not_load_model(self):
        self.assertEqual(rank_jobs([], "Project manager", "solar", "Any"), ([], 0))

    def test_multilingual_meaning_and_seniority_with_real_model(self):
        jobs = [
            {"title": "Junior Projektkoordinator Photovoltaik", "description": "Koordination von Solarprojekten. Planung und Umsetzung von Photovoltaikanlagen und erneuerbaren Energien. Unterstützung der Projektleitung."},
            {"title": "Senior Project Manager Solar", "description": "Manage solar installations. At least 8 years experience required."},
            {"title": "Restaurant Manager", "description": "Manage a restaurant kitchen, serve customers, plan menus and recruit chefs."},
        ]
        ranked, hidden = rank_jobs(jobs, "Project manager", "solar energy", "Junior / entry level", True)
        self.assertEqual(hidden, 1)
        self.assertIn("Photovoltaik", ranked[0]["title"])
        self.assertIn(ranked[0]["evidence"], jobs[0]["description"])

if __name__ == "__main__":
    unittest.main()
