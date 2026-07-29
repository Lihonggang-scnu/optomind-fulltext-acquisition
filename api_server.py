"""Local JSON API for agent-to-agent full-text acquisition.

This server deliberately serves no browser UI.  It binds to loopback by default
and exposes only JSON endpoints so an orchestrator, MCP wrapper, or local agent
can use the same acquisition engine as the command line interface.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from fulltext_acquisition.config import DEFAULT_CDP_ENDPOINT
from fulltext_acquisition.service import AcquisitionService


class ApiHandler(BaseHTTPRequestHandler):
    service: AcquisitionService

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"ok": True, "service": "fulltext-acquisition", "session": self.service.session_status()})
            return
        self._send_json({"error": "not_found", "available": ["GET /health", "POST /acquire", "POST /open-login"]}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self._send_json({"status": "invalid_input", "message": "Request body must be one UTF-8 JSON object."}, 400)
            return
        if not isinstance(payload, dict):
            self._send_json({"status": "invalid_input", "message": "Request body must be one JSON object."}, 400)
            return
        if path == "/open-login":
            self._send_json(self.service.open_login_browser(str(payload.get("login_url") or "")))
            return
        if path == "/acquire":
            self._send_json(self.service.acquire(payload, allow_institution=bool(payload.get("allow_institution", True))))
            return
        self._send_json({"error": "not_found", "available": ["GET /health", "POST /acquire", "POST /open-login"]}, 404)

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep metadata and request payloads out of terminal logs by default."""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the loopback JSON API for legal full-text acquisition.")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback by default; do not expose a logged-in browser session to a network.")
    parser.add_argument("--port", type=int, default=8874)
    parser.add_argument("--cdp-endpoint", default=DEFAULT_CDP_ENDPOINT)
    args = parser.parse_args()
    ApiHandler.service = AcquisitionService(cdp_endpoint=args.cdp_endpoint)
    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(json.dumps({"ok": True, "listen": f"http://{args.host}:{args.port}", "endpoints": ["GET /health", "POST /acquire", "POST /open-login"]}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
