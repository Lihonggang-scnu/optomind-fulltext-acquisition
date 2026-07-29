# OptoMind Full-text Acquisition

**A local, agent-first bridge from paper metadata to traceable scholarly full text.**

Give it a DOI, PMCID, or publisher URL. It tries lawful open-access sources
first, then—only when you have already signed in—reuses your institution's
visible Microsoft Edge session for subscription content. Every result is
returned as JSON and saved with provenance.

> Built for research agents, literature pipelines, RAG preparation, and
> reproducible evidence workflows. No web form. No password harvesting. No
> shadow-library sources.

## Why this exists

Metadata APIs are excellent at telling an agent *that* a paper exists, but not
at delivering a usable, auditable full text. Publisher pages can be abstracts,
paywall previews, login screens, or real articles that require a university
proxy. This project makes those states explicit instead of silently treating
any long HTML page as a paper.

```text
paper metadata
  │
  ├─ lawful OA route ──► JATS / TEI ─► publisher HTML ─► OA PDF
  │
  └─ authorized route ─► one manual institutional sign-in in visible Edge
                          └─► reusable Edge-CDP session ─► publisher HTML / PDF
                                                               │
                                                               ▼
                                               normalized text + provenance.json
```

## Features

- **Agent-native contracts** — CLI and loopback JSON API return structured
  states such as `acquired`, `needs_login`, and `manual_follow_up`.
- **Machine-friendly first** — prefers JATS XML and TEI XML, then article HTML,
  then PDF with extracted text.
- **Two legal acquisition routes** — OA discovery via Unpaywall/OpenAlex; or
  subscription access through the user's already-authorized institution.
- **Reusable browser authority** — sign in once in a visible Edge window; the
  session is reused paper by paper without reading or storing credentials.
- **Fail closed** — PubMed metadata pages, subscription previews, CAPTCHA pages,
  and weak PDF parses are not reported as full text.
- **Traceability** — each accepted result includes source URL, access method,
  parser, metadata, and local paths in `provenance.json`.
- **Portable institution configuration** — users provide their own library/VPN
  login URL and, where needed, their documented proxy URL template.

## Install

Requires Python 3.11+ and Microsoft Edge on Windows for institutional access.

```powershell
git clone https://github.com/YOUR-ACCOUNT/optomind-fulltext-acquisition.git
cd optomind-fulltext-acquisition
py -3.11 -m pip install -r requirements.txt
py -3.11 -m playwright install chromium
```

`playwright install` is only needed when the local Playwright components are
missing. The institution workflow controls your normal visible Edge browser;
it does **not** automate login credentials.

## Quick start: CLI

Acquire an OA article from one metadata JSON object:

```powershell
py -3.11 cli.py --metadata examples\oa_nature_communications.json
```

Check whether an authorized Edge session is available:

```powershell
py -3.11 cli.py --check-session
```

For subscription content, start a visible browser at your own library/VPN
entry page, sign in manually, and keep it open:

```powershell
py -3.11 cli.py --open-login --login-url "https://library.example.edu/login"
```

Then run the same metadata request. If your institution uses a URL-rewriting
proxy, pass its documented template (or configure it locally):

```powershell
py -3.11 cli.py --metadata examples\subscription_nature.json `
  --institution-proxy-template "https://{host_dash}-s.proxy.example.edu{path_query}"
```

`{host_dash}` becomes a publisher hostname with dots replaced by hyphens;
`{path_query}` preserves the article path and query. Never guess a proxy
format—use the format documented by your own institution.

## Local JSON API

For an orchestrator or another local agent, run a loopback-only API:

```powershell
py -3.11 api_server.py --port 8874
```

Endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API and Edge-CDP session status |
| `POST` | `/open-login` | Open Edge at a user-provided library/VPN URL |
| `POST` | `/acquire` | Acquire one paper from a metadata JSON object |

Example payload:

```json
{
  "title": "Passive radiative cooling below ambient air temperature under direct sunlight",
  "doi": "10.1038/nature13883",
  "is_oa": false,
  "institution_proxy_template": "https://{host_dash}-s.proxy.example.edu{path_query}"
}
```

Example response shape:

```json
{
  "status": "acquired",
  "route": "institution_edge_cdp",
  "output": {
    "raw_file": ".../fulltext.html",
    "text_file": ".../fulltext.txt",
    "provenance": ".../provenance.json",
    "source_url": "https://...",
    "access_method": "institution_edge_cdp_html"
  }
}
```

The API binds to `127.0.0.1` by default. Do not expose a logged-in browser
session on a LAN or public interface.

## Output contract

Each successful acquisition receives a separate folder under
`workspace/downloads/<paper-id>/`:

```text
fulltext.xml | fulltext.html | fulltext.pdf
fulltext.txt
provenance.json
```

`provenance.json` records the selected candidate, final source URL, legal access
method, parser, timestamp, and input metadata. Agents should pass these paths
downstream rather than copying or redistributing publisher content.

## Statuses that agents should respect

| Status | Meaning | Safe next action |
| --- | --- | --- |
| `acquired` | A parseable full text was saved. | Consume `fulltext.txt` and provenance. |
| `needs_login` | No reusable authorized Edge session exists. | Request one manual institution sign-in. |
| `public_fulltext_not_found` | No parseable lawful public copy was found. | Enable the authorized route or request a legal file. |
| `manual_follow_up` | Access exists but needs a human click, renewal, or separate entitlement. | Save a legal file to `workspace/manual_fulltexts/`. |
| `invalid_input` | Metadata is missing or malformed. | Correct the request; do not retry blindly. |

## Local configuration and security

Optional local values are read from environment variables or ignored files in
`secrets/`:

```text
UNPAYWALL_EMAIL=you@example.edu
OPENALEX_API_KEYS=key-one,key-two
INSTITUTION_LOGIN_URL=https://library.example.edu/login
INSTITUTION_PROXY_TEMPLATE=https://{host_dash}-s.proxy.example.edu{path_query}
```

See [`secrets/README.md`](secrets/README.md). Never commit API keys,
institution credentials, browser cookies, local downloads, or a browser profile.
The repository's `.gitignore` excludes these paths by default.

## Tests

```powershell
py -3.11 -m pytest tests -q
py -3.11 cli.py --check-session
```

The unit tests are offline. For a live smoke test, use one OA record first and
download only content you are authorized to access.

## Scope and responsible use

This project is intentionally narrow: it retrieves lawfully available scholarly
content for local research workflows. It does not bypass paywalls, solve CAPTCHAs,
collect passwords, scrape at scale, or redistribute copyrighted full texts.
Always follow publisher terms and your institution's access policy.
