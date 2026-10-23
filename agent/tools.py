import json
import logging
from typing import Optional
import httpx

try:
    from .config import settings
    from .policies import durable_policy
    from .guardrail import decider_guardrail, KillSwitchTriggeredError
    from .nim_tools import extract_invoice_from_image
except ImportError:
    from agent.config import settings
    from agent.policies import durable_policy
    from agent.guardrail import decider_guardrail, KillSwitchTriggeredError
    from agent.nim_tools import extract_invoice_from_image

try:
    from knowledge.rag_tools import query_vendor_history, enrich_context_with_vendor_history
except ImportError:
    try:
        from ..knowledge.rag_tools import query_vendor_history, enrich_context_with_vendor_history
    except Exception:
        def query_vendor_history(vendor_name: str) -> str:
            return json.dumps({"vendor": vendor_name, "risk_level": "UNKNOWN"})
        def enrich_context_with_vendor_history(ctx, v=None):
            return ctx

logger = logging.getLogger("agent-tools")


def list_invoices(status: str = "pending") -> str:
    """
    Retrieves invoices from the enterprise CRM filtered by status.
    Read-only operation: does not require guardrail intervention.
    """
    url = f"{settings.CRM_BASE_URL.rstrip('/')}/api/invoices"
    params = {}
    if status:
        params["status"] = status

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp.text
            return json.dumps({"error": f"CRM returned {resp.status_code}", "detail": resp.text})
    except Exception as exc:
        return json.dumps({"error": "crm_unreachable", "detail": str(exc)})


def get_invoice(invoice_id: str) -> str:
    """
    Retrieves full details for a specific invoice from CRM.
    Read-only operation.
    """
    url = f"{settings.CRM_BASE_URL.rstrip('/')}/api/invoices/{invoice_id}"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.text
            return json.dumps({"error": f"Invoice {invoice_id} not found", "status_code": resp.status_code})
    except Exception as exc:
        return json.dumps({"error": "crm_unreachable", "detail": str(exc)})


def approve_invoice(
    invoice_id: str,
    session_id: str,
    reason: str,
    user_request: Optional[str] = None
) -> str:
    """
    Approves an invoice in the enterprise CRM.
    Zero-Trust Guardrail: Every invocation is pre-verified by Strands Decider 2B.
    """
    # 1. Fetch current invoice context
    raw_inv = get_invoice(invoice_id)
    try:
        inv_data = json.loads(raw_inv)
    except Exception:
        inv_data = {"id": invoice_id, "amount": 0.0, "note": ""}

    # 2. Build Guardrail verification context and enrich with Qdrant vendor risk knowledge
    context = {
        "user_request": user_request or "Approve invoices under $10,000 per policy.",
        "invoice_data": inv_data,
        "session_id": session_id,
        "proposed_action": "approve"
    }
    context = enrich_context_with_vendor_history(context, inv_data.get("vendor"))

    tool_args = {
        "invoice_id": invoice_id,
        "session_id": session_id,
        "reason": reason
    }

    # 3. Strands Decider 2B Guardrail evaluation
    logger.info(f"[GUARDRAIL CHECK] Evaluating proposed tool call: approve_invoice({invoice_id}) with Qdrant historical risk context")
    verification = decider_guardrail.verify_tool_call(
        tool_name="approve_invoice",
        tool_arguments=tool_args,
        context=context
    )

    if not verification.get("allowed", False):
        action = verification.get("action", "block")
        msg = verification.get("message", "Approval blocked by policy")
        logger.warning(f"[GUARDRAIL BLOCKED] approve_invoice({invoice_id}) -> {msg}")
        return json.dumps({
            "status": "blocked",
            "action": action,
            "invoice_id": invoice_id,
            "reason": msg
        })

    # 4. If allowed, execute CRM state mutation
    url = f"{settings.CRM_BASE_URL.rstrip('/')}/api/invoices/{invoice_id}/approve"
    payload = {
        "actor": "strands-sentinel-agent",
        "session_id": session_id,
        "reason": reason
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"[CRM SUCCESS] Invoice {invoice_id} approved.")
                return resp.text
            elif resp.status_code == 423:
                logger.critical(f"[CRM LOCKED] Invoice {invoice_id} rejected because kill switch is active.")
                return resp.text
            return json.dumps({"error": f"CRM error {resp.status_code}", "detail": resp.text})
    except Exception as exc:
        return json.dumps({"error": "crm_call_failed", "detail": str(exc)})


def escalate_invoice(
    invoice_id: str,
    session_id: str,
    reason: str,
    user_request: Optional[str] = None
) -> str:
    """
    Escalates an invoice for human supervisor review.
    Lower operational risk than approval, but still logged and verified.
    """
    raw_inv = get_invoice(invoice_id)
    try:
        inv_data = json.loads(raw_inv)
    except Exception:
        inv_data = {"id": invoice_id, "amount": 0.0, "note": ""}

    context = {
        "user_request": user_request or "Escalate invoices above $10,000 to human supervisor.",
        "invoice_data": inv_data,
        "session_id": session_id,
        "proposed_action": "escalate"
    }
    tool_args = {
        "invoice_id": invoice_id,
        "session_id": session_id,
        "reason": reason
    }

    # Verify no critical prompt injection is hiding in escalation payload
    note = str(inv_data.get("note", "")).lower()
    if any(p.lower() in note for p in durable_policy.forbidden_phrases):
        logger.warning(f"[GUARDRAIL ALERT] Prompt injection detected during escalation inspection: {invoice_id}")
        # Let guardrail evaluate and trip kill switch if warranted
        decider_guardrail.verify_tool_call(
            tool_name="escalate_invoice",
            tool_arguments=tool_args,
            context=context
        )

    url = f"{settings.CRM_BASE_URL.rstrip('/')}/api/invoices/{invoice_id}/escalate"
    payload = {
        "actor": "strands-sentinel-agent",
        "session_id": session_id,
        "reason": reason
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"[CRM ESCALATED] Invoice {invoice_id} successfully escalated.")
                # Log audit event
                decider_guardrail.log_event_to_ledger(
                    session_id=session_id,
                    tool_name="escalate_invoice",
                    decision="escalate",
                    confidence=1.0,
                    latency_ms=0.5,
                    details=f"Invoice {invoice_id} escalated: {reason}"
                )
                return resp.text
            return json.dumps({"error": f"CRM error {resp.status_code}", "detail": resp.text})
    except Exception as exc:
        return json.dumps({"error": "crm_call_failed", "detail": str(exc)})


def trigger_kill_switch(session_id: str, reason: str) -> str:
    """
    Explicitly triggers the systemic kill switch in the Go audit ledger.
    """
    logger.critical(f"[EXPLICIT KILL SWITCH] Session {session_id}: {reason}")
    decider_guardrail.trigger_kill_switch_in_ledger(session_id=session_id, reason=reason)
    decider_guardrail.log_event_to_ledger(
        session_id=session_id,
        tool_name="trigger_kill_switch",
        decision="kill",
        confidence=1.0,
        latency_ms=1.0,
        details=f"Systemic kill switch tripped: {reason}"
    )
    return json.dumps({
        "status": "kill_switch_activated",
        "session_id": session_id,
        "reason": reason
    })


# Export tool catalogue (including Pillar 4 Qdrant and Pillar 5 NVIDIA NIM tools)
ALL_TOOLS = [
    list_invoices,
    get_invoice,
    approve_invoice,
    escalate_invoice,
    trigger_kill_switch,
    query_vendor_history,
    extract_invoice_from_image
]
