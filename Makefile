PY ?= python3
VENV = .venv
BIN = $(VENV)/bin
BASE_URL ?= http://127.0.0.1:8000

.PHONY: install run test newman monitor

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -r requirements.txt

run:
	MOCK_LLM=true $(BIN)/uvicorn target_api.main:app --port 8000

test:
	MOCK_LLM=true $(BIN)/pytest -q --cov=target_api --cov-report=term-missing

# Requires the API running (make run) and Newman (npm i -g newman newman-reporter-htmlextra)
newman:
	newman run postman/ai_api.postman_collection.json \
	  -e postman/local.postman_environment.json \
	  -r cli,htmlextra --reporter-htmlextra-export newman/report.html

monitor:
	BASE_URL=$(BASE_URL) $(BIN)/python monitor/run_checks.py
