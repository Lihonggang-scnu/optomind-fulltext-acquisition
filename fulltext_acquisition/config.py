from __future__ import annotations

import os
import random
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / "secrets"
WORKSPACE = ROOT / "workspace"
DOWNLOADS_DIR = WORKSPACE / "downloads"
MANUAL_DIR = WORKSPACE / "manual_fulltexts"
BROWSER_PROFILE_DIR = WORKSPACE / "browser_profile"
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_LOGIN_URL = ""


def _values(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[\n,;]+", value or "") if x.strip()]


def _file_values(name: str) -> list[str]:
    path = SECRETS_DIR / name
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def unpaywall_email() -> str:
    return (os.getenv("UNPAYWALL_EMAIL") or os.getenv("CONTACT_EMAIL") or (_file_values("unpaywall_email.txt") or [""])[0]).strip()


def openalex_keys() -> list[str]:
    candidates = _values(os.getenv("OPENALEX_API_KEYS") or os.getenv("OPENALEX_API_KEY") or "") + _file_values("openalex.txt")
    unique = list(dict.fromkeys(candidates))
    random.SystemRandom().shuffle(unique)
    return unique


def institution_login_url() -> str:
    """Read a local institution entry URL; it is configuration, never credentials."""
    return (os.getenv("INSTITUTION_LOGIN_URL") or (_file_values("institution_login_url.txt") or [DEFAULT_LOGIN_URL])[0]).strip()


def institution_proxy_templates() -> list[str]:
    """Read local, user-configured library proxy URL templates.

    A template must contain ``{host_dash}`` and ``{path_query}``.  Example:
    ``https://{host_dash}-s.libvpn.example.edu:20080{path_query}``.
    """
    values = _values(os.getenv("INSTITUTION_PROXY_TEMPLATE") or "") + _file_values("institution_proxy_templates.txt")
    return list(dict.fromkeys(value for value in values if "{host_dash}" in value and "{path_query}" in value))


def prepare_workspace() -> None:
    for path in (SECRETS_DIR, DOWNLOADS_DIR, MANUAL_DIR, BROWSER_PROFILE_DIR):
        path.mkdir(parents=True, exist_ok=True)
