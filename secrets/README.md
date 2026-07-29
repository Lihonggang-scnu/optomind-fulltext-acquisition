# Local configuration (never commit this directory)

The application works without secrets when explicit public URLs are supplied.
The following optional local files improve discovery and institutional routing:

| File | One value per line | Purpose |
| --- | --- | --- |
| `unpaywall_email.txt` | contact email | legal DOI-to-OA-location lookup |
| `openalex.txt` | OpenAlex API key | OpenAlex cached-PDF retrieval; keys rotate on 401/403/429 |
| `institution_login_url.txt` | library/VPN login URL | opened in visible Edge for the one manual sign-in |
| `institution_proxy_templates.txt` | proxy template | uses `{host_dash}` and `{path_query}` |

Environment variables take precedence:

```text
UNPAYWALL_EMAIL=you@example.edu
OPENALEX_API_KEYS=key-one,key-two
INSTITUTION_LOGIN_URL=https://library.example.edu/login
INSTITUTION_PROXY_TEMPLATE=https://{host_dash}-s.proxy.example.edu{path_query}
```

A proxy template is a route description, not a password. Obtain its exact
format from your institution; do not guess one. For example:

```text
https://{host_dash}-s.proxy.example.edu:20080{path_query}
```

Never put university usernames, passwords, browser cookies, Qwen keys, or
publisher credentials in this directory. Before publishing, remove every local
`.txt` file except this README. The Git ignore rules protect against accidental
commits, but they are not a substitute for checking `git status`.
