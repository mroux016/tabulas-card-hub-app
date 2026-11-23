# Tabulas Card Hub — Deep-Dive Engineering Audit (`DEBUG_AUDIT.md`)

**Workspace Audited:** `C:\Tabulas Card Hub\App_Sandbox`  
**Audit Mode:** Strict Read-Only Code & Empirical Fixture Audit (Zero Application Mutations)  
**Baseline Verification:** `py_compile` passed across all 20 Python modules; isolated `pytest tests` passed (`49 passed in 20.34s`).  
**Modules Audited:** `launch_tabulas_hub.py`, `cli.py`, `App.jsx`, `Core/vision_grader.py`, `Core/surface_defect_engine.py`, `Core/scraper_engine.py`, `Core/database.py`, `Core/config.py`, `Core/market_engine.py`, `Core/compute_backend.py`, `Core/neural_vision.py`, `Core/rate_learner.py`, `Core/sales_engine.py`, `Core/label_engine.py`.

---

## Executive Summary

| ID | Severity | Focus Area | Title | Primary Location |
| :--- | :--- | :--- | :--- | :--- |
| **CRIT-01** | **Critical** | Concurrency & File Integrity | `interprocess_file_lock` Unconditionally Breaks Active Locks After 20s/30s Even While Holder PID Is Alive | `Core/config.py:1202-1284` |
| **CRIT-02** | **Critical** | Concurrency & File Integrity | Unlocked Read-Modify-Write on `Inventory.csv` Across Background Workers and HTTP Endpoints Loses Concurrent Commits/Edits | `Core/database.py:527-605`, `cli.py:1870-1881`, `Core/vision_grader.py:7613-8429`, `launch_tabulas_hub.py:1850-2716` |
| **CRIT-03** | **Critical** | Concurrency & File Integrity | Non-Atomic In-Place Writes (`open(..., "w")` / `.to_csv()` / `.write_text()`) on Live CSVs, Manifests, Catalogs & `Master_Checklist.csv` | `launch_tabulas_hub.py:625-656, 1998`, `Core/database.py:1309, 1424`, `Core/vision_grader.py:7602`, `Core/scraper_engine.py:2687, 3007, 3049` |
| **CRIT-04** | **Critical** | Coordinate & Grading Math | Virtual Deskew Coordinate Space Mismatch Between `outer_card_rect`/`inner_frame_rect` (Deskewed) and `corners`/`bbox_norm` (Original Image) | `Core/vision_grader.py:5480-5518, 5693-5720, 6047-6118, 6708-6715`, `App.jsx:3027-3039` |
| **CRIT-05** | **Critical** | Scraper & Worker Resilience | TCDB Rate-Limit Bypass: Concurrent TCDB Scrapers Launch When Queued Behind Non-TCDB Jobs or Across Continuation Transitions | `cli.py:309-316, 549-565, 2006-2022` |
| **HIGH-01** | **High** | Concurrency & File Integrity | Cross-Process Race on `job_queue_<lane>.json` & Process-Local `_SLOT_DISPATCH_LOCK` Drops Enqueued Jobs | `cli.py:173, 357-399, 545, 2006-2022` |
| **HIGH-02** | **High** | Scraper & Worker Resilience | `stop_active_job` Orphans `job_queue_<lane>.json` (Permanently Bricking the Worker Slot) and Cooperative Stop Overwrites `"STOPPED"` With `"COMPLETED"` | `cli.py:296-306, 481-495, 1371-1382, 1966-2022` |
| **HIGH-03** | **High** | Coordinate & Grading Math | `_stable_defect_id` Computed in Deskewed Coordinates Before Inverse Mapping Causes Dismissed Defects to Resurrect When `skew_deg` Changes | `Core/surface_defect_engine.py:1563-1568, 2121`, `Core/vision_grader.py:6054-6118` |
| **HIGH-04** | **High** | Coordinate & Grading Math | Cross-Category NMS Merging in `_cluster_and_nms_defects` Silently Erases Corner/Edge Penalties Overlapping Surface Defects | `Core/surface_defect_engine.py:71-135` |
| **HIGH-05** | **High** | Coordinate & Grading Math | Manual `Raw_Price` & `Valuation_Source` Clobbered by Cached Comps in `compute_tier_aware_roi_and_recommendation` and Lost in `replace_card_images_from_bytes` / `fix_card_rotations_and_regrade` | `Core/market_engine.py:1631-1643`, `Core/vision_grader.py:8417-8429, 8719-8730` |
| **HIGH-06** | **High** | Coordinate & Grading Math | Batch/Inventory Regrade, Reprocess, Rotation Fixer & Image Replacement Ignore Sidecar `overrides` and Desync `Cache/Grading_Diagnostics/<SKU>.json` | `Core/vision_grader.py:7519, 7589, 7640, 7808, 8142, 8370, 8714` |
| **HIGH-07** | **High** | Frontend (`App.jsx`) | Out-of-Order Async `/api/grading/inspect-card` Fetch Race Overwrites Active Diagnostics on `Re-Scan` + Action or Prop Changes | `App.jsx:2081-2113, 2284-2373, 3532-3564` |
| **HIGH-08** | **High** | Frontend (`App.jsx`) | Stale Browser Image Cache After In-Place Rotation or Image Replacement Misaligns `<img src>` With Updated SVG Overlays | `App.jsx:2167-2177, 2241-2256, 9881-9883`, `launch_tabulas_hub.py:960-965, 1214` |
| **HIGH-09** | **High** | Quick Win (`ink_spot` FPs) | 40 Clean-Card Back-Emblem `ink_spot` False Positives Bypass Text/Glyph Proximity Guard Due to `area < 165.0 or max(bw, bh) <= 14` Gate | `Core/surface_defect_engine.py:1308-1328` |
| **MED-01** | **Medium** | Coordinate & Grading Math | PSA/BGS Ceiling & Tier Label Asymmetry (`Est_PSA = 7.0` While `Est_BGS = 9.0` With `"NM"` Label) + Subgrade Overrides Ignored by Defect Count Ceilings | `Core/vision_grader.py:5871-5921, 5979` |
| **MED-02** | **Medium** | Coordinate & Grading Math | `_map_bbox_norm_inverse` Allows `x + w > 1.0` or `y + h > 1.0` Near Bottom/Right Image Boundaries | `Core/vision_grader.py:879-899` |
| **MED-03** | **Medium** | Concurrency & File Integrity | Multi-Process Last-Writer-Wins Overwrite on `NEURAL_EMBEDDINGS_CACHE_FILE` (`neural_embeddings_v25.pkl`) Across Parallel Worker Slots | `Core/neural_vision.py:789-834` |
| **MED-04** | **Medium** | Concurrency & File Integrity | Thread-Unsafe Global DataFrame Caches (`_CHK_MASTER_CACHE`, `_CHK_SET_CACHE`, `_INV_MEM_CACHE`, `_DIR_MEM_CACHE`) in `ThreadingHTTPServer` | `launch_tabulas_hub.py:375-411, 480-531, 1380-1396` |
| **MED-05** | **Medium** | Scraper & Worker Resilience | Non-Atomic `dest_path.write_bytes(res.content)` in `_download_single_template_side` Permanently Caches Truncated Images on Crash/Stop | `Core/scraper_engine.py:4757-4758, 4836` |
| **MED-06** | **Medium** | Scraper & Worker Resilience | `cleanup_orphaned_drivers()` Executes System-Wide `taskkill /F /IM chromedriver.exe` Across All Processes | `Core/scraper_engine.py:396-409, 436, 468`, `launch_tabulas_hub.py:3026-3030` |
| **MED-07** | **Medium** | Frontend (`App.jsx`) | `GradingDeepDiveStudio` Fails to Reset `flagPresetId`, `showFlagModal`, `loupeZoom`, and `diagError` When Switching `Front` ↔ `Back` | `App.jsx:2115-2128, 1804-1806, 2746` |

