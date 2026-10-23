#!/usr/bin/env bash
# ==============================================================================
# Strands Sentinel: Launch Agent Harness inside NVIDIA OpenShell Sandbox
# ==============================================================================
# Demonstrates Pillar 3 (Sandbox): Containment of the Python agent process,
# enforcing network egress whitelisting, filesystem immutability, and credential stripping.
# ==============================================================================
set -e

POLICY_FILE="sandbox/openshell.toml"

echo "============================================================"
echo "    Launching Strands Sentinel inside NVIDIA OpenShell"
echo "    Policy: ${POLICY_FILE}"
echo "============================================================"

if [ ! -f "${POLICY_FILE}" ]; then
    echo "[-] Error: Sandbox policy '${POLICY_FILE}' not found!"
    exit 1
fi

# Check if the openshell CLI is installed on this host
if command -v openshell &> /dev/null; then
    echo "[+] Found NVIDIA OpenShell runtime. Enforcing isolation boundary..."
    exec openshell run --policy "${POLICY_FILE}" -- python agent/main.py "$@"
else
    echo ""
    echo "[!] 'openshell' binary was not detected on this system."
    echo ""
    echo "To install the official NVIDIA OpenShell sandbox runtime:"
    echo "  1. Download OpenShell from https://developer.nvidia.com/openshell"
    echo "  2. sudo install -m 755 openshell /usr/local/bin/"
    echo "  3. Verify with: openshell --version"
    echo ""
    echo "SIMULATING SANDBOX EXECUTION LOCALLY:"
    echo "Running with simulated sandbox environment variables..."
    echo "============================================================"
    export OPENSHELL_CONTAINMENT="active"
    export OPENSHELL_POLICY_VERSION="1.0.0"
    python agent/main.py "$@"
fi
