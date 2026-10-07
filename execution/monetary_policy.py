"""Official Copom schedule and publication metadata for Monitor BR."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup


BCB_BASE = "https://www.bcb.gov.br"
COPOM_DOCUMENTS_URL = f"{BCB_BASE}/api/servico/sitebcb/atascopom/ultimas"
COPOM_MINUTES_DETAIL_URL = f"{BCB_BASE}/api/servico/sitebcb/atascopom/principal"
COPOM_CALENDAR_SOURCES = {
    2026: "https://www.bcb.gov.br/detalhenoticia/20739/nota/https%3A/www3.bcb.gov.br/sgspub",
    2027: "https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=45452&tipo=Comunicado",
}
COPOM_MEETING_DATES = {
    2026: ((1, 27, 28), (3, 17, 18), (4, 28, 29), (6, 16, 17), (8, 4, 5), (9, 15, 16), (11, 3, 4), (12, 8, 9)),
    2027: ((1, 26, 27), (3, 16, 17), (4, 27, 28), (6, 15, 16), (8, 3, 4), (9, 21, 22), (10, 26, 27), (12, 7, 8)),
}


def next_copom_meeting(today: date | None = None) -> dict[str, Any] | None:
    today = today or date.today()
    meetings = []
    for year, entries in COPOM_MEETING_DATES.items():
        for month, first_day, decision_day in entries:
            first = date(year, month, first_day)
            decision = date(year, month, decision_day)
            if decision >= today:
                meetings.append({
                    "meeting_start": first.isoformat(),
                    "decision_date": decision.isoformat(),
                    "source": f"Calendário oficial do BCB para {year}",
                    "source_url": COPOM_CALENDAR_SOURCES[year],
                })
    return min(meetings, key=lambda item: item["decision_date"]) if meetings else None


def fetch_copom_documents(limit: int = 6, timeout: int = 15) -> list[dict[str, Any]]:
    response = requests.get(
        COPOM_DOCUMENTS_URL,
        params={"quantidade": max(1, min(int(limit), 20)), "filtro": ""},
        timeout=timeout,
        headers={"User-Agent": "TradingStrategyDashboard/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    documents = []
    for item in payload.get("conteudo", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        url = item.get("Url") or item.get("LinkPagina")
        if not url:
            continue
        documents.append({
            "title": str(item.get("Titulo") or "Ata do Copom"),
            "published_at": str(item.get("DataReferencia") or "")[:10],
            "document_url": url if str(url).startswith("http") else BCB_BASE + str(url),
            "page_url": BCB_BASE + str(item.get("LinkPagina")) if item.get("LinkPagina") else None,
            "source": "Banco Central do Brasil · atas do Copom",
        })
    for document in documents[:2]:
        page_path = str(document.get("page_url") or "").rstrip("/").split("/")[-1]
        if len(page_path) != 8 or not page_path.isdigit():
            continue
        try:
            detail = requests.get(
                COPOM_MINUTES_DETAIL_URL,
                params={"filtro": f"IdentificadorUrl eq '{page_path}'"},
                timeout=timeout,
                headers={"User-Agent": "TradingStrategyDashboard/1.0"},
            )
            detail.raise_for_status()
            detail_data = detail.json()
            content = (detail_data.get("conteudo") or [{}])[0].get("OutrasInformacoes", "")
            document["sections"] = _extract_minutes_sections(content)
        except Exception as exc:
            document["text_error"] = f"{type(exc).__name__}: {exc}"
    return documents


def _extract_minutes_sections(content: str, max_chars: int = 420) -> list[dict[str, str]]:
    soup = BeautifulSoup(content or "", "html.parser")
    labels = {
        "a)": "Conjuntura",
        "b)": "Cenários e riscos",
        "c)": "Condução da política monetária",
        "d)": "Decisão",
    }
    sections: list[dict[str, str]] = []
    current_label = None
    current_paragraphs: list[str] = []

    def flush() -> None:
        if current_label and current_paragraphs:
            excerpt = " ".join(current_paragraphs)
            sections.append({"section": current_label, "excerpt": excerpt[:max_chars].rstrip() + ("…" if len(excerpt) > max_chars else "")})

    for node in soup.select("h1, h2, h3, h4, p"):
        text = " ".join(node.get_text(" ", strip=True).split())
        if not text:
            continue
        if node.name.startswith("h"):
            flush()
            current_paragraphs = []
            heading = text.casefold().strip()
            current_label = next((label for prefix, label in labels.items() if heading.startswith(prefix)), None)
        elif current_label and len(current_paragraphs) < 2:
            current_paragraphs.append(text)
    flush()
    return sections


def build_monetary_policy_snapshot(
    selic: dict[str, Any] | None = None,
    focus: dict[str, Any] | None = None,
    documents: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    focus = focus if isinstance(focus, dict) else {}
    return {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "selic": selic or {},
        "focus_horizons": focus.get("horizons", {}),
        "focus_publish_date": focus.get("publish_date"),
        "next_meeting": next_copom_meeting(today),
        "documents": documents or [],
        "sources": {
            "policy_rate": "Banco Central · SGS 432",
            "expectations": "Banco Central · Boletim Focus",
            "documents": "Banco Central · API de atas do Copom",
        },
    }
