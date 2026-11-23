# Changelog — Tabulas Card Hub

All notable user-facing changes, workflow improvements, and bug fixes for Tabulas Card Hub are documented in this file.

## [v0.25.0-beta.8] — 2026-11-23 — Collapsible Updates Page, Spacious Changelog Reader, Click-to-Reboot & Actionable Notifications

### Features & Improvements
- **Full Historical Changelog (`CHANGELOG.md`)**: Backfilled user-facing release notes covering all historical releases from `v0.24.0-beta.45` through `v0.25.0-beta.8`, organized by Features & Improvements, UI & Workflow, and Bug Fixes.
- **GitHub Releases Pull-Through**: Release checks and OTA installations now parse, format, and store structured user-facing release notes in `version_registry.json`, with automatic fallback to `CHANGELOG.md` when release notes are minimal.
- **One-Click Server Restart (`POST /api/system/restart`)**: Added a clean self-restart endpoint that respects active worker pool locks (`slot_1`–`slot_8`) before shutting down and relaunching the local server.

### UI & Workflow
- **Collapsible Updates / About Sections**: Added expand/collapse toggles (with persisted state) for GitHub Releases OTA configuration, Installed Module Registry, and Changelogs & Release Notes.
- **Spacious Changelog Reader**: Added an expandable, readable release notes viewer with section badges, formatted bullet lists, search filtering, and Expand All / Collapse All controls.
- **Click-to-Reboot in Update Notifications**: Added a **Restart App** action button directly in update toasts, notification rows, and post-update banners with live reconnection polling.
- **Actionable Notifications & Copy Button**: Added a **Copy** button with visual confirmation (`Copied`) to every notification row and made notifications clickable to jump directly to the relevant workspace page.

### Bug Fixes
- Prevented cramped scrolling on the Updates / About page when multiple panels are open simultaneously.
- Ensured notification Copy and Clear buttons stop event propagation so clicking them does not trigger row navigation.

---

## [v0.25.0-beta.7] — 2026-11-23 — GitHub Releases OTA Updater, Release Packaging Workflow & SHA-256 Verification

### Features & Improvements
- **GitHub Releases OTA Updater (`updater.py`)**: Added remote release discovery and installation supporting `stable` and `beta` channels, optional GitHub token authentication, and `TABULAS_GITHUB_TOKEN` environment variable fallback.
- **Cryptographic & Path Safety**: Added mandatory `SHA256SUMS.txt` verification, zip-slip path traversal rejection, protected directory guards (`Data/`, `Cache/`, `Logs/`, `Set Library/`, `Archive/`, `.git/`, `.agents/`, `.env`), and automatic pre-update backup zips (retaining the 5 most recent backups).
- **Automated Release Packaging (`.github/workflows/release.yml`)**: Added tag-triggered (`v*`) GitHub Actions workflow to build clean release archives and `SHA256SUMS.txt`.

### UI & Workflow
- **Remote OTA Controls in Updates Page**: Added repository (`owner/repo`), channel selector, masked token storage, release preview, and one-click Download & Install actions.
- **Dependency & Restart Alerts**: Automatically detects changes to `requirements.txt` during OTA updates and notifies the user when a server restart is required.

### Bug Fixes
- Blocked OTA updates from running while any background worker slot (`slot_1`–`slot_8`) is active to prevent partial writes mid-job.

---

## [v0.25.0-beta.6] — 2026-11-23 — Clean Theme Skins, Local Maintenance Scheduler & Changelog-Only Updates

### Features & Improvements
- **Local-First Maintenance Scheduler (`Core/maintenance_scheduler.py`)**: Added atomic, lock-safe scheduling (`Data/maintenance_schedule.json`) for Neural Embedding Cache & Visual Index Rebuild, Master Checklist & Template Rollup, Learned Set Priors Refresh, and Housekeeping & Hygiene.
- **Worker Idle-Guard Deferral**: Scheduled and manual maintenance jobs automatically defer whenever any worker slot (`slot_1`–`slot_8`) or stop-signal is active.
- **Changelog-Only Update Packages (`updater.py`)**: Added `PACKAGE_TYPE: CHANGELOG_ONLY` support so historical release records can be validated and recorded without modifying code files.

