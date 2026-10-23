#!/usr/bin/env python3
"""
CLI helper for governance operations, health checks, and state resets.
"""

import sys
import os
import json
import httpx

CRM_URL = os.getenv("CRM_BASE_URL", "http://localhost:8000").rstrip("/")
LEDGER_URL = os.getenv("LEDGER_BASE_URL", "http://localhost:8081").rstrip("/")


def check_health():
    print("--- Service Health Status ---")
    try:
        r = httpx.get(f"{CRM_URL}/api/health", timeout=1.5)
        print(f"CRM ({CRM_URL}):    ONLINE ({r.json()})")
    except Exception:
        print(f"CRM ({CRM_URL}):    OFFLINE")

    try:
        r = httpx.get(f"{LEDGER_URL}/health", timeout=1.5)
        print(f"Ledger ({LEDGER_URL}): ONLINE ({r.json()})")
    except Exception:
        print(f"Ledger ({LEDGER_URL}): OFFLINE")


def check_kill():
    try:
        res = httpx.get(f"{LEDGER_URL}/kill", timeout=2.0).json()
        print("=== Systemic Kill Switch Status ===")
        print(f"Kill Switch Active: {res.get('killed')}")
        print(f"Trigger Reason:     {res.get('reason') or 'None'}")
        print(f"Session ID:         {res.get('session_id') or 'N/A'}")
        print(f"Timestamp:          {res.get('timestamp') or 'N/A'}")
    except Exception as exc:
        print(f"Unable to reach Go Ledger at {LEDGER_URL}: {exc}")


def trip_kill():
    try:
        payload = {
            "reason": "Manual Operator Override via Makefile CLI",
            "session_id": "operator-console"
        }
        res = httpx.post(f"{LEDGER_URL}/kill", json=payload, timeout=2.0).json()
        print("SYSTEMIC KILL SWITCH TRIPPED:")
        print(json.dumps(res, indent=2))
    except Exception as exc:
        print(f"Failed to trip kill switch at {LEDGER_URL}: {exc}")


def reset_services():
    print("--- Resetting Services ---")
    try:
        r_crm = httpx.post(f"{CRM_URL}/api/reset", timeout=2.0).json()
        print(f"CRM:    Reset complete ({r_crm.get('message', 'ok')})")
    except Exception:
        print(f"CRM:    Unable to reach {CRM_URL}")

    try:
        r_led = httpx.post(f"{LEDGER_URL}/reset", timeout=2.0).json()
        print(f"Ledger: Kill switch disarmed ({r_led})")
    except Exception:
        print(f"Ledger: Unable to reach {LEDGER_URL}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/governance_cli.py [health|kill-status|trip-kill|reset]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd in ("health", "status"):
        check_health()
    elif cmd in ("kill-status", "kill"):
        check_kill()
    elif cmd in ("trip-kill", "trip"):
        trip_kill()
    elif cmd in ("reset", "reset-all"):
        reset_services()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