---

## 1. Critical Severity Findings

### [CRIT-01] `interprocess_file_lock` Unconditionally Breaks Active Locks After `timeout=20s` or `stale_seconds=30s` Even While Holder PID Is Alive
- **File & Lines:** `Core/config.py:1202-1284` (specifically lines `1251-1260` and `1273-1279`)
- **Audit Area:** 1. Concurrency, State & File Integrity
- **Root Cause:**
  1. At lines `1252-1253`, `if (now_t - st.st_mtime) > float(stale_seconds): should_break = True` marks a `.lock` file stale based solely on file age (`> 30.0s`) **without checking whether `holder_pid` is still alive** (`_is_lock_holder_pid_alive(holder_pid)` is only checked in the `elif` branch at line `1254`).
  2. Worse, at lines `1273-1279` (`if now_t >= deadline: lp.unlink(); break`), when `timeout=20.0s` expires (which is shorter than `stale_seconds=30.0s`), the waiting process forcibly unlinks the active lock holder's `.lock` file and enters the `yield` block with `acquired_os_lock = False`.
- **Reproduction Condition:** Run `commit_batch_to_inventory_v2` (`Core/database.py:1754-1763`), which holds `INVENTORY_FILE.with_suffix(".csv.lock")` while `sync_inventory_copy_numbers_and_files()` walks `REVIEWED_CARDS_DIR.rglob("*.jpg")` and renames files across disk (`>20s` on a large collection), while any second writer calls `save_inventory_df()`. At `t = 20.0s`, the second writer deletes the active lock file and overwrites `Inventory.csv` concurrently with the commit.
- **Fix Plan:** Only break a lock file when `holder_pid > 0 and holder_pid != os.getpid() and not _is_lock_holder_pid_alive(holder_pid)` (or when `holder_pid == 0` and `(now_t - st.st_mtime) > stale_seconds`), and raise `TimeoutError` at `now_t >= deadline` instead of unlinking an active lock and entering `yield` unlocked.

---

### [CRIT-02] Unlocked Read-Modify-Write on `Inventory.csv` Across Background Workers and HTTP Endpoints Loses Concurrent Commits/Edits
- **File & Lines:** `Core/database.py:527-605` (`load_inventory_df`, `save_inventory_df`), `cli.py:1870-1881` (`refresh_market_valuations`), `Core/vision_grader.py:7613-7655` (`regrade_inventory_cards`), `Core/vision_grader.py:7940-8177` (`reprocess_inventory_skus`), `Core/vision_grader.py:8238-8429` (`fix_card_rotations_and_regrade`), `launch_tabulas_hub.py:1850-1916` (`POST /api/inventory`), `2505-2508` (`POST /api/sold-cards`), `2709-2716` (`POST /api/labels/mark-printed`)
- **Audit Area:** 1. Concurrency, State & File Integrity
- **Root Cause:** `save_inventory_df` (`Core/database.py:599-605`) acquires `interprocess_file_lock(inv_lock)` only around the final `atomic_write_bytes` write, while `load_inventory_df()` (`line 527`) is completely unlocked. Long-running background worker slots load `inv_df = load_inventory_df()` at job start, compute for seconds or minutes on an in-memory snapshot, and then call `save_inventory_df(updated_inv)`, blindly replacing the entire `Inventory.csv` file.
- **Reproduction Condition:** Start `refresh_market_valuations` or `regrade_inventory` on a worker slot; while it runs, commit a batch, record a sold card, mark labels printed, or dismiss a defect in `GradingDeepDiveStudio`. When the background job completes, `save_inventory_df(updated_inv)` overwrites `Inventory.csv` with its stale snapshot, permanently erasing every SKU committed or edited during the job.
- **Fix Plan:** Add a locked `update_inventory_df_atomic(mutator_fn)` context manager that holds `interprocess_file_lock(inv_lock)` across the read-merge-write cycle, and have long-running workers re-read `Inventory.csv` under the lock at completion to merge only their mutated columns/rows keyed by `SKU`.

---

