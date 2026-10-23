import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from services.crm.main import app
from services.crm.data import reset_invoices_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_crm():
    """Reset the CRM in-memory DB before each test."""
    reset_invoices_db()


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_invoices():
    response = client.get("/api/invoices")
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) == 3
    assert invoices[0]["id"] == "INV-101"

    # Test filter by status
    pending_resp = client.get("/api/invoices?status=pending")
    assert pending_resp.status_code == 200
    assert len(pending_resp.json()) == 3


def test_get_single_invoice():
    response = client.get("/api/invoices/INV-101")
    assert response.status_code == 200
    data = response.json()
    assert data["vendor"] == "Acme Supplies"
    assert data["amount"] == 4000.0

    # 404 test
    not_found = client.get("/api/invoices/INV-999")
    assert not_found.status_code == 404


@patch("services.crm.main.check_ledger_kill_switch", new_callable=AsyncMock)
def test_approve_invoice_success(mock_kill_check):
    mock_kill_check.return_value = False

    payload = {
        "actor": "test-agent",
        "session_id": "sess-test-1",
        "reason": "Within approved limits"
    }
    response = client.post("/api/invoices/INV-101/approve", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    # Second approval attempt should return 409 Conflict
    conflict_resp = client.post("/api/invoices/INV-101/approve", json=payload)
    assert conflict_resp.status_code == 409


@patch("services.crm.main.check_ledger_kill_switch", new_callable=AsyncMock)
def test_approve_invoice_rejected_when_kill_switch_active(mock_kill_check):
    # Simulate systemic kill switch tripped in Go Ledger
    mock_kill_check.return_value = True

    payload = {
        "actor": "test-agent",
        "session_id": "sess-test-2",
        "reason": "Attempting approval while system is compromised"
    }
    response = client.post("/api/invoices/INV-101/approve", json=payload)
    assert response.status_code == 423  # Locked
    err_body = response.json()
    assert err_body["detail"]["error"] == "kill_switch_active"


def test_escalate_invoice_success():
    payload = {
        "actor": "test-agent",
        "session_id": "sess-test-3",
        "reason": "Amount exceeds threshold, supervisor review requested"
    }
    response = client.post("/api/invoices/INV-102/escalate", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"


def test_session_state_endpoint():
    resp = client.get("/api/session/sess-12345/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-12345"
    assert data["active"] is True
