from __future__ import annotations

from fulltext_acquisition.models import PaperMetadata
from fulltext_acquisition.service import AcquisitionService, _institution_proxy_url, _is_metadata_or_abstract_page, _is_subscription_preview, _public_document_links


def test_candidate_order_prefers_machine_friendly_formats(monkeypatch) -> None:
    service = AcquisitionService(cdp_endpoint="http://127.0.0.1:9")
    monkeypatch.setattr(service, "_oa_discovery", lambda _meta: [])
    rows = service.candidates(PaperMetadata(title="test", is_oa=True, jats_xml_url="https://example.org/a.xml", tei_xml_url="https://example.org/a.tei.xml", publisher_url="https://example.org/a", pdf_url="https://example.org/a.pdf"), proxy_templates=[])
    assert [row.kind for row in rows] == ["jats_xml", "tei_xml", "publisher_html", "pdf"]


def test_no_cdp_session_is_explicit() -> None:
    status = AcquisitionService(cdp_endpoint="http://127.0.0.1:9").session_status()
    assert status["cdp_available"] is False
    assert "No Edge-CDP session" in status["message"]


def test_invalid_metadata_fails_closed() -> None:
    result = AcquisitionService(cdp_endpoint="http://127.0.0.1:9").acquire({}, allow_institution=False)
    assert result["status"] == "invalid_input"


def test_repository_page_pdf_discovery_uses_explicit_links_only() -> None:
    links = _public_document_links('<meta name="citation_pdf_url" content="/paper.pdf"><a href="/download/record">Download PDF</a>', "https://repository.example/item/1")
    assert links == ["https://repository.example/paper.pdf", "https://repository.example/download/record"]


def test_pubmed_abstract_page_is_never_accepted_as_fulltext() -> None:
    text = "Abstract " + ("article content " * 600) + " Full text links PubMed Disclaimer References"
    assert _is_metadata_or_abstract_page("https://pubmed.ncbi.nlm.nih.gov/25428501/", text) is True


def test_subscription_preview_is_not_authorized_fulltext() -> None:
    assert _is_subscription_preview("This is a preview of subscription content. Access via your institution.") is True


def test_navigation_login_text_does_not_reject_a_real_article_body() -> None:
    from fulltext_acquisition.service import _article_like

    article = "Log in " + ("Introduction Methods Results Discussion References detailed scientific content. " * 100)
    assert _article_like(article) is True


def test_institution_proxy_only_maps_publisher_hosts() -> None:
    template = "https://{host_dash}-s.libvpn.example.edu:20080{path_query}"
    assert _institution_proxy_url("https://www.nature.com/articles/nature13883", template) == "https://www-nature-com-s.libvpn.example.edu:20080/articles/nature13883"
    assert _institution_proxy_url("https://doi.org/10.1038/nature13883", template) == ""