### [CRIT-03] Non-Atomic In-Place File Writes (`open(..., "w")` / `.to_csv()` / `.write_text()`) on Live CSVs, Batch Manifests, Catalogs & `Master_Checklist.csv`
- **File & Lines:**
  - `launch_tabulas_hub.py:625-643` (`_write_csv_records`, called by `/api/notifications`, `/api/notifications/clear`, `/api/sold-cards`, `/api/sold-cards/delete` at lines `2439, 2455, 2501, 2524`)
  - `launch_tabulas_hub.py:654-656` (`_write_json_file`)
  - `launch_tabulas_hub.py:1998` (`res_df.to_csv(man_p)` in `POST /api/batches/update`)
  - `Core/database.py:1309` (`df.to_csv(manifest_path)` in `apply_manifest_overrides_and_rename`) and `Core/database.py:1424` (`df.to_csv(manifest_path)` in `commit_batch_to_inventory`)
  - `Core/vision_grader.py:7602` (`df.to_csv(manifest_path)` in `regrade_batch_cards`)
  - `Core/scraper_engine.py:2687` (`save_catalog`), `3007` and `3049-3051` (`sync_set_library_download_status` writing `Set_Checklists/<Set>.csv` and `Master_Checklist.csv` directly via `.to_csv()`, then copying the in-place file to `CHECKLIST_BACKUP_PATH`)
- **Audit Area:** 1. Concurrency, State & File Integrity
- **Root Cause:** These code paths open target files directly in `"w"` mode instead of writing to a PID/thread-unique `.tmp` sibling and calling `os.replace()` (`atomic_write_bytes` / `atomic_write_text`) under `interprocess_file_lock`. In `sync_set_library_download_status` (`Core/scraper_engine.py:3049-3051`), `master_df.to_csv(CHECKLIST_PATH)` truncates the 76 MB `Master_Checklist.csv` in place and immediately copies it over `CHECKLIST_BACKUP_PATH`.
- **Reproduction Condition:** Concurrent `ThreadingHTTPServer` requests (e.g., two worker completion notifications calling `_write_csv_records(NOTIFICATIONS_FILE, ...)` simultaneously, or saving a card in Guided Review while `regrade_batch` is writing `Batch_Inventory_Manifest.csv`), or killing a job during `sync_set_library_download_status`, truncates or corrupts the live CSV/JSON and its backup.
- **Fix Plan:** Replace direct `open(..., "w")`, `.write_text()`, and `.to_csv(path)` calls in `_write_csv_records`, `_write_json_file`, `save_catalog`, batch manifest writers, and `sync_set_library_download_status` with `atomic_write_bytes` / `atomic_write_text` wrapped in `interprocess_file_lock(path.with_suffix(path.suffix + ".lock"))`.

---

### [CRIT-04] Virtual Deskew Coordinate Space Mismatch Between `outer_card_rect`/`inner_frame_rect` (Deskewed Space) and `corners`/`bbox_norm` (Original Image Space)
- **File & Lines:** `Core/vision_grader.py:5480-5518`, `5693-5720`, `6047-6118`, `6708-6715`; `App.jsx:3027-3039`
- **Audit Area:** 2. Coordinate, Geometry & Grading Math
- **Root Cause:** When `abs(skew_deg) >= 0.35`, `estimate_card_pregrade` deskews the image (`_deskew_image_and_box`, line `6047`) and passes `front_work_img` and `inv_matrix=front_M_inv` to `_measure_side_centering` (`line 6073`). Inside `_measure_side_centering`:
  1. `default_corners` are inverse-mapped back to original skewed image space via `_map_point_norm_inverse(..., inv_matrix)` (`lines 5712-5714`), and surface defects' `bbox_norm` are inverse-mapped via `_map_bbox_norm_inverse` (`lines 6105-6117`), **but `outer_rect` (`lines 5693-5698`) and `inner_rect` (`lines 5699-5704`) are saved in deskewed coordinates** and rendered as unrotated axis-aligned SVG rectangles on top of the original skewed image (`App.jsx:3027-3039`).
  2. When the user drags `outer_card_rect` or `inner_frame_rect` on the original unrotated image in `App.jsx` (`saveGeometryEdit` / `applyGaugeAndReevaluate`), `_measure_side_centering` (`lines 5480-5485, 5508-5513`) applies `manual_outer_rect` and `manual_inner_rect` directly to `front_work_img` (the **deskewed** image) without forward-mapping through `M`.
  3. When `update_card_grading_geometry` receives manual `corners` (`lines 6709-6712`), it computes an axis-aligned bounding box `outer_r = [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]` from the **skewed** corners and applies that inflated box to the **deskewed** image, artificially widening the outer card box by $H \cdot \sin(|\theta|)$ (e.g., ~73 px on a 700×1000 card at $6^\circ$ skew) and corrupting L/R and T/B centering ratios.
- **Reproduction Condition:** Open any card with `|skew_deg| >= 1.5°` in `GradingDeepDiveStudio` and use `Edit Corners` → `Save & Recalculate` (or `Apply Gauge & Re-Evaluate`): the outer box expands horizontally and shifts L/R centering ratios even when the 4 corners sit tightly on the physical card corners.
- **Fix Plan:** In `update_card_grading_geometry` and `_measure_side_centering`, forward-map manual `corners` (and manual outer/inner rects defined in original image space) through the deskew affine matrix `M` before computing axis-aligned `[x, y, w, h]` border distances on `front_work_img`.

---

### [CRIT-05] TCDB Rate-Limit Bypass: Concurrent TCDB Scrapers Launch When Queued Behind Non-TCDB Jobs or Across Continuation Transitions
- **File & Lines:** `cli.py:309-316` (`_find_running_heavy_tcdb_slot`), `cli.py:549-565` (`start_or_queue_background_job`), `cli.py:2006-2022` (`run_background_job_from_file` `finally:` block)
- **Audit Area:** 4. Scraper & Worker Resilience
- **Root Cause:**
  1. `_find_running_heavy_tcdb_slot()` (`cli.py:309-316`) only checks whether any slot currently has `st.get("status") == "RUNNING"` with a TCDB rate-limited `job_type`; it never checks whether any slot's queue (`load_lane_job_queue(sk)`) already contains a queued TCDB job.
  2. When a worker finishes a job, its `finally:` block (`cli.py:2015-2022`) launches the next queued item with `is_queued_continuation=True`, which completely bypasses the `if _is_tcdb_rate_limited_job(...) and not is_queued_continuation:` check at `cli.py:549`.
