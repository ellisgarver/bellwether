#!/bin/bash
# One-time Playwright setup for CBO ingestion (ADR-017).
#
# CBO's cbo.gov is fronted by DataDome bot protection that defeats every
# curl_cffi Chrome/Safari/Edge/Firefox impersonation. The ADR-017 fix is to
# use Playwright to drive a real headless Chromium browser through DataDome's
# JS execution challenge once per ingest run, capture the resulting clearance
# cookies, and reuse them in subsequent curl_cffi fetches.
#
# Run this script once per Python environment (local or RCC mnd conda env)
# AFTER `pip install -r requirements.txt`. It downloads the Chromium binary
# (~300 MB) to the standard Playwright cache.
#
# Local:
#   bash scripts/install_playwright_for_cbo.sh
#
# RCC:
#   conda activate mnd
#   bash scripts/install_playwright_for_cbo.sh

set -euo pipefail

PY="${PYTHON:-python}"
echo "Using Python: $(${PY} -c 'import sys; print(sys.executable)')"

# Verify playwright python package is installed
${PY} -c "import playwright" 2>/dev/null || {
    echo "ERROR: playwright Python package not installed."
    echo "Run: pip install -r requirements.txt"
    exit 1
}

# Download Chromium binary
echo "Installing Playwright Chromium..."
${PY} -m playwright install chromium

# Sanity check: launch headless Chromium and load about:blank
${PY} - <<'PYEOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("about:blank")
    print(f"Chromium OK: {browser.version}")
    browser.close()
PYEOF

echo
echo "Playwright Chromium ready for CBO ingestion."
echo "The CBO ingestor will launch a headless browser on first fetch to"
echo "acquire DataDome clearance cookies, then reuse them across all"
echo "subsequent curl_cffi fetches."
