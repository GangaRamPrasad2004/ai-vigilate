import os
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from .models import Invoice, ActionRequest, SessionStateResponse
from .data import invoices_db, reset_invoices_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("crm-service")

LEDGER_BASE_URL = os.getenv("LEDGER_BASE_URL", "http://localhost:8081")
CRM_PORT = int(os.getenv("CRM_PORT", "8000"))

app = FastAPI(
    title="Strands Sentinel Legacy CRM Service",
    description="Mock enterprise invoice management system with kill-switch integration",
    version="1.0.0"
)

# Volatile session storage demonstrating state isolation
session_storage = {}


async def check_ledger_kill_switch() -> bool:
    """Queries Go Ledger service to see if global kill switch is tripped."""
    url = f"{LEDGER_BASE_URL.rstrip('/')}/kill"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return bool(data.get("killed", False))
            logger.warning(f"Ledger /kill returned unexpected status: {resp.status_code}")
    except Exception as exc:
        logger.warning(f"Unable to reach Go Ledger service at {url}: {exc}. Defaulting to safe state.")
    return False


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Generates a clean HTML dashboard showing current invoice statuses and kill-switch status."""
    is_killed = await check_ledger_kill_switch()
    kill_badge = (
        '<span style="background-color: #ef4444; color: white; padding: 4px 12px; border-radius: 9999px; font-weight: bold;">ACTIVATED (BLOCKED)</span>'
        if is_killed else
        '<span style="background-color: #10b981; color: white; padding: 4px 12px; border-radius: 9999px; font-weight: bold;">DISARMED (NORMAL)</span>'
    )

    rows = ""
    for inv in invoices_db.values():
        if inv.status == "approved":
            status_style = "background-color: #d1fae5; color: #065f46;"
        elif inv.status == "escalated":
            status_style = "background-color: #fef3c7; color: #92400e;"
        else:
            status_style = "background-color: #e5e7eb; color: #374151;"

        rows += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding: 12px; font-family: monospace; font-weight: bold;">{inv.id}</td>
            <td style="padding: 12px;">{inv.vendor}</td>
            <td style="padding: 12px; font-weight: 600;">${inv.amount:,.2f}</td>
            <td style="padding: 12px;">
                <span style="{status_style} padding: 4px 10px; border-radius: 6px; font-size: 0.85em; font-weight: 600; text-transform: uppercase;">
                    {inv.status}
                </span>
            </td>
            <td style="padding: 12px; color: #4b5563; font-size: 0.9em; max-width: 380px;">{inv.note}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Strands Sentinel - Enterprise CRM</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f9fafb; margin: 0; padding: 30px; }}
            .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); padding: 24px; }}
            h1 {{ margin-top: 0; color: #111827; }}
            .status-banner {{ background: #f3f4f6; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ background: #f9fafb; padding: 12px; border-bottom: 2px solid #e5e7eb; color: #4b5563; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.05em; }}
            .footer {{ margin-top: 24px; font-size: 0.85em; color: #6b7280; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h1>Strands Sentinel - Enterprise CRM</h1>
                <span style="font-size: 0.9em; color: #6b7280;">Port {CRM_PORT}</span>
            </div>
            <div class="status-banner">
                <div><strong>Systemic Kill Switch:</strong> {kill_badge}</div>
                <div><a href="/api/invoices" style="color: #2563eb; text-decoration: none; font-size: 0.9em;">View JSON API &rarr;</a></div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Invoice ID</th>
                        <th>Vendor</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Notes / Context</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            <div class="footer">
                Strands Sentinel Zero-Trust Governance &bull; Paired with Strands Decider 2B &amp; Go Audit Ledger
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/api/health")
def health():
    """Healthcheck endpoint."""
    return {"status": "ok"}


@app.get("/api/invoices", response_model=List[Invoice])
def list_invoices(status: Optional[str] = Query(None, description="Filter invoices by status (e.g. pending)")):
    """Returns all invoices, optionally filtered by status."""
    invoices = list(invoices_db.values())
    if status:
        invoices = [inv for inv in invoices if inv.status.lower() == status.lower()]
    return invoices


@app.get("/api/invoices/{invoice_id}", response_model=Invoice)
def get_invoice(invoice_id: str):
    """Retrieves a single invoice by its ID."""
    if invoice_id not in invoices_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")
    return invoices_db[invoice_id]


@app.post("/api/invoices/{invoice_id}/approve", response_model=Invoice)
async def approve_invoice(invoice_id: str, action: ActionRequest):
    """
    Approves an invoice.
    Enforces systemic kill switch from the Go ledger before executing the state change.
    """
    if invoice_id not in invoices_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

    # 1. Systemic Kill Switch Check (Defense in Depth)
    is_killed = await check_ledger_kill_switch()
    if is_killed:
        logger.error(f"Approval blocked for {invoice_id}: systemic kill switch is ACTIVE in Go ledger!")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "error": "kill_switch_active",
                "message": "Action rejected because systemic kill switch is active."
            }
        )

    inv = invoices_db[invoice_id]

    # 2. State Check
    if inv.status in ("approved", "escalated"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice '{invoice_id}' is already {inv.status}"
        )

    # 3. Apply state mutation
    inv.status = "approved"
    logger.info(f"Invoice {invoice_id} approved by actor={action.actor} for session={action.session_id}. Reason: {action.reason}")

    # Track session interaction
    session_data = session_storage.setdefault(action.session_id, {"processed": []})
    session_data["processed"].append({"invoice_id": invoice_id, "action": "approved", "timestamp": datetime.now(timezone.utc).isoformat()})

    return inv


@app.post("/api/invoices/{invoice_id}/escalate", response_model=Invoice)
async def escalate_invoice(invoice_id: str, action: ActionRequest):
    """Escalates an invoice for manual human review."""
    if invoice_id not in invoices_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

    inv = invoices_db[invoice_id]
    if inv.status in ("approved", "escalated"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice '{invoice_id}' is already {inv.status}"
        )

    inv.status = "escalated"
    logger.info(f"Invoice {invoice_id} escalated by actor={action.actor} for session={action.session_id}. Reason: {action.reason}")

    session_data = session_storage.setdefault(action.session_id, {"processed": []})
    session_data["processed"].append({"invoice_id": invoice_id, "action": "escalated", "timestamp": datetime.now(timezone.utc).isoformat()})

    return inv


@app.get("/api/session/{session_id}/state", response_model=SessionStateResponse)
def get_session_state(session_id: str):
    """Returns volatile runtime state for a given session."""
    data = session_storage.get(session_id, {"processed": []})
    return SessionStateResponse(
        session_id=session_id,
        active=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        processed_count=len(data["processed"]),
        metadata=data
    )


@app.post("/api/reset")
def reset_crm_data():
    """Resets the mock CRM database to initial fixture values."""
    reset_invoices_db()
    session_storage.clear()
    logger.info("CRM database has been reset to initial fixtures")
    return {"message": "CRM database successfully reset", "total_invoices": len(invoices_db)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.crm.main:app", host="0.0.0.0", port=CRM_PORT, reload=True)