- **Reproduction Condition:**
  - *Path A:* All 8 slots are running non-TCDB jobs; user starts TCDB Job A, which queues on `slot_1` (`cli.py:578`). `slot_2` finishes its non-TCDB job; user starts TCDB Job B. `_find_running_heavy_tcdb_slot()` sees no `RUNNING` TCDB job and launches TCDB Job B on `slot_2`. When `slot_1` finishes its non-TCDB job, its `finally:` block pops TCDB Job A and launches it on `slot_1` with `is_queued_continuation=True`. Both TCDB scrapers now hit `tcdb.com` in parallel.
  - *Path B:* `slot_1` finishes TCDB Job A and writes `status = "COMPLETED"` (`line 1966`) before spawning queued TCDB Job B (`line 2015`); a new TCDB job submitted during that window sees zero `RUNNING` TCDB slots and starts concurrently on `slot_2`.
- **Fix Plan:** Update `_find_running_heavy_tcdb_slot()` to also return any slot whose `load_lane_job_queue(sk)` contains a TCDB rate-limited job, and enforce the `_find_running_heavy_tcdb_slot()` check even when `is_queued_continuation=True` (re-queuing onto the active TCDB slot if another slot is already running a TCDB job).

---

## 2. High Severity Findings

### [HIGH-01] Cross-Process Race on `job_queue_<lane>.json` & Process-Local `_SLOT_DISPATCH_LOCK` Drops Enqueued Jobs
- **File & Lines:** `cli.py:173`, `cli.py:357-399` (`load_lane_job_queue`, `save_lane_job_queue`, `enqueue_job_for_lane`, `remove_queued_job`), `cli.py:545`, `cli.py:2006-2022`
- **Audit Area:** 1. Concurrency, State & File Integrity / 4. Scraper & Worker Resilience
- **Root Cause:** `_SLOT_DISPATCH_LOCK` (`cli.py:173`) is an in-process `threading.Lock()` that only serializes threads inside `launch_tabulas_hub.py`, not child `cli.py --bg-job` worker processes. When a worker subprocess finishes and executes `pending_q = load_lane_job_queue(base_lane); next_item = pending_q.pop(0); save_lane_job_queue(base_lane, pending_q)` (`cli.py:2006-2009`), it performs an unlocked read-modify-write using non-atomic `.write_text()` (`cli.py:369`).
- **Reproduction Condition:** Enqueue a job via `POST /api/jobs/start` (or remove one via `/api/jobs/queue/remove`) while the active worker on that slot is completing and popping `job_queue_<lane>.json`; the worker's `save_lane_job_queue` overwrites the newly appended queue item.
- **Fix Plan:** Guard `enqueue_job_for_lane`, `remove_queued_job`, `clear_lane_job_queue`, and the `finally:` pop in `run_background_job_from_file` with `interprocess_file_lock(get_lane_queue_file(base_lane).with_suffix(".json.lock"))` and write via `atomic_write_text`.

---

### [HIGH-02] `stop_active_job` Orphans `job_queue_<lane>.json` (Permanently Bricking the Worker Slot) and Cooperative Stop Overwrites `"STOPPED"` With `"COMPLETED"`
- **File & Lines:** `cli.py:296-306` (`_is_slot_currently_busy`), `cli.py:481-495` (`stop_active_job`), `cli.py:1371-1382` (`_stop_check_cb`), `cli.py:1966-2022`
- **Audit Area:** 4. Scraper & Worker Resilience
- **Root Cause:**
  1. `stop_active_job` (`cli.py:488`) runs `taskkill /F /T /PID <pid>`, terminating the worker subprocess immediately so its `finally:` block (`cli.py:2000-2022`, which releases the GPU slot and pops the next queued job from `job_queue_<lane>.json`) never executes. Because `_is_slot_currently_busy(slot_key)` (`cli.py:304`) returns `True` whenever `len(load_lane_job_queue(slot_key)) > 0`, any slot with queued items when stopped remains permanently `"busy"` (`status="STOPPED"` with non-empty queue) and never runs its queued jobs or accepts new jobs.
  2. If a job exits its loop cooperatively via `is_stop_requested()` (`cli.py:1378`) before `taskkill` kills the process, execution reaches `write_job_state("COMPLETED", ...)` at `cli.py:1966`, overwriting `"STOPPED"` with `"COMPLETED"`.
- **Reproduction Condition:** Queue 2 jobs on `slot_1`, then click **Stop** on the active job in `slot_1`: Job 1 is killed, Job 2 never launches, and `slot_1` is permanently unavailable until `job_queue_slot_1.json` is manually cleared.
- **Fix Plan:** In `stop_active_job`, either advance or clear `job_queue_<lane>.json` (and in `_is_slot_currently_busy`, treat a slot with `status != "RUNNING"` and a dead PID as idle or auto-launch the head of its orphaned queue), and in `run_background_job_from_file` check `if _stop_check_cb(): write_job_state("STOPPED", ...)` before writing `"COMPLETED"`.

---

### [HIGH-03] `_stable_defect_id` Computed in Deskewed Coordinates Before Inverse Mapping Causes Dismissed Defects to Resurrect When `skew_deg` Changes
- **File & Lines:** `Core/surface_defect_engine.py:1563-1568`, `2121`; `Core/vision_grader.py:6054-6118`
- **Audit Area:** 2. Coordinate, Geometry & Grading Math
- **Root Cause:** `_inspect_single_side` generates `item["id"] = _stable_defect_id(side_label, dtype, b_norm, used_ids)` (`Core/surface_defect_engine.py:1568`) and filters `dismissed_ids` (`line 2121`) using `b_norm` in **deskewed** image coordinates (`front_work_img`), *before* `estimate_card_pregrade` (`Core/vision_grader.py:6117`) maps `d_item["bbox_norm"] = _map_bbox_norm_inverse(...)` back into original image coordinates.
- **Reproduction Condition:** Dismiss a defect on a card in `GradingDeepDiveStudio`, then adjust the Centering Gauge rotation slider (`skew_deg`) by $1^\circ$–$2^\circ$ and click `Apply Gauge & Re-Evaluate`. Because `b_norm` in deskewed space shifts with `skew_deg`, its quantized grid bucket (`int(round(cx * 50))`) changes and no longer matches `overrides.dismissed_defect_ids`, causing the dismissed defect to reappear.
- **Fix Plan:** Pass the inverse affine matrix `M_inv` into `inspect_card_surface_through_sleeve` (or recompute `_stable_defect_id` and filter `dismissed_defect_ids` in `estimate_card_pregrade` after `_map_bbox_norm_inverse` maps `bbox_norm` to canonical original-image coordinates).

---

