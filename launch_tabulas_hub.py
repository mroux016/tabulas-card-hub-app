from __future__ import annotations
# ==============================================================================
# launch_tabulas_hub.py
# Unified Python React + Full REST API Server & Launcher for C:\Tabulas Card Hub
# Release: v0.24.0-beta.45
# ==============================================================================
import argparse
import csv
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HUB_DIR = Path(os.environ.get("CARDS_BASE_DIR", r"C:\Tabulas Card Hub"))
for _sp in (HUB_DIR / "App", HUB_DIR):
    if _sp.exists() and str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

from Core.config import (
    APP_DIR,
    ARCHIVE_DIR,
    BATCHES_DIR,
    CARD_LEVEL_TARGETS_FILE,
    CHECKLIST_PATH,
    COLLECTION_HISTORY_FILE,
    DAILY_LOGS_ROOT,
    EXPENSES_CSV_FILE,
    INPUT_PATH,
    INVENTORY_FILE,
    LABELS_OUTPUT_DIR,
    LEGACY_SET_TEMPLATES_DIR,
    LOGS_DIR,
    MARKET_ALERTS_FILE,
    MARKET_COMPS_CACHE_FILE,
    MARKET_SETTINGS_FILE,
    MASTER_DIRECTORY_CSV_FILE,
    RECOMMENDED_LOTS_FILE,
    REFERENCE_TEMPLATES_DIR as SET_LIBRARY_DIR,
    REVIEWED_CARDS_DIR,
    RUNTIME_DIR,
    SET_CART_JSON_FILE,
    SET_CHECKLISTS_DIR,
    SET_LIBRARY_ROOT,
    SOLD_CARDS_CSV,
    TRACKING_FILE,
    get_daily_log_dir,
)


def _log_ui_action_to_file(category: str, title: str, message: str = ""):
    """Auto-appends UI/API actions into `C:\\Tabulas Card Hub\\Logs\\Logs\\YYYYMMDD\\YYYYMMDD_ui_actions.log`."""
    try:
        from datetime import datetime
        day_dir = get_daily_log_dir()
        ui_log = day_dir / f"{datetime.now().strftime('%Y%m%d')}_ui_actions.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ui_log, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{category}] {title} — {message}\n")
    except Exception:
        pass


_TABULAS_HTML_SHELL_V2 = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Tabulas Card Management Hub — C:\Tabulas Card Hub</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    html { font-size: 17.5px; background: #020617; color: #f1f5f9; }
    body { margin: 0; background: #020617; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }
    [class*="text-[9px]"] { font-size: 10.5px !important; }
    [class*="text-[9.5px]"] { font-size: 11px !important; }
    [class*="text-[10px]"] { font-size: 11.5px !important; }
    [class*="text-[11px]"] { font-size: 12.5px !important; }
    .no-scrollbar::-webkit-scrollbar { display: none; }
    .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
  </style>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100">
  <div id="root">
    <div style="min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;background:#020617;color:#e2e8f0;font-family:system-ui,sans-serif;">
      <div style="font-size:28px;">🗃️</div>
      <div style="font-size:15px;font-weight:700;color:#38bdf8;">Loading Tabulas Card Management Hub...</div>
      <div id="boot-status" style="font-size:12px;color:#94a3b8;font-family:monospace;">Compiling UI bundle...</div>
    </div>
  </div>

  <script id="tabulas-jsx-source" type="text/plain">__TABULAS_JSX_SOURCE__</script>

  <script>
    (function () {
      function reportClientError(stage, message, stack, snippet) {
        try {
          fetch('http://localhost:5000/api/client-error', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              stage: String(stage || 'runtime'),
              message: String(message || 'Unknown error'),
              stack: String(stack || ''),
              snippet: String(snippet || ''),
            }),
          }).catch(function () {});
        } catch (_e) {}
      }

      function escapeHtml(s) {
        return String(s || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      }

      function showBootDiagnostic(stage, message, stack, snippet) {
        reportClientError(stage, message, stack, snippet);
        var rootEl = document.getElementById('root');
        if (!rootEl) return;
        var fullText = '[' + stage + '] ' + message + (snippet ? '\n\n' + snippet : '') + (stack ? '\n\n' + stack : '');
        rootEl.innerHTML =
          '<div style="min-height:100vh;padding:28px;background:#020617;color:#f1f5f9;font-family:system-ui,sans-serif;box-sizing:border-box;">' +
          '  <div style="max-width:960px;margin:0 auto;background:#0f172a;border:1px solid #f43f5e;border-radius:16px;padding:22px;box-shadow:0 20px 50px rgba(0,0,0,0.6);">' +
          '    <div style="font-size:16px;font-weight:800;color:#fda4af;margin-bottom:6px;">⚠️ Tabulas UI Boot / Render Error (' + escapeHtml(stage) + ')</div>' +
          '    <div style="font-size:13px;color:#e2e8f0;margin-bottom:12px;">' + escapeHtml(message) + '</div>' +
          (snippet ? '<pre style="background:#020617;border:1px solid #334155;border-radius:10px;padding:12px;font-size:11.5px;color:#7dd3fc;overflow:auto;max-height:260px;white-space:pre;">' + escapeHtml(snippet) + '</pre>' : '') +
          (stack ? '<pre style="background:#020617;border:1px solid #334155;border-radius:10px;padding:12px;font-size:11px;color:#fca5a5;overflow:auto;max-height:220px;white-space:pre-wrap;margin-top:10px;">' + escapeHtml(stack) + '</pre>' : '') +
          '    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;">' +
          '      <button id="diag-copy-btn" style="padding:8px 14px;border-radius:10px;border:1px solid #38bdf8;background:#0c4a6e;color:#e0f2fe;font-weight:700;cursor:pointer;font-size:12px;">📋 Copy Error Details</button>' +
          '      <button onclick="window.location.reload()" style="padding:8px 14px;border-radius:10px;border:1px solid #475569;background:#1e293b;color:#f1f5f9;font-weight:700;cursor:pointer;font-size:12px;">🔄 Reload Window</button>' +
          '      <button id="diag-rb-btn" style="padding:8px 14px;border-radius:10px;border:1px solid #f59e0b;background:#78350f;color:#fef3c7;font-weight:700;cursor:pointer;font-size:12px;">⏪ Emergency Rollback to Previous Snapshot</button>' +
          '    </div>' +
          '  </div>' +
          '</div>';
        var copyBtn = document.getElementById('diag-copy-btn');
        if (copyBtn) {
          copyBtn.onclick = function () {
            if (navigator.clipboard) navigator.clipboard.writeText(fullText).catch(function () {});
            copyBtn.textContent = '✅ Copied!';
          };
        }
        var rbBtn = document.getElementById('diag-rb-btn');
        if (rbBtn) {
          rbBtn.onclick = function () {
            rbBtn.textContent = '⏳ Checking snapshots...';
            fetch('http://localhost:5000/api/updater')
              .then(function (r) { return r.json(); })
              .then(function (d) {
                var snaps = (d && d.snapshots) || [];
                var prevSnap = snaps.find(function (s) { return !s.is_current; });
                if (!prevSnap) { rbBtn.textContent = 'No prior snapshot found'; return; }
                rbBtn.textContent = '⏪ Rolling back to v' + prevSnap.version + '...';
                return fetch('http://localhost:5000/api/updater/action', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ action: 'rollback', targetVersion: prevSnap.version }),
                }).then(function () { window.location.reload(); });
              })
              .catch(function (e) { rbBtn.textContent = 'Rollback failed: ' + e.message; });
          };
        }
      }

      window.addEventListener('error', function (ev) {
        if (ev && ev.error) {
          showBootDiagnostic('window.onerror', ev.message || String(ev.error), ev.error.stack || '', '');
        }
      });
      window.addEventListener('unhandledrejection', function (ev) {
        var r = ev && ev.reason;
        reportClientError('unhandledrejection', r && r.message ? r.message : String(r), r && r.stack ? r.stack : '', '');
      });

      function bootApp() {
        var statusEl = document.getElementById('boot-status');
        if (!window.React || !window.ReactDOM || !window.Babel) {
          showBootDiagnostic(
            'CDN Load Error',
            'Required frontend libraries failed to load (React=' + !!window.React + ', ReactDOM=' + !!window.ReactDOM + ', Babel=' + !!window.Babel + '). Check internet connectivity or firewall access to unpkg.com.',
            '',
            ''
          );
          return;
        }

        var srcEl = document.getElementById('tabulas-jsx-source');
        var rawSrc = srcEl ? srcEl.textContent : '';
        if (!rawSrc || rawSrc.trim().length < 50) {
          showBootDiagnostic('Source Empty', 'App.jsx source payload was empty.', '', '');
          return;
        }

        if (statusEl) statusEl.textContent = 'Compiling App.jsx (' + Math.round(rawSrc.length / 1024) + ' KB)...';

        var compiled;
        try {
          compiled = window.Babel.transform(rawSrc, {
            presets: [['react', { runtime: 'classic' }]],
            compact: false,
            filename: 'App.jsx',
          });
        } catch (babelErr) {
          var snippet = '';
          if (babelErr && babelErr.loc && babelErr.loc.line) {
            var lines = rawSrc.split(/\r?\n/);
            var ln = babelErr.loc.line;
            var start = Math.max(1, ln - 6);
            var end = Math.min(lines.length, ln + 6);
            var out = [];
            for (var i = start; i <= end; i++) {
              out.push((i === ln ? '>> ' : '   ') + String(i).padStart(5, ' ') + ' | ' + lines[i - 1]);
            }
            snippet = out.join('\n');
          }
          showBootDiagnostic('Babel JSX Compile Error', babelErr.message || String(babelErr), babelErr.stack || '', snippet);
          return;
        }

        var AppComponent = null;
        try {
          var factory = new Function('React', 'ReactDOM', compiled.code + '\n;return (typeof App !== "undefined" ? App : null);');
          AppComponent = factory(window.React, window.ReactDOM);
          if (!AppComponent) {
            throw new Error('Compiled App.jsx did not define function App().');
          }
        } catch (evalErr) {
          var codeLines = (compiled && compiled.code ? compiled.code : '').split(/\r?\n/);
          var badLines = [];
          for (var ci = 0; ci < codeLines.length; ci++) {
            if (/^\s*(import|export)\b/.test(codeLines[ci])) {
              badLines.push(String(ci + 1).padStart(5, ' ') + ' | ' + codeLines[ci]);
              if (badLines.length >= 12) break;
            }
          }
          var execSnippet = badLines.length
            ? 'Detected module statement(s) in compiled output:\n' + badLines.join('\n')
            : codeLines.slice(0, 12).map(function (l, idx) { return String(idx + 1).padStart(5, ' ') + ' | ' + l; }).join('\n');
          showBootDiagnostic('Module Execution Error', evalErr.message || String(evalErr), evalErr.stack || '', execSnippet);
          return;
        }

        class RootBootErrorBoundary extends window.React.Component {
          constructor(props) {
            super(props);
            this.state = { error: null };
          }
          static getDerivedStateFromError(err) {
            return { error: err };
          }
          componentDidCatch(err, info) {
            reportClientError('React Root Crash', err && err.message ? err.message : String(err), (err && err.stack ? err.stack : '') + '\n' + (info && info.componentStack ? info.componentStack : ''), '');
          }
          render() {
            if (this.state.error) {
              var eObj = this.state.error;
              return window.React.createElement(
                'div',
                { style: { minHeight: '100vh', padding: '28px', background: '#020617', color: '#f1f5f9' } },
                window.React.createElement(
                  'div',
                  { style: { maxWidth: '880px', margin: '0 auto', background: '#0f172a', border: '1px solid #f43f5e', borderRadius: '16px', padding: '20px' } },
                  window.React.createElement('div', { style: { fontSize: '15px', fontWeight: 800, color: '#fda4af', marginBottom: '8px' } }, '⚠️ React Root Render Error'),
                  window.React.createElement('pre', { style: { background: '#020617', padding: '12px', borderRadius: '10px', fontSize: '12px', color: '#fca5a5', overflow: 'auto', whiteSpace: 'pre-wrap' } }, String(eObj.message || eObj) + '\n\n' + String(eObj.stack || '')),
                  window.React.createElement('button', { onClick: function () { window.location.reload(); }, style: { marginTop: '12px', padding: '8px 14px', borderRadius: '10px', background: '#0284c7', color: '#fff', fontWeight: 700, border: 'none', cursor: 'pointer' } }, '🔄 Reload App')
                )
              );
            }
            return this.props.children;
          }
        }

        try {
          var root = window.ReactDOM.createRoot(document.getElementById('root'));
          root.render(
            window.React.createElement(
              RootBootErrorBoundary,
              null,
              window.React.createElement(AppComponent, null)
            )
          );
        } catch (mountErr) {
          showBootDiagnostic('React Mount Error', mountErr.message || String(mountErr), mountErr.stack || '', '');
        }
      }

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootApp);
      } else {
        setTimeout(bootApp, 0);
      }
    })();
  </script>
