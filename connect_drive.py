"""Authorize this copier with Google using an OAuth desktop-client JSON file.

The user's explicit consent is collected in Google's browser page. Tokens remain
in .local/rclone.conf; no existing calendar token is read or changed.
"""
import argparse
import configparser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import tempfile
import os
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def connect(client_file):
    document = json.loads(Path(client_file).read_text(encoding="utf-8-sig"))
    client = document.get("installed")
    if not client:
        raise ValueError("Choose a Google OAuth desktop-client JSON file.")
    state = secrets.token_urlsafe(32)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if query.get("state", [""])[0] != state:
                self.send_error(400, "Invalid OAuth state")
                return
            if "code" in query:
                result["code"] = query["code"][0]
            else:
                result["error"] = query.get("error", ["Authorization declined"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Google sign-in received. You can close this tab and return to Parallel Copy.")

        def log_message(self, *_):
            pass  # Authorization codes must never be logged.

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/"
        query = urllib.parse.urlencode({"client_id": client["client_id"],
            "redirect_uri": redirect, "response_type": "code", "state": state,
            "scope": "https://www.googleapis.com/auth/drive",
            "access_type": "offline", "prompt": "consent"})
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + query
        webbrowser.open(url)
        print("Google sign-in opened. Waiting for your consent (up to 10 minutes).", flush=True)
        import time
        deadline = time.monotonic() + 600
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if "code" not in result:
        raise RuntimeError(result.get("error", "Google sign-in timed out"))
    body = urllib.parse.urlencode({"client_id": client["client_id"],
        "client_secret": client["client_secret"], "code": result["code"],
        "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    request = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)
    expiry = datetime.now(timezone.utc) + timedelta(seconds=token["expires_in"])
    config = configparser.ConfigParser(interpolation=None)
    path = ROOT / ".local" / "rclone.conf"
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        config.read(path, encoding="utf-8")
    config["gdrive"] = {"type": "drive", "client_id": client["client_id"],
        "client_secret": client["client_secret"], "scope": "drive",
        "token": json.dumps({"access_token": token["access_token"],
            "token_type": token["token_type"], "refresh_token": token["refresh_token"],
            "expiry": expiry.isoformat()})}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="oauth-", delete=False) as handle:
            temporary = Path(handle.name)
            config.write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    print("Connected. Direct Drive transfers are ready; credentials saved locally only.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", help="OAuth desktop-client JSON path")
    connect(parser.parse_args().client)
