"""Authenticated, local-network phone interface. No cloud service or open file server."""
import argparse
import contextlib
import csv
import html
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'output'
SITES = ('Combined', 'Company careers', 'indeed', 'linkedin', 'arbeitsagentur', 'glassdoor')
LEVELS = ('Any', 'Junior / entry level', 'Mid-level', 'Senior')
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def search_command(data):
    def field(name, default, limit=160):
        value = data.get(name, default)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f'Check {name}.')
        return value.strip()
    role, location = field('role', 'Project manager'), field('location', 'Germany')
    site, level = field('site', 'Company careers'), field('seniority', 'Junior / entry level')
    if site not in SITES or level not in LEVELS:
        raise ValueError('Choose a valid source and seniority.')
    industry = data.get('industry', '')
    if not isinstance(industry, str) or len(industry) > 160:
        raise ValueError('Industry must be at most 160 characters.')
    values = []
    for name in ('days', 'count'):
        value = data.get(name, 7 if name == 'days' else 30)
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError('Days and results must be whole numbers from 1 to 100.')
        values.extend(['--' + name, str(value)])
    for name in ('remote', 'hide_mismatch'):
        if name in data and type(data[name]) is not bool:
            raise ValueError('Invalid checkbox value.')
    cmd = [sys.executable, str(ROOT / 'desktop_search.py'), '--search', '--role', role,
           '--location', location, '--site', site, '--seniority', level, '--industry', industry] + values
    if data.get('remote'):
        cmd.append('--remote')
    if data.get('hide_mismatch', True):
        cmd.append('--hide-mismatch')
    return cmd


def latest():
    try:
        data = json.loads((OUTPUT / 'latest.json').read_text(encoding='utf-8'))
        path = Path(data['csv']).resolve()
        if path.parent != OUTPUT.resolve() or not path.name.startswith('jobs-') or path.suffix != '.csv':
            return None
        with path.open(encoding='utf-8-sig', newline='') as file:
            rows = list(csv.DictReader(file))[:100]
        return {k: data.get(k) for k in ('count', 'role', 'location', 'warnings', 'coverage')} | {'jobs': rows}
    except (OSError, ValueError, KeyError):
        return None


def companies():
    import careers
    with contextlib.closing(careers.connect()) as db:
        states = {r['id']: dict(r) for r in db.execute('SELECT * FROM companies')}
    result = []
    known = set()
    for c in careers.directory()['companies']:
        item = dict(c)
        item['scan'] = states.get(c.get('slug'))
        known.add(c.get('slug'))
        result.append(item)
    for slug, state in states.items():
        if slug not in known:
            result.append(dict(name=state['name'], category='Added by you', relevance='', collection='personio',
                               career_url=f'https://{slug}.jobs.personio.de/', scan=state))
    return sorted(result, key=lambda c: c['name'].casefold())


class Tasks:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.running = False
        self.cancelled = False
        self.message = 'Ready. Company searches use your saved feeds.'

    def state(self):
        with self.lock:
            return dict(running=self.running, message=self.message)

    def start(self, cmd, label):
        with self.lock:
            if self.running:
                return False
            self.running, self.cancelled = True, False
            self.message = label
        threading.Thread(target=self._run, args=(cmd, label), daemon=True).start()
        return True

    @staticmethod
    def kill(proc):
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, creationflags=FLAGS)
        else:
            proc.kill()

    def cancel(self):
        with self.lock:
            self.cancelled = True
            proc = self.proc
        if proc and proc.poll() is None:
            self.kill(proc)

    def _run(self, cmd, label):
        message = 'Task failed. Previous results are preserved. See output/phone-worker.log on the PC.'
        try:
            with (OUTPUT / 'phone-worker.log').open('w', encoding='utf-8') as log:
                with self.lock:
                    if self.cancelled:
                        return
                    self.proc = proc = subprocess.Popen(cmd, stdout=log, stderr=log, cwd=ROOT, creationflags=FLAGS)
                try:
                    code = proc.wait(timeout=360)
                    if code == 0:
                        message = 'Search complete.' if '--search' in cmd else 'Company check complete. See each company’s scan status.'
                except subprocess.TimeoutExpired:
                    self.kill(proc)
                    proc.wait(timeout=10)
                    message = 'Stopped after six minutes. Completed company scans and previous results are preserved.'
        except Exception:
            pass
        finally:
            with self.lock:
                self.message = 'Stopped. Saved results are still available.' if self.cancelled else message
                self.running, self.proc = False, None


class PhoneServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token):
        self.token = token
        self.tasks = Tasks()
        super().__init__(address, Handler)
        host, port = self.server_address
        self.hosts = {f'{host}:{port}'}
        if host == '127.0.0.1':
            self.hosts.add(f'localhost:{port}')


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Never log access keys or request headers.

    def reply(self, data, code=200, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=True).encode() if mime.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if self.headers.get('Host') not in self.server.hosts:
            self.reply({'error': 'Unrecognised address.'}, 403)
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.reply({'error': 'Use the address shown on your PC.'}, 403)
            return False
        return True

    def authorised(self):
        key = self.headers.get('X-JobSpy-Key', '')
        if not secrets.compare_digest(key.encode(), self.server.token.encode()):
            self.reply({'error': 'Scan the QR code on your PC to connect.'}, 401)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path
        files = {'/': ('phone.html', 'text/html; charset=utf-8'),
                 '/phone.css': ('phone.css', 'text/css; charset=utf-8'),
                 '/phone.js': ('phone.js', 'text/javascript; charset=utf-8')}
        if path in files:
            name, mime = files[path]
            self.reply((ROOT / name).read_bytes(), mime=mime)
            return
        if not self.authorised():
            return
        if path == '/api/state':
            self.reply(self.server.tasks.state())
        elif path == '/api/results':
            self.reply(latest())
        elif path == '/api/companies':
            self.reply(companies())
        else:
            self.reply({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self.allowed() or not self.authorised():
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'):
                raise ValueError('Invalid request size.')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Expected JSON.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected an object.')
            path = urlsplit(self.path).path
            if path == '/api/search':
                cmd, label = search_command(data), 'Searching… Job boards can take up to six minutes.'
            elif path == '/api/refresh':
                cmd, label = [sys.executable, str(ROOT / 'careers.py')], 'Checking company feeds…'
            elif path == '/api/add-company':
                import careers
                url, name = data.get('url'), data.get('name')
                if not isinstance(url, str) or len(url) > 250 or not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                    raise ValueError('Enter a company name and supported career URL.')
                careers.company_id(url)
                cmd = [sys.executable, str(ROOT / 'careers.py'), '--add-url', url, '--name', name.strip()]
                label = 'Verifying and adding the company…'
            elif path == '/api/cancel':
                self.server.tasks.cancel()
                self.reply({'ok': True})
                return
            else:
                self.reply({'error': 'Not found'}, 404)
                return
            if not self.server.tasks.start(cmd, label):
                self.reply({'error': 'A task is already running. Wait or stop it first.'}, 409)
                return
            self.reply({'ok': True}, 202)
        except (ValueError, TypeError, UnicodeError) as exc:
            self.reply({'error': str(exc)}, 400)


def lan_address():
    # Routing lookup selects the active LAN interface without sending traffic.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1', 9))
            address = sock.getsockname()[0]
        except OSError:
            address = '127.0.0.1'
    return address


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default=lan_address())
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if address.version != 4 or not address.is_private or address.is_unspecified:
        parser.error('Choose a local IPv4 address; public hosting is not supported.')
    OUTPUT.mkdir(exist_ok=True)
    config = OUTPUT / 'phone-access.json'
    try:
        token = json.loads(config.read_text())['key']
        if not isinstance(token, str) or len(token) < 24:
            raise ValueError('Invalid key')
    except (OSError, ValueError, KeyError):
        token = secrets.token_urlsafe(24)
        config.write_text(json.dumps({'key': token}), encoding='utf-8')
    start_page = OUTPUT / 'phone-start.html'
    try:
        server = PhoneServer((args.host, args.port), token)
    except OSError:
        # Reopening the launcher reopens an existing instance only if its key matches.
        import requests
        try:
            r = requests.get(f'http://{args.host}:{args.port}/api/state', headers={'X-JobSpy-Key': token}, timeout=2)
            if r.status_code == 200 and start_page.exists():
                if not args.no_open:
                    webbrowser.open(start_page.as_uri())
                return
        except requests.RequestException:
            pass
        raise
    url = f'http://{args.host}:{server.server_port}/#key={token}'
    import qrcode
    from qrcode.image.svg import SvgPathImage
    qr = qrcode.make(url, image_factory=SvgPathImage)
    qr.save(str(OUTPUT / 'phone-qr.svg'))
    from qrcode.image.pil import PilImage
    qrcode.make(url, image_factory=PilImage).save(str(OUTPUT / 'phone-qr.png'))
    start_page.write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Connect your phone — JobSpy</title><style>body{font:18px system-ui;max-width:620px;margin:40px auto;padding:20px;background:#f3f6fb;color:#14243a}img{width:300px;max-width:100%;background:white}a{overflow-wrap:anywhere}li{margin:12px 0}</style>'
        '<h1>Your jobs, on your phone</h1><ol><li>Keep this PC on and connect your phone to the same Wi-Fi.</li>'
        '<li>Scan this QR code with your phone camera.</li></ol><img src="phone-qr.svg" alt="Scan to open JobSpy">'
        f'<p><a href="{html.escape(url, quote=True)}">Open JobSpy on this PC</a></p><p>Phone address: http://{args.host}:{server.server_port}/</p>'
        f'<p>If needed, enter this access key: <code>{html.escape(token)}</code></p>'
        '<p>If the phone cannot connect, run <strong>Allow Phone Access.cmd</strong> once on this PC and accept the Windows administrator prompt. Guest Wi-Fi may block connections between devices.</p>'
        '<p>This link gives access to your local searches. Keep it private. Access works on your local network while the server is running; no internet publishing is enabled.</p>'
        '<p>Use <strong>Stop Phone Access.cmd</strong> to stop access, or close the server window if you opened the launcher.</p>', encoding='utf-8')
    (OUTPUT / 'phone-server.json').write_text(json.dumps({'host': args.host, 'port': server.server_port, 'pid': os.getpid()}), encoding='utf-8')
    if not args.no_open:
        webbrowser.open(start_page.as_uri())
    print(f'JobSpy phone access: http://{args.host}:{server.server_port}/ — pairing QR: {start_page}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.tasks.cancel()
        server.server_close()


if __name__ == '__main__':
    main()