### UI & Workflow
- **Clean Theme Skin Names**: Removed leading numeric prefixes from all 9 Chrome-Pulse 3D skin display names while preserving `LEGACY_SKIN_KEY_MAP` compatibility.
- **Manual Maintenance Controls**: Added **Run Now** triggers and schedule configuration controls inside General Settings.

### Bug Fixes
- Backfilled 9 historical `Updates/*.txt` changelog packages so the in-app updater displays complete version history.

---

## [v0.25.0-beta.5] — 2026-11-22 — Concurrency Hardening, Geometry Precision & Learned Set/Mini Priors

### Features & Improvements
- **Learned Set & Mini Priors (`Core/vision_grader.py`)**: Added `learned_set_priors.json` with a 3-tier hierarchy `(set, subset, side)` -> `(set, side)` -> `(card_format, side)` and `rebuild_learned_set_priors()` from `grading_feedback_log.jsonl`.
- **PID-Safe Concurrency & Atomic Writes**: Added PID-safe file locks, atomic `Inventory.csv` and `Master_Checklist.csv` writes, a TCDB queue gate, and tracked browser driver cleanup.
- **Deskew Coordinate Consistency**: Unified deskew coordinate transforms and added a back-emblem `ink_spot` guard to reduce false surface defect flags on card backs.

### UI & Workflow
- **Fine Geometry Controls**: Added `0.1°` rotation step controls in the Grading Deep-Dive inspector for precise border alignment.
- **Fetch Hygiene**: Hardened client-side API fetch error handling and state synchronization across `App.jsx`.

### Bug Fixes
- Fixed coordinate drift between preview overlays and deskewed crop regions during manual geometry adjustments.
- Resolved race conditions when multiple worker slots accessed shared checklist or inventory files concurrently.

---

## [v0.25.0-beta.4] — 2026-11-22 — Track 2C: Deep-Dive Grading UI, Virtual Centering Gauge, CV Calibration & TCDB 403 Breaker

### Features & Improvements
- **Multi-Format Card Detection**: Added center-out edge detection, NMS clustering, drop-shadow edge detection, guarded 3-edge solver, and support for both Standard and Allen & Ginter Mini card formats.
- **Defect Recall & Precision Calibration**: Tuned pinstripe, margin-bleed, bio-text `ink_spot`, Stadium Club back recovery, and foil-tear calibration with PSA/BGS sub-grade ceilings.
- **TCDB 403 Circuit Breaker**: Added automated 403 circuit breaker and backoff protections to TCDB scraping pipelines to prevent IP rate-limit lockouts.

### UI & Workflow
- **Viewport-Locked Grading Deep-Dive**: Built a zero-scrollbar Deep-Dive Grading workspace with `10x` corner loupes, zoom/pan controls, PSA/BGS slab labels, and a Flag Error feedback loop.
- **Legends-Style Virtual Centering Gauge**: Added interactive centering geometry editing, virtual deskew, and **Apply Gauge & Re-Evaluate** workflow.

### Bug Fixes
- Prevented scanner streaks and sleeve glare from blinding edge detection and triggering false surface-crease penalties.

---

## [v0.25.0-beta.3] — 2026-11-21 — Tracks 2A, 2B & 3: DirectML DINOv2 Vision, Through-Sleeve Surface Defects & Market Comps

### Features & Improvements
- **DirectML DINOv2 Neural Vision (`Core/neural_vision.py`)**: Added micro-batched DirectML DINOv2 neural vision embeddings with multi-region spatial patches and color/foil parallel matching.
- **Through-Sleeve Surface Defect Engine (`Core/surface_defect_engine.py`)**: Introduced GPU-accelerated surface defect and sleeve-artifact discrimination.
- **Exact-Card Market Comps & Pricing (`Core/market_engine.py`, `Core/sales_engine.py`)**: Added exact-card trimmed median comps, `Valuation_Source` tracking, and auto-recalculating Sales Strategy pricing.

### UI & Workflow
- **Valuation Source Visibility**: Surfaced `Valuation_Source` and trimmed median comp breakdowns in inventory and sales strategy views.

### Bug Fixes
- Improved parallel matching accuracy on foil and refractor cards where global color histograms previously caused false matches.

---

