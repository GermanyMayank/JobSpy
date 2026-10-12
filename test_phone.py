import json
import threading
import unittest
from unittest.mock import patch

import requests
import phone_server as phone


class PhoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = phone.PhoneServer(('127.0.0.1', 0), 'test-key-for-unit-tests-only')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.headers = {'X-JobSpy-Key': cls.server.token}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_api_requires_pairing_but_shell_loads(self):
        self.assertEqual(requests.get(self.url, timeout=3).status_code, 200)
        self.assertEqual(requests.get(self.url+'/api/companies', timeout=3).status_code, 401)
        self.assertEqual(requests.get(self.url+'/api/state', headers=self.headers, timeout=3).status_code, 200)

    def test_cross_origin_and_rebinding_rejected(self):
        for extra in ({'Origin': 'http://untrusted.example'}, {'Host': 'untrusted.example'}):
            r = requests.post(self.url+'/api/refresh', headers=self.headers | extra, json={}, timeout=3)
            self.assertEqual(r.status_code, 403)
        r = requests.options(self.url+'/api/refresh', timeout=3)
        self.assertNotIn('Access-Control-Allow-Origin', r.headers)

    def test_local_files_not_exposed(self):
        for path in ('/output/phone-access.json', '/company_directory.json', '/.git/config', '/output/careers.sqlite3'):
            self.assertEqual(requests.get(self.url+path, headers=self.headers, timeout=3).status_code, 404)

    def test_invalid_search_rejected_before_start(self):
        for data in ({'count': 500}, {'days': True}, {'role': ''}, {'site': 'arbitrary'}, {'remote': 'false'}):
            with patch.object(self.server.tasks, 'start') as start:
                r = requests.post(self.url+'/api/search', headers=self.headers, json=data, timeout=3)
                self.assertEqual(r.status_code, 400)
                start.assert_not_called()

    def test_single_task_and_argument_list(self):
        with patch.object(self.server.tasks, 'start', return_value=False):
            self.assertEqual(requests.post(self.url+'/api/search', headers=self.headers, json={}, timeout=3).status_code, 409)
        cmd = phone.search_command({'role': 'Project manager; echo unsafe'})
        self.assertIn('Project manager; echo unsafe', cmd)
        self.assertIn('--hide-mismatch', cmd)
        self.assertNotIn('--remote', cmd)

    def test_unsupported_company_rejected(self):
        r = requests.post(self.url+'/api/add-company', headers=self.headers,
                          json={'name': 'test', 'url': 'https://localhost/'}, timeout=3)
        self.assertEqual(r.status_code, 400)

    def test_request_limits_and_non_object(self):
        for data in ('[]', 'x'*4097):
            r = requests.post(self.url+'/api/search', headers=self.headers | {'Content-Type': 'application/json'}, data=data, timeout=3)
            self.assertEqual(r.status_code, 400)


if __name__ == '__main__':
    unittest.main()
