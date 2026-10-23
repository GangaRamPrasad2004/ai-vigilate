#!/usr/bin/env bash
# ==============================================================================
# Setup script for Strands Sentinel monorepo
# ==============================================================================
set -e

echo "=== 1. Checking Python and Go Prerequisites ==="
python3 --version || python --version
go version

echo ""
echo "=== 2. Creating Python Virtual Environment (if not present) ==="
if [ ! -d ".venv" ]; then
    python3 -m venv .venv || python -m venv .venv
fi

# Source virtualenv if on POSIX
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
fi

echo ""
echo "=== 3. Installing Python Dependencies ==="
pip install -r requirements.txt

echo ""
echo "=== 4. Downloading Go Modules ==="
cd services/ledger
go mod download
cd ../..

echo ""
echo "=== 5. Copying .env Configuration ==="
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

echo ""
echo "=== Setup Complete! ==="
echo "Run 'make test' to verify your installation."
