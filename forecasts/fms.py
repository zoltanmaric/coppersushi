"""Authenticate File Library downloads with a private local account file."""
import argparse
import getpass
import json
import os
from pathlib import Path
import stat
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def access_token(credentials: Path) -> str:
    """Exchange a user-only credentials file for a token held in memory."""
    with credentials.open() as handle:
        info = os.fstat(handle.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("ENTSO-E credentials must be readable only by their owner")
        account = json.load(handle)
    return _sign_in(account["username"], account["password"])


def main() -> None:
    """Verify an interactive login before saving it for unattended collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("credentials", type=Path)
    args = parser.parse_args()
    path = args.credentials
    print(f"Save your ENTSO-E login for unattended use in {path} (owner-only local file).")
    username = input("ENTSO-E email: ").strip()
    password = getpass.getpass("ENTSO-E password (hidden): ")
    _sign_in(username, password)
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as handle:
        json.dump({"username": username, "password": password}, handle)
    print("Login verified and saved.")


def _sign_in(username: str, password: str) -> str:
    payload = urlencode({"client_id": "tp-fms-public", "grant_type": "password",
                         "username": username, "password": password}).encode()
    request = Request("https://keycloak.tp.entsoe.eu/realms/tp/protocol/openid-connect/token", data=payload)
    try:
        with urlopen(request, timeout=20) as response:
            token = json.load(response).get("access_token")
    except HTTPError as exc:
        raise RuntimeError(f"ENTSO-E File Library sign-in failed (HTTP {exc.code})") from None
    if not isinstance(token, str) or not token:
        raise ValueError("ENTSO-E File Library returned no access token")
    return token


if __name__ == "__main__":
    main()