### [HIGH-04] Cross-Category NMS Merging in `_cluster_and_nms_defects` Silently Erases Corner/Edge Penalties Overlapping Surface Defects
- **File & Lines:** `Core/surface_defect_engine.py:71-135` (`_boxes_close` at `lines 80-97` and `_cluster_and_nms_defects` at `lines 100-135`)
- **Audit Area:** 2. Coordinate, Geometry & Grading Math
- **Root Cause:** `_boxes_close(a, b)` checks `a.get("side") == b.get("side")` and bounding-box overlap (`inter > 0` or center distance `<= 0.035`), without checking whether `a` and `b` belong to the same subgrade category (`category` / `target`: `"surface"`, `"edges"`, `"corners"`). When a `surface_scratch` or `print_line` bounding box overlaps an `edge_chipping`, `edge_dent`, or `corner_whitening` box, BFS clustering merges them into one representative defect (`max(cluster, ...)`, `line 122`), discarding the other category's defect and its subgrade penalty.
- **Reproduction Condition:** Grade a card where a `surface_scratch` (`severity=1.0, target="surface"`) reaches the card border and overlaps an `edge_chipping` (`severity=0.5, target="edges"`): `_cluster_and_nms_defects` drops the `edge_chipping` defect, leaving `Sub_Edges = 9.5`.
- **Fix Plan:** In `_boxes_close` (`Core/surface_defect_engine.py:81`), require `str(a.get("category") or a.get("target") or "") == str(b.get("category") or b.get("target") or "")` so NMS only merges defects targeting the same subgrade category.

---

### [HIGH-05] Manual `Raw_Price` & `Valuation_Source` Clobbered by Cached Comps in `compute_tier_aware_roi_and_recommendation` and Lost in `replace_card_images_from_bytes` / `fix_card_rotations_and_regrade`
- **File & Lines:** `Core/market_engine.py:1631-1643`, `Core/vision_grader.py:8417-8429` (`fix_card_rotations_and_regrade`), `Core/vision_grader.py:8719-8730` (`replace_card_images_from_bytes`)
- **Audit Area:** 2. Coordinate, Geometry & Grading Math
- **Root Cause:**
  1. In `compute_tier_aware_roi_and_recommendation` (`Core/market_engine.py:1635-1640`), `if comp_verified:` is evaluated **before** `elif existing_val_src.lower() == "manual" and existing_raw > 0.0:`. Whenever a card has a cached entry in `Market_Comps.csv` and the user later sets a manual `Raw_Price` (`Valuation_Source="Manual"`), calling `recalculate_dataframe_multi_grader_roi` overwrites the user's manual price and resets `Valuation_Source` to `"Verified SCP Exact"`.
  2. In `fix_card_rotations_and_regrade` (`Core/vision_grader.py:8417-8429`) and `replace_card_images_from_bytes` (`lines 8719-8730`), the code saves and restores `Raw_Price` and `Rec_Sale_Price` around `recalculate_dataframe_multi_grader_roi`, but fails to save/restore `Valuation_Source` (unlike `_apply_csv_grade_and_cache_roi` at `line 6272`), and for batch cards (`is_inventory == False` at `line 8726`) `replace_card_images_from_bytes` does not restore `saved_raw` or `saved_rec` at all.
- **Reproduction Condition:** Set a manual `Raw_Price` (`Valuation_Source="Manual"`) on a card, then run `Replace Images` or `Rotation Fixer` (or `regrade_inventory_cards` on a card with a cached comp): `Valuation_Source` is overwritten to `"Uncomped"` or `"Verified SCP Exact"`, and manual batch prices are wiped.
- **Fix Plan:** In `compute_tier_aware_roi_and_recommendation` (`Core/market_engine.py:1635`), check `if existing_val_src.lower() == "manual" and existing_raw > 0.0:` before `elif comp_verified:`, and delegate post-grade ROI recalculation in `replace_card_images_from_bytes` and `fix_card_rotations_and_regrade` to `_apply_csv_grade_and_cache_roi`.

---

### [HIGH-06] Batch/Inventory Regrade, Reprocess, Rotation Fixer & Image Replacement Ignore Sidecar `overrides` and Desync `Cache/Grading_Diagnostics/<SKU>.json`
- **File & Lines:** `Core/vision_grader.py:7519` (`grade_card_images`), `7589` (`regrade_batch_cards`), `7640` (`regrade_inventory_cards`), `7808` (`reprocess_batch_cards`), `8142` (`reprocess_inventory_skus`), `8370` (`fix_card_rotations_and_regrade`), `8714` (`replace_card_images_from_bytes`)
- **Audit Area:** 2. Coordinate, Geometry & Grading Math / 1. File Integrity
- **Root Cause:** All 7 batch/inventory regrade and reprocess functions call `estimate_card_pregrade(f_im, b_im, front_box=..., back_box=...)` without loading existing per-card `overrides` from `get_grading_diagnostics_path(...)` and without passing `diagnostics_path=diag_path`.
- **Reproduction Condition:** Dismiss a false-positive defect or calibrate centering/subgrades on SKU `INV-00100` in `GradingDeepDiveStudio` (which persists `overrides` in `Cache/Grading_Diagnostics/INV-00100.json` and updates `Inventory.csv`), then run `Regrade Inventory` or `Reprocess SKU`. `Inventory.csv` reverts to the un-overridden grade while `Cache/Grading_Diagnostics/INV-00100.json` still shows the old diagnostics and overrides, causing the table row and the Deep-Dive modal to display different grades for the same SKU.
- **Fix Plan:** Before calling `estimate_card_pregrade` in regrade/reprocess/replace routines, resolve `diag_path = get_grading_diagnostics_path(...)`, load `existing_overrides = (load_grading_diagnostics(diag_path) or {}).get("overrides")`, and pass `overrides=existing_overrides, diagnostics_path=diag_path` to `estimate_card_pregrade`.

---

