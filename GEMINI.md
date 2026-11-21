# Tabulas Card Hub — Always-On Antigravity Workspace Guardrails

Follow these rules strictly on every task in this workspace (`C:\Tabulas Card Hub\App`):

## 1. Live User Data Protection (ZERO Mutations During Tests/Audits)
- **NEVER** modify, overwrite, move, or delete live user data files or media outside `C:\Tabulas Card Hub\App`:
  - `C:\Tabulas Card Hub\Data\` (`Inventory.csv`, `Master_Checklist.csv`, `TCDB_Set_Directory.csv`, `Expenses.csv`, `Sold_Cards.csv`, `Listing_Drafts.csv`, `Market_Comps.csv`, `Collection_Value_History.csv`)
  - `D:\Tabulas Set Library\` (`_My_Collection\`, `Unprocessed_Cards\`, `Reference_Library\`)
  - `F:\Tabulas Archive\`
- Read-only inspection of logs (`C:\Tabulas Card Hub\Logs\Logs\`) and caches (`C:\Tabulas Card Hub\Cache\`) is permitted for diagnostics.
- Any automated test that writes CSVs, JSONs, or images **MUST** run against isolated temporary copies in `tempfile` / `%TEMP%`, never live user folders.
- During live browser checks on `http://localhost:5000`, **NEVER** click Commit, Clear, Delete, Save, Reset, or trigger destructive endpoints.

## 2. External Web & TCDB Rate-Limit Protection
- **NEVER** launch live TCDB scrapers, TCDB directory crawls, SportsCardsPro comps, or external web scraping jobs during audits or automated tests.
- Never open `tcdb.com` in the browser subagent (Cloudflare ~25 req/min IP limit).

## 3. Architecture & Runtime Invariants
- **Python Environment:** Always execute Python using `C:\Users\micha\tabulas_env\Scripts\python.exe` (or `C:\Tabulas Card Hub\.venv\Scripts\python.exe` if present).
- **Environment Variables When Launching Server/Scripts:**
  - `CARDS_BASE_DIR=C:\Tabulas Card Hub`
  - `TABULAS_SET_LIBRARY_DIR=D:\Tabulas Set Library`
  - `TABULAS_ARCHIVE_DIR=F:\Tabulas Archive`
- **3-Drive Layout (`v0.24.0`):** Always use canonical path constants from `Core/config.py` (`INVENTORY_FILE`, `BATCHES_DIR`, `INPUT_PATH`, `REVIEWED_CARDS_DIR`, `REFERENCE_TEMPLATES_DIR`, `CHECKLIST_PATH`, `SET_CHECKLISTS_DIR`, `DAILY_LOGS_ROOT`, `ARCHIVE_DIR`, etc.). Never reintroduce legacy paths (`Inventory\Batches`, `Checklists\`, `_Cards`).
- **8-Slot Parallel Worker Pool (`cli.py`):** Maintain `slot_1`..`slot_8`. ONLY TCDB rate-limited scrapers queue sequentially behind each other; all other processes (including non-TCDB scrapers, scan processing, reprocessing, pre-grading, commits, and maintenance) run immediately in parallel on the first available idle worker.
- **GPU & CPU Fallback (`Core/compute_backend.py`, `Core/neural_vision.py`):** Preserve DXGI discrete-GPU (`dGPU`) steering for `onnxruntime-directml`, OpenCV OpenCL `cv2.UMat`, and 100% automatic CPU fallback on any GPU/VRAM error.
- **React/Babel Bootloader (`launch_tabulas_hub.py` + `App.jsx`):** `App.jsx` is >590 KB and compiled via `Babel.transform(..., { presets: [['react', { runtime: 'classic' }]], compact: false })`. Never introduce top-level ES `import`/`export` syntax that breaks non-module execution, and keep `compact: false` and `runtime: 'classic'`.

## 4. Mandatory Verification Before Completing Any Code Edit
1. Run `python -m py_compile` on every modified `.py` file.
2. If `App.jsx` or `launch_tabulas_hub.py` was modified, start `launch_tabulas_hub.py --browser`, verify `http://localhost:5000` loads cleanly with zero Babel/JS/React console errors in the browser subagent, and stop the test server cleanly afterward.
3. Keep changes surgical, preserve existing user features/themes/layouts, and clearly summarize every modified file so the user can review `git diff` and commit.