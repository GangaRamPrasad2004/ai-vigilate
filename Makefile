.PHONY: help install test test-python test-go crm ledger decider agent demo-mock demo run health status kill-status trip-kill reset metrics clean docker-build docker-up docker-down article pattern video-script arch

PYTHON ?= python
GO ?= go

help:
	@echo "=================================================================="
	@echo "          Strands Sentinel - Zero-Trust Governance Agent          "
	@echo "=================================================================="
	@echo "Quickstart & Demo:"
	@echo "  make demo-mock     Run complete end-to-end demo in mock mode (offline)"
	@echo "  make demo          Run complete demo with live Strands Decider 2B"
	@echo "  make test          Run full test suite (Python pytest + Go tests)"
	@echo ""
	@echo "Development Services:"
	@echo "  make install       Install Python and Go dependencies"
	@echo "  make crm           Start FastAPI Legacy CRM on port 8000"
	@echo "  make ledger        Start Go Audit Ledger & Kill Switch on port 8081"
	@echo "  make decider       Launch local Strands Decider 2B model server"
	@echo "  make agent         Run Sentinel Agent against running services"
	@echo "  make run           Run background services and monitor status"
	@echo "  make sandbox       Run Agent within NVIDIA OpenShell Sandbox policy"
	@echo "  make knowledge     Query Qdrant Vector Knowledge Foundation"
	@echo "  make nim           Run CUDA-X NVIDIA NIM Vision OCR Extraction"
	@echo ""
	@echo "Governance & Operations:"
	@echo "  make status        Check health of CRM and Go Ledger"
	@echo "  make kill-status   Inspect current systemic kill-switch state"
	@echo "  make trip-kill     Manually trip the systemic kill switch"
	@echo "  make reset         Reset CRM invoice database and disarm kill switch"
	@echo "  make metrics       Display Decider latency and token savings metrics"
	@echo "  make clean         Clean temporary caches, build artifacts, and logs"
	@echo ""
	@echo "Containers (Docker):"
	@echo "  make docker-build  Build Docker images for CRM, Ledger, and Agent"
	@echo "  make docker-up     Start container stack with Docker Compose"
	@echo "  make docker-down   Stop and remove Docker Compose containers"
	@echo ""
	@echo "Hackathon Documentation:"
	@echo "  make article       View AWS Builder Center article draft"
	@echo "  make pattern       View reusable Guardrail Before Tool Call pattern"
	@echo "  make video-script  View 3-minute video presentation script"
	@echo "  make arch          View architecture specification and threat model"
	@echo "=================================================================="

install:
	$(PYTHON) -m pip install -r requirements.txt
	cd services/ledger && $(GO) mod download

test: test-python test-go

test-python:
	$(PYTHON) -m pytest -v

test-go:
	cd services/ledger && $(GO) test -v ./...

crm:
	$(PYTHON) -m uvicorn services.crm.main:app --host 0.0.0.0 --port 8000 --reload

ledger:
	cd services/ledger && $(GO) run main.go

decider:
	@bash scripts/start_decider.sh 8001 2>nul || sh scripts/start_decider.sh 8001

agent:
	$(PYTHON) agent/main.py

demo-mock:
	$(PYTHON) scripts/run_demo.py

demo:
	$(PYTHON) -c "import os, subprocess, sys; os.environ['DECIDER_MODE']='http'; subprocess.run([sys.executable, 'scripts/run_demo.py'])"

run:
	$(PYTHON) -c "import subprocess, sys; subprocess.run([sys.executable, 'scripts/run_demo.py'])"

sandbox:
	@bash scripts/run_in_sandbox.sh 2>nul || sh scripts/run_in_sandbox.sh

knowledge:
	@$(PYTHON) -c "from knowledge.rag_tools import query_vendor_history; print(query_vendor_history('Initech Systems'))"

nim:
	@$(PYTHON) -c "from agent.nim_tools import extract_invoice_from_image; print(extract_invoice_from_image('mock_invoices/INV-103.png'))"

status: health

health:
	@$(PYTHON) scripts/governance_cli.py health

kill-status:
	@$(PYTHON) scripts/governance_cli.py kill-status

trip-kill:
	@$(PYTHON) scripts/governance_cli.py trip-kill

reset:
	@$(PYTHON) scripts/governance_cli.py reset

metrics:
	@$(PYTHON) -c "import os; p = os.path.join('metrics', 'decider-metrics.json'); print(open(p).read() if os.path.exists(p) else 'No metrics recorded yet. Run make demo-mock first.')"

clean:
	@$(PYTHON) -c "import os, shutil; [shutil.rmtree(os.path.join(r, d)) for r, ds, _ in os.walk('.') for d in ds if d in ('__pycache__', '.pytest_cache')]; print('Cleaned Python and Pytest caches.')"

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

article:
	@$(PYTHON) -c "print(open('docs/hackathon-article.md', encoding='utf-8').read())"

pattern:
	@$(PYTHON) -c "print(open('patterns/guardrail-before-tool.md', encoding='utf-8').read())"

video-script:
	@$(PYTHON) -c "print(open('docs/demo-video-script.md', encoding='utf-8').read())"

arch:
	@$(PYTHON) -c "print(open('docs/architecture.md', encoding='utf-8').read())"
