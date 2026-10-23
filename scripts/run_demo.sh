#!/usr/bin/env bash
# ==============================================================================
# End-to-end automated demo runner for hackathon evaluation
# ==============================================================================
set -e

MODE=${1:-mock}
export DECIDER_MODE=$MODE

echo "============================================================"
echo "    STRANDS SENTINEL: LIVE END-TO-END DEMONSTRATION"
echo "    Mode: DECIDER_MODE=${DECIDER_MODE}"
echo "============================================================"

# 1. Start Go Ledger
echo "--> Launching Go Audit Ledger (Port 8081)..."
(cd services/ledger && go run main.go) &
LEDGER_PID=$!

# 2. Start FastAPI CRM
echo "--> Launching FastAPI Legacy CRM (Port 8000)..."
python -m uvicorn services.crm.main:app --host 0.0.0.0 --port 8000 &
CRM_PID=$!

cleanup() {
    echo ""
    echo "--> Shutting down background demo services..."
    kill $LEDGER_PID $CRM_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for services to become healthy
echo "--> Waiting for services to initialize..."
sleep 2

# Reset CRM fixtures
echo "--> Resetting CRM to clean test fixtures..."
python -c "import httpx; httpx.post('http://localhost:8000/api/reset', timeout=3.0)" 2>/dev/null || true
python -c "import httpx; httpx.post('http://localhost:8081/reset', timeout=3.0)" 2>/dev/null || true

echo ""
echo "--> Executing Sentinel Agent..."
python agent/main.py

echo ""
echo "============================================================"
echo "Demo execution finished."
echo "Check metrics in metrics/decider-metrics.json"
echo "============================================================"
