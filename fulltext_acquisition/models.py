from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PaperMetadata:
    title: str = ""
    doi: str = ""
    is_oa: bool | None = None
    pmcid: str = ""
    openalex_id: str = ""
    pdf_url: str = ""
    landing_page_url: str = ""
    publisher_url: str = ""
    jats_xml_url: str = ""
    tei_xml_url: str = ""
    source: str = "user_metadata"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "PaperMetadata":
        return cls(**{name: data.get(name, "") for name in cls.__dataclass_fields__})


@dataclass
class Candidate:
    url: str
    kind: str
    source: str
    priority: int
    requires_institution: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcquisitionResult:
    status: str
    route: str
    message: str
    metadata: dict[str, Any]
    attempts: list[dict[str, Any]] = field(default_factory=list)
    output: dict[str, str] = field(default_factory=dict)
    next_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
