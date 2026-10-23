#!/usr/bin/env bash
# ==============================================================================
# Starts CRM and Go Ledger background services for local development
# ==============================================================================
set -e

echo "Starting Go Ledger on port 8081..."
(cd services/ledger && go run main.go) &
LEDGER_PID=$!

echo "Starting FastAPI CRM on port 8000..."
python -m uvicorn services.crm.main:app --host 0.0.0.0 --port 8000 &
CRM_PID=$!

cleanup() {
    echo ""
    echo "Stopping background services..."
    kill $LEDGER_PID $CRM_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "Services are running:"
echo "  - CRM Dashboard:    http://localhost:8000"
echo "  - Ledger Dashboard: http://localhost:8081"
echo "Press Ctrl+C to stop all services."

wait
