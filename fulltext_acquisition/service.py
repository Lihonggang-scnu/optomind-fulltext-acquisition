"""Two legal routes: direct OA acquisition and a reusable Edge-CDP session."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .config import (
    BROWSER_PROFILE_DIR,
    DEFAULT_CDP_ENDPOINT,
    DEFAULT_LOGIN_URL,
    DOWNLOADS_DIR,
    MANUAL_DIR,
    institution_login_url,
    institution_proxy_templates,
    openalex_keys,
    prepare_workspace,
    unpaywall_email,
)
from .models import AcquisitionResult, Candidate, PaperMetadata


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
# Navigation bars often contain “Log in” even when an institution proxy has
# delivered the complete article.  Only hard access-denial signals belong here;
# subscription previews are detected separately from their page-level message.
BLOCKED = ("captcha", "access denied", "verify you are human", "unusual traffic")


def _safe_stem(metadata: PaperMetadata) -> str:
    basis = metadata.doi or metadata.title or "paper"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", basis).strip("_.")[:120] or "paper"


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in sorted(candidates, key=lambda x: x.priority):
        key = (candidate.url, candidate.kind)
        if candidate.url.startswith(("http://", "https://")) and key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def _html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for item in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        item.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def _article_like(text: str) -> bool:
    lowered = text.lower()
    if len(text) < 5000 or any(signal in lowered[:5000] for signal in BLOCKED):
        return False
    hits = sum(term in lowered for term in ("abstract", "introduction", "results", "methods", "discussion", "references"))
    return hits >= 2


def _is_metadata_or_abstract_page(final_url: str, text: str) -> bool:
    """Reject well-populated bibliographic pages that are not article full text.

    PubMed pages commonly contain an abstract, references, and enough boilerplate
    to pass a generic section-word heuristic.  They are useful discovery records,
    but must never be materialized as a downloaded full text.
    """
    host = (urllib.parse.urlparse(final_url).hostname or "").lower()
    if host in {"pubmed.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
        return True
    lowered = text.lower()
    return "pubmed disclaimer" in lowered and "full text links" in lowered


def _is_subscription_preview(text: str) -> bool:
    lowered = text.lower()
    return "preview of subscription content" in lowered or "access via your institution" in lowered


def _institution_proxy_url(url: str, template: str) -> str:
    """Map a publisher URL through a configured library proxy, never a metadata host."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    blocked_hosts = {"", "doi.org", "www.doi.org", "pubmed.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "api.openalex.org", "content.openalex.org"}
    if host in blocked_hosts:
        return ""
    path_query = parsed.path or "/"
    if parsed.query:
        path_query += "?" + parsed.query
    try:
        proxied = template.format(host_dash=host.replace(".", "-"), path_query=path_query)
    except (KeyError, ValueError):
        return ""
    return proxied if proxied.startswith(("http://", "https://")) else ""


def _public_document_links(html: str, base_url: str) -> list[str]:
    """Extract only explicit public document-looking links from an OA landing page."""
    soup = BeautifulSoup(html, "html.parser")
    raw: list[str] = []
    for meta in soup.find_all("meta"):
        if str(meta.get("name") or "").lower() in {"citation_pdf_url", "dc.identifier.pdf"}:
            raw.append(str(meta.get("content") or ""))
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        label = anchor.get_text(" ", strip=True).lower()
        if href.lower().split("?", 1)[0].endswith(".pdf") or "/download" in href.lower() or "download pdf" in label:
            raw.append(href)
    out: list[str] = []
    for value in raw:
        url = urllib.parse.urljoin(base_url, value)
        if url.startswith(("http://", "https://")) and url not in out:
            out.append(url)
    return out[:4]


