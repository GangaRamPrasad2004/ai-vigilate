import json
import pytest
from pathlib import Path

from knowledge.vendor_risk import VendorRiskKnowledgeBase, text_to_vector
from knowledge.rag_tools import query_vendor_history, enrich_context_with_vendor_history
from agent.nim_tools import extract_invoice_from_image


def test_text_to_vector_dimension():
    vec = text_to_vector("Acme Supplies Office Supplies")
    assert len(vec) == 64
    assert any(x != 0.0 for x in vec)


def test_qdrant_vendor_knowledge_base():
    kb = VendorRiskKnowledgeBase(in_memory=True)
    
    # Query known high risk vendor
    results = kb.search_vendor_history("Initech Systems", limit=1)
    assert len(results) > 0
    assert results[0]["vendor"] == "Initech Systems"
    assert results[0]["risk_level"] == "CRITICAL_HIGH"
    assert "prompt injection" in results[0]["historical_profile"].lower()

    # Query low risk vendor
    results_acme = kb.search_vendor_history("Acme Supplies", limit=1)
    assert len(results_acme) > 0
    assert results_acme[0]["vendor"] == "Acme Supplies"
    assert results_acme[0]["risk_level"] == "LOW"


def test_query_vendor_history_tool():
    res_str = query_vendor_history("Initech Systems")
    data = json.loads(res_str)
    assert data["vendor"] == "Initech Systems"
    assert data["risk_level"] == "CRITICAL_HIGH"
    assert "BLOCKED & QUARANTINED" in data["past_audit_verdict"]


def test_enrich_context_with_vendor_history():
    ctx = {
        "invoice_data": {
            "id": "INV-103",
            "vendor": "Initech Systems",
            "amount": 50000.0
        }
    }
    enriched = enrich_context_with_vendor_history(ctx)
    assert "vendor_historical_risk" in enriched
    assert enriched["vendor_historical_risk"]["risk_level"] == "CRITICAL_HIGH"


def test_nim_vision_extraction_tool():
    # Test fallback extraction with mock path
    res_str = extract_invoice_from_image("mock_invoices/INV-101.png")
    data = json.loads(res_str)
    assert data["invoice_id"] == "INV-101"
    assert data["amount"] == 4000.0
    assert "NVIDIA NIM" in data["hardware_acceleration"]

    # Test INV-103 containing injection memo
    res_str_103 = extract_invoice_from_image("mock_invoices/INV-103.jpg")
    data_103 = json.loads(res_str_103)
    assert data_103["invoice_id"] == "INV-103"
    assert "Ignore all previous policies" in data_103["notes"]


def test_openshell_toml_syntax_valid():
    """Validates that sandbox/openshell.toml is syntactically valid TOML."""
    toml_path = Path(__file__).parent.parent / "sandbox" / "openshell.toml"
    assert toml_path.exists()

    try:
        import tomllib  # Python 3.11+ standard library
    except ImportError:
        import tomli as tomllib

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    assert "sandbox" in data
    assert "network" in data
    assert "filesystem" in data
    assert data["network"]["default_egress"] == "deny"
    assert any("8000" in egress["destination"] for egress in data["network"]["allow_egress"])
    assert any("8081" in egress["destination"] for egress in data["network"]["allow_egress"])
