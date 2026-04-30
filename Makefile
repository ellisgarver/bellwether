# Macro Narrative Dynamics — common developer tasks.
#
# Run `make help` for a list of targets.

.DEFAULT_GOAL := help
SHELL := /bin/bash
PYTHON ?= python

.PHONY: help install install-dev preflight test lint format clean pilot \
        ingest filter embed cluster validate dashboard

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install the project as editable + all pinned dependencies
	$(PYTHON) -m pip install -e . -r requirements.txt

install-dev:  ## Install dev tools (ruff, pytest extras)
	$(PYTHON) -m pip install -e . -r requirements.txt
	$(PYTHON) -m pip install ruff pytest-cov

preflight:  ## Run the pre-flight environment check (no model download)
	$(PYTHON) scripts/preflight_check.py --skip-embedding

preflight-full:  ## Run pre-flight INCLUDING embedding model load (~600MB download)
	$(PYTHON) scripts/preflight_check.py

test:  ## Run pytest suite
	$(PYTHON) -m pytest

lint:  ## Lint with ruff
	ruff check src/ scripts/ tests/

format:  ## Format with ruff
	ruff format src/ scripts/ tests/

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ipynb_checkpoints -exec rm -rf {} + 2>/dev/null || true

# ----------------------------------------------------------------------------
# Pipeline targets — these dispatch to scripts/run_pipeline.py once it exists.
# ----------------------------------------------------------------------------

pilot:  ## Run the Phase 1 pilot end-to-end (6-month sample)
	$(PYTHON) scripts/run_pipeline.py pilot

ingest:  ## Run ingestion for a date range. Use START=YYYY-MM-DD END=YYYY-MM-DD
	$(PYTHON) scripts/run_pipeline.py ingest --start $(START) --end $(END)

filter:  ## Run topic filter + MinHash dedup over ingested articles
	$(PYTHON) scripts/run_pipeline.py filter

embed:  ## Embed filtered articles. ROLE=primary|comparator
	$(PYTHON) scripts/run_pipeline.py embed --role $(or $(ROLE),primary)

cluster:  ## Run clustering on embeddings
	$(PYTHON) scripts/run_pipeline.py cluster

validate:  ## Run anchor-narrative recovery validation
	$(PYTHON) scripts/run_pipeline.py validate

dashboard:  ## Launch the Streamlit dashboard locally
	streamlit run src/mnd/dashboard/app.py