### [HIGH-07] Out-of-Order Async `/api/grading/inspect-card` Fetch Race Overwrites Active Diagnostics on `Re-Scan` + Action or Prop Changes
- **File & Lines:** `App.jsx:2081-2113` (`fetchDiagnostics` and `useEffect`), `App.jsx:2284-2373` (`saveGeometryEdit`, `applyGaugeAndReevaluate`), `App.jsx:3532-3564` (1-click Loupe dismissal)
- **Audit Area:** 3. Frontend (`App.jsx` — classic React/Babel)
- **Root Cause:** `fetchDiagnostics` (`App.jsx:2081-2101`) uses neither an `AbortController` nor a monotonically increasing request ID / mounted guard. Although the three parent call sites pass `key={...sku}` (`App.jsx:7304, 8040, 9834`), an unmounted component's in-flight `fetchDiagnostics` still executes `if (forceRefresh && onCardUpdated) onCardUpdated(res)` on resolution (`line 2094`), and within a mounted component, clicking `🔄 Re-Scan` (`fetchDiagnostics(true)`, ~500 ms uncached CV pass) and then clicking `✓ Not a Defect` or `Save & Recalculate` allows the slower `inspect-card` response to resolve last and clobber the newer `diagnostics` state.
- **Reproduction Condition:** In `GradingDeepDiveStudio`, click `🔄 Re-Scan` and immediately click `✓ Not a Defect` on a defect (or rapidly click `Next` right after clicking `🔄 Re-Scan`): the slow `inspect-card` response resolves after the dismissal POST (or after unmount) and overwrites `diagnostics` / invokes `onCardUpdated` with stale data.
- **Fix Plan:** Add a `reqSeqRef = useRef(0)` and `AbortController` inside `GradingDeepDiveStudio`; abort in-flight fetches in the `useEffect` cleanup and ignore any response where `myReqId !== reqSeqRef.current` or `res.sku !== sku`.

---

### [HIGH-08] Stale Browser Image Cache After In-Place Rotation or Image Replacement Misaligns `<img src>` With Updated SVG Overlays
- **File & Lines:** `App.jsx:2167-2177` (`frontUrl`, `backUrl`), `App.jsx:2241-2256` (`buildCropUrl`), `App.jsx:9881-9883` (`SideBySideCardComparison`); `launch_tabulas_hub.py:960-965`, `1214`
- **Audit Area:** 3. Frontend (`App.jsx` — classic React/Babel)
- **Root Cause:** `POST /api/inventory/rotate-image`, `POST /api/batches/rotate-image`, and `POST /api/inventory/replace-images` overwrite the `.jpg` file on disk in-place under the exact same filename. However, `GradingDeepDiveStudio` constructs `frontUrl` and `backUrl` (`App.jsx:2167-2177`) and `buildCropUrl` (`App.jsx:2241-2256`) without any cache-busting query string (`&v=...`), and `/api/grading/crop` sets `Cache-Control: private, max-age=60` (`launch_tabulas_hub.py:1214`).
- **Reproduction Condition:** Rotate a card $90^\circ$/$180^\circ$ or replace its images, then open `GradingDeepDiveStudio` (or inspect a defect crop within 60 seconds): the browser renders the cached pre-rotation JPEG while the SVG overlays and defect boxes render at the newly computed post-rotation coordinates.
- **Fix Plan:** Append `&v=${encodeURIComponent(diagnostics?.source_images?.[activeSide === 'Back' ? 'back_mtime' : 'front_mtime'] || diagnostics?.updated_at || '')}` to `frontUrl`, `backUrl`, and `buildCropUrl` in `GradingDeepDiveStudio` (and `SideBySideCardComparison`).

---

### [HIGH-09] Quick Win: 40 Clean-Card Back-Emblem `ink_spot` False Positives Bypass Text/Glyph Proximity Guard Due to `area < 165.0 or max(bw, bh) <= 14` Gate
- **File & Lines:** `Core/surface_defect_engine.py:1308-1328` (`_detect_ink_spots`)
- **Audit Area:** 5. Quick Wins (`ink_spot` False Positives vs. `FLAWED_Card004726_F` Recall)
- **Root Cause:** Detailed empirical analysis and 1–2 line surgical fix are provided in **Section 4 (Quick Wins)** below.

---

## 3. Medium Severity Findings

### [MED-01] PSA/BGS Ceiling & Tier Label Asymmetry (`Est_PSA = 7.0` While `Est_BGS = 9.0` With `"NM"` Label) + Subgrade Overrides Ignored by Defect Count Ceilings
- **File & Lines:** `Core/vision_grader.py:5871-5921`, `5979`
- **Audit Area:** 2. Coordinate, Geometry & Grading Math
- **Root Cause:**
  1. At `Core/vision_grader.py:5898-5905`, `if num_defects >= 3 or total_penalty >= 1.5:` caps `est_psa = min(est_psa, 8.0)` and `if has_heavy_structural or total_penalty >= 2.5:` caps `est_psa = min(est_psa, 7.0)`, **but neither branch caps `est_bgs`** (which is only capped at `9.5` on line `5900`). Then line `5906` derives `tier_lbl` solely from `est_psa` and assigns that PSA tier label to `out_diag["grades"]["bgs"]["tier"]` (`line 5920`) while setting `csv_grade["Est_Grade"] = f"{est_bgs:.1f}"` (`line 5979`).
  2. When a user overrides a subgrade via `ov["subgrade_overrides"]` (`lines 5871-5879`, e.g., setting `surface = 9.5`), `active_defects` still includes that category's raw defects, so lines `5898-5904` still force `est_psa <= 9.0` / `8.0` / `7.0`.
- **Reproduction Condition:** A card with clean centering/edges/surface (`9.5`) and a single `corner_crease` (`severity=1.5`, `Sub_Corners=8.0`) produces `Est_PSA = 7.0 ("NM")` alongside `Est_BGS = 9.0` (labeled `"NM"`) and `Est_Grade = 9.0`.
- **Fix Plan:** Cap `est_bgs = min(est_bgs, 8.5)` when `num_defects >= 3 or total_penalty >= 1.5` and `est_bgs = min(est_bgs, 7.5)` when `has_heavy_structural or total_penalty >= 2.5`, compute BGS's tier label from `est_bgs`, and exclude categories present in `ov["subgrade_overrides"]` from `active_defects` ceiling checks.

---

