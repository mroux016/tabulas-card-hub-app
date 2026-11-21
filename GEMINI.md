# Tabulas Card Management Hub — Antigravity Workspace Rules & Guardrails

These rules are **always active** for all agents working inside `C:\Tabulas Card Hub\App`.

---

## 1. Strict Data & Media Protection (NON-NEGOTIABLE)
1. **Never modify, overwrite, move, or delete live user data** outside `C:\Tabulas Card Hub\App`:
   - Protected Data: `C:\Tabulas Card Hub\Data\` (`Inventory.csv`, `Master_Checklist.csv`, `TCDB_Set_Directory.csv`, `Expenses.csv`, `Sold_Cards.csv`, `Listing_Drafts.csv`, `Market_Comps.csv`, `Collection_Value_History.csv`, `Set_Checklists\`).
   - Protected Media: `D:\Tabulas Set Library\` (`_My_Collection\`, `Unprocessed_Cards\`, `Reference_Library\`).
   - Protected Archive: `F:\Tabulas Archive\`.
   - Protected Caches/Models: `C:\Tabulas Card Hub\Cache\` (`tracked_sets.json`, `dinov2_vits14.onnx`, `neural_embeddings_v1.pkl`, `adaptive_rate_learner.json`).
2. Read-only inspection of `Data\`, `Cache\`, `Logs\Logs\`, or sample images on `D:` is allowed for debugging, **but any write tests must use isolated temporary directories** (e.g., `tempfile.TemporaryDirectory()`).
3. Never click **Commit**, **Clear**, **Delete**, **Save**, or **Rollback** against live data during automated browser verification.

---

## 2. External Network & Scraper Restrictions
1. **Never launch live TCDB scraping jobs** (`tcdb_*`, `crawl_tcdb_directory`, or live `repair_tcdb_directory` Img% backfills) during testing. TCDB enforces a strict ~25 req/min Cloudflare limit per IP/session.
2. **Never launch live external market/bio scrapers** (`refresh_market_valuations` with web comps, `batch_generate_listings` with web refresh) during automated tests.
3. Preserve the **TCDB-only queuing rule** in `cli.py`: ONLY active TCDB web scrapers serialize behind each other; all other tasks (non-TCDB scrapers, reprocessing, scan processing, pre-grading, commits, rotation fixes, local repairs) must dispatch immediately in parallel across the 8-worker pool (`slot_1` .. `slot_8`).

---

## 3. Environment & Architecture Invariants
1. **Python Interpreter:** Always run Python commands, syntax checks, and the local server using the Tabulas virtual environment:
   - Primary: `C:\Users\micha\tabulas_env\Scripts\python.exe` (or `C:\Tabulas Card Hub\.venv\Scripts\python.exe` if present).
2. **Single-File React Bootloader (`App.jsx` + `launch_tabulas_hub.py`):**
   - `App.jsx` (~600 KB) is compiled client-side by `@babel/standalone` inside `_build_tabulas_react_html_v2()` using `presets: [['react', { runtime: 'classic' }]]` and `compact: false`.
   - Never introduce unstripped ES module `import`/`export` statements that break `new Function(...)` execution, and never break JSX syntax.
3. **3-Drive Path Policy:** Always import paths from `Core/config.py` (`INVENTORY_FILE`, `BATCHES_DIR`, `INPUT_PATH`, `REVIEWED_CARDS_DIR`, `REFERENCE_TEMPLATES_DIR`, `CHECKLIST_PATH`, `SET_CHECKLISTS_DIR`, `DAILY_LOGS_ROOT`, `ARCHIVE_DIR`, etc.). Never hardcode legacy pre-v0.24 paths (`Inventory\Batches`, `Checklists\`, `_Cards`).
4. **GPU & Fallback Policy:** Machine has an **AMD Radeon RX 9070 XT (16 GB VRAM)** plus an integrated GPU.
   - Always preserve DXGI `dGPU`-first steering (`Core/compute_backend.py`) so DirectML (`onnxruntime-directml`) runs on the discrete GPU, never the iGPU.
   - Every GPU feature (DirectML RapidOCR, DINOv2-small ONNX, OpenCV OpenCL `cv2.UMat`) **must** retain 100% automatic CPU fallback without crashing on CPU-only machines.
5. **No Unsolicited `.txt` Update Packages:** When editing files directly inside `C:\Tabulas Card Hub\App`, edit the source files directly (the user uses Git for local version control). Do not generate `Updates\update_*.txt` packages unless explicitly asked.

---

## 4. Mandatory Verification Before Finishing Any Task
Before declaring any code edit complete, you MUST:
1. Run `py_compile` on every modified `.py` file using the Tabulas Python environment:
   `C:\Users\micha\tabulas_env\Scripts\python.exe -m py_compile <modified_files>`
2. If `App.jsx` or `launch_tabulas_hub.py` was modified:
   - Verify no port `5000` orphan conflicts, launch `launch_tabulas_hub.py --browser`, open `http://localhost:5000` in the browser tool, and confirm the UI renders with **zero Babel errors, zero uncaught console errors, and zero 500 API responses** on the modified screens.
   - Shut down any test server process you started when verification finishes.
3. Keep changes clean, focused, and easy to review in `git diff`. Never silently delete features or change CSV column schemas without explicit user approval.