## [v0.25.0-beta.2] — 2026-11-21 — Track 1: Incremental TCDB Checkpointing, Tier Hints & Instant Plan Preview

### Features & Improvements
- **Incremental TCDB Checkpointing (`Core/scraper_engine.py`)**: Implemented per-set checkpointing, tier hints, smart image sync, and pre-run plan previews.
- **Single-Pass Plan Preview & Cache Invalidation**: Added single-pass multi-mode plan preview and file modification-time (`mtime`) checklist cache invalidation.

### UI & Workflow
- **Instant Set Scraper Tab Switching**: Eliminated redundant reloads when switching tabs in the Set Scraper & Set Library workspace.

### Bug Fixes
- Prevented interrupted TCDB set scrapes from re-downloading already verified checklist rows and reference images.

---

## [v0.25.0-beta.1] — 2026-11-21 — Home Dashboard, Logo Navigation & Configurable Sandbox Port

### Features & Improvements
- **Dashboard Aggregation API (`/api/dashboard/summary`)**: Added backend summary aggregation for inventory, batches, valuations, and worker status.
- **Configurable Port & Dynamic Origin**: Added `--port` CLI support in `launch_tabulas_hub.py` and dynamic `API_ORIGIN` resolution (with `http://localhost:5000` fallback) in `App.jsx` for isolated sandbox testing.

### UI & Workflow
- **Home Dashboard & Logo Navigation**: Added the Home Dashboard overview page and clickable top-left logo navigation back to Home.

### Bug Fixes
- Fixed hardcoded origin assumptions so running the hub on alternate ports routes API and asset requests cleanly.

---

## [v0.24.0-beta.48] — 2026-11-21 — Atomic Persistence, Cross-Process Locking, UI Polish & Audit Fixes

### Features & Improvements
- **Atomic Persistence & Thread Safety**: Added atomic file writes, cross-process file locking, `RLock` protection for neural embedding caches, and worker race-condition hardening.
- **Atomic Checklist Writes**: Ensured Master Checklist and per-set checklist updates write atomically without partial-file corruption.

### UI & Workflow
- **Guided Review Bulk Auto-Clear**: Added bulk auto-clear support in Guided Batch Review alongside improved loading states and error banners.
- **Codebase Cleanup**: Removed dead code and unified error handling across `App.jsx` and `launch_tabulas_hub.py`.

### Bug Fixes
- Fixed a GPU slot leak during compute benchmarks that could leave a worker slot appearing busy.

---

## [v0.24.0-beta.47] — 2026-11-21 — REST API Guards, Comps Cache & Listing Writer Fixes

### Features & Improvements
- **REST API & Static Path Security**: Fixed REST API route handling, added static path traversal guards, exposed daily logs endpoints, and hardened safe `Sale_ID` generation.
- **Inventory & Comps Cache Restoration**: Restored Inventory Replace Scans and Comps Cache workflows.

### UI & Workflow
- **Listing Writer & Client Stability**: Fixed Listing Writer saves and stabilized client-side ID generation.

### Bug Fixes
- Resolved stale closure bugs in background status pollers that could display outdated job progress.

---

## [v0.24.0-beta.46] — 2026-11-21 — Stability Fixes, 3-Drive Scheduler Standardization & GPU Decoupling

### Features & Improvements
- **3-Drive Scheduler Standardization**: Standardized `C:` / `D:` / `F:` paths across background workers, deduplicated parallel worker slots, and enforced cache-only market comps lookups.
- **GPU Compute Decoupling**: Decoupled GPU compute settings from vision grading so CPU fallback and DirectML configuration operate independently.

### Bug Fixes
- Fixed critical crashes and data-safety issues across database, rate learner, scraper engine, vision grader, and CLI worker pipelines.

---

## [v0.24.0-beta.45] — 2026-11-21 — Baseline 3-Drive Tabulas Card Hub Release

### Features & Improvements
- **3-Drive Architecture Baseline**: Established canonical `C:\Tabulas Card Hub` (App & Data), `D:\Tabulas Set Library` (Collection, Scans & Reference Library), and `F:\Tabulas Archive` (Archives & Snapshots) layout with 8-slot parallel worker execution (`slot_1`–`slot_8`).
