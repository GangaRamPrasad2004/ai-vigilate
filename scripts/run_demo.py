#!/usr/bin/env python3
"""
Cross-platform automated demo runner.
Works on Windows, macOS, and Linux without requiring bash or external shell tools.
"""

import os
import sys
import time
import subprocess
import httpx


def wait_for_endpoint(url: str, name: str, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                print(f"[OK] {name} is ready at {url}")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print(f"[FAIL] {name} did not become healthy within {timeout}s at {url}")
    return False


def main():
    mode = os.environ.get("DECIDER_MODE", "mock")
    print("=" * 60)
    print(f"   STRANDS SENTINEL DEMO RUNNER (DECIDER_MODE={mode.upper()})")
    print("=" * 60)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)

    # 1. Start Go Ledger
    print("\n--> [1/4] Launching Go Audit Ledger (port 8081)...")
    ledger_proc = subprocess.Popen(
        ["go", "run", "main.go"],
        cwd=os.path.join(repo_root, "services", "ledger"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # 2. Start FastAPI CRM
    print("--> [2/4] Launching FastAPI CRM Service (port 8000)...")
    crm_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.crm.main:app", "--port", "8000"],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        # Wait for healthchecks
        if not wait_for_endpoint("http://localhost:8081/health", "Go Ledger", timeout=10.0):
            sys.exit(1)
        if not wait_for_endpoint("http://localhost:8000/api/health", "FastAPI CRM", timeout=10.0):
            sys.exit(1)

        # Reset fixtures
        print("--> [3/4] Resetting CRM fixtures and Ledger kill switch...")
        httpx.post("http://localhost:8000/api/reset", timeout=3.0)
        httpx.post("http://localhost:8081/reset", timeout=3.0)

        # 3. Run Agent
        print("\n--> [4/4] Executing Sentinel Agent Workflow...\n")
        env = os.environ.copy()
        env["DECIDER_MODE"] = mode
        agent_proc = subprocess.run([sys.executable, "agent/main.py"], cwd=repo_root, env=env)

    finally:
        print("\n--> Cleaning up background demo services...")
        try:
            crm_proc.terminate()
            ledger_proc.terminate()
            crm_proc.wait(timeout=3)
            ledger_proc.wait(timeout=3)
        except Exception:
            crm_proc.kill()
            ledger_proc.kill()
        print("--> Background services terminated cleanly.")


if __name__ == "__main__":
    main()