</body>
</html>
"""


def _build_tabulas_react_html_v2(jsx_path: Path) -> str:
    """
    Prepares `App.jsx` for browser/pywebview execution using explicit `Babel.transform(..., compact=False)`
    and a full diagnostic error screen so >500 KB files and any compile/runtime errors never produce a silent blank screen.
    """
    raw_jsx = Path(jsx_path).read_text(encoding="utf-8-sig")
    cleaned = raw_jsx.replace("\r\n", "\n").replace("\r", "\n")

    # Strip TypeScript pragma
    cleaned = re.sub(r"^\s*//\s*@ts-nocheck\s*\n?", "", cleaned, flags=re.MULTILINE)

    # Convert React & ReactDOM imports into global destructuring
    cleaned = re.sub(
        r"^\s*import\s+React\s*,\s*\{([^}]+)\}\s+from\s+['\"]react['\"]\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$",
        r"const {\1} = React;",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*import\s+\{([^}]+)\}\s+from\s+['\"]react['\"]\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$",
        r"const {\1} = React;",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*import\s+(?:\*\s+as\s+)?React\s+from\s+['\"]react['\"]\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*import\s+(?:ReactDOM\s*,\s*)?\{([^}]+)\}\s+from\s+['\"]react-dom(?:/client)?['\"]\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$",
        r"const {\1} = ReactDOM;",
        cleaned,
        flags=re.MULTILINE,
    )

    # Strip any remaining top-level ES module imports (single-line or multi-line)
    cleaned = re.sub(
        r"^\s*import\s+(?:type\s+)?(?:\*\s+as\s+[A-Za-z_$][\w$]*|[A-Za-z_$][\w$]*(?:\s*,\s*(?:\{[^}]*\}|\*\s+as\s+[A-Za-z_$][\w$]*))?|\{[^}]*\})\s+from\s+['\"][^'\"]+['\"]\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*import\s+['\"][^'\"]+['\"]\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )

    # Strip ES module exports so `new Function(...)` can execute cleanly
    cleaned = re.sub(r"^\s*export\s+default\s+function\s+App\s*\(", "function App(", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*export\s+default\s+App\s*;?(?:[ \t]*//[^\n]*)?[ \t]*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*export\s+(?=(?:async\s+)?(?:function|const|let|var|class)\b)", "", cleaned, flags=re.MULTILINE)

    # Prevent any literal </script sequence inside App.jsx from prematurely closing the source tag
    safe_jsx = re.sub(r"</script", r"<\/script", cleaned, flags=re.IGNORECASE)
    return _TABULAS_HTML_SHELL_V2.replace("__TABULAS_JSX_SOURCE__", safe_jsx)


# ==============================================================================
# MTIME-KEYED IN-MEMORY CHECKLIST CACHE & SKU RANGE PARSER
# ==============================================================================
_CHK_MASTER_CACHE = {"mtime": -1.0, "df": None, "known_sets": [], "known_years": []}
_CHK_SET_CACHE: dict[str, tuple[float, object]] = {}
_INV_MEM_CACHE = {"mtime": -1.0, "rows": []}
_DIR_MEM_CACHE = {"mtime": -1.0, "rows": []}


def _get_cached_inventory_records() -> list[dict]:
    """mtime-validated in-memory cache for Inventory.csv (auto-reloads whenever disk file changes)."""
    if not INVENTORY_FILE.exists():
        return []
    try:
        mt = INVENTORY_FILE.stat().st_mtime
        if _INV_MEM_CACHE["mtime"] != mt:
            _INV_MEM_CACHE["rows"] = _read_csv_records(INVENTORY_FILE, max_rows=50000)
            _INV_MEM_CACHE["mtime"] = mt
        return _INV_MEM_CACHE["rows"]
    except Exception:
        return _read_csv_records(INVENTORY_FILE, max_rows=50000)


def _get_cached_directory_records() -> list[dict]:
    """mtime-validated in-memory cache for TCDB_Set_Directory.csv."""
    try:
        if MASTER_DIRECTORY_CSV_FILE.exists():
            mt = MASTER_DIRECTORY_CSV_FILE.stat().st_mtime
            if _DIR_MEM_CACHE["mtime"] == mt and _DIR_MEM_CACHE["rows"]:
                return _DIR_MEM_CACHE["rows"]
        from Core.scraper_engine import load_tcdb_master_directory
        df_dir = load_tcdb_master_directory()
        rows = df_dir.to_dict(orient="records")
        if MASTER_DIRECTORY_CSV_FILE.exists():
            _DIR_MEM_CACHE["mtime"] = MASTER_DIRECTORY_CSV_FILE.stat().st_mtime
            _DIR_MEM_CACHE["rows"] = rows
        return rows
    except Exception:
        return []


def _start_background_cache_prewarm():
    """
    Pre-warms Master_Checklist.csv, TCDB_Set_Directory.csv, Inventory.csv, and Rate Learner
    telemetry into mtime-checked RAM caches in a non-blocking daemon thread at startup so the
    desktop window opens immediately while first-click UI queries become instantaneous.
    """
    import threading

    def _prewarm_worker():
        t0 = time.time()
        parts = []
        try:
            inv_rows = _get_cached_inventory_records()
            parts.append(f"Inventory ({len(inv_rows):,} SKUs)")
        except Exception:
            pass
        try:
            dir_rows = _get_cached_directory_records()
            parts.append(f"Set Directory ({len(dir_rows):,} sets)")
        except Exception:
            pass
        try:
            chk_df = _get_cached_checklist_df("")
            parts.append(f"Master Checklist ({len(chk_df):,} rows)")
        except Exception:
            pass
        try:
            from Core.rate_learner import get_rate_learner
            get_rate_learner().get_dashboard_summary()
        except Exception:
            pass
        summary = f"Pre-warmed RAM caches in {time.time() - t0:.2f}s: " + ", ".join(parts)
        print(f"  [PRELOAD] {summary}", flush=True)
        _log_ui_action_to_file("System", "Startup Cache Pre-Warm", summary)

    threading.Thread(target=_prewarm_worker, name="tabulas-cache-prewarm", daemon=True).start()


def _expand_sku_tokens(raw_skus: list[str]) -> list[str]:
    """Expands SKU tokens and ranges (e.g. '1000001-1000005') into a deduplicated SKU list."""
    out: list[str] = []
    seen: set[str] = set()
    for raw_tok in raw_skus or []:
        for tok in re.split(r"[,;\s]+", str(raw_tok or "").strip()):
            t_c = tok.strip()
            if not t_c:
                continue
            if "-" in t_c:
                p1, p2 = t_c.split("-", 1)
                if p1.strip().isdigit() and p2.strip().isdigit():
                    s_i, e_i = int(p1.strip()), int(p2.strip())
                    lo, hi = min(s_i, e_i), min(max(s_i, e_i), min(s_i, e_i) + 5000)
                    for n_i in range(lo, hi + 1):
                        sku_s = f"{n_i:07d}" if n_i >= 1000000 else str(n_i)
                        if sku_s not in seen:
                            seen.add(sku_s)
                            out.append(sku_s)
                    continue
            if t_c.isdigit():
                n_i = int(t_c)
                t_c = f"{n_i:07d}" if n_i >= 1000000 else str(n_i)
            if t_c not in seen:
                seen.add(t_c)
                out.append(t_c)
    return out


def _get_cached_checklist_df(set_name: str = ""):
    """
    Fast mtime-keyed checklist loader:
      - If `set_name` is provided and `Checklists/Set_Checklists/<Set>.csv` exists, reads & caches
        that single set CSV directly (50x+ faster than scanning the full 76MB Master_Checklist.csv).
      - Otherwise returns the cached Master_Checklist.csv DataFrame, reloading only when file mtime changes.
    """
    import pandas as pd
    from Core.config import CHECKLIST_COLUMNS, CHECKLIST_PATH, SET_CHECKLISTS_DIR, sanitize_filename_part

    def _ensure_cols(df_in):
        for col in CHECKLIST_COLUMNS:
            if col not in df_in.columns:
                df_in[col] = ""
        return df_in

    if set_name:
        cand_csv = SET_CHECKLISTS_DIR / f"{sanitize_filename_part(set_name)}.csv"
        if not cand_csv.exists() and SET_CHECKLISTS_DIR.exists():
            target_low = sanitize_filename_part(set_name).lower()
            cand_csv = next((p for p in SET_CHECKLISTS_DIR.glob("*.csv") if p.stem.lower() == target_low), cand_csv)
        if cand_csv.exists():
            mt = cand_csv.stat().st_mtime
            key = str(cand_csv)
            cached = _CHK_SET_CACHE.get(key)
            if cached is not None and cached[0] == mt:
                return cached[1]
            df_s = _ensure_cols(pd.read_csv(cand_csv, dtype=str, keep_default_na=False))
            _CHK_SET_CACHE[key] = (mt, df_s)
            return df_s

    if not CHECKLIST_PATH.exists():
        return pd.DataFrame(columns=CHECKLIST_COLUMNS)

    mt_master = CHECKLIST_PATH.stat().st_mtime
    if _CHK_MASTER_CACHE["df"] is None or _CHK_MASTER_CACHE["mtime"] != mt_master:
        df_m = _ensure_cols(pd.read_csv(CHECKLIST_PATH, dtype=str, keep_default_na=False))
        k_sets = sorted([s for s in df_m["Set"].dropna().unique().tolist() if str(s).strip()])
        k_yrs = set()
        for s_v in k_sets:
            m_yr = re.search(r"\b((?:19|20)\d{2}(?:-\d{2})?)\b", str(s_v))
            if m_yr:
                k_yrs.add(m_yr.group(1))
        _CHK_MASTER_CACHE["mtime"] = mt_master
        _CHK_MASTER_CACHE["df"] = df_m
        _CHK_MASTER_CACHE["known_sets"] = k_sets
        _CHK_MASTER_CACHE["known_years"] = sorted(list(k_yrs), reverse=True)

    master_df = _CHK_MASTER_CACHE["df"]
    if set_name:
        return master_df[master_df["Set"] == set_name]
    return master_df


def consolidate_single_react_app_file():
    app_jsx = APP_DIR / "App.jsx"
    app_tsx = APP_DIR / "app.tsx"
    if app_tsx.exists():
        try:
            if not app_jsx.exists() or app_tsx.stat().st_size > app_jsx.stat().st_size:
                shutil.copy2(app_tsx, app_jsx)
            backup_dir = APP_DIR / "Core" / ".verified_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(app_tsx, backup_dir / "app.tsx.bak")
            app_tsx.unlink()
        except Exception:
            pass


def run_health_check() -> bool:
    print("=" * 72)
    print(f"TABULAS CARD HUB PRE-FLIGHT CHECK ({HUB_DIR})")
    print("=" * 72)
    if not HUB_DIR.exists():
        print(f"[ERROR] Hub directory not found: {HUB_DIR}")
        return False
    consolidate_single_react_app_file()

    # Automatically run updater.py on startup to apply any new packages in .\Updates
    try:
        import updater
        upd_res = updater.check_and_apply_pending_updates(auto_apply=True)
        print(f"  [UPDATER] {upd_res.get('message')}")
    except Exception as e:
        print(f"  [UPDATER] Startup check skipped: {e}")
    try:
        import cli
        maint_res = cli.run_startup_maintenance()
        print(f"  [SYSTEM]  {maint_res.get('message')}")
    except Exception as e:
        print(f"  [SYSTEM]  Startup maintenance skipped: {e}")

    checks = [
        ("Master Inventory CSV", INVENTORY_FILE, False),
        ("Expenses Ledger CSV", EXPENSES_CSV_FILE, False),
        ("Sold Cards CSV", SOLD_CARDS_CSV, False),
        ("Master Checklist CSV", CHECKLIST_PATH, False),
        ("Set Checklists Folder", SET_CHECKLISTS_DIR, False),
        ("TCDB Set Directory CSV", MASTER_DIRECTORY_CSV_FILE, False),
        ("Tracked Sets Registry", TRACKING_FILE, False),
        ("Incoming Scans", INPUT_PATH, True),
        ("Uncommitted Batches", BATCHES_DIR, True),
        ("My Collection (_Cards)", REVIEWED_CARDS_DIR, True),
        ("Reference Library", SET_LIBRARY_DIR, True),
        ("Unified Archive Vault", ARCHIVE_DIR, True),
        ("Core Python Engine", APP_DIR / "Core" / "config.py", False),
        ("CLI Background Worker", APP_DIR / "cli.py", False),
        ("Unified React UI", APP_DIR / "App.jsx", False),
    ]
    for label, path, shallow_dir_count in checks:
        if path.exists():
            if path.is_dir():
                if shallow_dir_count:
                    top_dirs = sum(1 for p in path.iterdir() if p.is_dir())
                    top_files = sum(1 for p in path.iterdir() if p.is_file())
                    detail = f"{top_dirs:,} folders, {top_files:,} files" if top_files else f"{top_dirs:,} folders"
                else:
                    cnt = sum(1 for p in path.iterdir() if p.is_file())
                    detail = f"{cnt:,} files"
                print(f"  [OK] {label:<24} : {path} ({detail})")
            else:
                size_mb = path.stat().st_size / (1024.0 * 1024.0)
                size_str = f"{size_mb:,.1f} MB" if size_mb >= 1.0 else f"{path.stat().st_size / 1024.0:,.1f} KB"
                print(f"  [OK] {label:<24} : {path} ({size_str})")
        else:
            print(f"  [--] {label:<24} : {path} (not created yet)")
    return True


def _read_csv_records(csv_path: Path, max_rows: int = 50000) -> list[dict]:
    if not csv_path.exists():
        return []
    try:
        with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            out = []
            for idx, row in enumerate(reader):
                if idx >= max_rows:
                    break
                out.append({str(k or "").strip(): str(v or "").strip() for k, v in row.items() if k})
            return out
    except Exception:
        return []


def _write_csv_records(csv_path: Path, records: list[dict], explicit_cols: list[str] | None = None):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        cols = explicit_cols or []
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            if cols:
                writer = csv.DictWriter(f, fieldnames=cols)
                writer.writeheader()
        return
    cols = explicit_cols or list(records[0].keys())
    for r in records:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def _read_json_file(json_path: Path, default_val):
    if not json_path.exists():
        return default_val
    try:
        return json.loads(json_path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return default_val


def _write_json_file(json_path: Path, data):
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _discover_incoming_scans() -> list[dict]:
    try:
        from Core.database import find_unarchived_scan_batches
        return [
            {"batchName": b_name, "folderPath": str(b_dir), "pdfCount": len(b_pdfs), "samplePdfs": [p.name for p in b_pdfs[:5]]}
            for b_name, b_dir, b_pdfs in find_unarchived_scan_batches()
        ]
    except Exception:
        return []


def _discover_uncommitted_batches(include_cards_for: str = "") -> list[dict]:
    batches_dir = BATCHES_DIR
    if not batches_dir.exists():
        return []
    dirs = sorted(
        [d for d in batches_dir.iterdir() if d.is_dir() and d.name.lower() != "archive"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    valid_entries = []
    for d in dirs:
        if (d / "_COMMITTED.lock").exists():
            continue
        man_p = d / "Batch_Inventory_Manifest.csv"
        if not man_p.exists():
            continue
        rows = _read_csv_records(man_p, max_rows=20000)
        needs_rev = sum(1 for r in rows if str(r.get("Needs_Review", "")).lower() == "true")
        below_185 = 0
        for r in rows:
            try:
                if int(float(str(r.get("OCR_Confidence") or "0"))) < 185:
                    below_185 += 1
            except Exception:
                below_185 += 1
        valid_entries.append((d, rows, needs_rev, below_185))

    if not valid_entries:
        return []

    include_all = str(include_cards_for or "").strip() == "__ALL__"
    valid_names = {d.name for d, _, _, _ in valid_entries}
    active_target = include_cards_for if include_cards_for in valid_names else valid_entries[0][0].name

    out = []
    for d, rows, needs_rev, below_190 in valid_entries:
        should_load = include_all or (d.name == active_target)
        tagged_rows = [{**r, "_BatchName": d.name} for r in rows] if should_load else []
        out.append({
            "batchName": d.name,
            "folderPath": str(d),
            "cardCount": len(rows),
            "needsReviewCount": needs_rev,
            "below190Count": below_190,
            "cards": tagged_rows,
        })
    return out


def _get_live_lanes_and_logs() -> dict:
    try:
        import cli
        all_states = cli.get_all_lanes_state()
        safe_states = {}
        for lk, st_obj in all_states.items():
            clean_st = {k: v for k, v in st_obj.items() if k != "parallel_workers"}
            clean_workers = []
            for w in st_obj.get("parallel_workers") or []:
                if isinstance(w, dict):
                    clean_workers.append({wk: wv for wk, wv in w.items() if wk != "parallel_workers"})
            clean_st["parallel_workers"] = clean_workers
            safe_states[lk] = clean_st
        logs_by_lane = {lk: cli.get_active_job_logs(max_lines=500, lane=lk) for lk in cli.PROCESS_LANES.keys()}
        return {"lanes": safe_states, "logs": logs_by_lane, "runLogFiles": []}
    except Exception as e:
        return {"lanes": {}, "logs": {}, "error": str(e)}


def _load_tracked_sets_list() -> list[dict]:
    from Core.scraper_engine import load_tracked_sets_meta
    meta = load_tracked_sets_meta(prioritize=True)
    return [
        {
            "Folder_Name": m.get("folder_name", ""),
            "Sport": m.get("sport", "Baseball"),
            "Year": m.get("year", ""),
            "Manufacturer": m.get("manufacturer", "Topps"),
            "Checklist_Source": m.get("checklist_source", "Auto"),
            "Last_Scraped": m.get("last_scraped", "") or "NEVER",
            "Last_Upgraded": m.get("last_upgraded", "") or "NEVER",
            "TCDB_URL": u,
        }
        for u, m in meta.items()
    ]


def _save_tracked_sets_list(items: list[dict]):
    from Core.scraper_engine import save_all_tracked_sets
    new_dict = {}
    for r in items:
        u = str(r.get("TCDB_URL") or "").strip()
        fn = str(r.get("Folder_Name") or "").strip().replace(" ", "_")
        if not u or not fn:
            continue
        new_dict[u] = {
            "folder_name": fn,
            "sport": str(r.get("Sport") or "Baseball").strip(),
            "year": str(r.get("Year") or "").strip(),
            "manufacturer": str(r.get("Manufacturer") or "Topps").strip(),
            "checklist_source": str(r.get("Checklist_Source") or "Auto").strip(),
            "last_scraped": "" if str(r.get("Last_Scraped", "")).upper() == "NEVER" else str(r.get("Last_Scraped", "")),
            "last_upgraded": "" if str(r.get("Last_Upgraded", "")).upper() == "NEVER" else str(r.get("Last_Upgraded", "")),
        }
    save_all_tracked_sets(new_dict)


class _TabulasPythonApiAndReactHandler(BaseHTTPRequestHandler):
    def log_message(self, format_str, *args):
        pass

    def _send_json(self, data, status: int = 200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static_file(self, file_path: Path, root_dir: Path | None = None):
        try:
            resolved_file = file_path.resolve()
            if root_dir is not None:
                resolved_root = root_dir.resolve()
                if not resolved_file.is_relative_to(resolved_root):
                    self.send_response(403)
                    self.end_headers()
                    return
        except (OSError, ValueError):
            self.send_response(400)
            self.end_headers()
            return
        if not resolved_file.exists() or not resolved_file.is_file():
            self.send_response(404)
            self.end_headers()
            return
        mime, _ = mimetypes.guess_type(str(resolved_file))
        data = resolved_file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if route == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if route in ("/", "/index.html"):
            jsx_path = (APP_DIR / "App.jsx") if (APP_DIR / "App.jsx").exists() else (HUB_DIR / "App.jsx")
            body = _build_tabulas_react_html_v2(jsx_path).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if route.startswith("/static/cards/"):
            rel_part = route[len("/static/cards/"):].lstrip("/\\")
            self._serve_static_file(REVIEWED_CARDS_DIR / rel_part, root_dir=REVIEWED_CARDS_DIR)
            return
        if route.startswith("/static/templates/"):
            rel_part = route[len("/static/templates/"):].lstrip("/\\")
            self._serve_static_file(SET_LIBRARY_DIR / rel_part, root_dir=SET_LIBRARY_DIR)
            return
        if route.startswith("/static/batches/"):
            rel_part = route[len("/static/batches/"):].lstrip("/\\")
            self._serve_static_file(BATCHES_DIR / rel_part, root_dir=BATCHES_DIR)
            return
        if route.startswith("/static/labels/"):
            rel_part = route[len("/static/labels/"):].lstrip("/\\")
            self._serve_static_file(LABELS_OUTPUT_DIR / rel_part, root_dir=LABELS_OUTPUT_DIR)
            return

        if route == "/api/status":
            from Core.config import APP_RELEASE_VERSION, inspect_all_module_versions
            from Core.scraper_engine import load_resume_state
            import updater
            upd_check = updater.check_and_apply_pending_updates(auto_apply=False)
            pending_mod_map = updater.get_pending_module_updates(upd_check.get("pending_packages"))
            self._send_json({
                "ok": True,
                "version": APP_RELEASE_VERSION,
                "baseDir": str(HUB_DIR),
                "setLibraryDir": str(SET_LIBRARY_DIR),
                "modules": inspect_all_module_versions(pending_updates_map=pending_mod_map),
                "resumeState": load_resume_state(),
                "updater": {
                    "status": upd_check.get("status"),
                    "current_version": upd_check.get("current_version"),
                    "pending_count": upd_check.get("pending_count", 0),
                    "message": upd_check.get("message", ""),
                    "packages": upd_check.get("all_packages", []),
                    "snapshots": updater.list_available_rollback_versions(include_archived=False),
                    "archived_snapshots_count": updater.count_archived_rollback_snapshots(),
                },
            })
            return

        if route == "/api/updater":
            from Core.config import inspect_all_module_versions
            import updater
            inc_arc = (query.get("includeArchived") or ["false"])[0].lower() == "true"
            upd_check = updater.check_and_apply_pending_updates(auto_apply=False)
            pending_mod_map = updater.get_pending_module_updates(upd_check.get("pending_packages"))
            all_snaps = updater.list_available_rollback_versions(include_archived=inc_arc)
            self._send_json({
                **upd_check,
                "modules": inspect_all_module_versions(pending_updates_map=pending_mod_map),
                "snapshots": [s for s in all_snaps if not s.get("is_archived")],
                "archived_snapshots": [s for s in all_snaps if s.get("is_archived")],
                "archived_snapshots_count": updater.count_archived_rollback_snapshots(),
                "registry": updater.load_version_registry(),
            })
            return

        if route == "/api/templates/lookup":
            from Core.database import resolve_template_reference_paths
            set_n = (query.get("set") or [""])[0].strip()
            sub_n = (query.get("subset") or ["Base"])[0].strip()
            cnum_n = (query.get("cardNumber") or [""])[0].strip()
            self._send_json(resolve_template_reference_paths(set_n, sub_n, cnum_n))
            return

        if route == "/api/expenses":
            from Core.sales_engine import load_expenses_and_pricing_config
            self._send_json(load_expenses_and_pricing_config())
            return

        if route == "/api/compute/status":
            from Core.compute_backend import probe_system_hardware
            force_p = (query.get("refresh") or ["false"])[0].lower() == "true"
            self._send_json(probe_system_hardware(force_refresh=force_p))
            return

        if route == "/api/rate-learner":
            from Core.rate_learner import get_rate_learner
            self._send_json(get_rate_learner().get_dashboard_summary())
            return

        if route == "/api/logs/list":
            from datetime import datetime
            files_out = []
            if DAILY_LOGS_ROOT.exists():
                cands = [p for p in DAILY_LOGS_ROOT.rglob("*.log") if p.is_file()]
                cands.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
                for p in cands[:80]:
                    try:
                        st = p.stat()
                        files_out.append({
                            "name": p.name,
                            "relPath": p.relative_to(DAILY_LOGS_ROOT).as_posix(),
                            "fullPath": str(p),
                            "sizeKb": round(st.st_size / 1024.0, 1),
                            "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        })
                    except Exception:
                        continue
            self._send_json({"files": files_out, "logsDir": str(DAILY_LOGS_ROOT)})
            return

        if route == "/api/logs/download":
            rel_f = (query.get("file") or [""])[0].strip().lstrip("/\\")
            if not rel_f:
                self.send_response(400)
                self.end_headers()
                return
            try:
                logs_root = DAILY_LOGS_ROOT.resolve()
                target_log = (DAILY_LOGS_ROOT / rel_f).resolve()
                if not target_log.is_relative_to(logs_root):
                    self.send_response(403)
                    self.end_headers()
                    return
            except (OSError, ValueError):
                self.send_response(400)
                self.end_headers()
                return
            if not target_log.exists() or not target_log.is_file():
                self.send_response(404)
                self.end_headers()
                return
            raw_bytes = target_log.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{target_log.name}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(raw_bytes)))
            self.end_headers()
            self.wfile.write(raw_bytes)
            return

        if route == "/api/lanes":
            self._send_json(_get_live_lanes_and_logs())
            return

        if route == "/api/inventory":
            self._send_json(_get_cached_inventory_records())
            return

        if route == "/api/incoming-scans":
            self._send_json(_discover_incoming_scans())
            return

        if route == "/api/batches":
            batch_name = (query.get("batch") or [""])[0]
            self._send_json(_discover_uncommitted_batches(include_cards_for=batch_name))
            return

        if route == "/api/checklists/lookup":
            from Core.config import format_print_run
            from Core.database import lookup_card_details

            set_name = (query.get("set") or [""])[0].strip()
            q_txt = (query.get("q") or [""])[0].strip().lower()
            card_num = (query.get("cardNumber") or [""])[0].strip().lstrip("#")
            sub_hint = (query.get("subset") or [""])[0].strip()
            lim = max(10, min(200, int((query.get("limit") or ["40"])[0] or 40)))

            set_df = _get_cached_checklist_df(set_name) if set_name else _get_cached_checklist_df("")
            if set_df is None or set_df.empty:
                self._send_json({"subsets": ["Base"], "matches": [], "exact": None})
                return

            raw_subs = [s for s in set_df["Subset"].dropna().unique().tolist() if str(s).strip()]
            subsets_sorted = list(dict.fromkeys((["Base"] if "Base" in raw_subs else []) + sorted(raw_subs)))

            exact_info = lookup_card_details(set_df, set_name, card_num, sub_hint or None) if (set_name and card_num) else None

            view = set_df
            if q_txt:
                q_no_hash = q_txt.lstrip("#")
                mask = (
                    view["Card Number"].astype(str).str.lower().str.contains(q_no_hash, regex=False, na=False)
                    | view["Player"].astype(str).str.lower().str.contains(q_txt, regex=False, na=False)
                    | view["Team"].astype(str).str.lower().str.contains(q_txt, regex=False, na=False)
                )
                view = view[mask]

            grouped: dict[tuple[str, str], dict] = {}
            for _, r in view.head(1500).iterrows():
                cn = str(r.get("Card Number") or "").strip().lstrip("#")
                plr = str(r.get("Player") or "").strip()
                sub = str(r.get("Subset") or "Base").strip() or "Base"
                pr = format_print_run(r.get("Print Run") or "")
                k = (cn, plr)
                if k not in grouped:
                    if len(grouped) >= lim:
                        continue
                    grouped[k] = {
                        "cardNumber": cn,
                        "player": plr,
                        "team": str(r.get("Team") or "").strip(),
                        "attributes": str(r.get("Attributes") or "").strip(),
                        "subsets": [],
                        "printRuns": {},
                    }
                if sub not in grouped[k]["subsets"]:
                    grouped[k]["subsets"].append(sub)
                if pr:
                    grouped[k]["printRuns"][sub] = pr

            self._send_json({
                "subsets": subsets_sorted,
                "matches": list(grouped.values()),
                "exact": exact_info,
            })
            return

        if route == "/api/checklists":
            from Core.config import TCDB_STANDARD_GLOSSARY
            set_filter = (query.get("set") or [""])[0].strip()
            year_filter = (query.get("year") or [""])[0].strip()
            subset_filter = (query.get("subset") or [""])[0].strip()
            attr_filter = (query.get("attribute") or [""])[0].strip()
            status_filter = (query.get("status") or [""])[0].strip()
            q_filter = (query.get("q") or [""])[0].strip().lower()
            page_num = max(1, int((query.get("page") or ["1"])[0] or 1))
            limit_val = max(50, min(5000, int((query.get("limit") or ["350"])[0] or 350)))

            chk_path = CHECKLIST_PATH
            set_dir = SET_CHECKLISTS_DIR
            set_files = sorted([p.name for p in set_dir.glob("*.csv")]) if set_dir.exists() else []

            # Populate knownSets / knownYears from cached master metadata
            master_df = _get_cached_checklist_df("")
            total_records = len(master_df)
            known_sets = list(_CHK_MASTER_CACHE.get("known_sets") or [])
            known_years = list(_CHK_MASTER_CACHE.get("known_years") or [])

            # Fast path: use cached per-set CSV when a specific Set is chosen
            work_df = _get_cached_checklist_df(set_filter) if set_filter else master_df
            if not work_df.empty and year_filter:
                work_df = work_df[work_df["Set"].astype(str).str.contains(year_filter, regex=False, na=False)]

            known_subsets = sorted([s for s in work_df["Subset"].dropna().unique().tolist() if str(s).strip()]) if not work_df.empty else []

            if not work_df.empty:
                if subset_filter:
                    work_df = work_df[work_df["Subset"].astype(str) == subset_filter]
                if attr_filter:
                    work_df = work_df[work_df["Attributes"].astype(str).str.upper().str.contains(attr_filter.upper(), regex=False, na=False)]
                if status_filter in ("Downloaded (Front & Back)", "Missing Back Only", "Not Downloaded Yet"):
                    f_yes = work_df["Front_Downloaded"].astype(str).str.strip().str.lower() == "yes"
                    b_yes = work_df["Back_Downloaded"].astype(str).str.strip().str.lower() == "yes"
                    if status_filter == "Downloaded (Front & Back)":
                        work_df = work_df[f_yes & b_yes]
                    elif status_filter == "Missing Back Only":
                        work_df = work_df[f_yes & (~b_yes)]
                    else:
                        work_df = work_df[~f_yes]
                if q_filter:
                    q_mask = (
                        work_df["TCDB_CID"].astype(str).str.lower().str.contains(q_filter, regex=False, na=False)
                        | work_df["Player"].astype(str).str.lower().str.contains(q_filter, regex=False, na=False)
                        | work_df["Card Number"].astype(str).str.lower().str.contains(q_filter, regex=False, na=False)
                        | work_df["Subset"].astype(str).str.lower().str.contains(q_filter, regex=False, na=False)
                        | work_df["Team"].astype(str).str.lower().str.contains(q_filter, regex=False, na=False)
                        | work_df["Attributes"].astype(str).str.lower().str.contains(q_filter, regex=False, na=False)
                    )
                    work_df = work_df[q_mask]

            total_matching = len(work_df)
            offset = (page_num - 1) * limit_val
            rows = work_df.iloc[offset : offset + limit_val].to_dict(orient="records") if total_matching > 0 else []

            self._send_json({
                "masterPath": str(chk_path),
                "setFiles": set_files,
                "knownSets": known_sets,
                "knownYears": known_years,
                "knownSubsets": known_subsets,
                "totalRecords": total_records,
                "totalMatchingCount": total_matching,
                "page": page_num,
                "limit": limit_val,
                "glossary": TCDB_STANDARD_GLOSSARY,
                "rows": rows,
            })
            return

        if route == "/api/completion":
            import pandas as pd
            from Core.database import load_inventory_df
            from Core.market_engine import SET_COMPLETION_MODES, compute_set_completion_metrics

            set_name = (query.get("set") or [""])[0].strip()
            mode_idx = max(0, min(4, int((query.get("modeIdx") or ["0"])[0] or 0)))
            excl_sn = (query.get("excludeSN") or ["false"])[0].lower() == "true"

            chk_df = _get_cached_checklist_df(set_name) if set_name else pd.DataFrame()
            if chk_df is None or chk_df.empty or not set_name:
                self._send_json({"modes": [], "owned": [], "missing": [], "bySubset": [], "byPlayer": []})
                return

            inv_df = load_inventory_df()

            modes_summary = []
            active_res = None
            for idx_m, m_lbl in enumerate(SET_COMPLETION_MODES):
                res_m = compute_set_completion_metrics(
                    chk_df,
                    inv_df,
                    set_name=set_name,
                    completion_mode=m_lbl,
                    exclude_limited_print_runs=excl_sn,
                )
                modes_summary.append({
                    "modeIdx": idx_m,
                    "label": m_lbl,
                    "owned_count": res_m["owned_count"],
                    "total_count": res_m["total_count"],
                    "missing_count": res_m.get("missing_count", 0),
                    "completion_pct": res_m["completion_pct"],
                })
                if idx_m == mode_idx:
                    active_res = res_m

            owned_df = active_res["owned_df"] if active_res else pd.DataFrame()
            missing_df = active_res["missing_df"] if active_res else pd.DataFrame()
            combined_df = pd.concat([owned_df, missing_df], ignore_index=True) if (not owned_df.empty or not missing_df.empty) else pd.DataFrame()

            by_subset = []
            by_player = []
            if not combined_df.empty:
                for sub_k, grp in combined_df.groupby("Subset"):
                    tot_s = len(grp)
                    own_s = int((grp["Owned"] == True).sum())
                    by_subset.append({
                        "Subset": str(sub_k),
                        "Owned": own_s,
                        "Total": tot_s,
                        "Missing": tot_s - own_s,
                        "Pct": round((own_s / float(tot_s)) * 100.0, 1) if tot_s else 0.0,
                    })
                by_subset.sort(key=lambda x: (-x["Owned"], -x["Total"], x["Subset"]))

                for plr_k, grp in combined_df.groupby("Player"):
                    tot_p = len(grp)
                    own_p = int((grp["Owned"] == True).sum())
                    by_player.append({
                        "Player": str(plr_k),
                        "Owned": own_p,
                        "Total": tot_p,
                        "Missing": tot_p - own_p,
                        "Pct": round((own_p / float(tot_p)) * 100.0, 1) if tot_p else 0.0,
                    })
                by_player.sort(key=lambda x: (-x["Owned"], -x["Total"], x["Player"]))

            self._send_json({
                "modes": modes_summary,
                "owned": owned_df.head(2000).to_dict(orient="records") if not owned_df.empty else [],
                "missing": missing_df.head(2000).to_dict(orient="records") if not missing_df.empty else [],
                "bySubset": by_subset[:250],
                "byPlayer": by_player[:250],
            })
            return

        if route == "/api/purchase-planner":
            from urllib.parse import quote
            import pandas as pd
            from Core.config import canonical_subset_key, format_print_run, norm
            from Core.database import load_inventory_df
            from Core.market_engine import (
                _safe_float,
                build_comp_key,
                generate_cards_to_buy_list,
                load_market_comps_cache,
            )

            set_name = (query.get("set") or [""])[0].strip()
            subset_f = (query.get("subset") or ["All Subsets"])[0].strip()
            player_f = (query.get("player") or [""])[0].strip()
            max_budget = float((query.get("maxBudget") or ["0"])[0] or 0)
            excl_sn = (query.get("excludeSN") or ["false"])[0].lower() == "true"

            set_slice = _get_cached_checklist_df(set_name) if set_name else pd.DataFrame()
            if set_slice is None or set_slice.empty or not set_name:
                self._send_json({"rows": [], "summary": {"owned_count": 0, "total_count": 0, "missing_count": 0, "estimated_total_cost": 0.0}, "subsets": [], "players": []})
                return

            inv_df = load_inventory_df()
            subsets_list = sorted(set_slice["Subset"].dropna().unique().tolist())
            players_list = sorted(set_slice["Player"].dropna().unique().tolist())[:500]

            if player_f:
                # Filter across ALL matching cards for the player (or #CardNumber) AND optional Subset
                work = set_slice.copy()
                if subset_f and subset_f != "All Subsets":
                    work = work[work["Subset"].astype(str).str.lower() == subset_f.lower()]
                if player_f.startswith("#"):
                    cn_q = norm(player_f.lstrip("#"))
                    work = work[work["Card Number"].map(norm) == cn_q]
                else:
                    pf_low = player_f.lower()
                    work = work[
                        work["Player"].astype(str).str.lower().str.contains(pf_low, regex=False, na=False)
                        | work["Card Number"].astype(str).str.lower().eq(pf_low)
                    ]
                if excl_sn and not work.empty:
                    pr_nums = pd.to_numeric(work["Print Run"].map(format_print_run), errors="coerce")
                    work = work[pr_nums.isna()]

                inv_slice = inv_df[(inv_df["Set"] == set_name) & (inv_df["Status"] != "Sold")] if not inv_df.empty else pd.DataFrame()
                owned_pairs = {
                    (norm(str(cn).lstrip("#")), canonical_subset_key(str(s), set_name))
                    for cn, s in zip(inv_slice.get("Card Number", []), inv_slice.get("Subset", []))
                }
                work["Owned"] = [
                    (norm(str(cn).lstrip("#")), canonical_subset_key(str(s), set_name)) in owned_pairs
                    for cn, s in zip(work["Card Number"], work["Subset"])
                ]
                owned_cnt = int((work["Owned"] == True).sum())
                tot_cnt = len(work)
                miss = work[work["Owned"] != True].copy()

                if miss.empty:
                    buy_df = pd.DataFrame()
                    summary = {"owned_count": owned_cnt, "total_count": tot_cnt, "missing_count": 0, "estimated_total_cost": 0.0}
                else:
                    comps_df = load_market_comps_cache()
                    comps_by_key = {str(r["Comp_Key"]): r.to_dict() for _, r in comps_df.iterrows() if r.get("Comp_Key")}
                    est_prices, buy_links = [], []
                    for _, r in miss.iterrows():
                        ck = build_comp_key(r["Set"], r["Subset"], r["Card Number"], r["Player"])
                        cc = comps_by_key.get(ck)
                        if cc and _safe_float(cc.get("Ungraded"), 0.0) > 0:
                            p_val = _safe_float(cc["Ungraded"], 1.50)
                        else:
                            pr_s = format_print_run(r.get("Print Run", ""))
                            sub_u = str(r.get("Subset", "Base")).upper()
                            if pr_s == "1":
                                p_val = 150.00
                            elif pr_s.isdigit() and int(pr_s) <= 10:
                                p_val = 45.00
                            elif pr_s.isdigit() and int(pr_s) <= 50:
                                p_val = 18.00
                            elif pr_s.isdigit() and int(pr_s) <= 199:
                                p_val = 7.50
                            elif sub_u in ("BASE", "BASE SET"):
                                p_val = 1.25
                            else:
                                p_val = 3.00
                        est_prices.append(round(p_val, 2))
                        q_ebay = quote(f"{r['Set']} #{r['Card Number']} {r['Player']} {r['Subset'] if r['Subset'] != 'Base' else ''}".strip())
                        buy_links.append(f"https://www.ebay.com/sch/i.html?_nkw={q_ebay}&_sop=15")
                    miss["Est_Cost_USD"] = est_prices
                    miss["eBay_Buy_Link"] = buy_links
                    if max_budget > 0:
                        miss = miss[miss["Est_Cost_USD"] <= float(max_budget)].copy()
                    buy_df = miss.sort_values(by=["Est_Cost_USD", "Card Number"], ascending=[True, True]).reset_index(drop=True)
                    summary = {
                        "owned_count": owned_cnt,
                        "total_count": tot_cnt,
                        "missing_count": len(buy_df),
                        "estimated_total_cost": round(float(buy_df["Est_Cost_USD"].sum()), 2),
                    }
            else:
                target_type = "Specific Subset / Insert" if (subset_f and subset_f != "All Subsets") else "Set Completion"
                buy_df, summary = generate_cards_to_buy_list(
                    set_slice,
                    inv_df,
                    set_name=set_name,
                    target_type=target_type,
                    subset_filter="" if subset_f == "All Subsets" else subset_f,
                    rainbow_card_number="",
                    exclude_limited_print_runs=excl_sn,
                    max_budget_per_card=max_budget,
                )

            self._send_json({
                "rows": buy_df.head(400).to_dict(orient="records") if not buy_df.empty else [],
                "summary": summary,
                "subsets": subsets_list,
                "players": players_list,
            })
            return

        if route == "/api/sales/strategy-recommendations":
            from Core.database import load_inventory_df
            from Core.sales_engine import compute_expense_based_strategy_recommendations
            inv_df = load_inventory_df()
            self._send_json(compute_expense_based_strategy_recommendations(inv_df))
            return

        if route == "/api/directory":
            self._send_json(_get_cached_directory_records())
            return

        if route == "/api/market-data":
            from Core.market_engine import load_grading_tiers_cache
            self._send_json({
                "tiers": load_grading_tiers_cache(),
                "comps": _read_csv_records(MARKET_COMPS_CACHE_FILE, max_rows=15000),
                "history": _read_csv_records(COLLECTION_HISTORY_FILE, max_rows=1000),
                "alerts": _read_json_file(MARKET_ALERTS_FILE, []),
                "alertSettings": _read_json_file(MARKET_SETTINGS_FILE, {}),
            })
            return

        if route == "/api/sales-data":
            from Core.sales_engine import load_expenses_and_pricing_config, load_listing_drafts_df
            self._send_json({
                "expensesConfig": load_expenses_and_pricing_config(),
                "listingDrafts": load_listing_drafts_df().to_dict(orient="records"),
                "recommendedLots": _read_json_file(RECOMMENDED_LOTS_FILE, []),
                "cardLevelTargets": _read_json_file(CARD_LEVEL_TARGETS_FILE, {}),
            })
            return

        if route == "/api/schedules":
            import cli
            self._send_json(cli.load_all_scheduled_jobs(query_live_os_status=True))
            return

        if route == "/api/config/tracked-sets":
            self._send_json(_load_tracked_sets_list())
            return

        if route == "/api/notifications":
            from Core.config import NOTIFICATIONS_CSV_COLUMNS, NOTIFICATIONS_HISTORY_CSV
            if not NOTIFICATIONS_HISTORY_CSV.exists():
                _write_csv_records(NOTIFICATIONS_HISTORY_CSV, [], explicit_cols=NOTIFICATIONS_CSV_COLUMNS)
            all_notifs = _read_csv_records(NOTIFICATIONS_HISTORY_CSV, max_rows=5000)
            visible_notifs = [n for n in all_notifs if str(n.get("Cleared", "False")).lower() != "true"]
            visible_notifs.reverse()
            self._send_json({
                "notifications": visible_notifs,
                "totalArchivedCount": len(all_notifs),
                "csvPath": str(NOTIFICATIONS_HISTORY_CSV),
            })
            return

        if route == "/api/sold-cards":
            from Core.config import SOLD_CARDS_CSV, SOLD_CARDS_CSV_COLUMNS
            if not SOLD_CARDS_CSV.exists():
                _write_csv_records(SOLD_CARDS_CSV, [], explicit_cols=SOLD_CARDS_CSV_COLUMNS)
            sold_rows = _read_csv_records(SOLD_CARDS_CSV, max_rows=20000)
            sold_rows.reverse()
            self._send_json({
                "rows": sold_rows,
                "csvPath": str(SOLD_CARDS_CSV),
            })
            return

        if route == "/api/inventory/card-level":
            from Core.database import load_inventory_df
            from Core.sales_engine import build_card_level_inventory_df
            inv_df = load_inventory_df()
            cl_df = build_card_level_inventory_df(inv_df, default_retain_qty=1)
            self._send_json({
                "rows": cl_df.to_dict(orient="records") if not cl_df.empty else [],
                "totalUniqueCards": len(cl_df),
            })
            return

        if route == "/api/sales/set-blurb":
            from Core.sales_engine import fetch_and_cache_set_blurb
            set_q = (query.get("set") or [""])[0].strip()
            force_ref = (query.get("forceRefresh") or ["false"])[0].lower() == "true"
            reset_def = (query.get("resetToDefault") or ["false"])[0].lower() == "true"
            self._send_json(fetch_and_cache_set_blurb(set_q, force_refresh=force_ref, reset_to_default=reset_def))
            return

        if route == "/api/sales/lots":
            from Core.database import load_inventory_df
            from Core.sales_engine import build_card_level_inventory_df, generate_lot_and_set_recommendations
            inv_df = load_inventory_df()
            strict_multi = (query.get("strictMulti") or ["true"])[0].lower() == "true"
            lots_df = generate_lot_and_set_recommendations(inv_df, only_surplus_multi_copies=strict_multi)
            card_lvl_df = build_card_level_inventory_df(inv_df, default_retain_qty=1)
            self._send_json({
                "lots": lots_df.to_dict(orient="records") if not lots_df.empty else [],
                "cardLevel": card_lvl_df.to_dict(orient="records") if not card_lvl_df.empty else [],
            })
            return
        if route == "/api/config/set-cart":
            self._send_json(_read_json_file(SET_CART_JSON_FILE, []))
            return

        self._send_json({"ok": False, "error": f"Not found: {route}"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(raw_body)
        except Exception:
            payload = {}

        if route == "/api/updater/action" and isinstance(payload, dict):
            import importlib
            import updater
            act = str(payload.get("action") or "check")

            def _reload_loaded_core_modules():
                for mod_name in (
                    "Core.config",
                    "Core.database",
                    "Core.label_engine",
                    "Core.scraper_engine",
                    "Core.market_engine",
                    "Core.vision_grader",
                    "Core.sales_engine",
                    "cli",
                    "updater",
                ):
                    if mod_name in sys.modules:
                        try:
                            importlib.reload(sys.modules[mod_name])
                        except Exception:
                            pass

            from Core.config import inspect_all_module_versions
            if act == "check":
                res = updater.check_and_apply_pending_updates(auto_apply=False)
                pending_mod_map = updater.get_pending_module_updates(res.get("pending_packages"))
                self._send_json({
                    "success": True,
                    **res,
                    "modules": inspect_all_module_versions(pending_updates_map=pending_mod_map),
                    "snapshots": updater.list_available_rollback_versions(include_archived=False),
                    "archived_snapshots_count": updater.count_archived_rollback_snapshots(),
                })
                return
            elif act == "apply":
                res = updater.check_and_apply_pending_updates(auto_apply=True, dry_run=bool(payload.get("dryRun", False)))
                reloaded = False
                restart_required = False
                if res.get("status") == "UPDATED" and not payload.get("dryRun", False):
                    _reload_loaded_core_modules()
                    reloaded = True
                    for ar in res.get("applied_results") or []:
                        if "launch_tabulas_hub.py" in (ar.get("files_modified") or []):
                            restart_required = True
                from Core.config import inspect_all_module_versions as _inspect_mods_fresh
                self._send_json({
                    "success": res.get("status") in ("UPDATED", "UP_TO_DATE"),
                    "reloaded": reloaded,
                    "restartRequired": restart_required,
                    **res,
                    "modules": _inspect_mods_fresh(),
                    "snapshots": updater.list_available_rollback_versions(include_archived=False),
                    "archived_snapshots_count": updater.count_archived_rollback_snapshots(),
                })
                return
            elif act == "rollback":
                target_v = str(payload.get("targetVersion") or "").strip()
                res = updater.rollback_to_version(target_v)
                restart_required = False
                if res.get("success"):
                    _reload_loaded_core_modules()
                    restart_required = "launch_tabulas_hub.py" in (res.get("restored_files") or [])
                from Core.config import inspect_all_module_versions as _inspect_mods_fresh
                self._send_json({
                    **res,
                    "reloaded": bool(res.get("success")),
                    "restartRequired": restart_required,
                    "modules": _inspect_mods_fresh(),
                    "snapshots": updater.list_available_rollback_versions(include_archived=False),
                    "archived_snapshots_count": updater.count_archived_rollback_snapshots(),
                })
                return

        if route == "/api/set-library/action" and isinstance(payload, dict):
            import cli
            act = str(payload.get("action") or "")
            exec_mode = str(payload.get("executionMode") or "queue")
            set_dir = SET_CHECKLISTS_DIR
            est_sets = len(list(set_dir.glob("*.csv"))) if set_dir.exists() else 64
            try:
                if act == "sync_status":
                    res_j = cli.start_or_queue_background_job(
                        job_type="sync_set_library_status",
                        title="Sync Set Library Download Status",
                        payload={"estimated_total": max(1, est_sets)},
                        lane=None,
                        execution_mode=exec_mode,
                    )
                    self._send_json({"success": True, **res_j, "asyncJob": True, "message": f"Launched Set Library Status Sync on {res_j.get('lane')}!"})
                elif act == "repair_checklists":
                    res_j = cli.start_or_queue_background_job(
                        job_type="repair_checklists",
                        title=f"Repair Existing Checklist CSVs ({est_sets} sets)",
                        payload={"estimated_total": max(1, est_sets)},
                        lane=None,
                        execution_mode=exec_mode,
                    )
                    self._send_json({"success": True, **res_j, "asyncJob": True, "message": f"Launched Checklist CSV Repair ({est_sets} sets) on {res_j.get('lane')}!"})
                elif act == "clean_reference_library":
                    res_j = cli.start_or_queue_background_job(
                        job_type="clean_reference_library",
                        title="Clean Reference Library Folders & Filenames",
                        payload={
                            "dry_run": bool(payload.get("dryRun", False)),
                            "estimated_total": max(1, est_sets),
                        },
                        lane=None,
                        execution_mode=exec_mode,
                    )
                    self._send_json({"success": True, **res_j, "asyncJob": True, "message": f"Launched Reference Library Folder & Filename Cleanup on {res_j.get('lane')}!"})
                elif act == "repair_directory":
                    from Core.scraper_engine import load_tcdb_master_directory, repair_tcdb_set_directory
                    res_dir = repair_tcdb_set_directory(fetch_missing_image_pct=False)
                    _log_ui_action_to_file("Set Browser", "Repair Set Directory CSV", res_dir.get("message", ""))
                    self._send_json({
                        "success": True,
                        **res_dir,
                        "directoryRows": load_tcdb_master_directory().to_dict(orient="records"),
                    })
                elif act == "deduplicate_tracked_sets":
                    from Core.scraper_engine import deduplicate_tracked_sets_and_directory, load_tcdb_master_directory
                    res_dedup = deduplicate_tracked_sets_and_directory()
                    _log_ui_action_to_file(
                        "Maintenance",
                        "Deduplicate Tracked Sets & Directory",
                        f"Tracked {res_dedup['before_tracked']}->{res_dedup['after_tracked']} ({res_dedup['removed_tracked']} removed, {res_dedup['renamed_tracked']} renamed) | Directory -{res_dedup['removed_directory']}",
                    )
                    self._send_json({
                        "success": True,
                        **res_dedup,
                        "trackedSets": _load_tracked_sets_list(),
                        "directoryRows": load_tcdb_master_directory().to_dict(orient="records"),
                        "message": (
                            f"Cleaned Tracked Sets ({res_dedup['before_tracked']} -> {res_dedup['after_tracked']}: "
                            f"{res_dedup['removed_tracked']} duplicate(s) removed, {res_dedup['renamed_tracked']} standardized) "
                            f"& Directory ({res_dedup['removed_directory']} duplicate(s) removed)."
                        ),
                    })
                else:
                    self._send_json({"success": False, "error": f"Unknown set-library action: {act}"}, status=400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if route == "/api/expenses" and isinstance(payload, dict):
            from Core.database import load_inventory_df, save_inventory_df
            from Core.sales_engine import apply_pricing_strategy_to_inventory_df, load_expenses_and_pricing_config, save_expenses_and_pricing_config
            curr_cfg = load_expenses_and_pricing_config()
            if isinstance(payload.get("expenses_ledger"), list):
                curr_cfg["expenses_ledger"] = payload["expenses_ledger"]
            if isinstance(payload.get("pricing_strategy"), dict):
                curr_cfg["pricing_strategy"].update(payload["pricing_strategy"])
            save_expenses_and_pricing_config(curr_cfg)
            if payload.get("applyToInventory", False):
                inv_df = load_inventory_df()
                upd_inv, summary = apply_pricing_strategy_to_inventory_df(inv_df, cfg=curr_cfg)
                save_inventory_df(upd_inv)
                self._send_json({"success": True, "config": load_expenses_and_pricing_config(), "summary": summary, "inventoryRows": upd_inv.to_dict(orient="records")})
            else:
                self._send_json({"success": True, "config": load_expenses_and_pricing_config()})
            return

        if route == "/api/inventory" and isinstance(payload, list):
            import pandas as pd
            from Core.database import load_inventory_df, save_inventory_df, sync_inventory_copy_numbers_and_files
            from Core.vision_grader import recalculate_dataframe_multi_grader_roi

            prev_df = load_inventory_df()
            prev_by_sku = {str(r["SKU"]).strip(): r.to_dict() for _, r in prev_df.iterrows() if str(r.get("SKU", "")).strip()} if not prev_df.empty else {}

            in_df = pd.DataFrame(payload)
            if not in_df.empty:
                recalc_indices = []
                manual_price_overrides: dict[int, tuple[str | None, str | None]] = {}

                for idx_r, row_r in in_df.iterrows():
                    sku_s = str(row_r.get("SKU") or "").strip()
                    prev_r = prev_by_sku.get(sku_s)
                    in_raw = str(row_r.get("Raw_Price") or "").strip()
                    in_rec = str(row_r.get("Rec_Sale_Price") or "").strip()

                    if prev_r is None or not in_rec:
                        # Brand new row or missing Rec_Sale_Price -> calculate ROI & pricing
                        recalc_indices.append(idx_r)
                        if in_raw or in_rec:
                            manual_price_overrides[idx_r] = (in_raw if in_raw else None, in_rec if in_rec else None)
                    else:
                        label_fields_changed = (
                            str(row_r.get("Set") or "").strip() != str(prev_r.get("Set") or "").strip()
                            or str(row_r.get("Subset") or "").strip() != str(prev_r.get("Subset") or "").strip()
                            or str(row_r.get("Card Number") or "").strip().lstrip("#") != str(prev_r.get("Card Number") or "").strip().lstrip("#")
                            or str(row_r.get("Player") or "").strip() != str(prev_r.get("Player") or "").strip()
                            or str(row_r.get("Team") or "").strip() != str(prev_r.get("Team") or "").strip()
                            or str(row_r.get("Print Run") or "").strip() != str(prev_r.get("Print Run") or "").strip()
                        )
                        id_changed = label_fields_changed or (
                            str(row_r.get("Hold_Tag") or "").strip() != str(prev_r.get("Hold_Tag") or "").strip()
                        )
                        raw_edited = in_raw != str(prev_r.get("Raw_Price") or "").strip()
                        rec_edited = in_rec != str(prev_r.get("Rec_Sale_Price") or "").strip()

                        if label_fields_changed:
                            # Auto-flag card as unprinted whenever label-visible identity metadata changes
                            in_df.at[idx_r, "Label_Printed"] = "False"
                        if id_changed:
                            recalc_indices.append(idx_r)
                        if raw_edited or rec_edited:
                            manual_price_overrides[idx_r] = (
                                in_raw if raw_edited else None,
                                in_rec if rec_edited else None,
                            )

                if recalc_indices:
                    sub_recalc = recalculate_dataframe_multi_grader_roi(in_df.loc[recalc_indices].copy())
                    for col_c in sub_recalc.columns:
                        if col_c not in in_df.columns:
                            in_df[col_c] = ""
                        in_df.loc[recalc_indices, col_c] = sub_recalc[col_c]

                # Strictly preserve user-typed Raw_Price and Rec_Sale_Price edits
                for idx_r, (keep_raw, keep_rec) in manual_price_overrides.items():
                    if keep_raw is not None:
                        in_df.at[idx_r, "Raw_Price"] = keep_raw
                    if keep_rec is not None:
                        in_df.at[idx_r, "Rec_Sale_Price"] = keep_rec

            synced_df, renamed_cnt = sync_inventory_copy_numbers_and_files(in_df, previous_inv_df=prev_df)
            saved_df = save_inventory_df(synced_df)
            self._send_json({"success": True, "count": len(saved_df), "renamedFiles": renamed_cnt, "rows": saved_df.to_dict(orient="records")})
            return

        if route == "/api/inventory/delete" and isinstance(payload, dict):
            from Core.database import delete_inventory_skus, load_inventory_df
            res_del = delete_inventory_skus([str(s).strip() for s in (payload.get("skus") or []) if str(s).strip()], delete_card_images=bool(payload.get("deleteCardImages", False)))
            self._send_json({"success": True, **res_del, "rows": load_inventory_df().to_dict(orient="records")})
            return

        if route == "/api/batches/update" and isinstance(payload, dict):
            import pandas as pd
            from Core.database import apply_manifest_overrides_and_rename
            from Core.vision_grader import recalculate_dataframe_multi_grader_roi
            b_name = str(payload.get("batchName") or "").strip()
            b_dir = BATCHES_DIR / b_name
            man_p = b_dir / "Batch_Inventory_Manifest.csv"
            if not man_p.exists():
                self._send_json({"success": False, "error": f"Batch manifest not found in {BATCHES_DIR}: {b_name}"}, status=404)
                return
            full_df = pd.read_csv(man_p, dtype=str, keep_default_na=False)
            updates_list = payload.get("cards") or []
            confirm_only = bool(payload.get("confirmOnly", False))
            target_skus_set: set[str] = set()
            touched_sets: set[str] = set()

            if updates_list and not full_df.empty:
                full_df["SKU"] = full_df["SKU"].astype(str).str.strip()
                if confirm_only:
                    # Fast-path confirmation when nothing changed: mark Needs_Review = False & tag UserConfirmed
                    target_skus_set = {str(u.get("SKU") or "").strip() for u in updates_list if str(u.get("SKU") or "").strip()}
                    for r_idx, row in full_df.iterrows():
                        if str(row.get("SKU") or "").strip() in target_skus_set:
                            full_df.at[r_idx, "Needs_Review"] = "False"
                            sig_now = str(row.get("OCR_Signals") or "").strip()
                            if "UserConfirmed" not in sig_now:
                                full_df.at[r_idx, "OCR_Signals"] = f"{sig_now}+UserConfirmed".strip("+")
                    tmp_man = man_p.with_suffix(".csv.tmp")
                    full_df.to_csv(tmp_man, index=False, encoding="utf-8-sig")
                    os.replace(str(tmp_man), str(man_p))
                    _log_ui_action_to_file("Batch", f"Confirmed {len(target_skus_set)} card(s) correct in {b_name}", "confirmOnly=True")
                    self._send_json({
                        "success": True,
                        "confirmedOnly": True,
                        "confirmedCount": len(target_skus_set),
                        "overridesApplied": 0,
                        "renamedCount": 0,
                        "cards": full_df.to_dict(orient="records"),
                    })
                    return

                upd_df = pd.DataFrame(updates_list)
                if "SKU" in upd_df.columns:
                    upd_df["SKU"] = upd_df["SKU"].astype(str).str.strip()
                    target_skus_set = {s for s in upd_df["SKU"].tolist() if s}
                    if "Set" in upd_df.columns:
                        touched_sets = {str(s).strip() for s in upd_df["Set"].tolist() if str(s).strip()}
                    for col_c in upd_df.columns:
                        if col_c not in full_df.columns:
                            full_df[col_c] = ""
                    idx_full = full_df.set_index("SKU")
                    idx_upd = upd_df.drop_duplicates(subset=["SKU"], keep="last").set_index("SKU")
                    idx_full.update(idx_upd)
                    full_df = idx_full.reset_index()

            # Use cached single-set checklist when all updated rows belong to 1 set (instant save!)
            cached_chk = _get_cached_checklist_df(next(iter(touched_sets))) if len(touched_sets) == 1 else _get_cached_checklist_df("")
            res_df, ovr_c, ren_c = apply_manifest_overrides_and_rename(
                b_dir,
                df_override=full_df,
                target_skus=target_skus_set if target_skus_set else None,
                master_df_override=cached_chk,
            )

            # Recalculate ROI only on modified rows for snappy response
            if target_skus_set and not res_df.empty:
                mod_mask = res_df["SKU"].astype(str).isin(target_skus_set)
                if mod_mask.any():
                    sub_roi = recalculate_dataframe_multi_grader_roi(res_df.loc[mod_mask].copy())
                    for col_r in sub_roi.columns:
                        if col_r not in res_df.columns:
                            res_df[col_r] = ""
                        res_df.loc[mod_mask, col_r] = sub_roi[col_r]
                    res_df.to_csv(man_p, index=False, encoding="utf-8-sig")

            _log_ui_action_to_file("Batch", f"Updated {len(target_skus_set) or len(res_df)} card(s) in {b_name}", f"overrides={ovr_c}, renamed={ren_c}")
            self._send_json({
                "success": True,
                "overridesApplied": ovr_c,
                "renamedCount": ren_c,
                "cards": res_df.to_dict(orient="records"),
            })
            return

        if route == "/api/batches/rotate-image" and isinstance(payload, dict):
            from PIL import Image
            b_name = str(payload.get("batchName") or "").strip()
            file_name = str(payload.get("fileName") or "").strip()
            degrees = int(payload.get("degrees") or 90)
            img_p = (BATCHES_DIR / b_name / file_name).resolve()
            if not b_name or not file_name or not str(img_p).startswith(str(BATCHES_DIR.resolve())) or not img_p.exists():
                self._send_json({"success": False, "error": f"Image not found: {file_name}"}, status=404)
                return
            try:
                with Image.open(img_p) as im:
                    # PIL rotate is counter-clockwise, so -degrees rotates clockwise
                    rot_im = im.convert("RGB").rotate(-degrees, expand=True)
                rot_im.save(img_p, format="JPEG", quality=94)
                _log_ui_action_to_file("Batch", f"Rotated {file_name} {degrees}° CW", f"Batch: {b_name}")
                self._send_json({"success": True, "fileName": file_name, "rotatedDegrees": degrees})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if route == "/api/batches/reprocess-card" and isinstance(payload, dict):
            import cli
            b_name = str(payload.get("batchName") or "").strip()
            raw_skus = payload.get("skus") if isinstance(payload.get("skus"), list) else [payload.get("sku")]
            skus_list = [str(s).strip() for s in raw_skus if str(s or "").strip()]
            b_dir = BATCHES_DIR / b_name
            if not b_name or not skus_list or not (b_dir / "Batch_Inventory_Manifest.csv").exists():
                self._send_json({"success": False, "error": f"Invalid batch '{b_name}' or empty SKU list."}, status=400)
                return

            job_title = (
                f"Reprocess Batch SKU {skus_list[0]} ({b_name})"
                if len(skus_list) == 1
                else f"Reprocess {len(skus_list)} Batch Card(s) ({b_name})"
            )
            res_job = cli.start_or_queue_background_job(
                job_type="reprocess_batch_cards",
                title=job_title,
                payload={
                    "batch_dir": str(b_dir),
                    "batch_name": b_name,
                    "skus": skus_list,
                    "locked_set": str(payload.get("lockedSet") or "").strip(),
                    "locked_subset": str(payload.get("lockedSubset") or "").strip(),
                    "regrade_too": bool(payload.get("regradeToo", True)),
                    "estimated_total": len(skus_list),
                },
                lane=None,
                execution_mode="queue",
            )
            _log_ui_action_to_file("Batch", job_title, f"Dispatched to {res_job.get('lane')} (PID {res_job.get('pid')})")
            self._send_json({
                "success": True,
                "asyncJob": True,
                "skus": skus_list,
                **res_job,
                "lanes": _get_live_lanes_and_logs(),
            })
            return

        if route == "/api/inventory/reprocess" and isinstance(payload, dict):
            import cli
            raw_skus = payload.get("skus") if isinstance(payload.get("skus"), list) else [payload.get("sku")]
            skus_list = [str(s).strip() for s in raw_skus if str(s or "").strip()]
            if not skus_list:
                self._send_json({"success": False, "error": "No SKU(s) provided for reprocessing."}, status=400)
                return

            job_title = (
                f"Reprocess Inventory SKU {skus_list[0]}"
                if len(skus_list) == 1
                else f"Reprocess {len(skus_list)} Inventory SKU(s)"
            )
            res_job = cli.start_or_queue_background_job(
                job_type="reprocess_inventory_skus",
                title=job_title,
                payload={
                    "skus": skus_list,
                    "locked_set": str(payload.get("lockedSet") or "").strip(),
                    "locked_subset": str(payload.get("lockedSubset") or "").strip(),
                    "regrade_too": bool(payload.get("regradeToo", True)),
                    "estimated_total": len(skus_list),
                },
                lane=None,
                execution_mode="queue",
            )
            _log_ui_action_to_file("Inventory", job_title, f"Dispatched to {res_job.get('lane')} (PID {res_job.get('pid')})")
            self._send_json({
                "success": True,
                "asyncJob": True,
                "skus": skus_list,
                **res_job,
                "lanes": _get_live_lanes_and_logs(),
            })
            return

        if route == "/api/inventory/rotate-image" and isinstance(payload, dict):
            from PIL import Image
            from Core.config import sanitize_filename_part
            set_name = str(payload.get("setName") or "").strip()
            file_name = str(payload.get("fileName") or "").strip()
            degrees = int(payload.get("degrees") or 90)
            if not file_name or ".." in file_name or "/" in file_name or "\\" in file_name:
                self._send_json({"success": False, "error": f"Invalid fileName: {file_name}"}, status=400)
                return

            cand_p = (REVIEWED_CARDS_DIR / sanitize_filename_part(set_name) / file_name) if set_name else None
            img_p = cand_p if (cand_p is not None and cand_p.exists()) else None
            if img_p is None and REVIEWED_CARDS_DIR.exists():
                img_p = next((p for p in REVIEWED_CARDS_DIR.rglob(file_name) if p.is_file()), None)
            if img_p is None or not str(img_p.resolve()).startswith(str(REVIEWED_CARDS_DIR.resolve())):
                self._send_json({"success": False, "error": f"Collection image not found: {file_name}"}, status=404)
                return

            try:
                with Image.open(img_p) as im:
                    rot_im = im.convert("RGB").rotate(-degrees, expand=True)
                rot_im.save(img_p, format="JPEG", quality=94)
                _log_ui_action_to_file("Inventory", f"Rotated {file_name} {degrees}° CW", f"Set: {set_name}")
                self._send_json({"success": True, "fileName": file_name, "rotatedDegrees": degrees})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        if route in ("/api/inventory/replace-images", "/api/batches/replace-images") and isinstance(payload, dict):
            from Core.vision_grader import replace_card_images_from_bytes
            t_type = "inventory" if route == "/api/inventory/replace-images" else "batch"
            sku_v = str(payload.get("sku") or "").strip()
            b_name = str(payload.get("batchName") or "").strip()
            res_rep = replace_card_images_from_bytes(
                target_type=t_type,
                sku=sku_v,
                batch_name=b_name,
                front_b64=str(payload.get("frontBase64") or ""),
                front_filename=str(payload.get("frontFileName") or ""),
                back_b64=str(payload.get("backBase64") or ""),
                back_filename=str(payload.get("backFileName") or ""),
                pdf_b64=str(payload.get("pdfBase64") or ""),
                pdf_filename=str(payload.get("pdfFileName") or ""),
                auto_orient=bool(payload.get("autoOrient", True)),
                regrade_too=bool(payload.get("regradeToo", True)),
            )
            if res_rep.get("success"):
                _log_ui_action_to_file(
                    "Inventory" if t_type == "inventory" else "Batch",
                    f"Replaced {' & '.join(res_rep.get('replacedSides') or [])} Image(s) — SKU {sku_v}",
                    f"Front ↻{res_rep.get('frontRotated', 0)}° | Back ↻{res_rep.get('backRotated', 0)}° | PSA {res_rep.get('oldPSA')}->{res_rep.get('newPSA')}",
                )
                self._send_json(res_rep)
            else:
                self._send_json(res_rep, status=400)
            return

        if route == "/api/batches/commit" and isinstance(payload, dict):
            import cli
            try:
                move_imgs = bool(payload.get("moveImages", True))
                raw_names = payload.get("batchNames") if isinstance(payload.get("batchNames"), list) else []
                single_name = str(payload.get("batchName") or "").strip()
                commit_all = bool(payload.get("commitAll", False))

                discovered_now = _discover_uncommitted_batches()
                counts_by_name = {b["batchName"]: int(b.get("cardCount", 0) or 0) for b in discovered_now}

                if commit_all:
                    target_names = [b["batchName"] for b in discovered_now]
                elif raw_names:
                    target_names = [str(n).strip() for n in raw_names if str(n or "").strip() and str(n).strip() != "__ALL__"]
                elif single_name and single_name != "__ALL__":
                    target_names = [single_name]
                else:
                    target_names = [b["batchName"] for b in discovered_now]

                valid_names = [bn for bn in target_names if (BATCHES_DIR / bn / "Batch_Inventory_Manifest.csv").exists()]
                if not valid_names:
                    self._send_json({"success": False, "error": "No valid uncommitted batch(es) found to commit."}, status=400)
                    return

                est_cards = max(1, sum(counts_by_name.get(bn, 0) for bn in valid_names))
                job_title = (
                    f"Commit to Inventory ({valid_names[0]} • {est_cards:,} cards)"
                    if len(valid_names) == 1
                    else f"Commit {len(valid_names)} Batches to Inventory ({est_cards:,} cards)"
                )

                res_job = cli.start_or_queue_background_job(
                    job_type="commit_batches",
                    title=job_title,
                    payload={
                        "batch_names": valid_names,
                        "move_images": move_imgs,
                        "estimated_total": est_cards,
                    },
                    lane=None,
                    execution_mode="queue",
                )
                _log_ui_action_to_file(
                    "Batch",
                    job_title,
                    f"Dispatched to {res_job.get('lane')} (PID {res_job.get('pid')}) | Batches: {', '.join(valid_names)}",
                )
                self._send_json({
                    "success": True,
                    "asyncJob": True,
                    "batchNames": valid_names,
                    "estimatedCards": est_cards,
                    **res_job,
                    "lanes": _get_live_lanes_and_logs(),
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                _log_ui_action_to_file("Batch", "Commit Dispatch Error", str(e))
                self._send_json({"success": False, "error": f"Commit dispatch failed: {e}"}, status=500)
            return

        if route == "/api/batches/delete-cards" and isinstance(payload, dict):
            from Core.database import remove_cards_from_batch
            try:
                delete_files = bool(payload.get("deleteFiles", True))
                grouped: dict[str, list[str]] = {}
                if isinstance(payload.get("items"), list) and payload["items"]:
                    for it in payload["items"]:
                        if not isinstance(it, dict):
                            continue
                        bn = str(it.get("batchName") or "").strip()
                        sk = str(it.get("sku") or "").strip()
                        if bn and sk:
                            grouped.setdefault(bn, []).append(sk)
                else:
                    bn = str(payload.get("batchName") or "").strip()
                    sks = payload.get("skus") if isinstance(payload.get("skus"), list) else [payload.get("sku")]
                    clean_sks = [str(s).strip() for s in sks if str(s or "").strip()]
                    if bn and clean_sks:
                        grouped[bn] = clean_sks

                if not grouped:
                    self._send_json({"success": False, "error": "No batch card SKU(s) provided to delete."}, status=400)
                    return

                total_removed = 0
                removed_skus_all: list[str] = []
                last_cards = None
                for bn, sk_list in grouped.items():
                    res_del = remove_cards_from_batch(BATCHES_DIR / bn, sk_list, delete_files=delete_files)
                    if res_del.get("success"):
                        total_removed += int(res_del.get("removedCount", 0))
                        removed_skus_all.extend(res_del.get("removedSkus") or [])
                        last_cards = res_del.get("cards")
                        _log_ui_action_to_file("Batch", f"Removed {res_del.get('removedCount', 0)} card(s) from {bn}", f"SKUs: {', '.join(res_del.get('removedSkus') or [])[:200]}")

                view_batch = str(payload.get("activeBatchName") or (next(iter(grouped.keys())) if len(grouped) == 1 else "__ALL__"))
                self._send_json({
                    "success": True,
                    "removedCount": total_removed,
                    "removedSkus": removed_skus_all,
                    "cards": last_cards,
                    "batches": _discover_uncommitted_batches(include_cards_for=view_batch),
                })
            except Exception as e:
                self._send_json({"success": False, "error": f"Delete card failed: {e}"}, status=500)
            return

        if route == "/api/batches/clear" and isinstance(payload, dict):
            from Core.database import clear_uncommitted_batch
            b_name = str(payload.get("batchName") or "").strip()
            b_dir = (BATCHES_DIR / b_name) if b_name else None
            res_clr = clear_uncommitted_batch(
                batch_dir=b_dir,
                clear_all=bool(payload.get("clearAll", False)),
                restore_raw_scans_from_archive=True,
            )
            _log_ui_action_to_file("Batch", f"Cleared {b_name or 'ALL'}", f"restored_pdfs={res_clr.get('restored_pdfs', 0)}")
            self._send_json({"success": True, **res_clr, "batches": _discover_uncommitted_batches()})
            return

        if route == "/api/batches/split-flatbed" and isinstance(payload, dict):
            from Core.database import find_unarchived_scan_batches
            from Core.vision_grader import expand_flatbed_pdfs_in_batch_folder
            target_name = str(payload.get("batchName") or "ALL").strip()
            discovered = find_unarchived_scan_batches()
            total_split = 0
            for b_name, b_path, b_pdfs in discovered:
                if target_name in ("", "ALL") or b_name == target_name:
                    _, cnt = expand_flatbed_pdfs_in_batch_folder(b_path, pdf_files=b_pdfs, flip_mode="auto")
                    total_split += cnt
            _log_ui_action_to_file("Scan", "Flatbed Split", f"Created {total_split} individual card PDF(s) for {target_name}")
            self._send_json({"success": True, "createdCount": total_split, "incomingScans": _discover_incoming_scans()})
            return

        if route == "/api/config/tracked-sets" and isinstance(payload, list):
            _save_tracked_sets_list(payload)
            self._send_json({"success": True, "trackedSets": _load_tracked_sets_list()})
            return

        if route == "/api/config/set-cart":
            if isinstance(payload, dict) and payload.get("action") == "commit":
                from Core.scraper_engine import commit_set_cart_to_tracked, save_set_cart
                if isinstance(payload.get("cart"), list):
                    save_set_cart(payload["cart"])
                res = commit_set_cart_to_tracked()
                self._send_json({"success": True, "committedCount": res.get("committed_count", 0), "trackedSets": _load_tracked_sets_list()})
                return
            elif isinstance(payload, list):
                from Core.scraper_engine import save_set_cart
                self._send_json({"success": True, "cart": save_set_cart(payload)})
                return

        if route == "/api/jobs/start" and isinstance(payload, dict):
            import cli
            res_job = cli.start_or_queue_background_job(
                job_type=str(payload.get("jobType") or "tcdb_scrape"),
                title=str(payload.get("title") or "Background Job"),
                payload=dict(payload.get("payload") or {"estimated_total": 10}),
                lane=payload.get("lane") or None,
                execution_mode=str(payload.get("executionMode") or "queue"),
            )
            self._send_json({
                "success": True,
                **res_job,
                "lanes": _get_live_lanes_and_logs(),
            })
            return

        if route == "/api/notifications" and isinstance(payload, dict):
            from datetime import datetime
            from Core.config import NOTIFICATIONS_CSV_COLUMNS, NOTIFICATIONS_HISTORY_CSV
            existing = _read_csv_records(NOTIFICATIONS_HISTORY_CSV, max_rows=10000)
            new_id = str(payload.get("Notification_ID") or f"NTF-{int(time.time() * 1000)}")
            rec = {
                "Notification_ID": new_id,
                "Timestamp": str(payload.get("Timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "Category": str(payload.get("Category") or "System"),
                "Title": str(payload.get("Title") or "Notification"),
                "Message": str(payload.get("Message") or ""),
                "Severity": str(payload.get("Severity") or "info"),
                "Cleared": "False",
            }
            existing.append(rec)
            _write_csv_records(NOTIFICATIONS_HISTORY_CSV, existing, explicit_cols=NOTIFICATIONS_CSV_COLUMNS)
            _log_ui_action_to_file(rec["Category"], rec["Title"], rec["Message"])
            self._send_json({"success": True, "notification": rec})
            return

        if route == "/api/notifications/clear" and isinstance(payload, dict):
            from Core.config import NOTIFICATIONS_CSV_COLUMNS, NOTIFICATIONS_HISTORY_CSV
            existing = _read_csv_records(NOTIFICATIONS_HISTORY_CSV, max_rows=10000)
            clear_all = bool(payload.get("clearAll", False))
            target_id = str(payload.get("notificationId") or "").strip()
            cleared_cnt = 0
            for r in existing:
                if clear_all or (target_id and r.get("Notification_ID") == target_id):
                    if str(r.get("Cleared", "False")).lower() != "true":
                        r["Cleared"] = "True"
                        cleared_cnt += 1
            _write_csv_records(NOTIFICATIONS_HISTORY_CSV, existing, explicit_cols=NOTIFICATIONS_CSV_COLUMNS)
            visible_notifs = [n for n in existing if str(n.get("Cleared", "False")).lower() != "true"]
            visible_notifs.reverse()
            self._send_json({"success": True, "clearedCount": cleared_cnt, "notifications": visible_notifs})
            return

        if route == "/api/sold-cards" and isinstance(payload, dict):
            from datetime import datetime
            from Core.config import SOLD_CARDS_CSV, SOLD_CARDS_CSV_COLUMNS
            from Core.database import load_inventory_df, save_inventory_df
            existing = _read_csv_records(SOLD_CARDS_CSV, max_rows=20000)
            sale_price = float(payload.get("Sale_Price") or 0.0)
            ship_col = float(payload.get("Shipping_Collected") or 0.0)
            fees = float(payload.get("Marketplace_Fees") or 0.0)
            ship_cost = float(payload.get("Shipping_Cost") or 0.0)
            seller_paid_ship = bool(payload.get("Seller_Paid_Shipping", False))
            cost_basis = float(payload.get("Cost_Basis") or 0.0)
            effective_ship_deduction = ship_cost if seller_paid_ship else 0.0
            net_profit = round((sale_price + ship_col) - (fees + effective_ship_deduction + cost_basis), 2)
            sku_val = str(payload.get("SKU") or "").strip()

            max_sale_num = 0
            for ex_r in existing:
                m_sid = re.search(r"(\d+)$", str(ex_r.get("Sale_ID") or "").strip())
                if m_sid:
                    max_sale_num = max(max_sale_num, int(m_sid.group(1)))

            new_rec = {
                "Sale_ID": str(payload.get("Sale_ID") or f"SALE-{max_sale_num + 1:05d}"),
                "Sale_Date": str(payload.get("Sale_Date") or datetime.now().strftime("%Y-%m-%d")),
                "SKU": sku_val,
                "Set": str(payload.get("Set") or "").strip(),
                "Subset": str(payload.get("Subset") or "Base").strip(),
                "Card_Number": str(payload.get("Card_Number") or "").strip().lstrip("#"),
                "Player": str(payload.get("Player") or "").strip(),
                "Platform": str(payload.get("Platform") or "eBay").strip(),
                "Sale_Price": f"{sale_price:.2f}",
                "Shipping_Collected": f"{ship_col:.2f}",
                "Marketplace_Fees": f"{fees:.2f}",
                "Shipping_Cost": f"{ship_cost:.2f}",
                "Seller_Paid_Shipping": "True" if seller_paid_ship else "False",
                "Cost_Basis": f"{cost_basis:.2f}",
                "Net_Profit": f"{net_profit:.2f}",
                "Notes": str(payload.get("Notes") or "").strip(),
            }
            existing.append(new_rec)
            _write_csv_records(SOLD_CARDS_CSV, existing, explicit_cols=SOLD_CARDS_CSV_COLUMNS)

            if sku_val and bool(payload.get("markInventorySold", True)):
                try:
                    inv_df = load_inventory_df()
                    if not inv_df.empty and sku_val in set(inv_df["SKU"].astype(str)):
                        inv_df.loc[inv_df["SKU"] == sku_val, "Status"] = "Sold"
                        save_inventory_df(inv_df)
                except Exception:
                    pass

            existing.reverse()
            self._send_json({"success": True, "sale": new_rec, "rows": existing})
            return

        if route == "/api/sold-cards/delete" and isinstance(payload, dict):
            from Core.config import SOLD_CARDS_CSV, SOLD_CARDS_CSV_COLUMNS
            from Core.database import load_inventory_df, save_inventory_df
            target_sale_id = str(payload.get("Sale_ID") or payload.get("saleId") or "").strip()
            revert_inv = bool(payload.get("revertInventoryStatus", True))
            existing = _read_csv_records(SOLD_CARDS_CSV, max_rows=20000)
            removed_rec = next((r for r in existing if str(r.get("Sale_ID") or "").strip() == target_sale_id), None)
            kept = [r for r in existing if str(r.get("Sale_ID") or "").strip() != target_sale_id]
            _write_csv_records(SOLD_CARDS_CSV, kept, explicit_cols=SOLD_CARDS_CSV_COLUMNS)

            if removed_rec and revert_inv:
                sku_rev = str(removed_rec.get("SKU") or "").strip()
                if sku_rev:
                    try:
                        inv_df = load_inventory_df()
                        if not inv_df.empty and sku_rev in set(inv_df["SKU"].astype(str)):
                            inv_df.loc[inv_df["SKU"] == sku_rev, "Status"] = "In Stock"
                            save_inventory_df(inv_df)
                    except Exception:
                        pass

            kept.reverse()
            self._send_json({"success": True, "deletedSaleId": target_sale_id, "rows": kept})
            return

        if route == "/api/labels/generate" and isinstance(payload, dict):
            from Core.database import load_inventory_df
            from Core.label_engine import generate_alignment_test_pdf, generate_labels_pdf
            tpl_key = str(payload.get("templateKey") or "R037L")
            x_off = float(payload.get("xOffsetMm") or 0.0)
            y_off = float(payload.get("yOffsetMm") or 0.0)
            s_row = int(payload.get("startRow") or 1)
            s_col = int(payload.get("startCol") or 1)
            used_cells = [tuple(c) for c in (payload.get("usedCellsPage1") or [])]
            mode = str(payload.get("mode") or "production")

            if mode == "alignment":
                pdf_p = generate_alignment_test_pdf(
                    template_key=tpl_key,
                    x_offset_mm=x_off,
                    y_offset_mm=y_off,
                    used_cells_page1=used_cells,
                    start_row=s_row,
                    start_col=s_col,
                )
                self._send_json({"success": True, "pdfName": pdf_p.name, "pdfUrl": f"/static/labels/{pdf_p.name}"})
                return

            import pandas as pd
            if mode == "sample":
                sample_card = dict(payload.get("sampleCard") or {
                    "SKU": "1000001", "Set": "2026 Topps Baseball", "Card Number": "1",
                    "Player": "Aaron Judge", "Team": "New York Yankees", "Subset": "Gold Foil", "Print Run": "50",
                })
                res_lbl = generate_labels_pdf(
                    pd.DataFrame([sample_card]),
                    template_key=tpl_key,
                    start_row=s_row,
                    start_col=s_col,
                    used_cells_page1=used_cells,
                    x_offset_mm=x_off,
                    y_offset_mm=y_off,
                    draw_cell_outlines=True,
                )
                pdf_p = Path(res_lbl["output_pdf_path"])
                self._send_json({"success": True, "pdfName": pdf_p.name, "pdfUrl": f"/static/labels/{pdf_p.name}", "cardsPrinted": 1, "pagesRendered": 1, "printedSkus": []})
                return

            from Core.label_engine import resolve_template_spec
            inv_df = load_inventory_df()
            reprint_mode = str(payload.get("reprintMode") or "unprinted_only")
            source_batch = str(payload.get("sourceBatch") or "").strip()
            exact_skus = [str(s).strip() for s in (payload.get("exactSkus") or []) if str(s).strip()]
            reprint_skus = _expand_sku_tokens(payload.get("reprintSkus") or payload.get("skus") or [])

            if exact_skus and not inv_df.empty:
                inv_by_sku = inv_df.drop_duplicates(subset=["SKU"], keep="first").set_index("SKU")
                ordered_hits = [s for s in exact_skus if s in inv_by_sku.index]
                target_df = inv_by_sku.loc[ordered_hits].reset_index() if ordered_hits else inv_df.iloc[0:0].copy()
            else:
                scoped_inv = inv_df.copy()
                if source_batch and source_batch != "All Intake Batches" and "Source_Batch" in scoped_inv.columns:
                    scoped_inv = scoped_inv[scoped_inv["Source_Batch"].astype(str).str.strip() == source_batch].copy()
                unprinted_df = scoped_inv[scoped_inv["Label_Printed"].astype(str).str.lower() != "true"].copy()

                if reprint_mode == "intake_batch_all":
                    target_df = scoped_inv.copy()
                elif reprint_mode == "reprint_only" and reprint_skus:
                    target_df = inv_df[inv_df["SKU"].isin(reprint_skus)].copy()
                elif reprint_mode == "append_reprints" and reprint_skus:
                    reprint_df = inv_df[inv_df["SKU"].isin(reprint_skus)].copy()
                    target_df = pd.concat([unprinted_df, reprint_df], ignore_index=True).drop_duplicates(subset=["SKU"], keep="first")
                elif reprint_skus:
                    target_df = inv_df[inv_df["SKU"].isin(reprint_skus)].copy()
                else:
                    target_df = unprinted_df

            used_by_page_raw = payload.get("usedCellsByPage") if isinstance(payload.get("usedCellsByPage"), dict) else {}
            has_multipage_skips = any(int(k) > 1 and len(v or []) > 0 for k, v in used_by_page_raw.items() if str(k).isdigit())

            if not has_multipage_skips:
                p1_skips = [tuple(c) for c in (used_by_page_raw.get("1") or used_cells)]
                res_lbl = generate_labels_pdf(
                    target_df,
                    template_key=tpl_key,
                    start_row=s_row,
                    start_col=s_col,
                    used_cells_page1=p1_skips,
                    x_offset_mm=x_off,
                    y_offset_mm=y_off,
                    draw_cell_outlines=bool(payload.get("drawOutlines", False)),
                )
                pdf_p = Path(res_lbl["output_pdf_path"])
                self._send_json({
                    "success": True,
                    "pdfName": pdf_p.name,
                    "pdfUrl": f"/static/labels/{pdf_p.name}",
                    "cardsPrinted": res_lbl["cards_printed"],
                    "pagesRendered": res_lbl["pages_rendered"],
                    "printedSkus": res_lbl["printed_skus"],
                })
                return

            # Multi-Page Per-Sheet Skip PDF Stitcher (supports unique skipped sticker maps on Page 1, 2, 3...)
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            geom = resolve_template_spec(tpl_key)
            cells_per_page = int(geom["rows"]) * int(geom["cols"])
            rem_df = target_df.reset_index(drop=True)
            cursor_idx = 0
            page_num = 1
            temp_pdfs: list[Path] = []
            all_printed_skus: list[str] = []

            while cursor_idx < len(rem_df) and page_num <= 60:
                raw_p_skips = used_by_page_raw.get(str(page_num)) or ([] if page_num > 1 else used_cells)
                valid_skips = list({
                    (int(rc[0]), int(rc[1]))
                    for rc in raw_p_skips
                    if len(rc) == 2 and 1 <= int(rc[0]) <= int(geom["rows"]) and 1 <= int(rc[1]) <= int(geom["cols"])
                })
                avail_slots = cells_per_page - len(valid_skips)
                if avail_slots <= 0:
                    page_num += 1
                    continue
                slice_df = rem_df.iloc[cursor_idx : cursor_idx + avail_slots].copy()
                cursor_idx += len(slice_df)
                r_page = generate_labels_pdf(
                    slice_df,
                    template_key=tpl_key,
                    start_row=1,
                    start_col=1,
                    used_cells_page1=valid_skips,
                    x_offset_mm=x_off,
                    y_offset_mm=y_off,
                    draw_cell_outlines=bool(payload.get("drawOutlines", False)),
                )
                temp_pdfs.append(Path(r_page["output_pdf_path"]))
                all_printed_skus.extend(r_page.get("printed_skus") or [])
                page_num += 1

            ts_lbl = time.strftime("%Y%m%d_%H%M%S")
            merged_pdf_path = LABELS_OUTPUT_DIR / f"Tabulas_Labels_{tpl_key}_MultiPage_{ts_lbl}.pdf"
            merged_doc = fitz.open()
            for tp in temp_pdfs:
                if tp.exists():
                    src_d = fitz.open(str(tp))
                    merged_doc.insert_pdf(src_d)
                    src_d.close()
                    try:
                        tp.unlink()
                    except Exception:
                        pass
            merged_doc.save(str(merged_pdf_path))
            pages_cnt = len(merged_doc)
            merged_doc.close()

            self._send_json({
                "success": True,
                "pdfName": merged_pdf_path.name,
                "pdfUrl": f"/static/labels/{merged_pdf_path.name}",
                "cardsPrinted": len(all_printed_skus),
                "pagesRendered": pages_cnt,
                "printedSkus": all_printed_skus,
            })
            return

        if route == "/api/labels/mark-printed" and isinstance(payload, dict):
            from Core.database import load_inventory_df, save_inventory_df
            skus = [str(s).strip() for s in (payload.get("skus") or []) if str(s).strip()]
            printed_val = "False" if bool(payload.get("unmark", False)) else "True"
            inv_df = load_inventory_df()
            marked_cnt = 0
            if skus and not inv_df.empty:
                mask = inv_df["SKU"].astype(str).str.strip().isin(skus)
                marked_cnt = int(mask.sum())
                if marked_cnt > 0:
                    inv_df.loc[mask, "Label_Printed"] = printed_val
                    inv_df = save_inventory_df(inv_df)
            _log_ui_action_to_file("Labels", f"Set Label_Printed={printed_val}", f"Updated {marked_cnt} SKU(s)")
            self._send_json({
                "success": True,
                "markedCount": marked_cnt,
                "rows": inv_df.to_dict(orient="records") if not inv_df.empty else [],
            })
            return

        if route == "/api/market/action" and isinstance(payload, dict):
            from Core.database import load_inventory_df, save_inventory_df
            from Core.market_engine import (
                purge_mismatched_comps_and_recalculate_inventory,
                refresh_dugout_vault_grading_tiers,
                save_market_alert_settings,
            )
            act = str(payload.get("action") or "")
            if act == "refresh_tiers":
                tiers = refresh_dugout_vault_grading_tiers()
                self._send_json({"success": True, "tiers": tiers})
                return
            elif act == "purge_comps":
                inv_df = load_inventory_df()
                cleaned, rst = purge_mismatched_comps_and_recalculate_inventory(inv_df)
                save_inventory_df(cleaned)
                self._send_json({"success": True, "resetCount": rst, "rows": cleaned.to_dict(orient="records")})
                return
            elif act == "save_alert_settings":
                saved = save_market_alert_settings(dict(payload.get("settings") or {}))
                self._send_json({"success": True, "settings": saved})
                return
            elif act == "test_alert":
                from Core.market_engine import load_market_alert_settings, send_market_alert_email
                cfg_s = dict(payload.get("settings") or load_market_alert_settings())
                sample = [{
                    "alert_type": "TEST_ALERT",
                    "sku": "1000001",
                    "card_desc": "2026 Topps Baseball #1 Aaron Judge [Base]",
                    "old_action": "LIST RAW ($2.00)",
                    "new_action": "GRADE PSA (+$22.50)",
                    "old_price": "2.00",
                    "new_price": "3.50",
                }]
                ok_em, msg_em = send_market_alert_email(sample, settings=cfg_s)
                self._send_json({"success": ok_em, "message": msg_em})
                return

        if route == "/api/inventory/card-level/update" and isinstance(payload, dict):
            from Core.database import load_inventory_df, save_inventory_df
            from Core.sales_engine import (
                auto_allocate_pc_and_sale_copies,
                build_card_level_inventory_df,
                build_unique_card_key,
                load_card_level_targets,
                save_card_level_targets,
            )

            updates_list = payload.get("updates") if isinstance(payload.get("updates"), list) else [payload]
            inv_df = load_inventory_df()
            targets_map = load_card_level_targets()
            updated_skus_cnt = 0
            reallocate = bool(payload.get("reallocateHoldTags", False))

            upd_by_key = {}
            for u_item in updates_list:
                ck = str(u_item.get("Card_Key") or "").strip()
                if not ck:
                    continue
                upd_by_key[ck] = u_item
                if "Target_Retain_Qty" in u_item and u_item["Target_Retain_Qty"] is not None:
                    try:
                        targets_map[ck] = {"target_retain_qty": max(0, int(float(u_item["Target_Retain_Qty"])))}
                    except Exception:
                        pass

            save_card_level_targets(targets_map)

            if not inv_df.empty and (upd_by_key or reallocate):
                if upd_by_key:
                    for r_idx, row in inv_df.iterrows():
                        if str(row.get("Status") or "").strip().lower() == "sold":
                            continue
                        ck_r = build_unique_card_key(
                            row.get("Set", ""),
                            row.get("Subset", "Base"),
                            row.get("Card Number", ""),
                            row.get("Player", ""),
                        )
                        if ck_r in upd_by_key:
                            u_d = upd_by_key[ck_r]
                            if u_d.get("Unit_Raw_Price") not in (None, ""):
                                inv_df.at[r_idx, "Raw_Price"] = f"{float(u_d['Unit_Raw_Price']):.2f}"
                            if u_d.get("Unit_Rec_Sale_Price") not in (None, ""):
                                inv_df.at[r_idx, "Rec_Sale_Price"] = f"{float(u_d['Unit_Rec_Sale_Price']):.2f}"
                            updated_skus_cnt += 1

                if reallocate:
                    inv_df, _ = auto_allocate_pc_and_sale_copies(inv_df, default_retain_qty=1)
                save_inventory_df(inv_df)

            cl_df = build_card_level_inventory_df(inv_df, default_retain_qty=1)
            _log_ui_action_to_file("Inventory", "Card-Level Price / Retain Update", f"Updated {len(upd_by_key)} unique card(s) across {updated_skus_cnt} physical SKU(s)")
            self._send_json({
                "success": True,
                "updatedCards": len(upd_by_key),
                "updatedSkus": updated_skus_cnt,
                "cardLevelRows": cl_df.to_dict(orient="records") if not cl_df.empty else [],
                "inventoryRows": inv_df.to_dict(orient="records") if not inv_df.empty else [],
            })
            return

        if route == "/api/sales/set-blurb" and isinstance(payload, dict):
            from Core.sales_engine import save_custom_set_blurb
            saved_b = save_custom_set_blurb(
                set_name=str(payload.get("set") or "").strip(),
                blurb_text=str(payload.get("blurb") or "").strip(),
            )
            self._send_json({"success": True, **saved_b})
            return

        if route == "/api/sales/action" and isinstance(payload, dict):
            from datetime import datetime
            import pandas as pd
            from Core.database import load_inventory_df, save_inventory_df
            from Core.sales_engine import (
                auto_allocate_pc_and_sale_copies,
                generate_card_listing_copy,
                load_listing_drafts_df,
                save_listing_drafts_df,
            )
            act = str(payload.get("action") or "")
            if act == "auto_allocate":
                inv_df = load_inventory_df()
                upd_inv, stats = auto_allocate_pc_and_sale_copies(inv_df, default_retain_qty=int(payload.get("defaultRetainQty") or 1))
                save_inventory_df(upd_inv)
                self._send_json({"success": True, "stats": stats, "rows": upd_inv.to_dict(orient="records")})
                return
            elif act == "generate_listing":
                inv_df = load_inventory_df()
                sku_v = str(payload.get("sku") or "").strip()
                hit = inv_df[inv_df["SKU"] == sku_v]
                if hit.empty:
                    self._send_json({"success": False, "error": f"SKU {sku_v} not found"}, status=404)
                    return
                card_row = hit.iloc[0].to_dict()
                copy_res = generate_card_listing_copy(
                    card_row,
                    platform=str(payload.get("platform") or "eBay & CollX"),
                    include_pregrade_notes=bool(payload.get("includePregrade", True)),
                    extract_back_ocr_blurb=bool(payload.get("includeBio", True)),
                    force_web_refresh=bool(payload.get("forceRefreshBio", False)),
                    content_options=payload.get("contentOptions") if isinstance(payload.get("contentOptions"), dict) else None,
                    custom_set_blurb=str(payload.get("customSetBlurb") or "").strip() or None,
                )
                if bool(payload.get("saveDraft", False)):
                    custom_title = str(payload.get("customTitle") or "").strip()
                    custom_price = str(payload.get("customPrice") or "").strip()
                    custom_desc = str(payload.get("customDescription") or "").strip()
                    if custom_title:
                        copy_res["SEO_Title_80Char"] = custom_title
                    if custom_price:
                        copy_res["Recommended_Price"] = custom_price
                    if custom_desc:
                        copy_res["Description_Body"] = custom_desc
                    curr_d = load_listing_drafts_df()
                    new_d = pd.DataFrame([{
                        "Draft_ID": f"DRF-{sku_v}",
                        "Listing_Type": "Single Card",
                        "SKU_or_Lot_ID": sku_v,
                        "Set": card_row.get("Set", ""),
                        "Subset": card_row.get("Subset", "Base"),
                        "Card_Number": card_row.get("Card Number", ""),
                        "Player_or_Bundle": card_row.get("Player", ""),
                        "Team": card_row.get("Team", ""),
                        "Quantity": "1",
                        "Recommended_Price": copy_res["Recommended_Price"],
                        "Platform_Target": str(payload.get("platform") or "eBay & CollX"),
                        "SEO_Title_80Char": copy_res["SEO_Title_80Char"],
                        "Description_Body": copy_res["Description_Body"],
                        "Front_File": card_row.get("Front_File", ""),
                        "Back_File": card_row.get("Back_File", ""),
                        "Created_At": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }])
                    save_listing_drafts_df(new_d if curr_d.empty else pd.concat([curr_d, new_d], ignore_index=True))
                self._send_json({"success": True, **copy_res})
                return
            elif act == "generate_lot_listing":
                from Core.sales_engine import generate_lot_listing_copy
                lot_row = dict(payload.get("lot") or {})
                inv_df = load_inventory_df()
                lot_copy = generate_lot_listing_copy(lot_row, inv_df)
                curr_d = load_listing_drafts_df()
                lot_id = str(lot_row.get("Lot_ID") or f"LOT-{int(time.time())}")
                new_d = pd.DataFrame([{
                    "Draft_ID": f"DRF-{lot_id}",
                    "Listing_Type": str(lot_row.get("Lot_Category") or "Lot"),
                    "SKU_or_Lot_ID": lot_id,
                    "Set": str(lot_row.get("Set") or ""),
                    "Subset": str(lot_row.get("Lot_Category") or "Lot"),
                    "Card_Number": f"{lot_row.get('Total_Cards', 1)} Cards",
                    "Player_or_Bundle": str(lot_row.get("Lot_Title") or "Card Lot"),
                    "Team": "Multi",
                    "Quantity": str(lot_row.get("Total_Cards") or "1"),
                    "Recommended_Price": lot_copy["Recommended_Price"],
                    "Platform_Target": "eBay & CollX",
                    "SEO_Title_80Char": lot_copy["SEO_Title_80Char"],
                    "Description_Body": lot_copy["Description_Body"],
                    "Front_File": "",
                    "Back_File": "",
                    "Created_At": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }])
                save_listing_drafts_df(new_d if curr_d.empty else pd.concat([curr_d, new_d], ignore_index=True))
                self._send_json({"success": True, "draftId": f"DRF-{lot_id}", **lot_copy})
                return

        if route == "/api/schedules" and isinstance(payload, list):
            import cli
            synced, msgs = cli.save_and_sync_all_scheduled_jobs(payload)
            self._send_json({"success": True, "schedules": synced, "messages": msgs})
            return

        if route == "/api/sales/drafts/update" and isinstance(payload, dict):
            from Core.sales_engine import load_listing_drafts_df, save_listing_drafts_df
            draft_id = str(payload.get("Draft_ID") or "").strip()
            df_d = load_listing_drafts_df()
            if draft_id and not df_d.empty and draft_id in set(df_d["Draft_ID"].astype(str)):
                for fld in ("SEO_Title_80Char", "Description_Body", "Recommended_Price", "Platform_Target"):
                    if fld in payload:
                        df_d.loc[df_d["Draft_ID"] == draft_id, fld] = str(payload[fld])
                saved_d = save_listing_drafts_df(df_d)
                self._send_json({"success": True, "drafts": saved_d.to_dict(orient="records")})
                return
            self._send_json({"success": False, "error": "Draft not found"}, status=404)
            return

        if route == "/api/devtools/action" and isinstance(payload, dict):
            import ast
            act = str(payload.get("action") or "")
            if act == "ast_audit":
                results = []
                for rel in ("Core/config.py", "Core/database.py", "Core/label_engine.py", "Core/scraper_engine.py", "Core/rate_learner.py", "Core/compute_backend.py", "Core/neural_vision.py", "Core/vision_grader.py", "Core/market_engine.py", "Core/sales_engine.py", "cli.py", "launch_tabulas_hub.py", "updater.py"):
                    fp = (APP_DIR / rel) if (APP_DIR / rel).exists() else (HUB_DIR / rel)
                    if not fp.exists():
                        results.append({"file": rel, "ok": False, "message": "Missing"})
                        continue
                    try:
                        ast.parse(fp.read_text(encoding="utf-8-sig", errors="replace"), filename=rel)
                        results.append({"file": rel, "ok": True, "message": f"AST OK ({fp.stat().st_size / 1024:.1f} KB)"})
                    except SyntaxError as se:
                        results.append({"file": rel, "ok": False, "message": f"Line {se.lineno}: {se.msg}"})
                self._send_json({"success": True, "results": results})
                return
            elif act == "clear_cache":
                from Core.config import CHECKLIST_CACHE_FILE, FEATURE_CACHE_FILE
                removed = []
                for cf in (CHECKLIST_CACHE_FILE, FEATURE_CACHE_FILE):
                    if cf.exists():
                        cf.unlink()
                        removed.append(cf.name)
                self._send_json({"success": True, "message": f"Cleared {len(removed)} cache file(s): {', '.join(removed) or 'none present'}."})
                return
            elif act == "cleanup_drivers":
                from Core.scraper_engine import cleanup_orphaned_drivers
                cleanup_orphaned_drivers()
                self._send_json({"success": True, "message": "Cleaned up orphaned Chrome/UC drivers."})
                return
            elif act == "check_cardsight":
                from Core.config import CARDSIGHT_API_KEY
                has_key = bool(str(CARDSIGHT_API_KEY or "").strip())
                self._send_json({"success": True, "message": "CARDSIGHT_API_KEY is configured." if has_key else "CARDSIGHT_API_KEY is not set in environment."})
                return
            elif act == "reset_rate_learner":
                from Core.rate_learner import get_rate_learner
                summary = get_rate_learner().reset_all()
                self._send_json({"success": True, "message": "Reset Adaptive Rate Learner to clean defaults.", "rateLearner": summary})
                return
            self._send_json({"success": False, "error": f"Unknown devtools action: {act}"}, status=400)
            return
        if route == "/api/jobs/stop" and isinstance(payload, dict):
            import cli
            cli.stop_active_job(lane=str(payload.get("lane") or "slot_1"))
            self._send_json({"success": True, "lanes": _get_live_lanes_and_logs()})
            return

        if route == "/api/lanes/clear" and isinstance(payload, dict):
            import cli
            lane_k = str(payload.get("lane") or "slot_1")
            cli.clear_lane_monitor_log(lane=lane_k)
            self._send_json({"success": True, "lanes": _get_live_lanes_and_logs()})
            return

        if route == "/api/logs/open-folder":
            try:
                DAILY_LOGS_ROOT.mkdir(parents=True, exist_ok=True)
                if os.name == "nt":
                    os.startfile(str(DAILY_LOGS_ROOT))
                else:
                    subprocess.Popen(["xdg-open", str(DAILY_LOGS_ROOT)])
                self._send_json({"success": True, "path": str(DAILY_LOGS_ROOT)})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "path": str(DAILY_LOGS_ROOT)}, status=500)
            return

        if route == "/api/system/maintenance":
            import cli
            res_m = cli.run_startup_maintenance()
            self._send_json({"success": True, **res_m})
            return

        if route == "/api/compute/settings" and isinstance(payload, dict):
            from Core.compute_backend import probe_system_hardware, save_compute_settings
            saved_cs = save_compute_settings(payload)
            _log_ui_action_to_file(
                "Compute",
                f"Saved GPU Settings (mode={saved_cs['compute_mode']})",
                f"ocr_gpu={saved_cs['enable_ocr_gpu']}, opencl={saved_cs['enable_opencl_cv']}, max_gpu_workers={saved_cs['max_concurrent_gpu_workers']}",
            )
            self._send_json({"success": True, "settings": saved_cs, "status": probe_system_hardware(force_refresh=True)})
            return

        if route == "/api/compute/benchmark":
            from Core.compute_backend import probe_system_hardware, run_compute_benchmark
            bench_res = run_compute_benchmark()
            _log_ui_action_to_file(
                "Compute",
                "Ran CPU vs GPU Benchmark",
                f"OpenCL: {bench_res.get('opencl_cpu_ms')}ms vs {bench_res.get('opencl_gpu_ms')}ms ({bench_res.get('opencl_speedup')}x) | "
                f"OCR: {bench_res.get('ocr_cpu_ms')}ms vs {bench_res.get('ocr_gpu_ms')}ms ({bench_res.get('ocr_speedup')}x)",
            )
            self._send_json({"success": True, "benchmark": bench_res, "status": probe_system_hardware(force_refresh=True)})
            return

        if route == "/api/client-error" and isinstance(payload, dict):
            stage = str(payload.get("stage") or "client")
            msg = str(payload.get("message") or "Unknown error")
            snippet = str(payload.get("snippet") or "")
            stack = str(payload.get("stack") or "")
            print(f"\n[UI ERROR - {stage}] {msg}", flush=True)
            if snippet:
                print(snippet, flush=True)
            if stack:
                print(stack[:1200], flush=True)
            _log_ui_action_to_file("UI_Error", stage, f"{msg} | {snippet[:300]}")
            self._send_json({"success": True})
            return

        if route == "/api/jobs/queue/remove" and isinstance(payload, dict):
            import cli
            lane_k = str(payload.get("lane") or "slot_1")
            q_id = str(payload.get("queueId") or "").strip()
            cli.remove_queued_job(lane_k, q_id)
            self._send_json({"success": True, "lanes": _get_live_lanes_and_logs()})
            return

        if route == "/api/jobs/queue/clear" and isinstance(payload, dict):
            import cli
            lane_k = str(payload.get("lane") or "slot_1")
            cli.clear_lane_job_queue(lane_k)
            self._send_json({"success": True, "lanes": _get_live_lanes_and_logs()})
            return

        self._send_json({"success": False, "error": f"Not found: {route}"}, status=404)


def _find_edge_executable() -> str | None:
    """Finds Microsoft Edge executable for standalone chromeless --app desktop window fallback."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for cand in candidates:
        if cand and os.path.exists(cand):
            return cand
    return shutil.which("msedge")


