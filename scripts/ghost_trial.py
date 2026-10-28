"""Run an isolated, local Ghost preview using the imported theme and public OPF app."""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/ghost-trial"
COMPOSE = ROOT / "121gigawatts/local/compose.yml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down"])
    args = parser.parse_args()
    port = int(os.environ.get("GHOST_TRIAL_PORT", "2378"))
    if not 1024 <= port <= 65535:
        parser.error("GHOST_TRIAL_PORT must be between 1024 and 65535")
    origin = f"http://localhost:{port}"
    project = "coppersushi-ghost-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
    environment = {**os.environ, "COPPERSUSHI_ROOT": str(ROOT), "GHOST_TRIAL_PORT": str(port)}
    command = ["docker", "compose", "-p", project, "-f", str(COMPOSE)]
    if args.action == "down":
        subprocess.run([*command, "down"], env=environment, check=True)
        return
    for directory in [STATE / "content/data", STATE / "content/settings", STATE / "content/themes/121gigawatts"]:
        directory.mkdir(parents=True, exist_ok=True)
    theme = STATE / "content/themes/121gigawatts"
    shutil.rmtree(theme)
    with ZipFile(ROOT / "121gigawatts/dist/121gigawatts.zip") as archive:
        archive.extractall(theme)
    shutil.copyfile(ROOT / "121gigawatts/local/routes.yaml", STATE / "content/settings/routes.yaml")
    subprocess.run([*command, "up", "-d", "--force-recreate"], env=environment, check=True)
    client = Client(origin)
    deadline = time.monotonic() + 120
    while True:
        try:
            setup = client.request("GET", "authentication/setup/")
            break
        except (URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise RuntimeError("Local Ghost did not start within 120 seconds; inspect docker compose logs") from None
            time.sleep(2)
    credentials = STATE / "owner.json"
    if not setup["setup"][0]["status"]:
        if not credentials.exists():
            descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"username": "preview@example.invalid", "password": secrets.token_urlsafe(32)}, stream)
        owner = json.loads(credentials.read_text())
        client.request("POST", "authentication/setup/", {"setup": [{
            "name": "Local Preview", "email": owner["username"], "password": owner["password"],
            "blogTitle": "1.21 Gigawatts",
        }]})
    if not credentials.exists():
        raise RuntimeError("This local database has an owner but no trial credentials; refusing to change it")
    client.request("POST", "session/", json.loads(credentials.read_text()))
    client.request("PUT", "themes/121gigawatts/activate/", {})
    settings = {
        "title": "1.21 Gigawatts", "description": "Electricity systems, explored.",
        "navigation": json.dumps([{"label": "Writing", "url": "/"}, {"label": "Projects", "url": "/projects/"}]),
        "members_signup_access": "none",
    }
    client.request("PUT", "settings/", {"settings": [{"key": k, "value": v} for k, v in settings.items()]})
    client.request("PUT", "custom_theme_settings/", {"custom_theme_settings": [{"key": "show_projects", "value": True}]})
    for slug, title in [("projects", "Projects"), ("power-flow", "Copper Sushi — European power flow")]:
        existing = client.request("GET", f"pages/?filter=slug:{slug}")["pages"]
        if not existing:
            client.request("POST", "pages/?source=html", {"pages": [{
                "title": title, "slug": slug, "status": "published", "html": "<p>Explore electricity systems.</p>",
            }]})
    if not client.request("GET", "posts/?filter=slug:power-flow-models")["posts"]:
        client.request("POST", "posts/?source=html", {"posts": [{
            "title": "What can a power-flow model tell us?", "slug": "power-flow-models",
            "status": "published", "feature_image": f"{origin}/assets/images/w2000/Gigawatts.jpg",
            "custom_excerpt": "A map is a way into the choices, constraints and trade-offs behind an electricity system.",
            "html": "<p>Electricity follows the network. A power-flow model helps us explore how generation, demand and transmission interact.</p><p><a href='/projects/power-flow/'>Explore the European grid with Copper Sushi.</a></p>",
        }]})
    print(f"Ghost preview: {origin}/", flush=True)
    print(f"Project page: {origin}/projects/power-flow/", flush=True)
    print("Local sample content only. Stop with: pixi run ghost-trial-stop", flush=True)


class Client:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        request = Request(
            self.origin + "/ghost/api/admin/" + endpoint,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "Origin": self.origin, "Accept-Version": "v6.0"},
            method=method,
        )
        with self.opener.open(request, timeout=10) as response:
            body = response.read()
            return json.loads(body) if body and "application/json" in response.headers.get("Content-Type", "") else {}


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        raise SystemExit(f"Local Ghost API returned HTTP {error.code} for {error.url}") from None
