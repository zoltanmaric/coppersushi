"""Exercise the production Nginx cache policy against a disposable origin."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HOSTING = Path(__file__).parents[1]


class Origin(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        self.send_response(502 if path == "/error/" else 304 if path == "/not-modified/" else 200)
        if path != "/not-modified/":
            self.send_header("Content-Type", "text/css" if path == "/asset.css" else "application/json" if path == "/json/" else "text/html; charset=utf-8")
        self.send_header("Cache-Control", "private, max-age=0" if path == "/private-response/" else "public, no-store" if path == "/unsafe/" else "public, max-age=0")
        self.send_header("Vary", "Cookie" if path == "/vary/" else "Accept-Encoding")
        if path == "/sets-cookie/":
            self.send_header("Set-Cookie", "session=test; HttpOnly")
        if path == "/cdn-policy/":
            self.send_header("Cloudflare-CDN-Cache-Control", "private")
        self.end_headers()
        self.wfile.write(b"fixture")

    do_POST = do_GET

    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("nginx"), "Nginx integration needs the nginx executable")
class CacheHeadersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="ghost-cache-test-")
        root = Path(cls.folder.name)
        cls.origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        cls.thread = threading.Thread(target=cls.origin.serve_forever, daemon=True)
        cls.thread.start()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        maps = (HOSTING / "ansible/templates/ghost-cache.conf.j2").read_text()
        template = (HOSTING / "ansible/templates/nginx.conf.j2").read_text()
        excluded = root / "noindex-paths.conf"
        excluded.write_text('"/search-excluded/" "noindex";\n')
        maps += template.split("server {", 1)[0].replace("/etc/nginx/noindex-paths.conf", str(excluded))
        proxy = template.split("    location / {", 1)[1].rsplit("\n    }", 1)[0]
        proxy = proxy.replace("127.0.0.1:2368", f"127.0.0.1:{cls.origin.server_port}")
        config = root / "nginx.conf"
        config.write_text(f"pid {root}/nginx.pid;\nerror_log {root}/error.log;\nevents {{}}\nhttp {{ access_log off; {maps} server {{ listen 127.0.0.1:{cls.port}; location / {{{proxy} }} }} }}")
        cls.process = subprocess.Popen([shutil.which("nginx"), "-p", str(root), "-c", str(config), "-g", "daemon off;"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 5
        while True:
            if cls.process.poll() is not None:
                raise RuntimeError(cls.process.stderr.read().decode())
            try:
                urlopen(f"http://127.0.0.1:{cls.port}/", timeout=1).close()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.process.stderr.close()
        cls.origin.shutdown()
        cls.origin.server_close()
        cls.thread.join(timeout=2)
        cls.folder.cleanup()

    def request(self, path, headers=None, method="GET"):
        request = Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {}, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.headers

    def test_public_html_has_cdn_freshness_without_changing_browser_policy(self):
        headers = self.request("/")
        self.assertEqual(headers["Cloudflare-CDN-Cache-Control"], "public, max-age=300, stale-if-error=86400")
        self.assertEqual(headers["Cache-Tag"], "ghost-public-html")
        self.assertEqual(headers["Cache-Control"], "public, max-age=0")

    def test_noindex_header_coexists_with_public_cache_headers(self):
        headers = self.request("/search-excluded/")
        self.assertEqual(headers["X-Robots-Tag"], "noindex")
        self.assertEqual(headers["Cache-Tag"], "ghost-public-html")
        self.assertEqual(headers["Cloudflare-CDN-Cache-Control"], "public, max-age=300, stale-if-error=86400")
        self.assertIsNone(self.request("/")["X-Robots-Tag"])

    def test_not_modified_page_keeps_its_cdn_revalidation_policy(self):
        headers = self.request("/not-modified/")
        self.assertEqual(headers["Cloudflare-CDN-Cache-Control"], "public, max-age=300, stale-if-error=86400")
        self.assertEqual(headers["Cache-Tag"], "ghost-public-html")

    def test_sensitive_requests_and_responses_never_share_html(self):
        cases = [
            ("/ghost/", {}, "GET"), ("/members/", {}, "GET"),
            ("/p/secret/", {}, "GET"), ("/private/", {}, "GET"),
            ("/.ghost/", {}, "GET"), ("/?preview=true", {}, "GET"),
            ("/", {"Cookie": "ghost-members-ssr=example"}, "GET"),
            ("/", {"Cookie": "analytics=example"}, "GET"),
            ("/", {"Authorization": "Bearer example"}, "GET"),
            ("/", {}, "POST"), ("/sets-cookie/", {}, "GET"),
            ("/private-response/", {}, "GET"), ("/unsafe/", {}, "GET"),
            ("/cdn-policy/", {}, "GET"), ("/vary/", {}, "GET"),
            ("/error/", {}, "GET"), ("/json/", {}, "GET"),
        ]
        for path, request_headers, method in cases:
            with self.subTest(path=path, headers=request_headers, method=method):
                headers = self.request(path, request_headers, method)
                self.assertEqual(headers["Cloudflare-CDN-Cache-Control"], "no-store")
                self.assertIsNone(headers["Cache-Tag"])
                if path == "/sets-cookie/":
                    self.assertIn("session=test", headers["Set-Cookie"])

    def test_assets_keep_their_existing_cache_policy(self):
        for request_headers in [{}, {"Cookie": "analytics=example"}, {"Cookie": "ghost-members-ssr=example"}]:
            with self.subTest(headers=request_headers):
                headers = self.request("/asset.css?version=1", request_headers)
                self.assertIsNone(headers["Cloudflare-CDN-Cache-Control"])
                self.assertIsNone(headers["Cache-Tag"])


class NoindexProvisioningTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ansible-playbook"), "Needs the hosting Ansible environment")
    def test_reconfigure_creates_include_without_overwriting_existing_entries(self):
        import yaml

        site = yaml.safe_load((HOSTING / "ansible/site.yml").read_text())[0]
        task = next(task for task in site["tasks"] if task.get("ansible.builtin.copy", {}).get("dest") == "/etc/nginx/noindex-paths.conf")
        with tempfile.TemporaryDirectory(prefix="ghost-noindex-test-") as folder:
            target = Path(folder) / "noindex-paths.conf"
            task["ansible.builtin.copy"]["dest"] = str(target)
            playbook = Path(folder) / "playbook.yml"
            playbook.write_text(yaml.safe_dump([{"hosts": "localhost", "gather_facts": False, "tasks": [task]}]))
            command = [shutil.which("ansible-playbook"), "-i", "localhost,", "-c", "local", str(playbook)]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            self.assertEqual(target.read_text(), "")
            entries = '"/search-excluded.pdf" "noindex";\n'
            target.write_text(entries)
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            self.assertEqual(target.read_text(), entries)
