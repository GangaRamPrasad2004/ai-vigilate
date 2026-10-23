import json
import pytest
from unittest.mock import patch, MagicMock

from agent.tools import (
    list_invoices,
    get_invoice,
    approve_invoice,
    escalate_invoice,
    trigger_kill_switch
)
from agent.guardrail import KillSwitchTriggeredError


def test_list_invoices_tool():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps([{"id": "INV-101", "vendor": "Acme"}])
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = list_invoices(status="pending")
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["id"] == "INV-101"


def test_get_invoice_tool():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps({"id": "INV-101", "amount": 4000.0})
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = get_invoice("INV-101")
        data = json.loads(result)
        assert data["id"] == "INV-101"
        assert data["amount"] == 4000.0


def test_approve_invoice_tool_calls_guardrail():
    # Simulate CRM returning invoice 101
    mock_inv = json.dumps({"id": "INV-101", "amount": 4000.0, "note": "Normal supplies"})

    with patch("agent.tools.get_invoice", return_value=mock_inv), \
         patch("agent.tools.decider_guardrail.verify_tool_call") as mock_verify, \
         patch("httpx.Client") as mock_http_cls:

        mock_verify.return_value = {"allowed": True, "action": "allow", "message": "OK"}

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps({"id": "INV-101", "status": "approved"})
        mock_http.post.return_value = mock_resp
        mock_http_cls.return_value.__enter__.return_value = mock_http

        res = approve_invoice(invoice_id="INV-101", session_id="test-sess", reason="Good")
        assert mock_verify.called
        assert "approved" in res


def test_approve_invoice_tool_blocked_by_guardrail():
    mock_inv = json.dumps({"id": "INV-102", "amount": 15000.0, "note": "High value"})

    with patch("agent.tools.get_invoice", return_value=mock_inv), \
         patch("agent.tools.decider_guardrail.verify_tool_call") as mock_verify:

        mock_verify.return_value = {
            "allowed": False,
            "action": "block",
            "message": "Exceeds $10,000 threshold"
        }

        res = approve_invoice(invoice_id="INV-102", session_id="test-sess", reason="Test")
        parsed = json.loads(res)
        assert parsed["status"] == "blocked"
        assert "Exceeds $10,000" in parsed["reason"]


def test_trigger_kill_switch_tool():
    with patch("agent.tools.decider_guardrail.trigger_kill_switch_in_ledger") as mock_kill, \
         patch("agent.tools.decider_guardrail.log_event_to_ledger"):

        res = trigger_kill_switch(session_id="test-sess", reason="Manual operator override")
        parsed = json.loads(res)
        assert parsed["status"] == "kill_switch_activated"
        assert mock_kill.called
