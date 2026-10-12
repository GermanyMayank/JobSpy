import json
import unittest
from unittest.mock import patch

import careers


FEED = b'''<workzag-jobs><position><id>12</id><name>Projektmanager Solar</name>
<office>Berlin</office><createdAt>2020-01-01</createdAt><jobDescriptions>
<jobDescription><name>Role</name><value>&lt;p&gt;Solar projects&lt;/p&gt;</value></jobDescription>
</jobDescriptions></position></workzag-jobs>'''


class CareerTests(unittest.TestCase):
    def setUp(self):
        self.db = careers.connect(':memory:')
        self.rows = careers.parse_feed(FEED, 'maxsolar', 'MaxSolar')

    def tearDown(self):
        self.db.close()

    def job(self):
        return self.db.execute('SELECT * FROM jobs WHERE company="maxsolar"').fetchone()

    def test_parse_preserves_date_uncertainty_and_plain_text(self):
        row = self.rows[0]
        self.assertIsNone(row['date_posted'])
        self.assertIsNone(row['is_remote'])
        self.assertEqual(row['source_created_at'], '2020-01-01')
        self.assertIn('Solar projects', row['description'])
        self.assertNotIn('<p>', row['description'])
        self.assertEqual(row['job_url'], 'https://maxsolar.jobs.personio.de/job/12')

    def test_invalid_snapshots_rejected(self):
        for data in (b'<html>blocked</html>', b'<workzag-jobs><error/></workzag-jobs>',
                     FEED.replace(b'<id>12</id>', b'<id></id>'),
                     b'<!DOCTYPE test><workzag-jobs/>',
                     FEED.replace(b'</workzag-jobs>', FEED.split(b'<workzag-jobs>')[1])):
            with self.subTest(data=data), self.assertRaises(ValueError):
                careers.parse_feed(data, 'maxsolar', 'MaxSolar')
        self.assertEqual(careers.parse_feed(b'<workzag-jobs/>', 'maxsolar', 'MaxSolar'), [])

    def test_refresh_idempotent_and_first_seen_preserved(self):
        careers.snapshot(self.db, 'maxsolar', self.rows, now=100)
        careers.snapshot(self.db, 'maxsolar', self.rows, now=200)
        self.assertEqual(self.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
        self.assertEqual(self.job()['first_seen'], 100)
        self.assertEqual(self.job()['last_seen'], 200)

    def test_failure_never_removes_or_marks_missing(self):
        careers.snapshot(self.db, 'maxsolar', self.rows, now=100)
        careers.snapshot(self.db, 'maxsolar', [], now=30000, error='timeout')
        self.assertEqual(self.job()['misses'], 0)
        self.assertEqual(self.job()['last_seen'], 100)

    def test_missing_requires_spaced_successes_and_reappearance_restores(self):
        careers.snapshot(self.db, 'maxsolar', self.rows, now=100)
        careers.snapshot(self.db, 'maxsolar', [], now=200)
        careers.snapshot(self.db, 'maxsolar', [], now=201)
        self.assertEqual(self.job()['misses'], 1)
        careers.snapshot(self.db, 'maxsolar', [], now=22000, error='blocked')
        self.assertEqual(self.job()['misses'], 1)
        careers.snapshot(self.db, 'maxsolar', [], now=44000)
        self.assertEqual(self.job()['misses'], 2)
        careers.snapshot(self.db, 'maxsolar', self.rows, now=45000)
        self.assertEqual(self.job()['misses'], 0)
        self.assertEqual(self.job()['first_seen'], 100)

    def test_identical_ids_across_companies_are_distinct(self):
        careers.snapshot(self.db, 'maxsolar', self.rows, now=100)
        careers.snapshot(self.db, 'wrs', self.rows, now=100)
        self.assertEqual(self.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 2)

    def test_location_requires_evidence(self):
        self.assertTrue(careers.location_matches('Berlin | Remote', 'Germany'))
        self.assertTrue(careers.location_matches('München', 'Munich, Germany'))
        self.assertTrue(careers.location_matches('Germany - Home Based', 'Germany'))
        self.assertFalse(careers.location_matches('Greece - Athens', 'Germany'))
        self.assertFalse(careers.location_matches('Remote', 'Germany'))
        self.assertFalse(careers.location_matches('Berlin', 'Hamburg'))

    def test_url_restriction(self):
        self.assertEqual(careers.company_id('https://maxsolar.jobs.personio.de/'), 'maxsolar')
        for url in ('http://maxsolar.jobs.personio.de', 'https://localhost',
                    'https://x.jobs.personio.de.evil.com', 'https://user@x.jobs.personio.de'):
            with self.assertRaises(ValueError):
                careers.company_id(url)

    def test_directory_has_unique_urls_and_seeds_only_supported_feeds(self):
        catalog = careers.directory()['companies']
        self.assertEqual(len({c['career_url'] for c in catalog}), len(catalog))
        seeded = {r[0] for r in self.db.execute('SELECT id FROM companies')}
        for company in catalog:
            self.assertTrue(company['relevance'])
            self.assertTrue(company['source_url'].startswith('https://'))
            if company['collection'] == 'personio':
                self.assertEqual(careers.company_id(company['career_url']), company['slug'])
                self.assertIn(company['slug'], seeded)
            elif company.get('slug'):
                self.assertNotIn(company['slug'], seeded)

    def test_directory_does_not_activate_manual_pages(self):
        with patch.object(careers, 'directory', return_value={'companies': [
            {'name': 'Test supported', 'slug': 'test-supported', 'collection': 'personio'},
            {'name': 'Test manual', 'slug': 'test-manual', 'collection': 'manual'}]}):
            db = careers.connect(':memory:')
            ids = {r[0] for r in db.execute('SELECT id FROM companies')}
            db.close()
        self.assertIn('test-supported', ids)
        self.assertNotIn('test-manual', ids)


if __name__ == '__main__':
    unittest.main()