class AcquisitionService:
    """State-free acquisition service; Edge session itself is the reusable state."""

    def __init__(self, *, cdp_endpoint: str = DEFAULT_CDP_ENDPOINT) -> None:
        prepare_workspace()
        self.cdp_endpoint = cdp_endpoint.rstrip("/")

    def session_status(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.cdp_endpoint}/json/version", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            return {
                "cdp_available": True,
                "endpoint": self.cdp_endpoint,
                "browser": payload.get("Browser", "Edge/Chrome CDP"),
                "message": "A reusable Edge-CDP session is available. Subscription articles can be processed one at a time.",
            }
        except Exception:
            return {
                "cdp_available": False,
                "endpoint": self.cdp_endpoint,
                "browser": "",
                "message": "No Edge-CDP session is running. Start the login browser, complete institution/publisher login once, then return here.",
            }

    def open_login_browser(self, login_url: str = DEFAULT_LOGIN_URL) -> dict[str, Any]:
        login_url = str(login_url or institution_login_url()).strip()
        if not login_url.startswith(("https://", "http://")):
            return {"ok": False, "message": "Provide your institution's HTTPS login or library-proxy URL before opening Edge."}
        edge_paths = [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ]
        edge = next((path for path in edge_paths if path.exists()), None)
        if edge is None:
            return {"ok": False, "message": "Microsoft Edge was not found. Start any Chromium browser with remote debugging on port 9222."}
        if self.session_status()["cdp_available"]:
            return {"ok": True, "already_running": True, "message": "Edge-CDP is already running; complete or refresh login in that visible browser."}
        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [str(edge), "--remote-debugging-port=9222", f"--user-data-dir={BROWSER_PROFILE_DIR}", "--new-window", login_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        for _ in range(20):
            if self.session_status()["cdp_available"]:
                return {"ok": True, "already_running": False, "message": "Edge opened. Complete login in the visible window and keep it open."}
            time.sleep(0.4)
        return {"ok": False, "message": "Edge was launched but its CDP endpoint did not become available. Check that no policy blocked remote debugging."}

    def candidates(self, metadata: PaperMetadata, *, proxy_templates: list[str] | None = None) -> list[Candidate]:
        rows: list[Candidate] = []
        add = lambda url, kind, source, priority, requires=False: rows.append(Candidate(str(url or "").strip(), kind, source, priority, requires))
        if metadata.jats_xml_url:
            add(metadata.jats_xml_url, "jats_xml", "metadata", 10)
        if metadata.pmcid:
            pmcid = re.sub(r"[^A-Za-z0-9]", "", metadata.pmcid).upper()
            if pmcid.startswith("PMC"):
                add(f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/?report=xml", "jats_xml", "pmc", 15)
        if metadata.tei_xml_url:
            add(metadata.tei_xml_url, "tei_xml", "metadata", 20)
        if metadata.publisher_url:
            add(metadata.publisher_url, "publisher_html", "metadata", 30, not bool(metadata.is_oa))
        if metadata.landing_page_url:
            add(metadata.landing_page_url, "publisher_html", "metadata", 35, not bool(metadata.is_oa))
        if metadata.doi and DOI_RE.match(metadata.doi):
            add(f"https://doi.org/{metadata.doi}", "publisher_html", "doi", 40, not bool(metadata.is_oa))
        if metadata.pdf_url:
            add(metadata.pdf_url, "pdf", "metadata", 50, False)
        rows.extend(self._oa_discovery(metadata))
        for template in proxy_templates if proxy_templates is not None else institution_proxy_templates():
            for candidate in list(rows):
                if candidate.kind not in {"publisher_html", "pdf"}:
                    continue
                proxied = _institution_proxy_url(candidate.url, template)
                if proxied:
                    rows.append(Candidate(proxied, candidate.kind, "institution_proxy", max(1, candidate.priority - 2), True))
        return _dedupe(rows)

    def _oa_discovery(self, metadata: PaperMetadata) -> list[Candidate]:
        rows: list[Candidate] = []
        if not metadata.doi or not DOI_RE.match(metadata.doi):
            return rows
        email = unpaywall_email()
        if email:
            url = "https://api.unpaywall.org/v2/" + urllib.parse.quote(metadata.doi, safe="") + "?" + urllib.parse.urlencode({"email": email})
            try:
                payload = self._json_get(url, timeout=12)
                if isinstance(payload.get("is_oa"), bool):
                    # A user checkbox is merely a hint; authoritative metadata
                    # must be allowed to correct it in either direction.
                    metadata.is_oa = bool(payload["is_oa"])
                locations = [payload.get("best_oa_location") or {}, *(payload.get("oa_locations") or [])]
                for index, location in enumerate(locations[:6]):
                    if not isinstance(location, dict):
                        continue
                    pdf = location.get("url_for_pdf") or ""
                    page = location.get("url") or ""
                    if pdf:
                        rows.append(Candidate(pdf, "pdf", "unpaywall", 60 + index))
                    if page:
                        rows.append(Candidate(page, "publisher_html", "unpaywall", 45 + index))
            except Exception:
                pass
        # OpenAlex metadata is public.  Cached content needs a local key, but
        # the request URL stored in results deliberately remains key-free.
        try:
            # The filter endpoint is more robust than the work-by-URL endpoint
            # for DOI suffixes containing punctuation or encoded characters.
            openalex_url = "https://api.openalex.org/works?" + urllib.parse.urlencode({"filter": f"doi:https://doi.org/{metadata.doi}", "per-page": 1})
            response = self._json_get(openalex_url, timeout=12)
            work = (response.get("results") or [{}])[0]
            if not work:
                raise LookupError("OpenAlex returned no work for DOI")
            metadata.openalex_id = metadata.openalex_id or str(work.get("id") or "").rsplit("/", 1)[-1]
            oa_value = (work.get("open_access") or {}).get("is_oa")
            if isinstance(oa_value, bool):
                metadata.is_oa = oa_value
            best = work.get("best_oa_location") or {}
            locations = [best, *(work.get("locations") or [])]
            for index, location in enumerate(locations[:6]):
                if not isinstance(location, dict):
                    continue
                if location.get("pdf_url"):
                    rows.append(Candidate(str(location["pdf_url"]), "pdf", "openalex", 70 + index))
                if location.get("landing_page_url"):
                    rows.append(Candidate(str(location["landing_page_url"]), "publisher_html", "openalex", 55 + index))
        except Exception:
            pass
        work_id = (metadata.openalex_id or "").rsplit("/", 1)[-1].upper()
        if re.match(r"^W\d+$", work_id) and openalex_keys() and metadata.is_oa:
            rows.append(Candidate(f"https://content.openalex.org/works/{work_id}.pdf", "pdf", "openalex_content", 75))
        return rows

    def acquire(self, raw_metadata: dict[str, Any], *, allow_institution: bool = True) -> dict[str, Any]:
        metadata = PaperMetadata.from_mapping(raw_metadata)
        if not metadata.title and not metadata.doi and not metadata.pdf_url and not metadata.landing_page_url:
            return AcquisitionResult("invalid_input", "none", "Provide at least a title, DOI, PDF URL, or landing page URL.", raw_metadata).to_dict()
        provided_template = str(raw_metadata.get("institution_proxy_template") or "").strip()
        templates = [provided_template] if "{host_dash}" in provided_template and "{path_query}" in provided_template else None
        candidates = self.candidates(metadata, proxy_templates=templates)
        attempts: list[dict[str, Any]] = []
        # First try only candidates that are reasonably public. A failed public
        # attempt is evidence to switch, not a reason to pretend it succeeded.
        for candidate in candidates:
            if candidate.requires_institution:
                continue
            result = self._download_public(metadata, candidate)
            attempts.append(result)
            if result.get("ok"):
                return AcquisitionResult("acquired", "oa_direct", "Legal public full text acquired.", metadata.__dict__, attempts, result["output"]).to_dict()
        if not allow_institution:
            return AcquisitionResult("public_fulltext_not_found", "oa_direct", "No parseable public full text was found. Institution route was disabled.", metadata.__dict__, attempts, next_action="Enable institution access or add a legal file to workspace/manual_fulltexts.").to_dict()
        session = self.session_status()
        if not session["cdp_available"]:
            prefix = "OA metadata was found, but every legal public candidate either blocked automated access or returned a landing/metadata page. " if metadata.is_oa else ""
            return AcquisitionResult("needs_login", "oa_then_institution" if metadata.is_oa else "institution", prefix + session["message"], metadata.__dict__, attempts, next_action="Click ‘Open login browser’, sign in manually, keep Edge open, then retry. The institution route is a fallback, not proof that the article is not OA.").to_dict()
        for candidate in candidates:
            result = self._download_via_edge(metadata, candidate)
            attempts.append(result)
            if result.get("ok"):
                return AcquisitionResult("acquired", "institution_edge_cdp", "Authorized institution/publisher full text acquired.", metadata.__dict__, attempts, result["output"]).to_dict()
        saw_preview = any("subscription preview" in str(item.get("reason") or "").lower() for item in attempts)
        message = "The institution session was active, but the publisher returned only a subscription preview." if saw_preview else "No usable full text was saved automatically. The page may require a human click, a renewed login, or have no eligible access."
        action = "Open the publisher through your library proxy, verify that the full article is visible, then retry; otherwise save the legal PDF/HTML manually into" if saw_preview else "Use the visible Edge browser to open the DOI/publisher page and save the legal PDF/HTML into"
        return AcquisitionResult("manual_follow_up", "institution", message, metadata.__dict__, attempts, next_action=f"{action} {MANUAL_DIR}.").to_dict()

    def _json_get(self, url: str, timeout: int) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "OptoMind-Fulltext-Acquisition/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _download_public(self, metadata: PaperMetadata, candidate: Candidate) -> dict[str, Any]:
        try:
            raw, content_type, final_url = self._request_bytes(candidate.url, openalex_auth=candidate.source == "openalex_content")
            result = self._materialize(metadata, candidate, raw, content_type, final_url, access_method=f"oa_direct:{candidate.source}")
            if result.get("ok") or candidate.kind != "publisher_html":
                return result
            # Repository pages often are metadata wrappers.  Follow only their
            # explicitly advertised PDF/download links; never guess URLs.
            for link in _public_document_links(raw.decode("utf-8", errors="replace"), final_url):
                linked = Candidate(link, "pdf", f"{candidate.source}_linked_document", candidate.priority + 1)
                try:
                    linked_raw, linked_type, linked_final = self._request_bytes(link)
                    linked_result = self._materialize(metadata, linked, linked_raw, linked_type, linked_final, access_method=f"oa_direct:{linked.source}")
                    if linked_result.get("ok"):
                        return linked_result
                except Exception:
                    continue
            return result
        except Exception as exc:
            return {"ok": False, "candidate": candidate.to_dict(), "reason": f"{type(exc).__name__}: {exc}"}

    def _request_bytes(self, url: str, *, openalex_auth: bool = False) -> tuple[bytes, str, str]:
        if openalex_auth:
            errors: list[str] = []
            for key in openalex_keys():
                parsed = urllib.parse.urlparse(url)
                query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)); query["api_key"] = key
                authenticated = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
                try:
                    return self._request_bytes(authenticated)
                except urllib.error.HTTPError as exc:
                    errors.append(str(exc.code))
                    if exc.code not in {401, 403, 429}:
                        break
            raise RuntimeError("OpenAlex content failed with configured keys: " + ",".join(errors[-3:]))
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; OptoMind-Fulltext-Acquisition/1.0)", "Accept": "application/pdf,text/html,application/xml,text/xml,*/*"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read(30_000_000), str(response.headers.get("Content-Type") or ""), str(response.geturl() or url)

    def _materialize(self, metadata: PaperMetadata, candidate: Candidate, raw: bytes, content_type: str, final_url: str, *, access_method: str) -> dict[str, Any]:
        stem = _safe_stem(metadata)
        target = DOWNLOADS_DIR / stem
        target.mkdir(parents=True, exist_ok=True)
        lower_type = content_type.lower()
        is_pdf = raw[:4] == b"%PDF" or "pdf" in lower_type or candidate.kind == "pdf" and raw[:4] == b"%PDF"
        if is_pdf:
            raw_path = target / "fulltext.pdf"; raw_path.write_bytes(raw)
            text, parser = self._pdf_text(raw)
            text_path = target / "fulltext.txt"; text_path.write_text(text, encoding="utf-8")
            status = "available" if len(text) >= 500 else "downloaded_pdf_needs_parsing"
            return self._write_result(metadata, candidate, final_url, access_method, status, raw_path, text_path, parser)
        text = raw.decode("utf-8", errors="replace")
        if candidate.kind in {"jats_xml", "tei_xml"} or "xml" in lower_type:
            if len(text) < 500 or "<" not in text[:200]:
                return {"ok": False, "candidate": candidate.to_dict(), "reason": "XML endpoint did not return article XML"}
            raw_path = target / "fulltext.xml"; raw_path.write_text(text, encoding="utf-8")
            extracted = _html_text(text)
            text_path = target / "fulltext.txt"; text_path.write_text(extracted, encoding="utf-8")
            return self._write_result(metadata, candidate, final_url, access_method, "available" if len(extracted) >= 500 else "downloaded_xml_needs_parsing", raw_path, text_path, "xml_text")
        extracted = _html_text(text)
        if _is_metadata_or_abstract_page(final_url, extracted):
            return {
                "ok": False,
                "candidate": candidate.to_dict(),
                "reason": "HTML response is a metadata/abstract page, not article full text",
            }
        if _is_subscription_preview(extracted):
            return {
                "ok": False,
                "candidate": candidate.to_dict(),
                "reason": "HTML response is a subscription preview, not authorized full text",
            }
        if not _article_like(extracted):
            return {"ok": False, "candidate": candidate.to_dict(), "reason": "HTML response is not a substantial article body"}
        raw_path = target / "fulltext.html"; raw_path.write_text(text, encoding="utf-8")
        text_path = target / "fulltext.txt"; text_path.write_text(extracted, encoding="utf-8")
        return self._write_result(metadata, candidate, final_url, access_method, "available", raw_path, text_path, "html_text")

    def _write_result(self, metadata: PaperMetadata, candidate: Candidate, final_url: str, access_method: str, status: str, raw_path: Path, text_path: Path, parser: str) -> dict[str, Any]:
        provenance = {"metadata": metadata.__dict__, "candidate": candidate.to_dict(), "source_url": final_url, "access_method": access_method, "status": status, "parser": parser, "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        provenance_path = raw_path.parent / "provenance.json"; provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": status == "available", "candidate": candidate.to_dict(), "reason": status, "output": {"raw_file": str(raw_path), "text_file": str(text_path), "provenance": str(provenance_path), "source_url": final_url, "access_method": access_method}}

    @staticmethod
    def _pdf_text(raw: bytes) -> tuple[str, str]:
        try:
            import fitz
            document = fitz.open(stream=raw, filetype="pdf")
            return "\n\n".join(page.get_text("text") for page in document), "pymupdf"
        except Exception:
            return "", "unparsed_pdf"

    def _download_via_edge(self, metadata: PaperMetadata, candidate: Candidate) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(self.cdp_endpoint)
                context = browser.contexts[0]
                if candidate.kind == "pdf":
                    response = context.request.get(candidate.url, timeout=60_000, headers={"Accept": "application/pdf,*/*"})
                    raw = response.body(); content_type = str(response.headers.get("content-type") or ""); final_url = response.url
                    return self._materialize(metadata, candidate, raw, content_type, final_url, access_method="institution_edge_cdp_pdf")
                page = context.new_page()
                try:
                    response = page.goto(candidate.url, wait_until="domcontentloaded", timeout=60_000)
                    try: page.wait_for_load_state("networkidle", timeout=8_000)
                    except Exception: pass
                    html = page.content(); final_url = page.url
                    content_type = str(response.headers.get("content-type") or "text/html") if response else "text/html"
                    return self._materialize(metadata, candidate, html.encode("utf-8", errors="replace"), content_type, final_url, access_method="institution_edge_cdp_html")
                finally:
                    page.close()
        except Exception as exc:
            return {"ok": False, "candidate": candidate.to_dict(), "reason": f"Edge-CDP: {type(exc).__name__}: {exc}"}