### [MED-02] `_map_bbox_norm_inverse` Allows `x + w > 1.0` or `y + h > 1.0` Near Bottom/Right Image Boundaries
- **File & Lines:** `Core/vision_grader.py:879-899`
- **Audit Area:** 2. Coordinate, Geometry & Grading Math
- **Root Cause:** Unlike `_roi_bbox_to_norm` (`Core/surface_defect_engine.py:159-160`), which clamps `nx1, ny1` to `[0.0, 0.998]`, `_map_bbox_norm_inverse` clamps `nx1 = float(np.clip(np.min(xs), 0.0, 1.0))` and returns `max(0.002, nx2 - nx1)` for width/height (`line 898`), allowing `nx1 + nw > 1.0` or `ny1 + nh > 1.0` when an inverse-mapped defect touches the right or bottom image edge.
- **Reproduction Condition:** Any defect on a deskewed card (`|skew_deg| >= 0.35`) whose inverse-mapped `nx1 > 0.998` or `ny1 > 0.998` yields `bbox_norm` with `x + w > 1.0`.
- **Fix Plan:** Clamp `nx1 = float(np.clip(np.min(xs), 0.0, 0.998))` and `ny1 = float(np.clip(np.min(ys), 0.0, 0.998))` at `Core/vision_grader.py:893-895`, and clamp `nw = min(1.0 - nx1, max(0.002, nx2 - nx1))` and `nh = min(1.0 - ny1, max(0.002, ny2 - ny1))`.

---

### [MED-03] Multi-Process Last-Writer-Wins Overwrite on `NEURAL_EMBEDDINGS_CACHE_FILE` (`neural_embeddings_v25.pkl`) Across Parallel Worker Slots
- **File & Lines:** `Core/neural_vision.py:789-834` (`load_neural_embeddings_cache`, `save_neural_embeddings_cache`)
- **Audit Area:** 1. Concurrency, State & File Integrity
- **Root Cause:** `_INDEX_LOCK` (`Core/neural_vision.py:791, 816`) is a process-local `threading.RLock()`. When multiple worker slots (`slot_1`..`slot_8`) run scan ingestion or reprocessing concurrently, each subprocess loads `neural_embeddings_v25.pkl` into its own process memory and flushes via `save_neural_embeddings_cache(cache_obj)` without acquiring an `interprocess_file_lock` or merging newly written entries from disk.
- **Reproduction Condition:** Run two parallel scan-processing or reprocessing jobs on `slot_1` and `slot_2` across different sets: whichever worker flushes `neural_embeddings_v25.pkl` second overwrites all new DINOv2 embeddings computed by the first worker.
- **Fix Plan:** Wrap `save_neural_embeddings_cache` in `interprocess_file_lock(NEURAL_EMBEDDINGS_CACHE_FILE.with_suffix(".pkl.lock"))`, re-read existing disk embeddings if `st_mtime > _MEM_EMBED_MTIME`, and merge `disk_data["embeddings"].update(cache_obj["embeddings"])` before calling `atomic_write_bytes`.

---

### [MED-04] Thread-Unsafe Global DataFrame Caches (`_CHK_MASTER_CACHE`, `_CHK_SET_CACHE`, `_INV_MEM_CACHE`, `_DIR_MEM_CACHE`) in `ThreadingHTTPServer`
- **File & Lines:** `launch_tabulas_hub.py:375-411`, `480-531`, `1380-1396`, `1466`, `1549`
- **Audit Area:** 1. Concurrency, State & File Integrity
- **Root Cause:** `ThreadingHTTPServer` (`launch_tabulas_hub.py:3145`) serves HTTP requests across concurrent threads while `_start_background_cache_prewarm()` (`line 448`) populates the same global dictionaries without any `threading.Lock`. In `_get_cached_checklist_df` (`lines 523-526`), `_CHK_MASTER_CACHE["mtime"] = mt_master` is mutated **before** `_CHK_MASTER_CACHE["df"]` and `"known_sets"` are updated.
- **Reproduction Condition:** An incoming `/api/checklists` or `/api/purchase-planner` request arriving while `_prewarm_worker` is halfway through lines `523-526` sees matching `"mtime"` and reads the stale `"df"` (`None` or previous DataFrame) before `"df"` is assigned.
- **Fix Plan:** Guard `_INV_MEM_CACHE`, `_DIR_MEM_CACHE`, `_CHK_MASTER_CACHE`, and `_CHK_SET_CACHE` reads/updates with a module-level `threading.RLock()` and update `"mtime"` last after `"df"` and `"known_sets"` are populated.

---