def launch_zero_node_python_react_server(port: int = 5000, force_browser: bool = False):
    import threading
    url = f"http://localhost:{port}"
    server = ThreadingHTTPServer(("127.0.0.1", port), _TabulasPythonApiAndReactHandler)

    print("\n" + "=" * 72)
    print("🚀 TABULAS CARD HUB (DESKTOP APP + FULL PYTHON REST API) IS LIVE!")
    print(f"   Local API   : {url}")
    print(f"   Hub Dir     : {HUB_DIR}")
    print(f"   Set Library : {SET_LIBRARY_DIR}")
    print(f"   Logs Dir    : {DAILY_LOGS_ROOT}")
    print("=" * 72)

    # Pre-warm Master Checklist, Set Directory & Inventory caches asynchronously while window opens
    _start_background_cache_prewarm()

    if not force_browser:
        # Mode 1: Native Desktop App Window via pywebview (zero Chrome/browser tabs!)
        try:
            import webview
            srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
            srv_thread.start()
            print("  [Window] Opening Native Desktop Window (pywebview)...")
            webview.create_window(
                "Tabulas Card Management Hub",
                url,
                width=1600,
                height=960,
                min_size=(1120, 720),
                background_color="#020617",
            )
            webview.start()
            server.shutdown()
            server.server_close()
            return
        except Exception as e:
            print(f"  [Window] pywebview unavailable ({e}); trying standalone Edge Desktop App window...")

        # Mode 2: Standalone Chromeless Desktop Window via MS Edge --app (not Chrome!)
        edge_exe = _find_edge_executable()
        if edge_exe:
            profile_dir = RUNTIME_DIR / ".desktop_app_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            print(f"  [Window] Opening Standalone Desktop App Window via Edge --app ({edge_exe})...")
            subprocess.Popen(
                [
                    edge_exe,
                    f"--app={url}",
                    "--window-size=1600,960",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--disable-extensions",
                ],
                cwd=str(HUB_DIR),
            )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return

    # Mode 3: Explicit --browser flag or last-resort fallback
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Launch Tabulas Card Management Hub")
    parser.add_argument("--browser", action="store_true", help="Open in default web browser instead of standalone desktop window")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if not run_health_check():
        sys.exit(1)
    if args.check_only:
        cli_p = (APP_DIR / "cli.py") if (APP_DIR / "cli.py").exists() else (HUB_DIR / "cli.py")
        subprocess.run([sys.executable, str(cli_p), "--version"], cwd=str(HUB_DIR))
        return
    launch_zero_node_python_react_server(port=5000, force_browser=bool(args.browser))


if __name__ == "__main__":
    main()