#!/usr/bin/env bash
# ==============================================================================
# Strands Sentinel: Helper script to launch local Strands Decider 2B Model Server
# ==============================================================================
set -e

PORT=${1:-8001}
MODEL_TAG="StrandsAgents/strands-decider-2B-hobson-v19"

echo "============================================================"
echo "    Launching Strands Decider 2B Server on port ${PORT}"
echo "    Model: ${MODEL_TAG}"
echo "============================================================"

# Check if strands-decider command is available
if command -v strands-decider &> /dev/null; then
    echo "Found strands-decider CLI. Launching server..."
    exec strands-decider serve "${MODEL_TAG}" --port "${PORT}"
elif command -v vllm &> /dev/null; then
    echo "Found vLLM. Serving ${MODEL_TAG} with OpenAI-compatible API..."
    exec python -m vllm.entrypoints.openai.api_server --model "${MODEL_TAG}" --port "${PORT}"
else
    echo ""
    echo "[!] 'strands-decider' CLI tool was not found in your current PATH."
    echo ""
    echo "To install and serve the official Strands Decider 2B model, run:"
    echo "  1. pip install strands-decider"
    echo "     (or: pip install git+https://github.com/strands-labs/strands-decider.git)"
    echo "  2. strands-decider serve ${MODEL_TAG} --port ${PORT}"
    echo ""
    echo "Please verify the official Strands Decider repository for the current serve command."
    echo ""
    echo "NOTE FOR HACKATHON EVALUATION:"
    echo "You can run the full test suite and demo offline right now without GPU hardware"
    echo "by setting DECIDER_MODE=mock:"
    echo "  make demo-mock"
    echo "============================================================"
    exit 1
fi
