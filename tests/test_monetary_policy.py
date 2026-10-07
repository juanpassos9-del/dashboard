from datetime import date

from execution.monetary_policy import build_monetary_policy_snapshot, fetch_copom_documents, next_copom_meeting


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_next_meeting_uses_official_decision_day():
    result = next_copom_meeting(date(2026, 10, 7))
    assert result["meeting_start"] == "2026-11-03"
    assert result["decision_date"] == "2026-11-04"
    assert "bcb.gov.br" in result["source_url"]


def test_fetch_copom_document_metadata_resolves_official_links(monkeypatch):
    def fake_get(url, **kwargs):
        if url.endswith("/principal"):
            payload = {"conteudo": [{"OutrasInformacoes": "<h3>A) Conjuntura</h3><p>Indicadores de preços e atividade.</p><h3>D) Decisão</h3><p>O Copom decidiu manter a Selic.</p>"}]}
        else:
            payload = {"conteudo": [{
                "DataReferencia": "2026-09-16T03:00:00Z",
                "Titulo": "281ª Reunião - 15-16 setembro, 2026",
                "Url": "/content/copom/atascopom/Ata_281_final.pdf",
                "LinkPagina": "/publicacoes/atascopom/16092026",
            }]}
        return FakeResponse(payload)

    monkeypatch.setattr("execution.monetary_policy.requests.get", fake_get)
    documents = fetch_copom_documents(limit=4)
    assert documents[0]["document_url"] == "https://www.bcb.gov.br/content/copom/atascopom/Ata_281_final.pdf"
    assert documents[0]["page_url"] == "https://www.bcb.gov.br/publicacoes/atascopom/16092026"
    assert documents[0]["sections"][0] == {"section": "Conjuntura", "excerpt": "Indicadores de preços e atividade."}
    assert documents[0]["sections"][1]["section"] == "Decisão"


def test_policy_snapshot_preserves_selic_focus_and_document_source():
    snapshot = build_monetary_policy_snapshot(
        selic={"value": 15.0},
        focus={"publish_date": "2026-10-05", "horizons": {"2026": {"IPCA": {"value": 4.3}}}},
        documents=[{"title": "Ata"}],
        today=date(2026, 10, 7),
    )
    assert snapshot["selic"]["value"] == 15.0
    assert snapshot["focus_horizons"]["2026"]["IPCA"]["value"] == 4.3
    assert snapshot["documents"][0]["title"] == "Ata"
