from __future__ import annotations

import argparse
import json
from pathlib import Path

from fulltext_acquisition.config import DEFAULT_CDP_ENDPOINT
from fulltext_acquisition.service import AcquisitionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal metadata-to-fulltext acquisition for AI agents.")
    parser.add_argument("--metadata", help="Path to one PaperMetadata JSON object")
    parser.add_argument("--metadata-json", help="Inline PaperMetadata JSON object")
    parser.add_argument("--no-institution", action="store_true", help="Do not use the authorized Edge-CDP route")
    parser.add_argument("--check-session", action="store_true")
    parser.add_argument("--open-login", action="store_true")
    parser.add_argument("--login-url", help="Institution library/VPN URL to open for the one manual sign-in step")
    parser.add_argument("--institution-proxy-template", help="Optional proxy template containing {host_dash} and {path_query}")
    parser.add_argument("--cdp-endpoint", default=DEFAULT_CDP_ENDPOINT)
    args = parser.parse_args()
    service = AcquisitionService(cdp_endpoint=args.cdp_endpoint)
    if args.check_session:
        print(json.dumps(service.session_status(), ensure_ascii=False, indent=2)); return 0
    if args.open_login:
        print(json.dumps(service.open_login_browser(str(args.login_url or "")), ensure_ascii=False, indent=2)); return 0
    if not args.metadata and not args.metadata_json:
        parser.error("provide --metadata, --metadata-json, --check-session, or --open-login")
    try:
        payload = json.loads(args.metadata_json) if args.metadata_json else json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid_input", "message": f"Could not read one metadata JSON object: {type(exc).__name__}"}, ensure_ascii=False, indent=2))
        return 2
    if args.institution_proxy_template:
        payload["institution_proxy_template"] = args.institution_proxy_template
    result = service.acquire(payload, allow_institution=not args.no_institution)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "acquired" else 2


if __name__ == "__main__":
    raise SystemExit(main())
