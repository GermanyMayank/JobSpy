import json
import unittest
from datetime import date
from unittest.mock import patch
import renewable_boards as b

FEED = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Projektmanager Solar</title><updated>2026-10-13</updated><link href="https://www.eejobs.de/angebote/index.html?id=1"/></entry></feed>'''


def page(**overrides):
    job = {'@type': 'JobPosting', 'title': 'Projektmanager Solar', 'description': '<p>Photovoltaik projects</p>',
           'hiringOrganization': {'name': 'Example'}, 'jobLocation': {'address': {'addressLocality': 'Berlin', 'addressCountry': 'DE'}}}
    job.update(overrides)
    return ('<script type="application/ld+json">' + json.dumps(job) + '</script>').encode()


class BoardTests(unittest.TestCase):
    def test_feed_rejects_bad_xml_and_foreign_links(self):
        for data in (b'<html/>', b'<!DOCTYPE feed><feed/>'):
            with self.assertRaises(ValueError): b.feed_links(data, 'eejobs')
        self.assertEqual(b.feed_links(FEED.replace(b'www.eejobs.de', b'evil.example'), 'eejobs'), [])

    def test_posting_date_not_inferred_from_feed_update(self):
        with patch.object(b, 'download', side_effect=[FEED, page()]):
            rows, _ = b.collect('eejobs', 'Project manager', 'Germany', 7, 20, False)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['date_posted'])
        self.assertEqual(rows[0]['description'], 'Photovoltaik projects')

    def test_foreign_expired_old_and_hybrid_excluded(self):
        for kwargs, remote in [({'jobLocation': {'address': {'addressLocality': 'Paris', 'addressCountry': 'FR'}}}, False),
                               ({'validThrough': '2000-01-01'}, False), ({'datePosted': '2000-01-01'}, False), ({}, True)]:
            with patch.object(b, 'download', side_effect=[FEED, page(**kwargs)]):
                rows, _ = b.collect('eejobs', 'Project manager', 'Germany', 7, 20, remote)
                self.assertEqual(rows, [])

    def test_detail_failure_is_not_empty_success(self):
        with patch.object(b, 'download', side_effect=[FEED, b'<html>blocked</html>']):
            with self.assertRaises(ValueError): b.collect('eejobs', 'Project manager', 'Germany', 7, 20, False)

    def test_energy_filter(self):
        self.assertFalse(b.energy_related(dict(title='Projektmanager Naturschutz', description='Wald und Wasser')))
        self.assertTrue(b.energy_related(dict(title='Projektmanager', description='Windparkentwicklung und Photovoltaik')))


if __name__ == '__main__':
    unittest.main()
