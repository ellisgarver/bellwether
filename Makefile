# bellwether — common developer tasks.
#
# Run `make help` for a list of targets.

.DEFAULT_GOAL := help
SHELL := /bin/bash
PYTHON ?= python

.PHONY: help install install-dev preflight preflight-full test lint format clean \
        ingest filter-pre-embed filter embed cluster validate update dashboard site

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

preflight-full:  ## Run pre-flight INCLUDING embedding model load (multi-GB download)
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
# Pipeline targets — local entry points. Full historical runs go on RCC via
# scripts/rcc/submit_parallel_ingest.sh; these targets are for spot-runs.
# ----------------------------------------------------------------------------

ingest:  ## Run institutional ingest for a date range. Use START=YYYY-MM-DD END=YYYY-MM-DD
	$(PYTHON) scripts/run_pipeline.py ingest --start $(START) --end $(END) --sources institutional

filter-pre-embed:  ## Exclude archived sources from raw JSONL (ADR-010/012)
	$(PYTHON) scripts/run_pipeline.py filter-pre-embed

filter:  ## Date-range filter + MinHash dedup (no topic filter per ADR-012)
	$(PYTHON) scripts/run_pipeline.py filter

embed:  ## Embed filtered articles (primary Qwen3 embedder)
	$(PYTHON) scripts/run_pipeline.py embed --role $(or $(ROLE),primary)

cluster:  ## Run clustering on embeddings
	$(PYTHON) scripts/run_pipeline.py cluster

validate:  ## Run anchor-narrative recovery validation
	$(PYTHON) scripts/run_pipeline.py validate

update:  ## Portable weekly refresh: per-source delta ingest + artifact re-bake
	$(PYTHON) scripts/run_pipeline.py update

dashboard:  ## Run the Astro dashboard dev server (web/)
	cd web && npm run dev

site:  ## Build the static site (web/dist)
	cd web && npm run build