### [MED-05] Non-Atomic `dest_path.write_bytes(res.content)` in `_download_single_template_side` Permanently Caches Truncated Images on Crash/Stop
- **File & Lines:** `Core/scraper_engine.py:4757-4758`, `4836`, `5015`
- **Audit Area:** 4. Scraper & Worker Resilience
- **Root Cause:** `_download_single_template_side` writes downloaded reference images directly via `dest_path.write_bytes(res.content)` (`line 4758`) instead of `atomic_write_bytes`. Because `_count_pending_catalog_downloads` (`line 4836`) and the resume check (`line 5015`) only check `(set_dir / f_file).exists()` or `_index_existing_set_dir_by_cid(set_dir)` (filename presence, not file size or JPEG EOI marker), a worker killed mid-write via `stop_active_job` (`taskkill /F`) can leave a 0-byte or truncated `.jpg` file on disk that future runs permanently skip.
- **Reproduction Condition:** Click **Stop** on an active image download job while `dest_path.write_bytes(res.content)` is flushing to `D:\Tabulas Set Library\<Set>\`; the partial file satisfies `.exists()` on subsequent runs and is never re-downloaded.
- **Fix Plan:** Replace `dest_path.write_bytes(res.content)` at `Core/scraper_engine.py:4758` with `atomic_write_bytes(dest_path, lambda tmp_p: tmp_p.write_bytes(res.content))`.

---

### [MED-06] `cleanup_orphaned_drivers()` Executes System-Wide `taskkill /F /IM chromedriver.exe` Across All Processes
- **File & Lines:** `Core/scraper_engine.py:396-409`, `436`, `468`; `launch_tabulas_hub.py:3026-3030`
- **Audit Area:** 4. Scraper & Worker Resilience
- **Root Cause:** `cleanup_orphaned_drivers()` runs `taskkill /F /IM uc_driver.exe /T` and `taskkill /F /IM chromedriver.exe /T` by image name (`Core/scraper_engine.py:400-405`), killing every ChromeDriver process on the machine regardless of which worker slot or external browser session owns it.
- **Reproduction Condition:** Trigger `cleanup_drivers` via `/api/devtools/action` (or hit a Selenium startup retry at `Core/scraper_engine.py:468`) while another Selenium/ChromeDriver session is active on the host: `taskkill /IM` terminates the unrelated driver process.
- **Fix Plan:** Track the spawned driver/browser PIDs per worker session (e.g., `driver.service.process.pid` and `driver.browser_pid`) and terminate only the current worker's owned PID tree (`taskkill /F /T /PID <pid>`).

---

### [MED-07] `GradingDeepDiveStudio` Fails to Reset `flagPresetId`, `showFlagModal`, `loupeZoom`, and `diagError` When Switching `Front` ↔ `Back`
- **File & Lines:** `App.jsx:2115-2128`, `1804-1806`, `2746`
- **Audit Area:** 3. Frontend (`App.jsx` — classic React/Babel)
- **Root Cause:** The `useEffect` on `[activeSide, sku]` (`App.jsx:2115-2128`) resets `isolatedDefectId` and `editMode`, but does not reset `flagPresetId`, `showFlagModal`, `loupeZoom`, or `diagError`. If `flagPresetId` was set on `Front` and the user switches to `Back` before opening `FlagGradingErrorModal` (`line 2746`), `initialTargetItemId={flagPresetId || isolatedDefectId || ''}` passes the stale Front defect ID into the modal for the Back side.
- **Fix Plan:** Add `setFlagPresetId(''); setShowFlagModal(false); setLoupeZoom(2.0); setDiagError(null);` inside the `useEffect(..., [activeSide, sku])` reset hook at `App.jsx:2115-2128`.

---

## 4. Quick Wins: Cleanest Surgical Fix for the ~42 Clean-Card Back-Emblem `ink_spot` False Positives

### Empirical Root-Cause Analysis Across All 398 Clean Fixture Scans & `FLAWED_Card004726_F`
Running `Core/surface_defect_engine.py` across the entire `tests/fixtures/real_cards/` benchmark (199 clean fronts, 199 clean backs, plus `FLAWED_*` fixtures) produces **42 clean-card `ink_spot` false positives** (**40 on clean card backs** and **2 on clean card fronts**), plus **6 identical back-emblem false positives** on `FLAWED_Card004725_B.jpg`–`FLAWED_Card004730_B.jpg`:
- **26 of the 40 clean card backs** (and all 6 `FLAWED_Card004725_B..4730_B` backs) are the exact same `17×15` to `19×17` px (`area = 152.5..212.5`) printed stat-table/player-bio emblem in the `mid-right` zone (`x ≈ 1163..1426, y ≈ 1041..1148`).
- **9 of the 40 clean card backs** (`[2026_Topps_Baseball]_[Base]_..._B.jpg`) are the `14×17` to `19×20` px (`area = 165.0..262.5`) printed card-number/MLB header badge in the `top-center` zone (`x ≈ 953..1267, y ≈ 270..308`).
- **5 of the 40 clean card backs** are `18×14` to `44×29` px (`area = 185.0..793.0`) printed team/insert logos embedded inline with printed bio/stat text (`Twins - Limited_001-back`, `Rangers - Limited_001-back`, `Phillies - Limited_001-back`, `Dodgers - Relic_001-back`, `Orioles - Insert_003-back`).

#### Why They Slip Through `_detect_ink_spots` (`Core/surface_defect_engine.py:1308-1328`)
At lines `1314-1327`, `_detect_ink_spots` already builds `glyphs` (dark text/graphic components with `8 <= g_area <= 2500`) and counts horizontally aligned peers (`h_peers` within `|Δy| <= 28 px`, `4 <= |Δx| <= 140 px`) and vertically aligned peers (`v_peers` within `|Δx| <= 28 px`, `4 <= |Δy| <= 140 px`):
```python
        if area < 165.0 or max(bw, bh) <= 14:
            h_peers = 0
            v_peers = 0
            for gcx, gcy, gw, gh in glyphs:
                ...
            if h_peers >= 2 or v_peers >= 2:
                continue
```
Because line `1314` gates the glyph-alignment check on `if area < 165.0 or max(bw, bh) <= 14:`, **every printed back icon measuring `14×17` (`max=17, area=165.0`) up to `24×17` (`max=24, area=212.5`) completely bypasses the `glyphs` check**, even though 39 of the 40 clean card-back false positives sit directly inline with printed text baselines and table columns (`h_peers >= 2` or `v_peers >= 2`, and `h_peers >= 4 and v_peers >= 4` on larger insert emblems like `Orioles - Insert_003-back` where `hp=20, vp=9`).

By contrast, on **`FLAWED_Card004726_F.jpg`**, the true ink spot is on the **Front** (`side_label == "Front"`), measures **`41×22` px (`area = 534.5`, `max(bw, bh) = 41`)**, is jet-black (`blob_l_med = 9.0`), and has **`v_peers = 0`** (`h_peers = 4, v_peers = 0`).

### Cleanest 1–2 Line Surgical Fix (`Core/surface_defect_engine.py:1314-1327`)
In `_detect_ink_spots` (`Core/surface_defect_engine.py:1314-1327`), compute `h_peers` and `v_peers` for candidate blobs and replace the `if area < 165.0 or max(bw, bh) <= 14:` gate with:
```python
        if area <= 320.0 or max(bw, bh) <= 26 or (side_label.lower() == "back" and area <= 850.0):
            # ... existing h_peers / v_peers loop ...
            if (max(bw, bh) <= 26 and (h_peers >= 2 or v_peers >= 2)) or (h_peers >= 4 and v_peers >= 4):
                continue
```
- **Verified Impact:**
  - **Clean Card Backs:** Eliminates **39 of 40** (`97.5%`) clean-back `ink_spot` false positives (reducing clean-back FPs from `40 → 1`) and eliminates **all 6** `FLAWED_Card004725_B..4730_B` back-emblem false positives.
  - **`FLAWED_Card004726_F` Recall:** **100% preserved** (`bw=41 > 26`, `area=534.5 > 320.0`, `v_peers=0 < 4`, `side="Front"`).
  - **Existing Unit Tests:** 100% preserved (in `test_biotext_punctuation_not_flagged_as_ink_spot`, the true ink blob at `(240, 760)` is isolated with `h_peers=0, v_peers=0`).
