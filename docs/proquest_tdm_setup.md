# ProQuest TDM Studio Setup Guide

This document explains how to get paywalled-outlet full text into the
Macro Narrative Dynamics pipeline via ProQuest TDM Studio. The workflow has
three parts: create a dataset in the TDM Studio web UI, export it to JSONL
using the provided script inside TDM Studio's Jupyter environment, then drop
the JSONL file into the project for the pipeline to ingest.

Access confirmed for UChicago: Global Newsstream covers WSJ, FT, Reuters,
Bloomberg, and most Tier 1/2 whitelist outlets.

---

## Part 1: Access TDM Studio

1. Go to the UChicago Library ProQuest TDM Studio portal (library.uchicago.edu
   → Databases → ProQuest TDM Studio, or navigate directly to
   tdmstudio.proquest.com and authenticate with your CNetID).
2. Log in with your institutional credentials. TDM Studio uses SSO — no
   separate password needed.
3. You will land on the **Projects** dashboard.

---

## Part 2: Create a dataset

A dataset is a saved query that TDM Studio materializes into a collection of
full-text documents. You create and manage datasets through the web UI.

1. Click **New Dataset** (or **Add Dataset** to an existing project).
2. Select **Global Newsstream** as the database.
3. Set the **date range** matching the ingestion window you plan to run.
   For Phase 2 full corpus: 2010-01-01 to present.
   For a narrower test run: match a specific `--start`/`--end` window.
4. Add **Publication filters**. Use the publication names listed in
   `config/whitelist.yaml` under `proquest_publication_name` fields. Key ones:
   - The Wall Street Journal
   - Financial Times
   - Reuters
   - Bloomberg
   - The New York Times
   - The Washington Post
   (Add all Tier 1 and Tier 2 paywalled outlets from the whitelist.)
5. Optionally add **keyword filters** to reduce dataset size. The topic filter
   already lives in the pipeline; you can leave this open or add broad terms
   like "Federal Reserve OR inflation OR interest rate OR monetary policy".
6. Click **Build Dataset**. ProQuest materializes the dataset asynchronously
   (minutes to hours depending on volume). You will receive an email when ready.
7. Once built, open the dataset's **Settings** tab and copy the **Dataset ID**
   (a UUID like `abc12345-6789-...`). You will need this in Parts 3 and 4.

---

## Part 3: Export the dataset to JSONL inside TDM Studio

The export script is `scripts/tdm_studio_export.py`. It is fully standalone —
no project dependencies, no `mnd.*` imports. Upload it directly to TDM Studio
and run it there.

### Option A: Upload and run from the terminal

1. Open a **Jupyter notebook** in your TDM Studio project.
2. In the file browser (left panel), upload `scripts/tdm_studio_export.py`.
3. Open a terminal (File → New → Terminal) and run:
   ```bash
   PROQUEST_DATASET_ID=<your-dataset-id> python tdm_studio_export.py
   ```
4. The script writes `proquest_<dataset-id>.jsonl` in the current directory.

### Option B: Paste into a notebook cell

Copy the entire contents of `scripts/tdm_studio_export.py` into a notebook
cell, then add a final cell:
```python
import os
from pathlib import Path

os.environ["PROQUEST_DATASET_ID"] = "<your-dataset-id>"
export_dataset(
    dataset_id="<your-dataset-id>",
    output_path=Path("proquest_<your-dataset-id>.jsonl"),
)
```

### Verifying the export

Before downloading, spot-check the output:
```python
import json
with open("proquest_<your-dataset-id>.jsonl") as f:
    first = json.loads(f.readline())
print(list(first.keys()))
print(first["title"])
print(first["body"][:200])
```

If `title` and `body` are empty, the TDM Studio document field names differ
from what the script expects. Run `print(list(doc.keys()))` on the first
document from the TDM client to see the actual names, then update `_FIELD_MAP`
at the top of `tdm_studio_export.py` and re-run.

### Download the JSONL file

In the TDM Studio file browser, right-click the JSONL file → Download.
For large files (>100 MB), use the terminal to compress first:
```bash
gzip proquest_<dataset-id>.jsonl
# download the .gz, then: gunzip proquest_<dataset-id>.jsonl.gz
```

---

## Part 4: Place the file and run the pipeline

1. Move the downloaded JSONL file to:
   ```
   data/raw/articles/proquest_<your-dataset-id>.jsonl
   ```
2. Add the dataset ID to `.env`:
   ```
   PROQUEST_DATASET_ID=<your-dataset-id>
   ```
3. Run the pipeline with `--sources paywalled`:
   ```bash
   python scripts/run_pipeline.py ingest \
       --start 2010-01-01 --end 2024-12-31 \
       --sources paywalled
   ```
   The `PaywalledSourceIngestor` reads from the JSONL file, filters to the
   requested date range, and yields Articles to the rest of the pipeline.

4. Continue with the normal pipeline stages:
   ```bash
   python scripts/run_pipeline.py filter
   python scripts/run_pipeline.py embed --role primary
   # etc.
   ```

---

## Notes

- **One dataset per query**: if you change the date range or publication list,
  create a new dataset in TDM Studio and repeat the export. Update
  `PROQUEST_DATASET_ID` in `.env` to point to the new file.
- **Dataset ID in the filename**: the JSONL filename encodes the dataset ID,
  making it easy to keep multiple exports alongside each other without
  confusion.
- **Re-ingestion**: because the JSONL is a stable local artifact, you can
  re-run `ingest --sources paywalled` as many times as needed without going
  back to TDM Studio.
- **Field name verification**: the `_FIELD_MAP` in `tdm_studio_export.py` covers common
  TDM Studio document field variants. If an export produces empty
  `title`/`body` fields, print a raw document dict inside TDM Studio to
  check the actual field names and update `_FIELD_MAP`.
