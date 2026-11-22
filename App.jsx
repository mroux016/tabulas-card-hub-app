// @ts-nocheck
import React, { useState, useEffect, useMemo, useRef } from 'react';

const APP_VERSION = '0.24.0-beta.45';
const LAST_UPDATED = '2026-11-21 15:05:00';
const STORAGE_ROOT = 'C:\\Tabulas Card Hub';
const SET_LIBRARY_ROOT = 'D:\\Tabulas Set Library';
const API_ORIGIN = (typeof window !== 'undefined' && window.location && window.location.origin && !window.location.origin.startsWith('file://') && window.location.origin !== 'null') ? window.location.origin : 'http://localhost:5000';
const NODE_API_BASE = `${API_ORIGIN}/api`;

// ============================================================================
// 9 CHROME-PULSE SKINS (GRADIENTS, 3D DEPTH & SNAPPY MOTION)
// ============================================================================
// Authentic 9 Chrome-Pulse 3D Skins (Restored from Chrome-Pulse v4.5)
const CHROME_PULSE_SKINS = {
  screenshot_signature_3d: {
    name: '1. Chrome-Pulse 3D (Default)',
    tagline: 'Midnight Navy & Emerald/Cyan beveled 3D depth',
    swatch: 'linear-gradient(135deg, #10b981, #06b6d4)',
    appBg: 'bg-gradient-to-b from-[#080d18] via-[#060a12] to-[#04070d]',
    railBg: 'bg-gradient-to-b from-[#0b1220]/95 to-[#060a12]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#101829]/95 to-[#0a101d]/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(6,182,212,0.28)]',
    border: 'border-cyan-500/25',
    accentBtn: 'bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 font-extrabold shadow-lg shadow-cyan-950/60',
    accentActive: 'bg-gradient-to-r from-emerald-500/25 via-teal-500/25 to-cyan-500/25 text-emerald-200 border-cyan-400/60',
    iconBg: 'bg-gradient-to-br from-emerald-500/25 to-cyan-600/35 border-cyan-400/40',
    accentText: 'text-cyan-300',
    textMain: 'text-slate-100',
  },
  classic_bronze_3d: {
    name: '2. Classic Warm Bronze & Obsidian 3D',
    tagline: 'Warm amber-bronze accents paired with deep obsidian-cyan',
    swatch: 'linear-gradient(135deg, #f59e0b, #06b6d4)',
    appBg: 'bg-gradient-to-b from-[#141008] via-[#0a101f] to-[#04070d]',
    railBg: 'bg-gradient-to-b from-[#1a1206]/95 to-[#080d19]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#1e1609]/95 to-[#0d1322]/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(245,158,11,0.25)]',
    border: 'border-amber-500/30',
    accentBtn: 'bg-gradient-to-r from-amber-400 to-cyan-500 hover:from-amber-300 hover:to-cyan-400 text-slate-950 font-extrabold shadow-lg shadow-amber-950/60',
    accentActive: 'bg-gradient-to-r from-amber-500/25 to-cyan-500/25 text-amber-200 border-amber-400/60',
    iconBg: 'bg-gradient-to-br from-amber-500/25 to-cyan-600/30 border-amber-400/40',
    accentText: 'text-amber-300',
    textMain: 'text-amber-50',
  },
  superfractor_gold: {
    name: '3. Superfractor 1/1 (Gold Foil & Carbon)',
    tagline: 'Brushed carbon slate with metallic 24k gold foil trim',
    swatch: 'linear-gradient(135deg, #eab308, #fde047)',
    appBg: 'bg-gradient-to-b from-[#121216] via-[#0c0c0e] to-[#08080a]',
    railBg: 'bg-gradient-to-b from-[#141004]/95 to-[#08080a]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-br from-zinc-900/95 to-neutral-950/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(234,179,8,0.28)]',
    border: 'border-yellow-500/35',
    accentBtn: 'bg-gradient-to-r from-yellow-300 via-amber-400 to-yellow-500 hover:from-yellow-200 hover:to-amber-400 text-slate-950 font-extrabold shadow-lg shadow-yellow-950/60',
    accentActive: 'bg-gradient-to-r from-yellow-500/25 to-amber-500/25 text-yellow-200 border-yellow-400/60',
    iconBg: 'bg-gradient-to-br from-yellow-500/25 to-amber-600/35 border-yellow-400/40',
    accentText: 'text-yellow-300',
    textMain: 'text-zinc-100',
  },
  sapphire_edition: {
    name: '4. Topps Sapphire Chrome (Cracked Ice)',
    tagline: 'Deep crystalline sapphire blue with ice-blue refractor borders',
    swatch: 'linear-gradient(135deg, #38bdf8, #3b82f6)',
    appBg: 'bg-gradient-to-b from-[#061330] via-[#040d21] to-[#030917]',
    railBg: 'bg-gradient-to-b from-[#08193d]/95 to-[#030917]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#0b1f4a]/95 to-[#06122e]/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(56,189,248,0.32)]',
    border: 'border-sky-400/35',
    accentBtn: 'bg-gradient-to-r from-sky-300 to-blue-500 hover:from-sky-200 hover:to-blue-400 text-slate-950 font-extrabold shadow-lg shadow-blue-950/60',
    accentActive: 'bg-gradient-to-r from-sky-500/30 to-blue-600/30 text-sky-200 border-sky-400/60',
    iconBg: 'bg-gradient-to-br from-sky-500/25 to-blue-600/35 border-sky-400/40',
    accentText: 'text-sky-300',
    textMain: 'text-sky-50',
  },
  quant_terminal: {
    name: '5. Quant Drop Terminal (OLED Pro)',
    tagline: 'Pitch-black OLED institutional terminal & neon telemetry',
    swatch: 'linear-gradient(135deg, #10b981, #f59e0b)',
    appBg: 'bg-[#020408]',
    railBg: 'bg-black/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#070d14] to-[#04070b] shadow-[0_10px_30px_-10px_rgba(16,185,129,0.25)]',
    border: 'border-emerald-500/30',
    accentBtn: 'bg-gradient-to-r from-emerald-400 to-lime-400 hover:from-emerald-300 hover:to-lime-300 text-black font-extrabold shadow-lg',
    accentActive: 'bg-emerald-500/25 text-emerald-200 border-emerald-400/60',
    iconBg: 'bg-gradient-to-br from-emerald-500/20 to-amber-500/25 border-emerald-400/40',
    accentText: 'text-emerald-300',
    textMain: 'text-emerald-50',
  },
  finest_refractor: {
    name: "6. Finest '93 Refractor (Holo Prism)",
    tagline: '90s Topps Finest violet-indigo glass with fuchsia-cyan holo sheen',
    swatch: 'linear-gradient(135deg, #e879f9, #22d3ee)',
    appBg: 'bg-gradient-to-br from-[#120924] via-[#0c061a] to-[#070310]',
    railBg: 'bg-gradient-to-b from-[#160b2b]/95 to-[#080412]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#1b1038]/90 to-[#110924]/90 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(232,121,249,0.30)]',
    border: 'border-fuchsia-500/35',
    accentBtn: 'bg-gradient-to-r from-fuchsia-400 via-purple-400 to-cyan-400 hover:from-fuchsia-300 hover:to-cyan-300 text-slate-950 font-extrabold shadow-lg shadow-fuchsia-950/60',
    accentActive: 'bg-gradient-to-r from-fuchsia-500/30 via-purple-500/25 to-cyan-500/25 text-fuchsia-200 border-fuchsia-400/60',
    iconBg: 'bg-gradient-to-br from-fuchsia-500/25 to-cyan-500/30 border-fuchsia-400/40',
    accentText: 'text-fuchsia-300',
    textMain: 'text-slate-100',
  },
  stadium_club: {
    name: '7. Stadium Club Modern (Slate & Crimson)',
    tagline: 'Brushed zinc-slate 3D surfaces with iconic Topps crimson-red',
    swatch: 'linear-gradient(135deg, #f43f5e, #38bdf8)',
    appBg: 'bg-gradient-to-b from-zinc-900 via-zinc-950 to-[#09090b]',
    railBg: 'bg-gradient-to-b from-zinc-900/95 to-zinc-950/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-zinc-900/95 to-zinc-950/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(244,63,94,0.28)]',
    border: 'border-rose-500/30',
    accentBtn: 'bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-400 hover:to-red-500 text-white font-extrabold shadow-lg shadow-rose-950/60',
    accentActive: 'bg-gradient-to-r from-rose-500/30 to-red-600/25 text-rose-200 border-rose-400/60',
    iconBg: 'bg-gradient-to-br from-rose-500/25 to-red-600/35 border-rose-400/40',
    accentText: 'text-rose-300',
    textMain: 'text-zinc-100',
  },
  bowman_turf_3d: {
    name: '8. Bowman Draft Emerald Turf 3D',
    tagline: 'Deep stadium forest-emerald 3D surfaces with lime-gold highlights',
    swatch: 'linear-gradient(135deg, #34d399, #a3e635)',
    appBg: 'bg-gradient-to-b from-[#061a12] via-[#04140e] to-[#030d09]',
    railBg: 'bg-gradient-to-b from-[#061c13]/95 to-[#03100b]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#09261b]/95 to-[#051710]/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(52,211,153,0.28)]',
    border: 'border-emerald-500/35',
    accentBtn: 'bg-gradient-to-r from-lime-400 to-emerald-400 hover:from-lime-300 hover:to-emerald-300 text-slate-950 font-extrabold shadow-lg shadow-emerald-950/60',
    accentActive: 'bg-gradient-to-r from-emerald-500/30 to-lime-500/25 text-emerald-200 border-emerald-400/60',
    iconBg: 'bg-gradient-to-br from-emerald-500/25 to-lime-500/30 border-emerald-400/40',
    accentText: 'text-emerald-300',
    textMain: 'text-emerald-50',
  },
  cosmic_chrome_3d: {
    name: '9. Cosmic Chrome Nebula 3D',
    tagline: 'Deep-space ultraviolet & electric cyan planetary glow',
    swatch: 'linear-gradient(135deg, #818cf8, #22d3ee)',
    appBg: 'bg-gradient-to-b from-[#0b0924] via-[#070617] to-[#04030e]',
    railBg: 'bg-gradient-to-b from-[#0f0c2e]/95 to-[#060514]/95 backdrop-blur-xl',
    cardBg: 'bg-gradient-to-b from-[#121036]/95 to-[#0a0821]/95 backdrop-blur-md shadow-[0_10px_30px_-10px_rgba(129,140,248,0.32)]',
    border: 'border-indigo-400/35',
    accentBtn: 'bg-gradient-to-r from-indigo-400 via-sky-400 to-cyan-300 hover:from-indigo-300 hover:to-cyan-200 text-slate-950 font-extrabold shadow-lg shadow-indigo-950/60',
    accentActive: 'bg-gradient-to-r from-indigo-500/30 to-cyan-500/25 text-indigo-200 border-indigo-400/60',
    iconBg: 'bg-gradient-to-br from-indigo-500/25 to-cyan-500/35 border-indigo-400/40',
    accentText: 'text-indigo-300',
    textMain: 'text-cyan-50',
  },
};

const LEGACY_SKIN_KEY_MAP = {
  chrome_pulse: 'screenshot_signature_3d',
  titanium_chrome: 'classic_bronze_3d',
  solar_amber: 'superfractor_gold',
  midnight_cobalt: 'sapphire_edition',
  arctic_slate: 'quant_terminal',
  cyber_magenta: 'finest_refractor',
  obsidian_rose: 'stadium_club',
  emerald_vault: 'bowman_turf_3d',
  violet_nebula: 'cosmic_chrome_3d',
};

function resolveChromePulseSkinKey(rawKey) {
  const k = String(rawKey || '').trim();
  if (CHROME_PULSE_SKINS[k]) return k;
  if (LEGACY_SKIN_KEY_MAP[k]) return LEGACY_SKIN_KEY_MAP[k];
  return 'screenshot_signature_3d';
}

// 8-Slot Dynamic Parallel Worker Pool (Unused workers stay hidden in Top Bar & Monitor!)
const PROCESS_LANES = {
  slot_1: { shortName: 'Worker 1', icon: '⚡' },
  slot_2: { shortName: 'Worker 2', icon: '⚡' },
  slot_3: { shortName: 'Worker 3', icon: '⚡' },
  slot_4: { shortName: 'Worker 4', icon: '⚡' },
  slot_5: { shortName: 'Worker 5', icon: '⚡' },
  slot_6: { shortName: 'Worker 6', icon: '⚡' },
  slot_7: { shortName: 'Worker 7', icon: '⚡' },
  slot_8: { shortName: 'Worker 8', icon: '⚡' },
};

const DEFAULT_LISTING_CONTENT_OPTS = {
  include_opening: true,
  include_set_blurb: true,
  include_player_bio: true,
  include_player_stats: true,
  include_player_accolades: true,
  include_pregrade_notes: true,
  include_grading_disclaimer: true,
  include_shipping_policy: true,
  include_as_is_disclaimer: true,
  include_sku_ref: true,
};

const NAV_CATEGORIES = [
  {
    id: 'inventory_mgmt',
    label: 'Inventory Management',
    icon: '📦',
    items: [
      { id: 'scan_ingestion', label: 'Batch Scan Processor', icon: '📥' },
      { id: 'guided_batch_review', label: 'Guided Batch Review', icon: '🪟', hiddenUntilLaunched: true },
      { id: 'batch_deep_dive', label: 'Deep-Dive Card Review', icon: '🔬', hiddenUntilLaunched: true },
      { id: 'inventory', label: 'Inventory', icon: '🗂️' },
      { id: 'card_level_inventory', label: 'Card-Level Inventory', icon: '🃏' },
      { id: 'inventory_editor', label: 'Inventory Editor', icon: '✏️', hiddenUntilLaunched: true },
      { id: 'label_hub', label: 'Label Hub', icon: '🏷️' },
    ],
  },
  {
    id: 'checklists_resources',
    label: 'Checklists & Resources',
    icon: '🏛️',
    items: [
      { id: 'checklist_builder', label: 'Checklist Builder', icon: '🕷️' },
      { id: 'unified_checklist_viewer', label: 'Unified Checklist Viewer', icon: '📊' },
      { id: 'set_browser', label: 'Set Browser', icon: '🌐' },
    ],
  },
  {
    id: 'sales_hub',
    label: 'Sales Hub',
    icon: '🏪',
    items: [
      { id: 'grading_engine', label: 'Grading Recommendation Engine', icon: '🎯' },
      { id: 'grading_inspector', label: 'Grading Candidate Inspector', icon: '🔬', hiddenUntilLaunched: true },
      { id: 'lot_suggestions', label: 'Multi-Card, Lot & Set Suggestions', icon: '📚' },
      { id: 'listing_writer', label: 'Listing Writer', icon: '✍️' },
      { id: 'sales_strategy', label: 'Sales Strategy Hub', icon: '📈' },
      { id: 'sold_cards', label: 'Sold Cards', icon: '💵' },
    ],
  },
  {
    id: 'collection',
    label: 'Collection',
    icon: '🏆',
    items: [
      { id: 'collection_value', label: 'Collection Value', icon: '💎' },
      { id: 'set_completion', label: 'Set Completion', icon: '📊' },
      { id: 'card_purchase_planner', label: 'Card Purchase Planner', icon: '🛒' },
    ],
  },
  {
    id: 'bookkeeping',
    label: 'Bookkeeping',
    icon: '🧾',
    items: [
      { id: 'expenses', label: 'Expenses', icon: '💳' },
      { id: 'analytics', label: 'Analytics', icon: '📉' },
      { id: 'accounting', label: 'Accounting', icon: '📒' },
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: '⚙️',
    items: [
      { id: 'general_settings', label: 'General Settings', icon: '⚙️' },
      { id: 'about', label: 'Check for Updates', icon: '🔄' },
      { id: 'notification_history', label: 'Notification History', icon: '🔔', hiddenUntilLaunched: true },
    ],
  },
];

const DEFAULT_GLOSSARY = {
  RC: 'Rookie Card', ASR: 'All-Star Rookies', LL: 'League Leaders', CPC: 'Combo Player Cards',
  TC: 'Team Card', FS: 'Future Stars', SP: 'Short Print', SSP: 'Super Short Print',
  VAR: 'Variation', Auto: 'Autographed', AU: 'Autographed', Mem: 'Memorabilia / Relic',
  REL: 'Relic', SN: 'Serial Numbered', '1/1': 'One of One', HOF: 'Hall of Fame',
  AS: 'All-Star', PRO: 'Prospect', ERR: 'Error Card', UER: 'Uncorrected Error', COR: 'Corrected Error',
};

const LABEL_TEMPLATES = {
  R037L: { name: 'Spartan Industrial R037L (1.5" x 0.5", 100/sheet | 12.2mm Top-Left)', cols: 5, rows: 20, widthIn: 1.5, heightIn: 0.5, aspectRatio: '3 / 1' },
  AVERY_5160: { name: 'Avery 5160 / 8160 (2.625" x 1.0", 30/sheet)', cols: 3, rows: 10, widthIn: 2.625, heightIn: 1.0, aspectRatio: '2.625 / 1' },
  AVERY_5167: { name: 'Avery 5167 / 8167 (1.75" x 0.5", 80/sheet)', cols: 4, rows: 20, widthIn: 1.75, heightIn: 0.5, aspectRatio: '3.5 / 1' },
};

function inferLeagueCodeFromSet(setName) {
  const low = String(setName || '').toLowerCase();
  if (low.includes('football') || low.includes('nfl') || low.includes('resurgence')) return 'NFL';
  if (low.includes('basketball') || low.includes('nba')) return 'NBA';
  if (low.includes('hockey') || low.includes('nhl')) return 'NHL';
  if (low.includes('soccer') || low.includes('mls') || low.includes('uefa') || low.includes('fifa')) return 'MLS';
  if (low.includes('formula 1') || low.includes('racing') || low.includes('f1')) return 'F1';
  if (low.includes('wrestling') || low.includes('wwe')) return 'WWE';
  if (low.includes('ufc') || low.includes('mma')) return 'UFC';
  if (low.includes('golf') || low.includes('pga')) return 'PGA';
  return 'MLB';
}

function getLabelSubsetBadgeStyle(subsetStr) {
  const u = String(subsetStr || 'Base').trim().toUpperCase();
  if (!u || u === 'BASE' || u === 'BASE SET') {
    return { borderCls: 'border border-slate-300', pillCls: 'bg-slate-100 text-slate-700', isBase: true };
  }
  if (u.includes('RED') || u.includes('RUBY') || u.includes('CRIMSON')) {
    return { borderCls: 'border-2 border-rose-600', pillCls: 'bg-rose-700 text-white', isBase: false };
  }
  if (u.includes('BLUE') || u.includes('SAPPHIRE') || u.includes('AQUA')) {
    return { borderCls: 'border-2 border-blue-600', pillCls: 'bg-blue-700 text-white', isBase: false };
  }
  if (u.includes('GREEN') || u.includes('EMERALD')) {
    return { borderCls: 'border-2 border-emerald-600', pillCls: 'bg-emerald-700 text-white', isBase: false };
  }
  if (u.includes('PURPLE') || u.includes('VIOLET')) {
    return { borderCls: 'border-2 border-purple-600', pillCls: 'bg-purple-700 text-white', isBase: false };
  }
  if (u.includes('ORANGE')) {
    return { borderCls: 'border-2 border-orange-600', pillCls: 'bg-orange-600 text-white', isBase: false };
  }
  if (u.includes('PINK')) {
    return { borderCls: 'border-2 border-pink-600', pillCls: 'bg-pink-600 text-white', isBase: false };
  }
  return { borderCls: 'border-2 border-amber-600', pillCls: 'bg-amber-700 text-white', isBase: false };
}

const EXPENSE_CATEGORIES = [
  'Boxes / Packs / Cases (COGS)',
  'Single Card Acquisitions (COGS)',
  'Card Protection & Storage (Sleeves, Toploaders, One-Touch, Boxes)',
  'Shipping Materials (Mailers, Team Bags, Tape, Labels)',
  'Equipment & Software (Scanner, Printer, Thermal Labels)',
  'Grading & Authentication Fees',
  'Other / Miscellaneous',
];

function safeNum(val, fallback = 0) {
  const n = parseFloat(String(val ?? '').replace(/[^0-9.\-]/g, ''));
  return Number.isFinite(n) ? n : fallback;
}

function fmtCurrency(val, signed = false) {
  const n = safeNum(val, 0);
  const absStr = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (signed) return n >= 0 ? `+$${absStr}` : `-$${absStr}`;
  return n < 0 ? `-$${absStr}` : `$${absStr}`;
}

function fmtEta(sec) {
  if (sec === null || sec === undefined || !Number.isFinite(Number(sec))) return '--:--';
  const s = Math.max(0, Math.round(Number(sec)));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rem = s % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}` : `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

function ThumbtackPinIcon({ pinned, className = 'w-3.5 h-3.5' }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={pinned ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2.1"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`${className} transition-transform duration-200 ease-out ${pinned ? 'rotate-0' : 'rotate-45'}`}
      aria-hidden="true"
    >
      <path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6z" />
      <path d="M12 14v7" />
    </svg>
  );
}

function sanitizeFolderName(val) {
  return String(val || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .replace(/[\\/:*?"<>|\[\]]+/g, '_')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '') || 'Unknown';
}

function expandSkuRangeTokens(rawInput) {
  const out = [];
  const seen = new Set();
  String(rawInput || '').split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean).forEach((tok) => {
    if (tok.includes('-')) {
      const [p1, p2] = tok.split('-', 2).map((x) => x.trim());
      if (/^\d+$/.test(p1) && /^\d+$/.test(p2)) {
        const sI = parseInt(p1, 10);
        const eI = parseInt(p2, 10);
        const lo = Math.min(sI, eI);
        const hi = Math.min(Math.max(sI, eI), lo + 2500);
        for (let n = lo; n <= hi; n++) {
          const skuS = n >= 1000000 ? String(n).padStart(7, '0') : String(n);
          if (!seen.has(skuS)) { seen.add(skuS); out.push(skuS); }
        }
        return;
      }
    }
    const clean = /^\d+$/.test(tok) && parseInt(tok, 10) >= 1000000 ? String(parseInt(tok, 10)).padStart(7, '0') : tok;
    if (!seen.has(clean)) { seen.add(clean); out.push(clean); }
  });
  return out;
}

function sortSetsNewestFirst(setsList) {
  return [...setsList].sort((a, b) => {
    const mA = String(a).match(/\b(19\d{2}|20\d{2})(?:-(\d{2}))?\b/);
    const mB = String(b).match(/\b(19\d{2}|20\d{2})(?:-(\d{2}))?\b/);
    const yA = mA ? parseFloat(mA[1]) + (mA[2] ? parseFloat(mA[2]) / 100 : 0) : 0;
    const yB = mB ? parseFloat(mB[1]) + (mB[2] ? parseFloat(mB[2]) / 100 : 0) : 0;
    if (yB !== yA) return yB - yA;
    return String(a).localeCompare(String(b));
  });
}

function inferSportFromSet(setName) {
  const low = String(setName || '').toLowerCase();
  if (low.includes('football') || low.includes('nfl') || low.includes('resurgence')) return 'Football';
  if (low.includes('basketball') || low.includes('nba')) return 'Basketball';
  if (low.includes('hockey') || low.includes('nhl')) return 'Hockey';
  if (low.includes('soccer') || low.includes('mls')) return 'Soccer';
  if (low.includes('formula 1') || low.includes('racing') || low.includes('f1')) return 'Racing';
  return 'Baseball';
}

const ALL_TCDB_SPORTS = ['Baseball', 'Football', 'Basketball', 'Hockey', 'Soccer', 'Racing', 'Wrestling', 'MMA', 'Golf'];
const SPORT_FIRST_CARD_YEAR = {
  Baseball: 1880,
  Football: 1894,
  Hockey: 1910,
  Golf: 1926,
  Basketball: 1948,
  Racing: 1954,
  Wrestling: 1954,
  Soccer: 1958,
  MMA: 2008,
};

function computeDynamicEraForYear(yearStr, referenceYear = new Date().getFullYear()) {
  const m = String(yearStr || '').match(/(18\d{2}|19\d{2}|20\d{2})/);
  const curDecStart = Math.floor(referenceYear / 10) * 10;
  const curDecEnd = referenceYear - 3;
  if (!m) return curDecEnd > curDecStart ? `${curDecStart}-${curDecEnd}` : String(curDecStart);
  const y = parseInt(m[1], 10);
  if (y >= referenceYear - 2) return String(y);
  if (y >= curDecStart) return curDecEnd > curDecStart ? `${curDecStart}-${curDecEnd}` : String(curDecStart);
  if (y >= 1980) {
    const dec = Math.floor(y / 10) * 10;
    return `${dec}-${dec + 9}`;
  }
  return 'Pre-1980';
}

function eraSortWeight(eraLabel) {
  const s = String(eraLabel || '').trim();
  if (s.toLowerCase().startsWith('pre-') || s.toLowerCase().includes('vintage')) return 0;
  const nums = (s.match(/\d{4}/g) || []).map((n) => parseInt(n, 10));
  return nums.length > 0 ? Math.max(...nums) : 1;
}

function renderFormattedChangelog(text) {
  const clean = String(text || '').replace(/\s*->\s*/g, ' → ');
  const parts = clean.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
      return (
        <span key={idx} className="font-mono text-sky-300 bg-slate-900/90 border border-slate-800 px-1 py-0.5 rounded text-[10.5px]">
          {part.slice(1, -1)}
        </span>
      );
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
      return <strong key={idx} className="text-white font-semibold">{part.slice(2, -2).replace(/`/g, '')}</strong>;
    }
    return <React.Fragment key={idx}>{part.replace(/`/g, '')}</React.Fragment>;
  });
}

function parseCardIdTier(card) {
  const ocr = Math.round(safeNum(card?.OCR_Confidence, 0));
  const sig = String(card?.OCR_Signals || '');
  const vis = safeNum(card?.Template_Similarity, 0);
  const visPct = vis > 0 ? Math.min(100, Math.round(vis * 100)) : null;
  const visBadgeCls =
    visPct === null
      ? 'bg-slate-900 border-slate-700 text-slate-500'
      : visPct >= 85
      ? 'bg-emerald-950/80 border-emerald-600/70 text-emerald-300'
      : visPct >= 75
      ? 'bg-cyan-950/80 border-cyan-600/70 text-cyan-200'
      : visPct >= 65
      ? 'bg-amber-950/80 border-amber-600/70 text-amber-200'
      : 'bg-rose-950/85 border-rose-600/80 text-rose-200';
  const needsRev = String(card?.Needs_Review || '').toLowerCase() === 'true';
  const parCorrected = sig.includes('ParallelSelfCorrected');

  const extra = { ocr, vis, visPct, visBadgeCls, parCorrected };
  if (sig.includes('T5_CardSightAI') || sig.includes('CardSightAI')) {
    return { code: 'T5_AI', label: '🤖 T5 AI', badgeCls: 'bg-sky-950/80 border-sky-600/70 text-sky-200', ...extra };
  }
  if (sig.includes('T4_SetVisual')) {
    return { code: 'T4_VISUAL', label: '🟣 T4 SetVis', badgeCls: 'bg-purple-950/80 border-purple-600/70 text-purple-200', ...extra };
  }
  if (sig.includes('T3_ReRead') || sig.includes('T3_Attempt')) {
    return { code: 'T3_REREAD', label: '🟠 T3 Re-Read', badgeCls: 'bg-amber-950/80 border-amber-600/70 text-amber-200', ...extra };
  }
  if (sig.includes('T2_VisualConfirmed')) {
    return { code: 'T2_VISUAL', label: '🔵 T2 Visual', badgeCls: 'bg-cyan-950/80 border-cyan-500/70 text-cyan-200', ...extra };
  }
  if (ocr >= 185 && !needsRev) {
    return { code: 'T1_LOCK', label: '🟢 T1 Lock', badgeCls: 'bg-emerald-950/80 border-emerald-600/70 text-emerald-300', ...extra };
  }
  if (ocr >= 185 && needsRev) {
    return { code: 'T1_FLAG', label: '🟡 T1 Flag', badgeCls: 'bg-amber-950/80 border-amber-600/70 text-amber-200', ...extra };
  }
  return { code: 'UNCONFIRMED', label: needsRev ? '🔴 Review' : '🟡 <185', badgeCls: needsRev ? 'bg-rose-950/85 border-rose-600/80 text-rose-200' : 'bg-amber-950/70 border-amber-700/70 text-amber-200', ...extra };
}

function AttributeBadges({ attributesStr, glossary = DEFAULT_GLOSSARY }) {
  const raw = String(attributesStr || '').trim();
  if (!raw) return <span className="text-slate-600">—</span>;
  const parts = raw.split(',').map((t) => t.trim()).filter(Boolean);
  return (
    <div className="flex flex-wrap gap-1">
      {parts.map((tok, i) => {
        const code = tok.split('[')[0].trim();
        const tip = glossary[code] || glossary[code.toUpperCase()] || (code.startsWith('#/') ? `Serial Numbered ${code}` : tok);
        return (
          <span
            key={i}
            title={`${code}: ${tip}`}
            className="px-1.5 py-0.5 rounded bg-sky-950/80 border border-sky-700/60 text-sky-200 font-mono text-[10px] cursor-help hover:bg-sky-800/70 transition"
          >
            {tok}
          </span>
        );
      })}
    </div>
  );
}

function SideBySideCardComparison({
  scanFrontUrl, scanBackUrl, cornersUrl, setName, subsetName, cardNumber,
  initialTmplFrontRel, initialTmplBackRel, heightClass = 'h-48',
}) {
  const [tmplRef, setTmplRef] = useState({ front_rel: initialTmplFrontRel || '', back_rel: initialTmplBackRel || '', cid_tag: '' });

  useEffect(() => {
    if (!setName) return;
    let active = true;
    const params = new URLSearchParams({ set: setName, subset: subsetName || 'Base', cardNumber: String(cardNumber || '').replace(/^#/, '') });
    fetch(`${NODE_API_BASE}/templates/lookup?${params.toString()}`)
      .then((r) => r.json())
      .then((res) => active && res && setTmplRef({ front_rel: res.front_rel || initialTmplFrontRel || '', back_rel: res.back_rel || initialTmplBackRel || '', cid_tag: res.cid_tag || '' }))
      .catch(() => {});
    return () => { active = false; };
  }, [setName, subsetName, cardNumber, initialTmplFrontRel, initialTmplBackRel]);

  const tmplFrontUrl = tmplRef.front_rel ? `${API_ORIGIN}/static/templates/${tmplRef.front_rel.split('/').map(encodeURIComponent).join('/')}` : '';
  const tmplBackUrl = tmplRef.back_rel ? `${API_ORIGIN}/static/templates/${tmplRef.back_rel.split('/').map(encodeURIComponent).join('/')}` : '';
  const cols = cornersUrl ? 'grid-cols-2 sm:grid-cols-5' : 'grid-cols-2 sm:grid-cols-4';
  return (
    <div className={`grid ${cols} gap-2`}>
      {[
        ['Scan Front (_F)', scanFrontUrl, 'border-slate-700 text-slate-300'],
        [`TCDB Front ${tmplRef.cid_tag ? `(${tmplRef.cid_tag})` : ''}`, tmplFrontUrl, 'border-sky-700/70 text-sky-300'],
        ['Scan Back (_B)', scanBackUrl, 'border-slate-700 text-slate-300'],
        [`TCDB Back ${tmplRef.cid_tag ? `(${tmplRef.cid_tag})` : ''}`, tmplBackUrl, 'border-sky-700/70 text-sky-300'],
        ...(cornersUrl ? [['8-Corner Sheet (_C)', cornersUrl, 'border-amber-700/60 text-amber-300']] : []),
      ].map(([lbl, u, cls], idx) => (
        <div key={idx} className={`bg-slate-950/90 border ${cls} rounded-xl p-2 flex flex-col items-center shadow-inner`}>
          <div className="text-[10px] font-bold mb-1 truncate max-w-full">{lbl}</div>
          {u ? <img src={u} alt={lbl} className={`${heightClass} w-auto object-contain rounded`} /> : <div className={`${heightClass} flex items-center justify-center text-[10px] text-slate-500`}>No Image</div>}
        </div>
      ))}
    </div>
  );
}

function GuidedReviewCardItem({
  card,
  draft,
  batchName,
  skin,
  dynamicSets,
  onDraftChange,
  onSaveOne,
  onRotateSide,
  onReplaceImages,
  onDeleteOne,
  onReprocessOne,
  onOpenDeepDive,
  isDirty,
  imageHeightClass = 'h-48',
  isDeepDive = false,
  externalImgBust = 0,
  isReprocessingExternal = false,
}) {
  const [searchQ, setSearchQ] = useState('');
  const [lookupData, setLookupData] = useState({ subsets: ['Base'], matches: [] });
  const [savingOne, setSavingOne] = useState(false);
  const [reprocessingOne, setReprocessingOne] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [deletingOne, setDeletingOne] = useState(false);
  const [reviewTouched, setReviewTouched] = useState(false);
  const [imgBust, setImgBust] = useState(0);

  const effectiveBatchName = card._BatchName || batchName;
  const curSet = draft.Set || '';
  const curSub = draft.Subset_Parallel || 'Base';
  const curCnum = String(draft.Card_Number || '').replace(/^#/, '');
  const tier = parseCardIdTier(card);
  const bEnc = encodeURIComponent(effectiveBatchName);
  const combinedBust = imgBust + (externalImgBust || 0);
  const bustQ = combinedBust ? `?v=${combinedBust}` : '';
  const isReprocBusy = reprocessingOne || isReprocessingExternal;

  const hasFieldChanges = (
    String(draft.Set || '').trim() !== String(card.Set || '').trim() ||
    String(draft.Subset_Parallel || 'Base').trim() !== String(card.Subset_Parallel || 'Base').trim() ||
    String(draft.Card_Number || '').replace(/^#/, '').trim() !== String(card.Card_Number || '').replace(/^#/, '').trim() ||
    String(draft.Player || '').trim() !== String(card.Player || '').trim() ||
    String(draft.Team || '').trim() !== String(card.Team || '').trim() ||
    String(draft.Print_Run || '').trim() !== String(card.Print_Run || '').trim()
  );
  const isAlreadyConfirmed = String(card.Needs_Review || '').toLowerCase() !== 'true' && String(card.OCR_Signals || '').includes('UserConfirmed');

  // Live debounced checklist lookup for type-ahead search & validated subset dropdown
  useEffect(() => {
    if (!curSet) return;
    let active = true;
    const timer = setTimeout(() => {
      const p = new URLSearchParams({ set: curSet, q: searchQ, limit: '45' });
      fetch(`${NODE_API_BASE}/checklists/lookup?${p.toString()}`)
        .then((r) => r.json())
        .then((d) => {
          if (active && d) {
            setLookupData({
              subsets: Array.isArray(d.subsets) && d.subsets.length > 0 ? d.subsets : ['Base'],
              matches: Array.isArray(d.matches) ? d.matches : [],
            });
          }
        })
        .catch(() => {});
    }, searchQ ? 180 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [curSet, searchQ]);

  const handleExactCardNumAutofill = (cnumVal, subVal = curSub) => {
    const cleanCn = String(cnumVal || '').trim().replace(/^#/, '');
    if (!curSet || !cleanCn) return;
    const p = new URLSearchParams({ set: curSet, cardNumber: cleanCn, subset: subVal || 'Base' });
    fetch(`${NODE_API_BASE}/checklists/lookup?${p.toString()}`)
      .then((r) => r.json())
      .then((d) => {
        if (d && d.exact && d.exact.player && d.exact.player !== 'Unknown Player') {
          onDraftChange({
            ...draft,
            Card_Number: `#${d.exact.card_number || cleanCn}`,
            Player: d.exact.player,
            Team: d.exact.team || draft.Team || '',
            Print_Run: d.exact.print_run || '',
            Attributes: d.exact.attributes || draft.Attributes || '',
            Needs_Review: 'False',
          });
        }
      })
      .catch(() => {});
  };

  // Parse Top_3_Template_Candidates pills for 1-click subset switching
  const candidatePills = useMemo(() => {
    const raw = String(card.Top_3_Template_Candidates || '').trim();
    if (!raw || raw.includes('(Locked)')) return [];
    return raw.split('|').map((seg) => {
      const s = seg.trim();
      const m = s.match(/^([^(]+)\((.+)\)$/);
      return m ? { name: m[1].trim(), detail: m[2].trim() } : null;
    }).filter(Boolean).slice(0, 4);
  }, [card.Top_3_Template_Candidates]);

  const validSubsetsList = useMemo(() => {
    const fromCard = String(card.Valid_Checklist_Subsets || '').split('|').map((s) => s.trim()).filter(Boolean);
    const merged = Array.from(new Set([curSub, ...fromCard, ...(lookupData.subsets || []), 'Base'].filter(Boolean)));
    return merged;
  }, [curSub, card.Valid_Checklist_Subsets, lookupData.subsets]);

  return (
    <div className={`${skin.cardBg} border ${isDirty ? 'border-amber-500/70' : skin.border} rounded-2xl p-4 space-y-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-bold text-white">
          SKU <span className="font-mono text-sky-400">{card.SKU}</span> — {curSet} #{curCnum} {draft.Player} (<span className="text-amber-200">{curSub}</span>)
          {hasFieldChanges && <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-950 border border-amber-600 text-amber-200 text-[10px]">Unsaved Edit</span>}
          {!hasFieldChanges && isAlreadyConfirmed && <span className="ml-2 px-1.5 py-0.5 rounded bg-emerald-950 border border-emerald-600 text-emerald-300 text-[10px]">✅ Confirmed</span>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {onOpenDeepDive && (
            <button
              type="button"
              onClick={() => onOpenDeepDive(card.SKU)}
              title="Open this card in the maximized full-page Deep-Dive Single-Card Review Studio"
              className="px-2 py-0.5 rounded-lg bg-indigo-950/90 hover:bg-indigo-800 border border-indigo-600/70 text-indigo-200 text-[10.5px] font-bold"
            >
              🔬 Deep-Dive
            </button>
          )}
          {onReprocessOne && (
            <button
              type="button"
              disabled={isReprocBusy}
              onClick={() => {
                setReprocessingOne(true);
                Promise.resolve(onReprocessOne(card.SKU, curSet))
                  .then(() => setImgBust((v) => v + 1))
                  .finally(() => setReprocessingOne(false));
              }}
              title="Re-run OCR, 5-Tier Visual Confirmation, Parallel Self-Correction & Pre-Grading immediately in an available parallel worker"
              className="px-2 py-0.5 rounded-lg bg-cyan-950/90 hover:bg-cyan-800 border border-cyan-600/70 text-cyan-200 text-[10.5px] font-bold disabled:opacity-50"
            >
              {isReprocBusy ? '⏳ Worker Running...' : '🔄 Reprocess'}
            </button>
          )}
          {card.Front_File && (
            <button
              type="button"
              onClick={() => Promise.resolve(onRotateSide(card.Front_File)).then(() => setImgBust((v) => v + 1))}
              title="Rotate Scan Front 90° clockwise on disk"
              className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[10.5px] font-semibold"
            >
              ↻ Front
            </button>
          )}
          {card.Back_File && (
            <button
              type="button"
              onClick={() => Promise.resolve(onRotateSide(card.Back_File)).then(() => setImgBust((v) => v + 1))}
              title="Rotate Scan Back 90° clockwise on disk"
              className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[10.5px] font-semibold"
            >
              ↻ Back
            </button>
          )}
          {onReplaceImages && (
            <button
              type="button"
              onClick={() => onReplaceImages(card)}
              title="Replace Front and/or Back scan images from files on your computer (JPG, PNG, or 2-Page PDF)"
              className="px-2 py-0.5 rounded-lg bg-emerald-950/90 hover:bg-emerald-800 border border-emerald-600/70 text-emerald-200 text-[10.5px] font-bold"
            >
              🖼️ Replace Scans
            </button>
          )}
          {onDeleteOne && (
            confirmRemove ? (
              <span className="inline-flex items-center gap-1">
                <button
                  type="button"
                  disabled={deletingOne}
                  onClick={() => {
                    setDeletingOne(true);
                    Promise.resolve(onDeleteOne(card)).finally(() => { setDeletingOne(false); setConfirmRemove(false); });
                  }}
                  className="px-2 py-0.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-[10.5px] font-bold disabled:opacity-50"
                >
                  {deletingOne ? '...' : '⚠️ Confirm Remove'}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRemove(false)}
                  className="px-1.5 py-0.5 rounded-lg bg-slate-800 text-slate-300 text-[10.5px]"
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmRemove(true)}
                title="Delete / remove this card and its scan images from the uncommitted batch"
                className="px-2 py-0.5 rounded-lg bg-rose-950/90 hover:bg-rose-800 border border-rose-700/80 text-rose-200 text-[10.5px] font-bold"
              >
                🗑️ Remove
              </button>
            )
          )}
          <span className={`px-2 py-0.5 rounded-lg border font-mono font-bold ${tier.badgeCls}`}>
            {tier.label} • OCR {tier.ocr}
          </span>
          <span className={`px-2 py-0.5 rounded-lg border font-mono font-bold ${tier.visBadgeCls}`} title={card.Top_3_Template_Candidates || 'Visual Match Confidence'}>
            👁️ Vis {tier.visPct !== null ? `${tier.visPct}%` : 'N/A'}
          </span>
          <span className="font-mono text-slate-400">PSA {card.Est_PSA || '—'} / BGS {card.Est_BGS || '—'}</span>
        </div>
      </div>

      {(card.OCR_Signals || candidatePills.length > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px]">
          {card.OCR_Signals && (
            <div className="font-mono text-slate-400 truncate max-w-2xl" title={card.OCR_Signals}>
              Signals: {card.OCR_Signals}
            </div>
          )}
          {candidatePills.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-slate-400 mr-0.5">Quick-Pick Parallel:</span>
              {candidatePills.map((cp, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    onDraftChange({ ...draft, Subset_Parallel: cp.name, Manual_Override: cp.name, Needs_Review: 'False' });
                    handleExactCardNumAutofill(curCnum, cp.name);
                  }}
                  className="px-2 py-0.5 rounded-md bg-sky-950/80 hover:bg-sky-800 border border-sky-700/70 text-sky-200 font-mono text-[10px]"
                >
                  {cp.name} ({cp.detail})
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <SideBySideCardComparison
        scanFrontUrl={card.Front_File ? `${API_ORIGIN}/static/batches/${bEnc}/${encodeURIComponent(card.Front_File)}${bustQ}` : ''}
        scanBackUrl={card.Back_File ? `${API_ORIGIN}/static/batches/${bEnc}/${encodeURIComponent(card.Back_File)}${bustQ}` : ''}
        cornersUrl={card.Corners_File ? `${API_ORIGIN}/static/batches/${bEnc}/${encodeURIComponent(card.Corners_File)}${bustQ}` : ''}
        setName={curSet}
        subsetName={curSub}
        cardNumber={curCnum}
        initialTmplFrontRel={card.Matched_Template_Front}
        initialTmplBackRel={card.Matched_Template_Back}
        heightClass={imageHeightClass}
      />

      {/* CHECKLIST TYPE-AHEAD SEARCH & AUTOFILL BAR */}
      <div className="p-2.5 bg-slate-950/85 border border-sky-700/40 rounded-xl grid grid-cols-1 md:grid-cols-12 gap-2">
        <div className="md:col-span-4">
          <label className="block text-[10px] text-sky-300 font-bold mb-0.5">🔎 Search Card # or Player in {curSet || 'Checklist'}</label>
          <input
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Type #121, Will Vest, Team..."
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs"
          />
        </div>
        <div className="md:col-span-8">
          <label className="block text-[10px] text-sky-300 font-bold mb-0.5">✨ Pick Checklist Match (Auto-Fills Card #, Player, Team, Subset, Print Run &amp; Ref Image)</label>
          <select
            value=""
            onChange={(e) => {
              const idxPick = parseInt(e.target.value, 10);
              const m = lookupData.matches?.[idxPick];
              if (!m) return;
              const nextSub = m.subsets?.includes(curSub) ? curSub : (m.subsets?.includes('Base') ? 'Base' : (m.subsets?.[0] || 'Base'));
              onDraftChange({
                ...draft,
                Card_Number: `#${m.cardNumber}`,
                Player: m.player,
                Team: m.team || draft.Team || '',
                Subset_Parallel: nextSub,
                Manual_Override: nextSub,
                Print_Run: (m.printRuns && m.printRuns[nextSub]) || '',
                Attributes: m.attributes || draft.Attributes || '',
                Needs_Review: 'False',
              });
            }}
            className="w-full bg-slate-900 border border-sky-700/70 rounded-lg px-2.5 py-1.5 text-xs text-sky-200"
          >
            <option value="">-- Select from {(lookupData.matches || []).length} matching card(s) in {curSet || 'Checklist'} --</option>
            {(lookupData.matches || []).map((m, i) => (
              <option key={`${m.cardNumber}-${m.player}-${i}`} value={i}>
                #{m.cardNumber} — {m.player}{m.attributes ? ` [${m.attributes}]` : ''} ({m.team}) [{(m.subsets || []).length} parallel(s)]
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* VALIDATED EDITABLE FIELDS + PER-CARD SAVE OVERRIDE */}
      <div className="grid grid-cols-2 md:grid-cols-8 gap-2 items-end">
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Set</label>
          <input
            list={`gbr-sets-${card.SKU}`}
            value={curSet}
            onChange={(e) => onDraftChange({ ...draft, Set: e.target.value })}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
          />
          <datalist id={`gbr-sets-${card.SKU}`}>{dynamicSets.map((s) => <option key={s} value={s} />)}</datalist>
        </div>
        <div>
          <label className="block text-[10px] text-slate-400 mb-0.5">Card # (Auto-Fill)</label>
          <input
            value={curCnum}
            onChange={(e) => onDraftChange({ ...draft, Card_Number: e.target.value })}
            onBlur={(e) => handleExactCardNumAutofill(e.target.value, curSub)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleExactCardNumAutofill(e.currentTarget.value, curSub); }}
            className="w-full bg-slate-950 border border-sky-700/70 rounded-lg px-2 py-1.5 text-xs font-mono"
            placeholder="121"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Player</label>
          <input
            value={draft.Player || ''}
            onChange={(e) => onDraftChange({ ...draft, Player: e.target.value })}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-bold text-white"
          />
        </div>
        <div className="md:col-span-2">
          <div className="flex items-center justify-between gap-1 mb-0.5">
            <label className="block text-[10px] text-slate-400">Validated Subset / Parallel</label>
            <button
              type="button"
              disabled={savingOne}
              onClick={() => {
                setSavingOne(true);
                const basePayload = {
                  ...card,
                  ...draft,
                  SKU: card.SKU,
                  Subset_Parallel: 'Base',
                  Manual_Override: 'Base',
                  Print_Run: '',
                  Needs_Review: 'False',
                };
                onDraftChange(basePayload);
                Promise.resolve(onSaveOne(basePayload, { confirmOnly: false }))
                  .finally(() => {
                    setSavingOne(false);
                    setReviewTouched(false);
                  });
              }}
              title="Set this card to Base, clear Print Run, and save & rename immediately"
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold leading-none border transition disabled:opacity-40 ${
                String(curSub || '').trim().toUpperCase() !== 'BASE'
                  ? 'bg-emerald-950/90 hover:bg-emerald-600 border-emerald-500/80 text-emerald-200 hover:text-white shadow-sm'
                  : 'bg-slate-800/80 hover:bg-emerald-800/80 border-slate-700 text-slate-300 hover:text-white'
              }`}
            >
              {savingOne ? '...' : 'Base'}
            </button>
          </div>
          <input
            list={`gbr-subs-${card.SKU}`}
            value={curSub}
            onChange={(e) => onDraftChange({ ...draft, Subset_Parallel: e.target.value, Manual_Override: e.target.value })}
            onBlur={(e) => handleExactCardNumAutofill(curCnum, e.target.value)}
            className="w-full bg-slate-950 border border-sky-700 rounded-lg px-2 py-1.5 text-xs font-semibold text-sky-200"
          />
          <datalist id={`gbr-subs-${card.SKU}`}>{validSubsetsList.slice(0, 300).map((s) => <option key={s} value={s} />)}</datalist>
        </div>
        <div>
          <label className="block text-[10px] text-slate-400 mb-0.5">Team</label>
          <input
            value={draft.Team || ''}
            onChange={(e) => onDraftChange({ ...draft, Team: e.target.value })}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
          />
        </div>
        <div>
          <label className="block text-[10px] text-slate-400 mb-0.5">Print Run</label>
          <input
            value={draft.Print_Run || ''}
            onChange={(e) => onDraftChange({ ...draft, Print_Run: e.target.value })}
            placeholder="#/"
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono text-amber-300"
          />
        </div>
        <div>
          <label className="block text-[10px] text-slate-400 mb-0.5">Needs Review</label>
          <select
            value={String(draft.Needs_Review).toLowerCase() === 'true' ? 'True' : 'False'}
            onChange={(e) => { setReviewTouched(true); onDraftChange({ ...draft, Needs_Review: e.target.value, _reviewTouched: true }); }}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
          >
            <option value="False">✅ False</option>
            <option value="True">🚩 True</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <button
            type="button"
            disabled={savingOne}
            onClick={() => {
              setSavingOne(true);
              const isConfirmOnly = !hasFieldChanges && (!reviewTouched || String(draft.Needs_Review).toLowerCase() !== 'true');
              const finalNeedsRev = reviewTouched ? String(draft.Needs_Review || 'False') : 'False';
              const { _reviewTouched: _ignoredReviewTouched, ...cleanDraft } = draft || {};
              Promise.resolve(
                onSaveOne(
                  {
                    ...card,
                    ...cleanDraft,
                    SKU: card.SKU,
                    Needs_Review: isConfirmOnly ? 'False' : finalNeedsRev,
                    Manual_Override: isConfirmOnly ? '' : (cleanDraft.Subset_Parallel || curSub),
                  },
                  { confirmOnly: isConfirmOnly }
                )
              ).finally(() => {
                setSavingOne(false);
                setReviewTouched(false);
              });
            }}
            className={`w-full py-1.5 px-3 rounded-xl font-bold text-xs ${
              hasFieldChanges
                ? skin.accentBtn
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow'
            }`}
          >
            {savingOne
              ? (hasFieldChanges ? 'Saving...' : 'Confirming...')
              : hasFieldChanges
              ? (isDeepDive ? `💾 Save SKU ${card.SKU} & Next ▶` : `💾 Save SKU ${card.SKU} & Rename`)
              : (isDeepDive ? '✅ Confirm Correct & Next ▶' : `✅ Confirm SKU ${card.SKU} Correct`)}
          </button>
        </div>
      </div>
    </div>
  );
}

function InventoryGuidedCardItem({
  card,
  draft,
  skin,
  dynamicSets,
  onDraftChange,
  onSaveOne,
  onRotateSide,
  onReplaceImages,
  onReprocessOne,
  onOpenDeepDive,
  onAutoAssignPrice,
  externalImgBust = 0,
  isReprocessingExternal = false,
  imageHeightClass = 'h-48',
  isDeepDive = false,
}) {
  const [searchQ, setSearchQ] = useState('');
  const [lookupData, setLookupData] = useState({ subsets: ['Base'], matches: [] });
  const [savingOne, setSavingOne] = useState(false);
  const [reprocessingOne, setReprocessingOne] = useState(false);
  const [imgBust, setImgBust] = useState(0);
  const [showGradeFields, setShowGradeFields] = useState(isDeepDive);

  const curSet = draft.Set || '';
  const curSub = draft.Subset || 'Base';
  const curCnum = String(draft['Card Number'] || '').replace(/^#/, '');
  const tier = parseCardIdTier(card);
  const sFold = encodeURIComponent(sanitizeFolderName(card.Set || curSet));
  const combinedBust = imgBust + (externalImgBust || 0);
  const bustQ = combinedBust ? `?v=${combinedBust}` : '';
  const isReprocBusy = reprocessingOne || isReprocessingExternal;

  const hasFieldChanges = [
    'Set', 'Subset', 'Card Number', 'Player', 'Team', 'Print Run', 'Attributes',
    'Status', 'Hold_Tag', 'Raw_Price', 'Min_Sale_Price', 'Rec_Sale_Price',
    'Label_Printed', 'Needs_Review', 'Source_Batch',
    'Est_PSA', 'Est_BGS', 'Centering_LR', 'Centering_TB',
    'Sub_Centering', 'Sub_Corners', 'Sub_Edges', 'Sub_Surface', 'Grading_Notes',
  ].some((k) => String(draft[k] ?? '').trim() !== String(card[k] ?? '').trim());

  useEffect(() => {
    if (!curSet) return;
    let active = true;
    const timer = setTimeout(() => {
      const p = new URLSearchParams({ set: curSet, q: searchQ, limit: '45' });
      fetch(`${NODE_API_BASE}/checklists/lookup?${p.toString()}`)
        .then((r) => r.json())
        .then((d) => {
          if (active && d) {
            setLookupData({
              subsets: Array.isArray(d.subsets) && d.subsets.length > 0 ? d.subsets : ['Base'],
              matches: Array.isArray(d.matches) ? d.matches : [],
            });
          }
        })
        .catch(() => {});
    }, searchQ ? 180 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [curSet, searchQ]);

  const handleExactCardNumAutofill = (cnumVal, subVal = curSub) => {
    const cleanCn = String(cnumVal || '').trim().replace(/^#/, '');
    if (!curSet || !cleanCn) return;
    const p = new URLSearchParams({ set: curSet, cardNumber: cleanCn, subset: subVal || 'Base' });
    fetch(`${NODE_API_BASE}/checklists/lookup?${p.toString()}`)
      .then((r) => r.json())
      .then((d) => {
        if (d && d.exact && d.exact.player && d.exact.player !== 'Unknown Player') {
          onDraftChange({
            ...draft,
            'Card Number': d.exact.card_number || cleanCn,
            Player: d.exact.player,
            Team: d.exact.team || draft.Team || '',
            'Print Run': d.exact.print_run || '',
            Attributes: d.exact.attributes || draft.Attributes || '',
            Needs_Review: 'False',
          });
        }
      })
      .catch(() => {});
  };

  const candidatePills = useMemo(() => {
    const raw = String(card.Top_3_Template_Candidates || '').trim();
    if (!raw || raw.includes('(Locked)')) return [];
    return raw.split('|').map((seg) => {
      const s = seg.trim();
      const m = s.match(/^([^(]+)\((.+)\)$/);
      return m ? { name: m[1].trim(), detail: m[2].trim() } : null;
    }).filter(Boolean).slice(0, 4);
  }, [card.Top_3_Template_Candidates]);

  const validSubsetsList = useMemo(
    () => Array.from(new Set([curSub, ...(lookupData.subsets || []), 'Base'].filter(Boolean))),
    [curSub, lookupData.subsets]
  );

  return (
    <div className={`${skin.cardBg} border ${hasFieldChanges ? 'border-amber-500/70' : skin.border} rounded-2xl p-4 space-y-3`}>
      {/* CARD HEADER BAR */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-bold text-white">
          SKU <span className="font-mono text-sky-400">{card.SKU}</span> — {curSet} #{curCnum} {draft.Player} (<span className="text-amber-200">{curSub}</span>)
          {card.Copy_Number && <span className="ml-1.5 font-mono text-[10px] text-slate-400">Copy #{card.Copy_Number}</span>}
          {hasFieldChanges && <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-950 border border-amber-600 text-amber-200 text-[10px]">Unsaved Edit</span>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {onOpenDeepDive && (
            <button
              type="button"
              onClick={() => onOpenDeepDive(card.SKU)}
              title="Open this SKU in maximized single-card Deep-Dive mode"
              className="px-2 py-0.5 rounded-lg bg-indigo-950/90 hover:bg-indigo-800 border border-indigo-600/70 text-indigo-200 text-[10.5px] font-bold"
            >
              🔬 Deep-Dive
            </button>
          )}
          {onReprocessOne && (
            <button
              type="button"
              disabled={isReprocBusy}
              onClick={() => {
                setReprocessingOne(true);
                Promise.resolve(onReprocessOne(card.SKU, curSet))
                  .finally(() => setReprocessingOne(false));
              }}
              title="Re-scan physical Front & Back images in an available parallel worker and instantly update this card"
              className="px-2 py-0.5 rounded-lg bg-cyan-950/90 hover:bg-cyan-800 border border-cyan-600/70 text-cyan-200 text-[10.5px] font-bold disabled:opacity-50"
            >
              {isReprocBusy ? '⏳ Worker Running...' : '🔄 Reprocess'}
            </button>
          )}
          {card.Front_File && onRotateSide && (
            <button
              type="button"
              onClick={() => Promise.resolve(onRotateSide(card.Set, card.Front_File)).then(() => setImgBust((v) => v + 1))}
              title="Rotate Scan Front 90° clockwise on disk"
              className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[10.5px] font-semibold"
            >
              ↻ Front
            </button>
          )}
          {card.Back_File && onRotateSide && (
            <button
              type="button"
              onClick={() => Promise.resolve(onRotateSide(card.Set, card.Back_File)).then(() => setImgBust((v) => v + 1))}
              title="Rotate Scan Back 90° clockwise on disk"
              className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[10.5px] font-semibold"
            >
              ↻ Back
            </button>
          )}
          {onReplaceImages && (
            <button
              type="button"
              onClick={() => onReplaceImages(card)}
              title="Replace Front and/or Back scan images from files on your computer (JPG, PNG, or 2-Page PDF)"
              className="px-2 py-0.5 rounded-lg bg-emerald-950/90 hover:bg-emerald-800 border border-emerald-600/70 text-emerald-200 text-[10.5px] font-bold"
            >
              🖼️ Replace Scans
            </button>
          )}
          <span className={`px-2 py-0.5 rounded-lg border font-mono font-bold ${tier.badgeCls}`}>
            {tier.label} • OCR {tier.ocr}
          </span>
          <span className={`px-2 py-0.5 rounded-lg border font-mono font-bold ${tier.visBadgeCls}`} title={card.Top_3_Template_Candidates || 'Visual Match Confidence'}>
            👁️ Vis {tier.visPct !== null ? `${tier.visPct}%` : 'N/A'}
          </span>
          <span className="font-mono text-slate-400">PSA {draft.Est_PSA || '—'} / BGS {draft.Est_BGS || '—'}</span>
        </div>
      </div>

      {/* OCR SIGNALS + QUICK-PICK PARALLEL PILLS */}
      {(card.OCR_Signals || candidatePills.length > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px]">
          {card.OCR_Signals && (
            <div className="font-mono text-slate-400 truncate max-w-2xl" title={card.OCR_Signals}>
              Signals: {card.OCR_Signals}
            </div>
          )}
          {candidatePills.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-slate-400 mr-0.5">Quick-Pick Parallel:</span>
              {candidatePills.map((cp, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    onDraftChange({ ...draft, Subset: cp.name, Needs_Review: 'False' });
                    handleExactCardNumAutofill(curCnum, cp.name);
                  }}
                  className="px-2 py-0.5 rounded-md bg-sky-950/80 hover:bg-sky-800 border border-sky-700/70 text-sky-200 font-mono text-[10px]"
                >
                  {cp.name} ({cp.detail})
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* SIDE-BY-SIDE SCAN vs TCDB REFERENCE + 8-CORNER SHEET */}
      <SideBySideCardComparison
        scanFrontUrl={card.Front_File ? `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Front_File)}${bustQ}` : ''}
        scanBackUrl={card.Back_File ? `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Back_File)}${bustQ}` : ''}
        cornersUrl={card.Corners_File ? `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Corners_File)}${bustQ}` : ''}
        setName={curSet}
        subsetName={curSub}
        cardNumber={curCnum}
        initialTmplFrontRel={card.Matched_Template_Front}
        initialTmplBackRel={card.Matched_Template_Back}
        heightClass={imageHeightClass}
      />

      {/* CHECKLIST TYPE-AHEAD SEARCH & AUTOFILL BAR */}
      <div className="p-2.5 bg-slate-950/85 border border-sky-700/40 rounded-xl grid grid-cols-1 md:grid-cols-12 gap-2">
        <div className="md:col-span-4">
          <label className="block text-[10px] text-sky-300 font-bold mb-0.5">🔎 Search Card # or Player in {curSet || 'Checklist'}</label>
          <input
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Type #121, Player, Team..."
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs"
          />
        </div>
        <div className="md:col-span-8">
          <label className="block text-[10px] text-sky-300 font-bold mb-0.5">✨ Pick Checklist Match (Auto-Fills Card #, Player, Team, Subset, Print Run &amp; Attributes)</label>
          <select
            value=""
            onChange={(e) => {
              const idxPick = parseInt(e.target.value, 10);
              const m = lookupData.matches?.[idxPick];
              if (!m) return;
              const nextSub = m.subsets?.includes(curSub) ? curSub : (m.subsets?.includes('Base') ? 'Base' : (m.subsets?.[0] || 'Base'));
              onDraftChange({
                ...draft,
                'Card Number': m.cardNumber,
                Player: m.player,
                Team: m.team || draft.Team || '',
                Subset: nextSub,
                'Print Run': (m.printRuns && m.printRuns[nextSub]) || '',
                Attributes: m.attributes || draft.Attributes || '',
                Needs_Review: 'False',
              });
            }}
            className="w-full bg-slate-900 border border-sky-700/70 rounded-lg px-2.5 py-1.5 text-xs text-sky-200"
          >
            <option value="">-- Select from {(lookupData.matches || []).length} matching card(s) in {curSet || 'Checklist'} --</option>
            {(lookupData.matches || []).map((m, i) => (
              <option key={`${m.cardNumber}-${m.player}-${i}`} value={i}>
                #{m.cardNumber} — {m.player}{m.attributes ? ` [${m.attributes}]` : ''} ({m.team}) [{(m.subsets || []).length} parallel(s)]
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ROW 1: CORE IDENTITY FIELDS (WITH 1-CLICK BASE AUTO-SAVE PILL) */}
      <div className="grid grid-cols-2 md:grid-cols-12 gap-2 items-end">
        <div className="md:col-span-3">
          <label className="block text-[10px] text-slate-400 mb-0.5">Set</label>
          <input list={`inv-g-sets-${card.SKU}`} value={curSet} onChange={(e) => onDraftChange({ ...draft, Set: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" />
          <datalist id={`inv-g-sets-${card.SKU}`}>{dynamicSets.map((s) => <option key={s} value={s} />)}</datalist>
        </div>
        <div className="md:col-span-1">
          <label className="block text-[10px] text-slate-400 mb-0.5">Card #</label>
          <input
            value={curCnum}
            onChange={(e) => onDraftChange({ ...draft, 'Card Number': e.target.value })}
            onBlur={(e) => handleExactCardNumAutofill(e.target.value, curSub)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleExactCardNumAutofill(e.currentTarget.value, curSub); }}
            className="w-full bg-slate-950 border border-sky-700/70 rounded-lg px-2 py-1.5 text-xs font-mono"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Player</label>
          <input value={draft.Player || ''} onChange={(e) => onDraftChange({ ...draft, Player: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-bold text-white" />
        </div>
        <div className="md:col-span-3">
          <div className="flex items-center justify-between gap-1 mb-0.5">
            <label className="block text-[10px] text-slate-400">Validated Subset / Parallel</label>
            <button
              type="button"
              disabled={savingOne}
              onClick={() => {
                setSavingOne(true);
                const basePayload = { ...card, ...draft, Subset: 'Base', 'Print Run': '', Needs_Review: 'False' };
                onDraftChange(basePayload);
                Promise.resolve(onSaveOne(basePayload)).finally(() => setSavingOne(false));
              }}
              title="Set Subset to Base, clear Print Run, and save & rename immediately"
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold leading-none border transition disabled:opacity-40 ${
                String(curSub || '').trim().toUpperCase() !== 'BASE'
                  ? 'bg-emerald-950/90 hover:bg-emerald-600 border-emerald-500/80 text-emerald-200 hover:text-white'
                  : 'bg-slate-800/80 hover:bg-emerald-800/80 border-slate-700 text-slate-300'
              }`}
            >
              Base
            </button>
          </div>
          <input
            list={`inv-g-subs-${card.SKU}`}
            value={curSub}
            onChange={(e) => onDraftChange({ ...draft, Subset: e.target.value })}
            onBlur={(e) => handleExactCardNumAutofill(curCnum, e.target.value)}
            className="w-full bg-slate-950 border border-sky-700 rounded-lg px-2 py-1.5 text-xs font-semibold text-sky-200"
          />
          <datalist id={`inv-g-subs-${card.SKU}`}>{validSubsetsList.slice(0, 300).map((s) => <option key={s} value={s} />)}</datalist>
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Team</label>
          <input value={draft.Team || ''} onChange={(e) => onDraftChange({ ...draft, Team: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" />
        </div>
        <div className="md:col-span-1">
          <label className="block text-[10px] text-slate-400 mb-0.5">Print Run</label>
          <input value={draft['Print Run'] || ''} onChange={(e) => onDraftChange({ ...draft, 'Print Run': e.target.value })} placeholder="#/" className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono text-amber-300" />
        </div>
      </div>

      {/* ROW 2: INVENTORY STATUS, ATTRIBUTES, PRICING & LABEL FIELDS */}
      <div className="grid grid-cols-2 md:grid-cols-12 gap-2 items-end">
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Attributes</label>
          <input value={draft.Attributes || ''} onChange={(e) => onDraftChange({ ...draft, Attributes: e.target.value })} placeholder="RC, ASR..." className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono text-sky-200" />
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Status</label>
          <select value={draft.Status || 'In Stock'} onChange={(e) => onDraftChange({ ...draft, Status: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs">
            <option>In Stock</option><option>Listed</option><option>Grading</option><option>Sold</option><option>PC / Hold</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Hold Tag</label>
          <select value={draft.Hold_Tag || 'For Sale'} onChange={(e) => onDraftChange({ ...draft, Hold_Tag: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs">
            <option>For Sale</option><option>Make Me an Offer</option><option>Personal Collection (PC)</option>
          </select>
        </div>
        <div className="md:col-span-1">
          <label className="block text-[10px] text-slate-400 mb-0.5">Raw ($)</label>
          <input type="number" step="0.25" value={draft.Raw_Price ?? ''} onChange={(e) => onDraftChange({ ...draft, Raw_Price: e.target.value, Valuation_Source: String(e.target.value || '').trim() ? 'Manual' : 'Uncomped' })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" />
        </div>
        <div className="md:col-span-2">
          <label className="block text-[10px] text-slate-400 mb-0.5">Sale Price ($)</label>
          <div className="flex items-center gap-1">
            <input type="number" step="0.25" value={draft.Rec_Sale_Price ?? ''} onChange={(e) => onDraftChange({ ...draft, Rec_Sale_Price: e.target.value })} className="flex-1 min-w-0 bg-slate-950 border border-emerald-700/70 rounded-lg px-2 py-1.5 text-xs font-mono text-emerald-300 font-bold" />
            {onAutoAssignPrice && (
              <button type="button" onClick={() => onDraftChange({ ...draft, Rec_Sale_Price: onAutoAssignPrice(draft) })} title="Auto-calculate Recommended Sale Price" className="px-2 py-1.5 rounded-lg bg-amber-950 hover:bg-amber-800 border border-amber-700/70 text-amber-200 text-xs">✨</button>
            )}
          </div>
        </div>
        <div className="md:col-span-1">
          <label className="block text-[10px] text-slate-400 mb-0.5">Label?</label>
          <select value={String(draft.Label_Printed).toLowerCase() === 'true' ? 'True' : 'False'} onChange={(e) => onDraftChange({ ...draft, Label_Printed: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-1.5 py-1.5 text-xs">
            <option value="False">No</option><option value="True">✅ Yes</option>
          </select>
        </div>
        <div className="md:col-span-2">
          <button
            type="button"
            disabled={savingOne}
            onClick={() => {
              setSavingOne(true);
              const preservedNeedsRev = String(draft.Needs_Review ?? card.Needs_Review ?? 'False').toLowerCase() === 'true' ? 'True' : 'False';
              Promise.resolve(onSaveOne({ ...card, ...draft, 'Card Number': String(draft['Card Number'] || '').replace(/^#/, ''), Needs_Review: preservedNeedsRev }))
                .finally(() => setSavingOne(false));
            }}
            className={`w-full py-1.5 px-3 rounded-xl font-bold text-xs ${hasFieldChanges ? skin.accentBtn : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow'}`}
          >
            {savingOne
              ? 'Saving...'
              : hasFieldChanges
              ? (isDeepDive ? `💾 Save SKU ${card.SKU} & Next ▶` : `💾 Save SKU ${card.SKU} & Rename`)
              : (isDeepDive ? '✅ Confirm & Next ▶' : `✅ Confirm SKU ${card.SKU}`)}
          </button>
        </div>
      </div>

      {/* ROW 3: COLLAPSIBLE GRADING, SUBGRADES, BATCH & NOTES FIELDS */}
      <div className="pt-1 border-t border-slate-800/80 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px]">
          <button
            type="button"
            onClick={() => setShowGradeFields((v) => !v)}
            className="text-sky-300 hover:text-sky-200 font-bold"
          >
            {showGradeFields ? '▲ Hide Grading, Centering, Batch & Notes Fields' : '▼ Edit Grading, Subgrades, Centering, Batch & Notes Fields'}
          </button>
          <div className="flex flex-wrap items-center gap-2 font-mono text-slate-400">
            <span>Min: {fmtCurrency(draft.Min_Sale_Price)}</span>
            <span>•</span>
            <span>Action: <span className="text-sky-300">{card.Recommended_Action || '—'}</span></span>
            <span>•</span>
            <span>Batch: {draft.Source_Batch || '—'}</span>
            {card.Date_Added && <><span>•</span><span>Added: {card.Date_Added}</span></>}
          </div>
        </div>
        {showGradeFields && (
          <div className="grid grid-cols-2 md:grid-cols-12 gap-2 pt-1">
            <div className="md:col-span-1"><label className="block text-[10px] text-slate-400 mb-0.5">Est PSA</label><input value={draft.Est_PSA ?? ''} onChange={(e) => onDraftChange({ ...draft, Est_PSA: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-1"><label className="block text-[10px] text-slate-400 mb-0.5">Est BGS</label><input value={draft.Est_BGS ?? ''} onChange={(e) => onDraftChange({ ...draft, Est_BGS: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-2"><label className="block text-[10px] text-slate-400 mb-0.5">Centering L/R</label><input value={draft.Centering_LR ?? ''} onChange={(e) => onDraftChange({ ...draft, Centering_LR: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-2"><label className="block text-[10px] text-slate-400 mb-0.5">Centering T/B</label><input value={draft.Centering_TB ?? ''} onChange={(e) => onDraftChange({ ...draft, Centering_TB: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-1"><label className="block text-[10px] text-slate-400 mb-0.5">Sub Cent</label><input value={draft.Sub_Centering ?? ''} onChange={(e) => onDraftChange({ ...draft, Sub_Centering: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-1"><label className="block text-[10px] text-slate-400 mb-0.5">Sub Corn</label><input value={draft.Sub_Corners ?? ''} onChange={(e) => onDraftChange({ ...draft, Sub_Corners: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-1"><label className="block text-[10px] text-slate-400 mb-0.5">Sub Edge</label><input value={draft.Sub_Edges ?? ''} onChange={(e) => onDraftChange({ ...draft, Sub_Edges: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-1"><label className="block text-[10px] text-slate-400 mb-0.5">Sub Surf</label><input value={draft.Sub_Surface ?? ''} onChange={(e) => onDraftChange({ ...draft, Sub_Surface: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-2"><label className="block text-[10px] text-slate-400 mb-0.5">Needs Review</label><select value={String(draft.Needs_Review).toLowerCase() === 'true' ? 'True' : 'False'} onChange={(e) => onDraftChange({ ...draft, Needs_Review: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs"><option value="False">✅ False</option><option value="True">🚩 True</option></select></div>
            <div className="md:col-span-3"><label className="block text-[10px] text-slate-400 mb-0.5">Source Batch</label><input value={draft.Source_Batch ?? ''} onChange={(e) => onDraftChange({ ...draft, Source_Batch: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
            <div className="md:col-span-9">
              <label className="flex items-center gap-2 text-[10px] text-slate-400 mb-0.5">
                <span>Grading &amp; Inspection Notes</span>
                {String(draft.Grading_Notes || '').includes('[Sleeve/Dust Check]') && (
                  <span className="px-1.5 py-0.5 rounded-full bg-amber-950/90 border border-amber-500/60 text-amber-300 text-[9px] font-bold">
                    🧹 Holder Dust / Glare Suspected — Verify Before Penalizing
                  </span>
                )}
                {/(?:Surface:|scratch|print line|dimple|fisheye|edge chipping|corner whitening)/i.test(String(draft.Grading_Notes || '')) && (
                  <span className="px-1.5 py-0.5 rounded-full bg-rose-950/90 border border-rose-500/60 text-rose-300 text-[9px] font-bold">
                    🔍 Confirmed Defect
                  </span>
                )}
              </label>
              <input value={draft.Grading_Notes ?? ''} onChange={(e) => onDraftChange({ ...draft, Grading_Notes: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function renderGradingNotesWithBadges(notes) {
  const txt = String(notes || '').trim();
  const hasSleeveWarn = txt.includes('[Sleeve/Dust Check]');
  const hasDefect = /(?:Surface:|scratch|print line|dimple|fisheye|edge chipping|corner whitening)/i.test(txt);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {hasSleeveWarn && (
        <span className="px-2 py-0.5 rounded-full bg-amber-950/90 border border-amber-500/60 text-amber-300 text-[10px] font-bold">
          🧹 Holder Dust / Glare Suspected — Verify Before Penalizing
        </span>
      )}
      {hasDefect && (
        <span className="px-2 py-0.5 rounded-full bg-rose-950/90 border border-rose-500/60 text-rose-300 text-[10px] font-bold">
          🔍 Confirmed Defect
        </span>
      )}
      <span>{txt || 'No defects noted.'}</span>
    </span>
  );
}

const CHART_DONUT_COLORS = ['#06b6d4', '#10b981', '#f59e0b', '#a855f7', '#f43f5e', '#3b82f6', '#ec4899', '#84cc16', '#94a3b8'];

function SvgDonutChart({ data = [], centerLabel = '', centerSub = '' }) {
  const total = data.reduce((acc, d) => acc + Math.max(0, Number(d.value) || 0), 0);
  if (total <= 0) {
    return <div className="py-8 text-center text-xs text-slate-500">No in-stock card data yet.</div>;
  }
  const r = 42;
  const circ = 2 * Math.PI * r;
  let offsetAcc = 0;

  return (
    <div className="flex flex-col sm:flex-row items-center gap-4">
      <div className="relative w-36 h-36 shrink-0">
        <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
          <circle cx="60" cy="60" r={r} fill="none" stroke="#1e293b" strokeWidth="16" />
          {data.map((d, i) => {
            const frac = Math.max(0, Number(d.value) || 0) / total;
            const dash = frac * circ;
            const segOffset = offsetAcc;
            offsetAcc += dash;
            return (
              <circle
                key={`${d.label}-${i}`}
                cx="60"
                cy="60"
                r={r}
                fill="none"
                stroke={CHART_DONUT_COLORS[i % CHART_DONUT_COLORS.length]}
                strokeWidth="16"
                strokeDasharray={`${dash} ${circ - dash}`}
                strokeDashoffset={-segOffset}
              >
                <title>{`${d.label}: ${Number(d.value).toLocaleString()} (${(frac * 100).toFixed(1)}%)`}</title>
              </circle>
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-sm font-extrabold text-white font-mono">{centerLabel || total.toLocaleString()}</span>
          {centerSub && <span className="text-[9.5px] text-slate-400 uppercase">{centerSub}</span>}
        </div>
      </div>
      <div className="flex-1 min-w-0 w-full space-y-1.5 text-[11px] max-h-40 overflow-y-auto pr-1">
        {data.map((d, i) => {
          const pct = ((Math.max(0, Number(d.value) || 0) / total) * 100).toFixed(1);
          return (
            <div key={`${d.label}-${i}`} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 min-w-0">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: CHART_DONUT_COLORS[i % CHART_DONUT_COLORS.length] }} />
                <span className="text-slate-200 truncate" title={d.label}>{d.label}</span>
              </span>
              <span className="font-mono text-slate-300 shrink-0">{Number(d.value).toLocaleString()} <span className="text-slate-500">({pct}%)</span></span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

class TabulasErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }
  static getDerivedStateFromError(err) {
    return { hasError: true, errorMessage: String(err?.message || err || 'Unknown UI error') };
  }
  componentDidUpdate(prevProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, errorMessage: '' });
    }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-slate-900 border border-rose-500/60 rounded-2xl p-6 space-y-3 max-w-2xl mx-auto my-8 text-xs shadow-2xl">
          <div className="text-sm font-bold text-rose-300">⚠️ Page Render Error Caught</div>
          <div className="font-mono text-rose-200 bg-slate-950 border border-slate-800 rounded-xl p-3 break-words">
            {this.state.errorMessage}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                this.setState({ hasError: false, errorMessage: '' });
                if (this.props.onReset) this.props.onReset();
              }}
              className="px-3.5 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-bold"
            >
              🔄 Recover &amp; Return to Home Dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function ReplaceCardImagesModal({ target, skin, onClose, onReplaced }) {
  const [pdfFile, setPdfFile] = useState(null);
  const [frontFile, setFrontFile] = useState(null);
  const [backFile, setBackFile] = useState(null);
  const [autoOrient, setAutoOrient] = useState(true);
  const [regradeToo, setRegradeToo] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState('');

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !submitting) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [submitting, onClose]);

  const readFileAsDataUrl = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({ name: file.name, sizeKb: Math.round(file.size / 1024), dataUrl: String(reader.result || ''), isPdf: file.name.toLowerCase().endsWith('.pdf') });
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
      reader.readAsDataURL(file);
    });

  const handlePickPdf = (file) => {
    if (!file) return;
    setErrMsg('');
    readFileAsDataUrl(file).then((info) => {
      setPdfFile(info);
      setFrontFile(null);
      setBackFile(null);
    }).catch((e) => setErrMsg(e.message));
  };

  const handlePickSide = (side, file) => {
    if (!file) return;
    setErrMsg('');
    readFileAsDataUrl(file).then((info) => {
      setPdfFile(null);
      if (side === 'front') setFrontFile(info);
      else setBackFile(info);
    }).catch((e) => setErrMsg(e.message));
  };

  const canSubmit = !submitting && Boolean(pdfFile || frontFile || backFile);

  const handleSubmit = () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setErrMsg('');
    const endpoint = target.type === 'inventory' ? `${NODE_API_BASE}/inventory/replace-images` : `${NODE_API_BASE}/batches/replace-images`;
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sku: target.sku,
        batchName: target.batchName || '',
        pdfBase64: pdfFile?.dataUrl || '',
        pdfFileName: pdfFile?.name || '',
        frontBase64: frontFile?.dataUrl || '',
        frontFileName: frontFile?.name || '',
        backBase64: backFile?.dataUrl || '',
        backFileName: backFile?.name || '',
        autoOrient,
        regradeToo,
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          onReplaced(res);
          onClose();
        } else {
          setErrMsg(res?.error || 'Failed to replace card images.');
        }
      })
      .catch((e) => setErrMsg(e.message || 'Network error replacing images.'))
      .finally(() => setSubmitting(false));
  };

  const cardLabel = `${target.set || ''} #${String(target.cardNumber || '').replace(/^#/, '')} ${target.player || ''} (${target.subset || 'Base'})`;

  return (
    <div
      onClick={() => { if (!submitting) onClose(); }}
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-2xl ${skin.cardBg} border ${skin.border} rounded-2xl shadow-2xl p-5 space-y-4 text-xs`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="min-w-0">
            <div className="text-[10.5px] font-mono text-cyan-300 uppercase">
              🖼️ Replace Card Scan Images — {target.type === 'inventory' ? 'Master Inventory (_My_Collection)' : `Uncommitted Batch (${target.batchName})`}
            </div>
            <h3 className="text-sm font-extrabold text-white truncate mt-0.5">
              SKU {target.sku} — {cardLabel}
            </h3>
          </div>
          <button type="button" disabled={submitting} onClick={onClose} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300">✖</button>
        </div>

        {/* OPTION A: INDIVIDUAL FRONT & BACK IMAGE PICKERS */}
        <div className="space-y-1.5">
          <div className="text-[11px] font-bold text-white">Option 1: Select Individual Front and/or Back Image Files (JPG, PNG, WEBP, BMP, TIFF, or 1-Page PDF)</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              { side: 'front', title: 'New Front Image (_F)', state: frontFile, clear: () => setFrontFile(null) },
              { side: 'back', title: 'New Back Image (_B)', state: backFile, clear: () => setBackFile(null) },
            ].map(({ side, title, state, clear }) => (
              <div
                key={side}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer?.files?.[0]; if (f) handlePickSide(side, f); }}
                className={`p-3 rounded-xl border border-dashed transition flex flex-col items-center justify-between gap-2 min-h-[168px] ${
                  state ? 'border-emerald-500/70 bg-emerald-950/20' : 'border-slate-700 bg-slate-950/75 hover:border-cyan-500/60'
                }`}
              >
                <div className="w-full flex items-center justify-between text-[11px]">
                  <span className="font-bold text-slate-200">{title}</span>
                  {state && (
                    <button type="button" onClick={clear} className="text-[10px] text-rose-400 hover:text-rose-200 font-semibold">Clear</button>
                  )}
                </div>

                {state ? (
                  <div className="flex flex-col items-center gap-1.5 w-full">
                    {!state.isPdf ? (
                      <img src={state.dataUrl} alt={title} className="h-24 w-auto object-contain rounded border border-slate-700" />
                    ) : (
                      <div className="h-24 flex items-center justify-center text-sky-300 font-mono text-xs">📄 PDF Ready</div>
                    )}
                    <div className="text-[10px] font-mono text-emerald-300 truncate max-w-full" title={state.name}>
                      {state.name} ({state.sizeKb.toLocaleString()} KB)
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] text-slate-500 text-center py-4">
                    Drag &amp; drop a file here<br />or browse your computer
                  </div>
                )}

                <label className="w-full text-center py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-200 font-semibold cursor-pointer">
                  {state ? 'Change File...' : `📂 Browse ${side === 'front' ? 'Front' : 'Back'}...`}
                  <input
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.pdf"
                    className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePickSide(side, f); e.target.value = ''; }}
                  />
                </label>
              </div>
            ))}
          </div>
        </div>

        {/* OPTION B: SINGLE 2-PAGE SCANNER PDF (REPLACES BOTH FRONT & BACK IN ONE PICK) */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer?.files?.[0]; if (f) handlePickPdf(f); }}
          className={`p-3 rounded-xl border border-dashed transition flex flex-wrap items-center justify-between gap-2.5 ${
            pdfFile ? 'border-emerald-500/70 bg-emerald-950/20' : 'border-slate-700 bg-slate-950/75 hover:border-cyan-500/60'
          }`}
        >
          <div className="min-w-0">
            <div className="text-[11px] font-bold text-amber-300">Option 2: Replace Both Sides from a Single 2-Page Scanner PDF</div>
            <div className="text-[10.5px] text-slate-400">
              {pdfFile
                ? <span className="font-mono text-emerald-300">📄 {pdfFile.name} ({pdfFile.sizeKb.toLocaleString()} KB) — Page 1 = Front, Page 2 = Back</span>
                : 'Drop or pick a fresh 2-page PDF scan from your Ricoh / flatbed scanner to replace both Front & Back at once.'}
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {pdfFile && (
              <button type="button" onClick={() => setPdfFile(null)} className="px-2 py-1 rounded-lg bg-rose-950/80 text-rose-200 text-[11px]">Clear</button>
            )}
            <label className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-200 font-bold cursor-pointer">
              📂 Browse 2-Page PDF...
              <input
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePickPdf(f); e.target.value = ''; }}
              />
            </label>
          </div>
        </div>

        {/* OPTIONS + FOOTER ACTIONS */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-800">
          <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-300">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={autoOrient} onChange={(e) => setAutoOrient(e.target.checked)} />
              Auto-orient upright
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={regradeToo} onChange={(e) => setRegradeToo(e.target.checked)} />
              Rebuild 8-Corner Sheet &amp; Re-Grade
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" disabled={submitting} onClick={onClose} className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold">
              Cancel
            </button>
            <button
              type="button"
              disabled={!canSubmit}
              onClick={handleSubmit}
              className={`px-4 py-2 rounded-xl font-bold disabled:opacity-40 ${skin.accentBtn}`}
            >
              {submitting ? '⏳ Replacing & Re-Grading...' : '💾 Replace Images & Update Card'}
            </button>
          </div>
        </div>

        {errMsg && (
          <div className="p-2.5 rounded-xl bg-rose-950/80 border border-rose-600/70 text-rose-200 text-[11px] font-semibold">
            ❌ {errMsg}
          </div>
        )}
      </div>
    </div>
  );
}

function FlagGradingErrorModal({
  card,
  targetType,
  batchName,
  diagnostics,
  initialSide,
  initialTargetItemId,
  skin,
  onClose,
  onSubmitted,
}) {
  const [errorType, setErrorType] = useState(initialTargetItemId ? 'not_a_defect_artwork' : 'centering_sleeve_rim');
  const [side, setSide] = useState(initialSide || 'Front');
  const [targetItemId, setTargetItemId] = useState(initialTargetItemId || '');
  const [manualCat, setManualCat] = useState('surface');
  const [manualType, setManualType] = useState('surface_scratch');
  const [manualSeverity, setManualSeverity] = useState('0.5');
  const [manualZone, setManualZone] = useState('mid-center');
  const [targetSubgrade, setTargetSubgrade] = useState('surface');
  const [correctedScore, setCorrectedScore] = useState('9.5');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState('');

  const confirmedDefects = Array.isArray(diagnostics?.confirmed_defects) ? diagnostics.confirmed_defects : [];
  const superficialArtifacts = Array.isArray(diagnostics?.superficial_artifacts) ? diagnostics.superficial_artifacts : [];
  const ov = diagnostics?.overrides || {};
  const hasActiveOverrides = Boolean(
    (ov.dismissed_defect_ids && ov.dismissed_defect_ids.length > 0) ||
    (ov.manual_defects && ov.manual_defects.length > 0) ||
    Number(ov.sleeve_inset_pct || 0) > 0 ||
    Boolean(ov.light_border_mode) ||
    (ov.subgrade_overrides && Object.keys(ov.subgrade_overrides).length > 0)
  );

  const submitFlag = (overridePayload = null) => {
    setSubmitting(true);
    setErrMsg('');
    const bodyPayload = overridePayload || {
      targetType,
      sku: card?.SKU || '',
      batchName: batchName || card?._BatchName || '',
      errorType,
      side,
      targetItemId,
      manualDefect: errorType === 'missed_real_defect' ? {
        category: manualCat,
        type: manualType,
        severity: parseFloat(manualSeverity) || 0.5,
        zone: manualZone,
      } : null,
      targetSubgrade: errorType === 'subgrade_calibration' ? targetSubgrade : '',
      correctedScore: errorType === 'subgrade_calibration' ? (parseFloat(correctedScore) || 9.5) : null,
      notes,
    };
    fetch(`${NODE_API_BASE}/grading/flag-error`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyPayload),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          onSubmitted(res);
          onClose();
        } else {
          setErrMsg(res?.error || 'Failed to apply grading feedback.');
        }
      })
      .catch((e) => setErrMsg(e.message || 'Network error submitting grading feedback.'))
      .finally(() => setSubmitting(false));
  };

  return (
    <div
      onClick={() => { if (!submitting) onClose(); }}
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-xl ${skin.cardBg} border ${skin.border} rounded-2xl shadow-2xl p-5 space-y-4 text-xs`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="min-w-0">
            <div className="text-[10.5px] font-mono text-rose-300 uppercase">🚩 Flag Grading Assessment Error</div>
            <h3 className="text-sm font-extrabold text-white truncate mt-0.5">
              SKU {card?.SKU} — {card?.Set} #{String(card?.['Card Number'] || card?.Card_Number || '').replace(/^#/, '')} {card?.Player}
            </h3>
          </div>
          <button type="button" onClick={() => !submitting && onClose()} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold">✕</button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="md:col-span-2">
            <label className="block text-[11px] font-bold text-slate-300 mb-1">Error Category</label>
            <select value={errorType} onChange={(e) => setErrorType(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
              <option value="not_a_defect_artwork">Not a defect — part of card artwork / photo (e.g., uniform stripe, text, pattern)</option>
              <option value="centering_sleeve_rim">Centering measured from penny sleeve / holder rim</option>
              <option value="false_positive_artifact">Hair / dust / glare misclassified as real defect</option>
              <option value="scanner_streak">Scanner glass / sensor streak misclassified as scratch / print line</option>
              <option value="false_light_border">False edge / corner whitening on light border</option>
              <option value="missed_real_defect">Missed real defect (add penalty)</option>
              <option value="subgrade_calibration">Subgrade calibration mismatch</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-300 mb-1">Card Side</label>
            <select value={side} onChange={(e) => setSide(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
              <option value="Front">Front</option>
              <option value="Back">Back</option>
              <option value="Both">Both Sides</option>
            </select>
          </div>

          {(errorType === 'not_a_defect_artwork' || errorType === 'false_positive_artifact' || errorType === 'false_light_border' || errorType === 'scanner_streak') && (
            <div>
              <label className="block text-[11px] font-bold text-slate-300 mb-1">Target Detected Item</label>
              <select value={targetItemId} onChange={(e) => setTargetItemId(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
                <option value="">All matching on {side}</option>
                {confirmedDefects.map((d) => (
                  <option key={d.id} value={d.id}>{d.label || d.id} (-{Number(d.penalty ?? d.severity ?? 0.5).toFixed(1)})</option>
                ))}
                {superficialArtifacts.map((a) => (
                  <option key={a.id} value={a.id}>[Ignored] {a.label || a.id}</option>
                ))}
              </select>
            </div>
          )}

          {errorType === 'missed_real_defect' && (
            <>
              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1">Defect Category</label>
                <select value={manualCat} onChange={(e) => setManualCat(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
                  <option value="surface">Surface</option>
                  <option value="corners">Corners</option>
                  <option value="edges">Edges</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1">Defect Type</label>
                <select value={manualType} onChange={(e) => setManualType(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
                  <option value="surface_scratch">Surface Scratch</option>
                  <option value="print_line">Print Line</option>
                  <option value="dimple_dent">Dimple / Dent</option>
                  <option value="print_spot_fisheye">Print Spot / Fisheye</option>
                  <option value="corner_whitening">Corner Whitening / Softness</option>
                  <option value="edge_chipping">Edge Chipping / Wear</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1">Penalty Severity</label>
                <select value={manualSeverity} onChange={(e) => setManualSeverity(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
                  <option value="0.5">Minor (-0.5)</option>
                  <option value="1.0">Moderate (-1.0)</option>
                  <option value="1.5">Major (-1.5)</option>
                  <option value="2.0">Severe (-2.0)</option>
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-[11px] font-bold text-slate-300 mb-1">Location / Zone</label>
                <input value={manualZone} onChange={(e) => setManualZone(e.target.value)} placeholder="e.g., Top-Right, mid-center, Left edge" className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white" />
              </div>
            </>
          )}

          {errorType === 'subgrade_calibration' && (
            <>
              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1">Subgrade</label>
                <select value={targetSubgrade} onChange={(e) => setTargetSubgrade(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
                  <option value="centering">Centering</option>
                  <option value="corners">Corners</option>
                  <option value="edges">Edges</option>
                  <option value="surface">Surface</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1">Corrected Score</label>
                <select value={correctedScore} onChange={(e) => setCorrectedScore(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white">
                  {['10.0','9.5','9.0','8.5','8.0','7.5','7.0','6.5','6.0','5.5','5.0'].map((sc) => (
                    <option key={sc} value={sc}>{sc}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          <div className="md:col-span-2">
            <label className="block text-[11px] font-bold text-slate-300 mb-1">Inspector Notes (logged for model tuning)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Describe what was misread (e.g. glare streak on top loader, white card border, etc.)..." className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white" />
          </div>
        </div>

        {errMsg && (
          <div className="p-2.5 rounded-xl bg-rose-950/80 border border-rose-600/70 text-rose-200 text-[11px] font-semibold">❌ {errMsg}</div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800">
          <div>
            {hasActiveOverrides && (
              <button
                type="button"
                disabled={submitting}
                onClick={() => submitFlag({
                  targetType,
                  sku: card?.SKU || '',
                  batchName: batchName || card?._BatchName || '',
                  errorType: 'reset_overrides',
                  resetOverrides: true,
                })}
                className="px-3 py-1.5 rounded-xl bg-amber-950/80 hover:bg-amber-900 border border-amber-600/70 text-amber-200 font-bold"
              >
                ♻️ Reset Overrides
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" disabled={submitting} onClick={onClose} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold">Cancel</button>
            <button type="button" disabled={submitting} onClick={() => submitFlag(null)} className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold shadow">
              {submitting ? '⏳ Re-Evaluating...' : '🚩 Submit & Re-Evaluate Grade'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function GradingDeepDiveStudio({
  card,
  targetType = 'inventory',
  batchName = '',
  cardIndex = 0,
  totalCards = 1,
  onPrev,
  onNext,
  onBack,
  backLabel = 'Back',
  onSwitchIndividual,
  onSwitchBulk,
  cardOptions,
  onSelectCardIndex,
  onCardUpdated,
  skin,
  pushNotification,
}) {
  const [activeSide, setActiveSide] = useState('Front');
  const [diagnostics, setDiagnostics] = useState(null);
  const [loadingDiag, setLoadingDiag] = useState(false);
  const [diagError, setDiagError] = useState('');
  const [activeLayers, setActiveLayers] = useState({ centering: true, corners: true, edges: true, surface: true });
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [isolatedDefectId, setIsolatedDefectId] = useState('');
  const [loupeZoom, setLoupeZoom] = useState(1.0);
  const [showFlagModal, setShowFlagModal] = useState(false);
  const [flagPresetId, setFlagPresetId] = useState('');
  const [naturalSize, setNaturalSize] = useState({ w: 1500, h: 2100 });
  const canvasWrapRef = useRef(null);
  const svgRef = useRef(null);
  const [fittedBox, setFittedBox] = useState({ w: 340, h: 476 });

  // Main Card Zoom & Pan
  const [mainZoom, setMainZoom] = useState(1.0);
  const [mainPan, setMainPan] = useState({ x: 0, y: 0 });
  const panDragRef = useRef(null);

  // Interactive Geometry Edit Modes ('none' | 'centering' | 'corners')
  const [editMode, setEditMode] = useState('none');
  const [draftOuter, setDraftOuter] = useState(null);
  const [draftInner, setDraftInner] = useState(null);
  const [draftCorners, setDraftCorners] = useState(null);
  const [savingGeom, setSavingGeom] = useState(false);
  const geomDragRef = useRef(null);

  // Virtual Clear Centering Card Overlay (Legends-style transparent centering tool)
  const [showCenteringGauge, setShowCenteringGauge] = useState(false);
  const [gaugeOpacity, setGaugeOpacity] = useState(80);
  const [gaugeRotate, setGaugeRotate] = useState(0.0);
  const [gaugeNudge, setGaugeNudge] = useState({ x: 0, y: 0 });
  const [gaugeFormatOverride, setGaugeFormatOverride] = useState('auto'); // 'auto' | 'standard' | 'mini'
  const [gaugeColorMode, setGaugeColorMode] = useState('contrast'); // 'contrast' | 'classic_black' | 'cyan'
  const [showLegendsChart, setShowLegendsChart] = useState(false);

  const sku = String(card?.SKU || '').trim();
  const effectiveBatch = batchName || card?._BatchName || '';

  const fetchDiagnostics = (forceRecompute = false) => {
    if (!sku) return;
    setLoadingDiag(true);
    setDiagError('');
    fetch(`${NODE_API_BASE}/grading/inspect-card`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targetType, sku, batchName: effectiveBatch, forceRecompute }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success && res.diagnostics) {
          setDiagnostics(res.diagnostics);
          if (res.card && onCardUpdated) onCardUpdated(res);
        } else {
          setDiagError(res?.error || 'Could not load grading diagnostics.');
        }
      })
      .catch((e) => setDiagError(e.message || 'Failed to inspect card diagnostics.'))
      .finally(() => setLoadingDiag(false));
  };

  useEffect(() => {
    setIsolatedDefectId('');
    setEditMode('none');
    setMainZoom(1.0);
    setMainPan({ x: 0, y: 0 });
    setGaugeRotate(0.0);
    setGaugeNudge({ x: 0, y: 0 });
    setGaugeFormatOverride('auto');
    setDiagnostics(null);
    fetchDiagnostics(false);
  }, [sku, targetType, effectiveBatch]);

  useEffect(() => {
    setIsolatedDefectId('');
    setEditMode('none');
    setMainZoom(1.0);
    setMainPan({ x: 0, y: 0 });
    const sKey = activeSide === 'Back' ? 'back' : 'front';
    const sc = diagnostics?.centering?.[sKey];
    const mg = diagnostics?.overrides?.manual_geometry?.[sKey];
    const initSkew = Number(sc?.skew_deg ?? mg?.skew_deg ?? 0);
    setGaugeRotate(Number.isFinite(initSkew) ? Math.max(-6.0, Math.min(6.0, Number(initSkew.toFixed(2)))) : 0.0);
    setGaugeNudge({ x: 0, y: 0 });
    const initFmt = String(mg?.card_format || 'auto');
    setGaugeFormatOverride(['standard', 'mini', 'non_standard'].includes(initFmt) ? initFmt : 'auto');
  }, [activeSide, diagnostics?.updated_at, diagnostics?.sku]);

  useEffect(() => {
    const srcSizes = diagnostics?.source_images || {};
    const sideSz = activeSide === 'Back' ? srcSizes.back_size : srcSizes.front_size;
    if (Array.isArray(sideSz) && sideSz.length === 2 && sideSz[0] > 0 && sideSz[1] > 0) {
      setNaturalSize({ w: Number(sideSz[0]), h: Number(sideSz[1]) });
    }
  }, [diagnostics, activeSide]);

  useEffect(() => {
    const el = canvasWrapRef.current;
    if (!el) return;
    const updateFit = () => {
      const rect = el.getBoundingClientRect();
      const availW = Math.max(80, Math.floor((rect.width - 24) * 0.96));
      const availH = Math.max(80, Math.floor((rect.height - 48) * 0.95));
      const natW = Math.max(1, naturalSize.w || 1500);
      const natH = Math.max(1, naturalSize.h || 2100);
      const ratio = natW / natH;
      let fw = availW;
      let fh = fw / ratio;
      if (fh > availH) {
        fh = availH;
        fw = fh * ratio;
      }
      setFittedBox({ w: Math.max(70, Math.floor(fw)), h: Math.max(70, Math.floor(fh)) });
    };
    updateFit();
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(updateFit);
      ro.observe(el);
      return () => ro.disconnect();
    }
    window.addEventListener('resize', updateFit);
    return () => window.removeEventListener('resize', updateFit);
  }, [naturalSize.w, naturalSize.h, showCenteringGauge, editMode]);

  const sFold = encodeURIComponent(sanitizeFolderName(card?.Set || ''));
  const frontUrl = card?.Front_File
    ? (targetType === 'batch'
        ? `${API_ORIGIN}/static/batches/${encodeURIComponent(effectiveBatch)}/${encodeURIComponent(card.Front_File)}`
        : `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Front_File)}`)
    : '';
  const backUrl = card?.Back_File
    ? (targetType === 'batch'
        ? `${API_ORIGIN}/static/batches/${encodeURIComponent(effectiveBatch)}/${encodeURIComponent(card.Back_File)}`
        : `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Back_File)}`)
    : '';
  const activeImgUrl = activeSide === 'Back' ? (backUrl || frontUrl) : (frontUrl || backUrl);

  const toggleLayer = (cat) => setActiveLayers((prev) => ({ ...prev, [cat]: !prev[cat] }));

  const showAllMarkers = () => {
    setIsolatedDefectId('');
    setActiveLayers({ centering: true, corners: true, edges: true, surface: true });
  };

  const psaInfo = diagnostics?.grades?.psa || {
    overall: card?.Est_PSA || '—',
    tier: '',
    subgrades: {
      centering: card?.Sub_Centering || '—',
      corners: card?.Sub_Corners || '—',
      edges: card?.Sub_Edges || '—',
      surface: card?.Sub_Surface || '—',
    },
  };
  const bgsInfo = diagnostics?.grades?.bgs || {
    overall: card?.Est_BGS || '—',
    tier: '',
    subgrades: {
      centering: card?.Sub_Centering || '—',
      corners: card?.Sub_Corners || '—',
      edges: card?.Sub_Edges || '—',
      surface: card?.Sub_Surface || '—',
    },
  };

  const sideCent = activeSide === 'Back' ? diagnostics?.centering?.back : diagnostics?.centering?.front;
  const confirmedAll = Array.isArray(diagnostics?.confirmed_defects) ? diagnostics.confirmed_defects : [];
  const artifactsAll = Array.isArray(diagnostics?.superficial_artifacts) ? diagnostics.superficial_artifacts : [];

  // Active-side defects only, sorted with matching (active) categories first
  const activeSideDefectsAll = confirmedAll
    .filter((d) => String(d.side || 'Front') === activeSide)
    .slice()
    .sort((a, b) => {
      const aOn = activeLayers[String(a.category || 'surface')] ? 0 : 1;
      const bOn = activeLayers[String(b.category || 'surface')] ? 0 : 1;
      if (aOn !== bOn) return aOn - bOn;
      return Number(b.penalty ?? b.severity ?? 0) - Number(a.penalty ?? a.severity ?? 0);
    });

  // Left card SVG markers: if isolatedDefectId is set, show ONLY that defect; otherwise show active categories
  const visibleSideDefects = isolatedDefectId
    ? activeSideDefectsAll.filter((d) => d.id === isolatedDefectId)
    : activeSideDefectsAll.filter((d) => activeLayers[String(d.category || 'surface')]);

  const sideArtifacts = showArtifacts && !isolatedDefectId
    ? artifactsAll.filter((a) => String(a.side || 'Front') === activeSide && Array.isArray(a.bbox_norm))
    : [];

  const isolatedDefect = isolatedDefectId ? activeSideDefectsAll.find((d) => d.id === isolatedDefectId) || null : null;

  const notesByCat = diagnostics?.notes_by_category || {
    centering: `${card?.Centering_LR || '—'} L/R | ${card?.Centering_TB || '—'} T/B`,
    corners: 'Pending deep-dive inspection...',
    edges: 'Pending deep-dive inspection...',
    surface: card?.Grading_Notes || 'Pending deep-dive inspection...',
    advisories: [],
  };

  const buildCropUrl = (sideLbl, bbox, pad = 0.03, size = 240) => {
    if (!sku || !Array.isArray(bbox)) return '';
    const qs = new URLSearchParams({
      targetType,
      sku,
      batchName: effectiveBatch,
      side: String(sideLbl || 'Front').toLowerCase(),
      x: String(bbox[0] ?? 0),
      y: String(bbox[1] ?? 0),
      w: String(bbox[2] ?? 0.15),
      h: String(bbox[3] ?? 0.15),
      pad: String(pad),
      size: String(size),
    });
    return `${NODE_API_BASE}/grading/crop?${qs.toString()}`;
  };

  // Interactive Geometry Edit helpers
  const startEditCentering = () => {
    const oc = Array.isArray(sideCent?.outer_card_rect) ? [...sideCent.outer_card_rect] : [0.04, 0.03, 0.92, 0.94];
    const ic = Array.isArray(sideCent?.inner_frame_rect) ? [...sideCent.inner_frame_rect] : [0.09, 0.08, 0.82, 0.84];
    setDraftOuter(oc);
    setDraftInner(ic);
    setEditMode('centering');
  };

  const startEditCorners = () => {
    const oc = Array.isArray(sideCent?.outer_card_rect) ? sideCent.outer_card_rect : [0.04, 0.03, 0.92, 0.94];
    const c = sideCent?.corners || {
      tl: [oc[0], oc[1]],
      tr: [oc[0] + oc[2], oc[1]],
      bl: [oc[0], oc[1] + oc[3]],
      br: [oc[0] + oc[2], oc[1] + oc[3]],
    };
    setDraftCorners({
      tl: [...(c.tl || [oc[0], oc[1]])],
      tr: [...(c.tr || [oc[0] + oc[2], oc[1]])],
      bl: [...(c.bl || [oc[0], oc[1] + oc[3]])],
      br: [...(c.br || [oc[0] + oc[2], oc[1] + oc[3]])],
    });
    setEditMode('corners');
  };

  const saveGeometryEdit = () => {
    setSavingGeom(true);
    const body = {
      targetType,
      sku,
      batchName: effectiveBatch,
      side: activeSide,
    };
    if (editMode === 'centering') {
      body.outer_card_rect = draftOuter;
      body.inner_frame_rect = draftInner;
    } else if (editMode === 'corners') {
      body.corners = draftCorners;
    }
    fetch(`${NODE_API_BASE}/grading/update-geometry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          if (res.diagnostics) setDiagnostics(res.diagnostics);
          if (onCardUpdated) onCardUpdated(res);
          setEditMode('none');
          const gb = res.gradesBefore || {};
          const ga = res.gradesAfter || {};
          if (pushNotification) {
            pushNotification(
              `Geometry Saved (${activeSide}) — SKU ${sku}`,
              `PSA ${gb.Est_PSA || '?'} → ${ga.Est_PSA || '?'} | BGS ${gb.Est_BGS || '?'} → ${ga.Est_BGS || '?'}`,
              'Grading',
              'success'
            );
          }
        } else {
          setDiagError(res?.error || 'Failed to save manual geometry.');
        }
      })
      .catch((e) => setDiagError(e.message || 'Network error saving geometry.'))
      .finally(() => setSavingGeom(false));
  };

  const applyGaugeAndReevaluate = () => {
    if (!sku || savingGeom) return;
    setSavingGeom(true);
    setDiagError('');
    const body = {
      targetType,
      sku,
      batchName: effectiveBatch,
      side: activeSide,
      source: 'centering_gauge',
      skew_deg: Number(Math.max(-6.0, Math.min(6.0, Number(gaugeRotate) || 0)).toFixed(2)),
      card_format: gaugeFormatOverride,
      outer_card_rect: [
        Number(gaugeGeometry.ox.toFixed(4)),
        Number(gaugeGeometry.oy.toFixed(4)),
        Number(gaugeGeometry.ow.toFixed(4)),
        Number(gaugeGeometry.oh.toFixed(4)),
      ],
    };
    fetch(`${NODE_API_BASE}/grading/update-geometry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          if (res.diagnostics) setDiagnostics(res.diagnostics);
          if (onCardUpdated) onCardUpdated(res);
          setGaugeNudge({ x: 0, y: 0 });
          const gb = res.gradesBefore || {};
          const ga = res.gradesAfter || {};
          if (pushNotification) {
            pushNotification(
              `Gauge Applied & Re-Evaluated (${activeSide}) — SKU ${sku}`,
              `PSA ${gb.Est_PSA || '?'} → ${ga.Est_PSA || '?'} | BGS ${gb.Est_BGS || '?'} → ${ga.Est_BGS || '?'}`,
              'Grading',
              'success'
            );
          }
        } else {
          setDiagError(res?.error || 'Failed to apply centering gauge.');
        }
      })
      .catch((e) => setDiagError(e.message || 'Network error applying centering gauge.'))
      .finally(() => setSavingGeom(false));
  };

  const clientToNorm = (clientX, clientY) => {
    const el = svgRef.current;
    if (!el) return [0.5, 0.5];
    const r = el.getBoundingClientRect();
    const nx = Math.max(0.0, Math.min(1.0, (clientX - r.left) / Math.max(1, r.width)));
    const ny = Math.max(0.0, Math.min(1.0, (clientY - r.top) / Math.max(1, r.height)));
    return [Number(nx.toFixed(4)), Number(ny.toFixed(4))];
  };

  const handleSvgPointerMove = (e) => {
    const gd = geomDragRef.current;
    if (!gd) return;
    e.stopPropagation();
    const [nx, ny] = clientToNorm(e.clientX, e.clientY);
    if (gd.kind === 'corner') {
      setDraftCorners((prev) => ({ ...(prev || {}), [gd.edge]: [nx, ny] }));
      return;
    }
    const setter = gd.kind === 'outer' ? setDraftOuter : setDraftInner;
    setter((prev) => {
      if (!prev) return prev;
      let [x, y, w, h] = prev;
      let x2 = x + w;
      let y2 = y + h;
      const minGap = 0.06;
      if (gd.edge === 'left') x = Math.min(x2 - minGap, nx);
      else if (gd.edge === 'right') x2 = Math.max(x + minGap, nx);
      else if (gd.edge === 'top') y = Math.min(y2 - minGap, ny);
      else if (gd.edge === 'bottom') y2 = Math.max(y + minGap, ny);
      return [Number(x.toFixed(4)), Number(y.toFixed(4)), Number((x2 - x).toFixed(4)), Number((y2 - y).toFixed(4))];
    });
  };

  const handleSvgPointerUp = () => {
    geomDragRef.current = null;
    panDragRef.current = null;
  };

  // Non-passive wheel zoom listener so wheel zooming never scrolls the page
  useEffect(() => {
    const el = canvasWrapRef.current;
    if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      e.stopPropagation();
      const delta = e.deltaY < 0 ? 0.25 : -0.25;
      setMainZoom((z) => {
        const nz = Number(Math.max(1.0, Math.min(4.0, z + delta)).toFixed(2));
        if (nz <= 1.0) setMainPan({ x: 0, y: 0 });
        return nz;
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const clampPan = (px, py, z = mainZoom) => {
    const maxX = Math.max(0, fittedBox.w * Math.max(0, z - 1.0) * 0.55);
    const maxY = Math.max(0, fittedBox.h * Math.max(0, z - 1.0) * 0.55);
    return {
      x: Math.max(-maxX, Math.min(maxX, px)),
      y: Math.max(-maxY, Math.min(maxY, py)),
    };
  };

  const handleCanvasPointerDown = (e) => {
    if (mainZoom <= 1.0 || geomDragRef.current) return;
    panDragRef.current = { startX: e.clientX, startY: e.clientY, origX: mainPan.x, origY: mainPan.y };
  };

  const handleCanvasPointerMove = (e) => {
    if (geomDragRef.current) {
      handleSvgPointerMove(e);
      return;
    }
    const pd = panDragRef.current;
    if (!pd) return;
    setMainPan(clampPan(pd.origX + (e.clientX - pd.startX), pd.origY + (e.clientY - pd.startY)));
  };

  // Live centering calculation during Edit Centering
  const activeOuterRect = editMode === 'centering' && draftOuter ? draftOuter : sideCent?.outer_card_rect;
  const activeInnerRect = editMode === 'centering' && draftInner ? draftInner : sideCent?.inner_frame_rect;
  const liveCentStats = (() => {
    if (!Array.isArray(activeOuterRect) || !Array.isArray(activeInnerRect)) {
      return { lr: sideCent?.lr || '50/50', tb: sideCent?.tb || '50/50' };
    }
    const [ox, oy, ow, oh] = activeOuterRect;
    const [ix, iy, iw, ih] = activeInnerRect;
    const l = Math.max(0.001, ix - ox);
    const r = Math.max(0.001, ox + ow - (ix + iw));
    const t = Math.max(0.001, iy - oy);
    const b = Math.max(0.001, oy + oh - (iy + ih));
    const lrL = Math.max(32, Math.min(68, Math.round((l / (l + r)) * 100)));
    const tbT = Math.max(32, Math.min(68, Math.round((t / (t + b)) * 100)));
    return { lr: `${lrL}/${100 - lrL}`, tb: `${tbT}/${100 - tbT}` };
  })();

  const renderSvgMarker = (d, idx) => {
    if (!Array.isArray(d.bbox_norm)) return null;
    const [bx, by, bw, bh] = d.bbox_norm;
    const x = bx * 1000;
    const y = by * 1000;
    const w = Math.max(14, bw * 1000);
    const h = Math.max(14, bh * 1000);
    const cx = x + w * 0.5;
    const cy = y + h * 0.5;
    const isSel = isolatedDefectId === d.id;
    const strokeCol = isSel ? '#facc15' : '#ef4444';
    const sw = isSel ? 5 : 3;
    const style = d.marker_style || 'circle';

    return (
      <g
        key={d.id || idx}
        onClick={(e) => {
          e.stopPropagation();
          setLoupeZoom(1.0);
          setIsolatedDefectId(isSel ? '' : d.id);
        }}
        style={{ cursor: 'pointer' }}
      >
        {style === 'box' ? (
          <rect x={x} y={y} width={w} height={h} rx={6} fill={isSel ? 'rgba(250,204,21,0.18)' : 'rgba(239,68,68,0.12)'} stroke={strokeCol} strokeWidth={sw} />
        ) : style === 'arrow' ? (
          <g>
            <circle cx={cx} cy={cy} r={Math.max(18, Math.max(w, h) * 0.65)} fill="rgba(239,68,68,0.14)" stroke={strokeCol} strokeWidth={sw} />
            <line x1={cx < 500 ? cx + 38 : cx - 38} y1={cy < 500 ? cy + 38 : cy - 38} x2={cx} y2={cy} stroke={strokeCol} strokeWidth={sw + 1} />
            <circle cx={cx} cy={cy} r={5} fill={strokeCol} />
          </g>
        ) : (
          <circle cx={cx} cy={cy} r={Math.max(20, Math.max(w, h) * 0.65)} fill={isSel ? 'rgba(250,204,21,0.18)' : 'rgba(239,68,68,0.14)'} stroke={strokeCol} strokeWidth={sw} />
        )}
        <title>{`${d.label || d.type} (-${Number(d.penalty ?? d.severity ?? 0.5).toFixed(1)})`}</title>
      </g>
    );
  };

  const cnumDisp = String(card?.['Card Number'] || card?.Card_Number || '').replace(/^#/, '');
  const subDisp = card?.Subset || card?.Subset_Parallel || 'Base';
  const anyFilteredOrIsolated = Boolean(isolatedDefectId) || !activeLayers.centering || !activeLayers.corners || !activeLayers.edges || !activeLayers.surface;

  // Authentic PSA Slab Label (Red Frame + White Interior + Security Watermark + Logo)
  const renderPsaCard = () => {
    const subs = psaInfo?.subgrades || {};
    const psaNum = parseFloat(psaInfo?.overall);
    const psaTier = !isNaN(psaNum)
      ? (psaNum >= 10 ? 'GEM MT' : psaNum >= 9 ? 'MINT' : psaNum >= 8 ? 'NM-MT' : psaNum >= 7 ? 'NM' : 'EX-MT')
      : String(psaInfo?.tier || '').toUpperCase();
    return (
      <div className="rounded-xl border-[3px] border-red-600 bg-red-600 p-0.5 shadow-lg select-none">
        <div
          className="rounded-lg bg-white text-slate-900 px-2.5 py-2 relative overflow-hidden flex items-stretch justify-between gap-2 min-h-[104px]"
          style={{
            backgroundImage: 'repeating-linear-gradient(135deg, rgba(226,232,240,0.42) 0px, rgba(226,232,240,0.42) 2px, rgba(255,255,255,0.92) 2px, rgba(255,255,255,0.92) 8px)',
          }}
        >
          {/* Left: Set, Player, Subset, Barcode & Compact Subgrades */}
          <div className="flex-1 min-w-0 flex flex-col justify-between">
            <div>
              <div className="text-[9.5px] font-extrabold uppercase tracking-tight text-slate-700 truncate">{card?.Set || 'CARD SET'}</div>
              <div className="text-[11.5px] font-black uppercase tracking-tight text-slate-950 truncate">{card?.Player || 'PLAYER'}</div>
              <div className="text-[9px] font-bold uppercase text-slate-600 truncate">{subDisp}</div>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <div
                className="h-3 w-16 rounded-xs opacity-75 shrink-0"
                style={{ backgroundImage: 'repeating-linear-gradient(90deg, #0f172a 0px, #0f172a 1.5px, transparent 1.5px, transparent 3px, #0f172a 3px, #0f172a 4px, transparent 4px, transparent 6.5px)' }}
              />
              <div className="text-[8.5px] font-mono font-bold text-slate-700 truncate">
                CTR {subs.centering ?? '—'} • CRN {subs.corners ?? '—'} • EDG {subs.edges ?? '—'} • SRF {subs.surface ?? '—'}
              </div>
            </div>
          </div>

          {/* Center-Bottom PSA Lighthouse Logo */}
          <div className="flex flex-col items-center justify-end shrink-0 pb-0.5">
            <img
              src={`${API_ORIGIN}/api/assets/logos/psa_logo.png`}
              alt="PSA"
              className="h-6 w-auto object-contain"
              onError={(e) => { e.currentTarget.style.display = 'none'; }}
            />
            <span className="text-[8px] font-black tracking-widest text-red-600 leading-none mt-0.5">PSA</span>
          </div>

          {/* Right: Card #, Tier, Large Grade & Cert SKU */}
          <div className="text-right flex flex-col justify-between shrink-0 min-w-[58px]">
            <div className="text-[9.5px] font-black font-mono text-slate-800">#{cnumDisp || '—'}</div>
            <div>
              <div className="text-[9px] font-black uppercase tracking-wider text-red-700 leading-none">{psaTier}</div>
              <div className="text-2xl font-black font-mono text-slate-950 leading-none mt-0.5">{psaInfo?.overall ?? '—'}</div>
            </div>
            <div className="text-[8.5px] font-mono font-bold text-slate-500">#{sku}</div>
          </div>
        </div>
      </div>
    );
  };

  // Authentic Beckett (BGS) Slab Label (Brushed Metallic Silver / Gold / Black Label 10)
  const renderBgsCard = () => {
    const subs = bgsInfo?.subgrades || {};
    const ovNum = parseFloat(bgsInfo?.overall);
    const cNum = parseFloat(subs.centering);
    const coNum = parseFloat(subs.corners);
    const eNum = parseFloat(subs.edges);
    const sNum = parseFloat(subs.surface);
    const isBlackLabel = !isNaN(ovNum) && ovNum >= 10.0 && cNum >= 10.0 && coNum >= 10.0 && eNum >= 10.0 && sNum >= 10.0;
    const isGoldLabel = !isBlackLabel && !isNaN(ovNum) && ovNum >= 9.5;

    const bgStyle = isBlackLabel
      ? {
          background: 'linear-gradient(180deg, #141418 0%, #0a0a0c 50%, #16161b 100%)',
          color: '#E5C158',
          borderColor: '#D4AF37',
        }
      : isGoldLabel
      ? {
          background: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.08) 0px, rgba(255,255,255,0.08) 1px, transparent 1px, transparent 3px), linear-gradient(135deg, #E6C86E 0%, #D4AF37 42%, #F3DC8A 62%, #C5A028 100%)',
          color: '#0f172a',
          borderColor: '#fef08a',
        }
      : {
          background: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.14) 0px, rgba(255,255,255,0.14) 1px, transparent 1px, transparent 3px), linear-gradient(135deg, #E2E8F0 0%, #CBD5E1 45%, #F1F5F9 65%, #94A3B8 100%)',
          color: '#0f172a',
          borderColor: '#f8fafc',
        };

    const bgsTier = isBlackLabel
      ? 'PRISTINE'
      : !isNaN(ovNum) && ovNum >= 10.0
      ? 'PRISTINE'
      : !isNaN(ovNum) && ovNum >= 9.5
      ? 'GEM MINT'
      : !isNaN(ovNum) && ovNum >= 9.0
      ? 'MINT'
      : 'NM-MT';

    return (
      <div
        className="rounded-xl border-2 px-2.5 py-2 shadow-lg select-none flex items-stretch justify-between gap-2 min-h-[104px]"
        style={bgStyle}
      >
        {/* Left Edge BGS Laurel Logo */}
        <div className="flex flex-col items-center justify-center shrink-0">
          <img
            src={`${API_ORIGIN}/api/assets/logos/bgs_logo.png`}
            alt="BGS"
            className="h-9 w-auto object-contain"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
          <span className={`text-[8px] font-black tracking-widest mt-0.5 ${isBlackLabel ? 'text-amber-300' : 'text-slate-900'}`}>BGS</span>
        </div>

        {/* Center: Metadata + Authentic 2x2 Subgrade Grid */}
        <div className="flex-1 min-w-0 flex flex-col justify-between">
          <div>
            <div className="text-[9px] font-extrabold uppercase tracking-tight opacity-85 truncate">{card?.Set || 'CARD SET'}</div>
            <div className="text-[11px] font-black uppercase tracking-tight truncate">#{cnumDisp} {card?.Player || 'PLAYER'}</div>
            <div className="text-[8.5px] font-bold uppercase opacity-75 truncate">{subDisp}</div>
          </div>
          <div className="grid grid-cols-2 gap-x-2.5 gap-y-0.5 text-[9px] font-mono font-black uppercase mt-1">
            <div className="flex justify-between"><span>CENTERING</span><span>{subs.centering ?? '—'}</span></div>
            <div className="flex justify-between"><span>CORNERS</span><span>{subs.corners ?? '—'}</span></div>
            <div className="flex justify-between"><span>EDGES</span><span>{subs.edges ?? '—'}</span></div>
            <div className="flex justify-between"><span>SURFACE</span><span>{subs.surface ?? '—'}</span></div>
          </div>
        </div>

        {/* Right: Huge Bold Grade + Tier + Cert SKU */}
        <div className={`text-right flex flex-col justify-between shrink-0 pl-2 border-l ${isBlackLabel ? 'border-amber-400/35' : 'border-black/20'} min-w-[62px]`}>
          <div className="text-[8.5px] font-black uppercase tracking-wider leading-none">{isBlackLabel ? 'BLACK 10' : bgsTier}</div>
          <div className="text-3xl font-black font-mono leading-none my-auto">{bgsInfo?.overall ?? '—'}</div>
          <div className="text-[8.5px] font-mono font-bold opacity-80">#{sku}</div>
        </div>
      </div>
    );
  };

  const noteBoxes = [
    { key: 'centering', title: 'Centering', icon: '📐', color: 'cyan', text: notesByCat.centering },
    { key: 'corners', title: 'Corners', icon: '⌜', color: 'rose', text: notesByCat.corners },
    { key: 'edges', title: 'Edges', icon: '║', color: 'amber', text: notesByCat.edges },
    { key: 'surface', title: 'Surface', icon: '✨', color: 'purple', text: notesByCat.surface },
  ];

  // Compute physical card format ('standard' 2.5x3.5 vs 'mini' 1.5x2.625), orientation, and skew angle for Virtual Centering Gauge
  const gaugeGeometry = (() => {
    const baseRect = Array.isArray(activeOuterRect) && activeOuterRect.length === 4
      ? activeOuterRect
      : [0.04, 0.03, 0.92, 0.94];
    const [ox, oy, ow, oh] = baseRect;
    const rawCardPxW = Math.max(10, ow * (naturalSize.w || 1500));
    const rawCardPxH = Math.max(10, oh * (naturalSize.h || 2100));
    const isLandscape = sideCent?.orientation === 'landscape' || rawCardPxW > rawCardPxH * 1.05 || (naturalSize.w || 1500) > (naturalSize.h || 2100) * 1.05;
    const shortLongAspect = Math.min(rawCardPxW, rawCardPxH) / Math.max(1, Math.max(rawCardPxW, rawCardPxH));
    const metaStr = `${card?.Set || ''} ${card?.Subset || ''} ${card?.Subset_Parallel || ''}`;
    const isFramedMini = /\b(framed|rip card|full[- ]size|boxloader)\b/i.test(metaStr);
    const isNamedMini = !isFramedMini && /\b(mini|t206|topps 206|tobacco)\b/i.test(metaStr);
    const autoIsMini = sideCent?.card_format === 'mini' || (!isFramedMini && shortLongAspect <= 0.635) || isNamedMini;
    const isMini = gaugeFormatOverride === 'mini' ? true : gaugeFormatOverride === 'standard' ? false : autoIsMini;

    // Base skew angle from sideCent.skew_deg or detected TL->TR corner slope
    let baseSkew = Number(sideCent?.skew_deg || 0);
    if (!Number.isFinite(baseSkew)) baseSkew = 0;
    if (baseSkew === 0 && sideCent?.corners?.tl && sideCent?.corners?.tr) {
      const dx = (sideCent.corners.tr[0] - sideCent.corners.tl[0]) * (naturalSize.w || 1500);
      const dy = (sideCent.corners.tr[1] - sideCent.corners.tl[1]) * (naturalSize.h || 2100);
      if (Math.abs(dx) > 20) {
        const calcDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
        if (Math.abs(calcDeg) <= 6.0) baseSkew = Number(calcDeg.toFixed(2));
      }
    }
    const totalAngle = Number(Math.max(-6.0, Math.min(6.0, Number(gaugeRotate) || 0)).toFixed(2));

    // Physical dimensions in inches
    const physShortIn = isMini ? 1.5 : 2.5;
    const physLongIn = isMini ? 2.625 : 3.5;
    const physWIn = isLandscape ? physLongIn : physShortIn;
    const physHIn = isLandscape ? physShortIn : physLongIn;

    return {
      ox: Math.max(0.0, Math.min(0.95, ox + gaugeNudge.x)),
      oy: Math.max(0.0, Math.min(0.95, oy + gaugeNudge.y)),
      ow: Math.max(0.05, Math.min(1.0, ow)),
      oh: Math.max(0.05, Math.min(1.0, oh)),
      isLandscape,
      isMini,
      autoIsMini,
      baseSkew,
      totalAngle,
      physWIn,
      physHIn,
      formatLabel: isMini ? 'Mini (1.5"×2.625")' : 'Standard (2.5"×3.5")',
      orientLabel: isLandscape ? 'Landscape' : 'Portrait',
    };
  })();

  return (
    <div className="flex-1 min-h-0 h-full flex flex-col gap-2 overflow-hidden">
      {/* SINGLE COMPACT TOP BAR (~44px) */}
      <div className={`${skin.cardBg} border ${skin.border} rounded-xl px-3 py-1.5 min-h-[42px] flex flex-wrap items-center justify-between gap-2 shrink-0`}>
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          {onBack && (
            <button type="button" onClick={onBack} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold shrink-0">
              ⬅ {backLabel}
            </button>
          )}
          {(onSwitchIndividual || onSwitchBulk) && (
            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-[11px] shrink-0">
              {onSwitchIndividual && (
                <button type="button" onClick={onSwitchIndividual} className="px-2 py-0.5 rounded-md font-bold text-slate-400 hover:text-white">🪟 Individual</button>
              )}
              <button type="button" className={`px-2 py-0.5 rounded-md font-bold ${skin.accentActive}`}>🔬 Deep-Dive</button>
              {onSwitchBulk && (
                <button type="button" onClick={onSwitchBulk} className="px-2 py-0.5 rounded-md font-bold text-slate-400 hover:text-white">📋 Bulk</button>
              )}
            </div>
          )}
          <div className="min-w-0 flex items-center gap-1.5 truncate">
            <span className="text-xs font-mono text-sky-400 font-bold shrink-0">SKU {sku}</span>
            <span className="text-xs font-extrabold text-white truncate">
              {card?.Set} #{cnumDisp} {card?.Player} <span className="text-slate-400 font-normal">({subDisp})</span>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => { setFlagPresetId(isolatedDefectId || ''); setShowFlagModal(true); }}
            className="px-2.5 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow"
          >
            🚩 Flag Error
          </button>
          <button
            type="button"
            disabled={loadingDiag}
            onClick={() => fetchDiagnostics(true)}
            className="px-2.5 py-1 rounded-lg bg-cyan-950/90 hover:bg-cyan-800 border border-cyan-600/70 text-cyan-200 font-bold text-xs disabled:opacity-45"
          >
            {loadingDiag ? '⏳ Scanning...' : '🔄 Re-Scan'}
          </button>
          <div className="flex items-center gap-1 text-xs">
            <button type="button" onClick={onPrev} disabled={cardIndex <= 0} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-35 font-bold">◀ Prev</button>
            {Array.isArray(cardOptions) && cardOptions.length > 1 && onSelectCardIndex ? (
              <select
                value={cardIndex}
                onChange={(e) => onSelectCardIndex(parseInt(e.target.value, 10) || 0)}
                className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-[11px] font-mono max-w-[210px] text-slate-200"
              >
                {cardOptions.map((opt) => (
                  <option key={opt.index} value={opt.index}>{opt.label}</option>
                ))}
              </select>
            ) : (
              <span className="font-mono text-slate-300 px-1">{cardIndex + 1} / {Math.max(1, totalCards)}</span>
            )}
            <button type="button" onClick={onNext} disabled={cardIndex >= totalCards - 1} className={`px-2 py-1 rounded-lg disabled:opacity-35 font-bold ${skin.accentBtn}`}>Next ▶</button>
          </div>
        </div>
      </div>

      {/* MAIN SPLIT PANE */}
      <div className="flex-1 min-h-0 overflow-hidden grid grid-cols-1 lg:grid-cols-12 gap-2.5">
        {/* LEFT PANE: FULL-HEIGHT SINGLE-SIDE IMAGE + ZOOM/PAN + CENTERING GAUGE + EDIT CENTERING/CORNERS */}
        <div className={`lg:col-span-6 ${skin.cardBg} border ${skin.border} rounded-2xl p-2.5 flex flex-col gap-1.5 min-h-0 h-full overflow-hidden`}>
          {/* LEFT TOOLBAR */}
          <div className="flex flex-wrap items-center justify-between gap-1.5 shrink-0">
            <div className="flex items-center gap-1.5">
              <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveSide('Front')}
                  className={`px-2.5 py-0.5 rounded-lg font-bold transition ${activeSide === 'Front' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                >
                  Front
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSide('Back')}
                  className={`px-2.5 py-0.5 rounded-lg font-bold transition ${activeSide === 'Back' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                >
                  Back
                </button>
              </div>
              {sideCent?.sleeve_detected && (
                <span className="px-2 py-0.5 rounded-lg bg-cyan-950/80 border border-cyan-700/70 text-cyan-200 text-[10px] font-semibold">
                  🛡️ Sleeve
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-1 text-[11px]">
              {/* ZOOM CONTROLS */}
              <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg px-1 py-0.5 gap-1">
                <button type="button" onClick={() => setMainZoom((z) => { const nz = Math.max(1.0, Number((z - 0.25).toFixed(2))); if (nz <= 1.0) setMainPan({ x: 0, y: 0 }); return nz; })} className="px-1.5 font-bold text-slate-300 hover:text-white">−</button>
                <span className="font-mono text-[10px] text-sky-300 w-10 text-center">{Math.round(mainZoom * 100)}%</span>
                <button type="button" onClick={() => setMainZoom((z) => Math.min(4.0, Number((z + 0.25).toFixed(2))))} className="px-1.5 font-bold text-slate-300 hover:text-white">+</button>
                {mainZoom > 1.0 && (
                  <button type="button" onClick={() => { setMainZoom(1.0); setMainPan({ x: 0, y: 0 }); }} className="px-1.5 text-[10px] text-amber-300 hover:text-amber-200 font-bold">Reset</button>
                )}
              </div>

              {/* VIRTUAL CLEAR CENTERING CARD TOGGLE BUTTON */}
              <button
                type="button"
                onClick={() => setShowCenteringGauge((v) => !v)}
                title="Toggle Legends-style Virtual Clear Centering Card Overlay"
                className={`px-2 py-1 rounded-lg border font-bold transition ${
                  showCenteringGauge
                    ? 'bg-cyan-500/25 border-cyan-400 text-cyan-100 ring-1 ring-cyan-400/40'
                    : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-cyan-200'
                }`}
              >
                📏 Centering Gauge
              </button>

              {editMode === 'none' ? (
                <>
                  <button type="button" onClick={startEditCentering} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-200 font-bold">
                    📐 Edit Centering
                  </button>
                  <button type="button" onClick={startEditCorners} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-200 font-bold">
                    📐 Edit Corners
                  </button>
                </>
              ) : (
                <>
                  <button type="button" disabled={savingGeom} onClick={saveGeometryEdit} className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold">
                    {savingGeom ? '⏳ Saving...' : '💾 Save & Recalculate'}
                  </button>
                  <button type="button" disabled={savingGeom} onClick={() => setEditMode('none')} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold">
                    Cancel
                  </button>
                </>
              )}

              {anyFilteredOrIsolated && (
                <button type="button" onClick={showAllMarkers} className="px-2 py-1 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-bold shadow">
                  👁️ Show All
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowArtifacts((s) => !s)}
                className={`px-2 py-1 rounded-lg border font-semibold ${
                  showArtifacts ? 'bg-amber-950/80 border-amber-500 text-amber-200' : 'bg-slate-900 border-slate-700 text-slate-400'
                }`}
              >
                Artifacts ({artifactsAll.filter((a) => String(a.side || 'Front') === activeSide).length})
              </button>
            </div>
          </div>

          {/* COMPACT CENTERING GAUGE CONTROLS BAR (OPACITY 20%-90%, ROTATE -3° TO +3°, NUDGE, FORMAT & LEGENDS % CHART) */}
          {showCenteringGauge && (
            <div className="px-2.5 py-1 rounded-xl bg-slate-950/95 border border-cyan-500/45 flex flex-wrap items-center justify-between gap-2 text-[10.5px] shrink-0">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-cyan-300">📏 {gaugeGeometry.formatLabel} • {gaugeGeometry.orientLabel}</span>
                <select
                  value={gaugeFormatOverride}
                  onChange={(e) => setGaugeFormatOverride(e.target.value)}
                  title="Card Physical Format (Auto-detects Standard 2.5x3.5 vs Mini 1.5x2.625)"
                  className="bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-[10px] text-slate-200 font-semibold"
                >
                  <option value="auto">Auto ({gaugeGeometry.autoIsMini ? 'Mini' : 'Std'})</option>
                  <option value="standard">Std 2.5×3.5</option>
                  <option value="mini">Mini 1.5×2.625</option>
                </select>
                <select
                  value={gaugeColorMode}
                  onChange={(e) => setGaugeColorMode(e.target.value)}
                  title="Gauge Line Contrast Theme"
                  className="bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-[10px] text-slate-200 font-semibold"
                >
                  <option value="contrast">Hi-Contrast</option>
                  <option value="classic_black">Legends Ink</option>
                  <option value="cyan">Cyan Glow</option>
                </select>
                <button
                  type="button"
                  onClick={() => setShowLegendsChart((v) => !v)}
                  title="Toggle Legends 1-10 Line Pair Centering Percentages Chart (Red = 60/40 or Better)"
                  className={`px-1.5 py-0.5 rounded border text-[10px] font-bold transition ${
                    showLegendsChart ? 'bg-rose-950/90 border-rose-500 text-rose-200' : 'bg-slate-900 hover:bg-slate-800 border-slate-700 text-slate-300'
                  }`}
                >
                  📊 % Chart
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-2.5">
                {/* OPACITY SLIDER (20% - 90%) */}
                <label className="flex items-center gap-1 text-slate-300" title="Virtual Centering Card Overlay Opacity (20%–90%)">
                  <span className="text-slate-400">Opacity</span>
                  <input
                    type="range"
                    min={20}
                    max={90}
                    step={5}
                    value={gaugeOpacity}
                    onChange={(e) => setGaugeOpacity(Number(e.target.value))}
                    className="w-16 accent-cyan-400 cursor-pointer"
                  />
                  <span className="font-mono text-cyan-300 w-7 text-right">{gaugeOpacity}%</span>
                </label>

                {/* ROTATE (-6° TO +6°) */}
                <div className="flex items-center gap-1 text-slate-300" title="Align Virtual Centering Card to skewed scans (-6° to +6°)">
                  <span className="text-slate-400">Rotate</span>
                  <button
                    type="button"
                    onClick={() => setGaugeRotate((r) => Math.max(-6.0, Number((r - 0.25).toFixed(2))))}
                    className="px-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold"
                  >
                    −
                  </button>
                  <input
                    type="range"
                    min={-6}
                    max={6}
                    step={0.1}
                    value={gaugeRotate}
                    onChange={(e) => setGaugeRotate(Number(e.target.value))}
                    className="w-16 accent-amber-400 cursor-pointer"
                  />
                  <button
                    type="button"
                    onClick={() => setGaugeRotate((r) => Math.min(6.0, Number((r + 0.25).toFixed(2))))}
                    className="px-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold"
                  >
                    +
                  </button>
                  <span className="font-mono text-amber-300 w-11 text-right">
                    {gaugeGeometry.totalAngle >= 0 ? `+${gaugeGeometry.totalAngle.toFixed(1)}°` : `${gaugeGeometry.totalAngle.toFixed(1)}°`}
                  </span>
                </div>

                {/* NUDGE X/Y, APPLY GAUGE & RESET */}
                {(() => {
                  const sKey = activeSide === 'Back' ? 'back' : 'front';
                  const savedSkew = Number(sideCent?.skew_deg ?? diagnostics?.overrides?.manual_geometry?.[sKey]?.skew_deg ?? 0);
                  const savedFmtRaw = String(diagnostics?.overrides?.manual_geometry?.[sKey]?.card_format || 'auto');
                  const savedFmt = ['standard', 'mini', 'non_standard'].includes(savedFmtRaw) ? savedFmtRaw : 'auto';
                  const gaugeDirty = Math.abs(gaugeRotate - savedSkew) >= 0.05 || gaugeNudge.x !== 0 || gaugeNudge.y !== 0 || gaugeFormatOverride !== savedFmt;
                  return (
                    <div className="flex items-center gap-0.5" title="Fine-nudge Virtual Centering Gauge position">
                      <button type="button" onClick={() => setGaugeNudge((p) => ({ ...p, x: Number(Math.max(-0.08, p.x - 0.0025).toFixed(4)) }))} className="px-1 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200">◀</button>
                      <button type="button" onClick={() => setGaugeNudge((p) => ({ ...p, y: Number(Math.max(-0.08, p.y - 0.0025).toFixed(4)) }))} className="px-1 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200">▲</button>
                      <button type="button" onClick={() => setGaugeNudge((p) => ({ ...p, y: Number(Math.min(0.08, p.y + 0.0025).toFixed(4)) }))} className="px-1 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200">▼</button>
                      <button type="button" onClick={() => setGaugeNudge((p) => ({ ...p, x: Number(Math.min(0.08, p.x + 0.0025).toFixed(4)) }))} className="px-1 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200">▶</button>
                      <button
                        type="button"
                        disabled={!gaugeDirty || savingGeom}
                        onClick={applyGaugeAndReevaluate}
                        title="Persist gauge skew, nudge & format and re-run deskewed grading"
                        className="ml-1 px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold"
                      >
                        {savingGeom ? '⏳ Applying...' : '💾 Apply Gauge & Re-Evaluate'}
                      </button>
                      {gaugeDirty && (
                        <button
                          type="button"
                          onClick={() => { setGaugeRotate(Number.isFinite(savedSkew) ? savedSkew : 0.0); setGaugeNudge({ x: 0, y: 0 }); setGaugeFormatOverride(savedFmt); }}
                          className="ml-0.5 px-1.5 py-0.5 rounded bg-amber-950/90 hover:bg-amber-800 border border-amber-600/60 text-amber-200 font-bold"
                        >
                          Reset
                        </button>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          )}

          {/* CARD CANVAS */}
          <div
            ref={canvasWrapRef}
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={handleCanvasPointerMove}
            onPointerUp={handleSvgPointerUp}
            onPointerLeave={handleSvgPointerUp}
            className={`flex-1 min-h-0 flex items-center justify-center pt-7 pb-2 px-2 bg-slate-950/90 border border-slate-800 rounded-xl overflow-hidden relative ${mainZoom > 1.0 ? 'cursor-grab active:cursor-grabbing' : ''}`}
          >
            {!activeImgUrl ? (
              <div className="text-xs text-slate-500">No {activeSide} scan image available.</div>
            ) : (
              <div
                className="relative shrink-0"
                style={{
                  width: `${fittedBox.w}px`,
                  height: `${fittedBox.h}px`,
                  transform: `translate(${mainPan.x}px, ${mainPan.y}px) scale(${mainZoom})`,
                  transformOrigin: 'center center',
                }}
              >
                <img
                  src={activeImgUrl}
                  alt={`${activeSide} card`}
                  draggable={false}
                  onLoad={(e) => {
                    const nw = e.currentTarget.naturalWidth;
                    const nh = e.currentTarget.naturalHeight;
                    if (nw > 0 && nh > 0) setNaturalSize({ w: nw, h: nh });
                  }}
                  className="w-full h-full block select-none rounded-lg"
                />
                <svg ref={svgRef} viewBox="0 0 1000 1000" preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
                  {/* CENTERING GUIDES (VIEW OR EDIT CENTERING MODE) */}
                  {(activeLayers.centering || editMode === 'centering') && Array.isArray(activeOuterRect) && Array.isArray(activeInnerRect) && (() => {
                    const [ox, oy, ow, oh] = activeOuterRect.map((v) => v * 1000);
                    const [ix, iy, iw, ih] = activeInnerRect.map((v) => v * 1000);
                    const isEditC = editMode === 'centering';
                    return (
                      <g>
                        <rect x={ox} y={oy} width={ow} height={oh} fill="none" stroke="#22d3ee" strokeWidth={isEditC ? 3.5 : 2.5} strokeDasharray="10 6" />
                        <rect x={ix} y={iy} width={iw} height={ih} fill="none" stroke="#38bdf8" strokeWidth={isEditC ? 3.5 : 2.5} />
                        <line x1={ox} y1={oy + oh * 0.5} x2={ix} y2={oy + oh * 0.5} stroke="#22d3ee" strokeWidth="2.5" />
                        <line x1={ix + iw} y1={oy + oh * 0.5} x2={ox + ow} y2={oy + oh * 0.5} stroke="#22d3ee" strokeWidth="2.5" />
                        <line x1={ox + ow * 0.5} y1={oy} x2={ox + ow * 0.5} y2={iy} stroke="#22d3ee" strokeWidth="2.5" />
                        <line x1={ox + ow * 0.5} y1={iy + ih} x2={ox + ow * 0.5} y2={oy + oh} stroke="#22d3ee" strokeWidth="2.5" />

                        {isEditC && (
                          <g>
                            {/* 4 Draggable Outer Edges */}
                            <line x1={ox} y1={oy} x2={ox} y2={oy + oh} stroke="transparent" strokeWidth="22" style={{ cursor: 'ew-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'outer', edge: 'left' }; }} />
                            <line x1={ox + ow} y1={oy} x2={ox + ow} y2={oy + oh} stroke="transparent" strokeWidth="22" style={{ cursor: 'ew-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'outer', edge: 'right' }; }} />
                            <line x1={ox} y1={oy} x2={ox + ow} y2={oy} stroke="transparent" strokeWidth="22" style={{ cursor: 'ns-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'outer', edge: 'top' }; }} />
                            <line x1={ox} y1={oy + oh} x2={ox + ow} y2={oy + oh} stroke="transparent" strokeWidth="22" style={{ cursor: 'ns-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'outer', edge: 'bottom' }; }} />
                            {/* 4 Draggable Inner Frame Edges */}
                            <line x1={ix} y1={iy} x2={ix} y2={iy + ih} stroke="transparent" strokeWidth="22" style={{ cursor: 'ew-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'inner', edge: 'left' }; }} />
                            <line x1={ix + iw} y1={iy} x2={ix + iw} y2={iy + ih} stroke="transparent" strokeWidth="22" style={{ cursor: 'ew-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'inner', edge: 'right' }; }} />
                            <line x1={ix} y1={iy} x2={ix + iw} y2={iy} stroke="transparent" strokeWidth="22" style={{ cursor: 'ns-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'inner', edge: 'top' }; }} />
                            <line x1={ix} y1={iy + ih} x2={ix + iw} y2={iy + ih} stroke="transparent" strokeWidth="22" style={{ cursor: 'ns-resize' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'inner', edge: 'bottom' }; }} />
                            {/* Visual Drag Handles */}
                            {[
                              { cx: ox, cy: oy + oh * 0.5, c: '#22d3ee' },
                              { cx: ox + ow, cy: oy + oh * 0.5, c: '#22d3ee' },
                              { cx: ox + ow * 0.5, cy: oy, c: '#22d3ee' },
                              { cx: ox + ow * 0.5, cy: oy + oh, c: '#22d3ee' },
                              { cx: ix, cy: iy + ih * 0.5, c: '#facc15' },
                              { cx: ix + iw, cy: iy + ih * 0.5, c: '#facc15' },
                              { cx: ix + iw * 0.5, cy: iy, c: '#facc15' },
                              { cx: ix + iw * 0.5, cy: iy + ih, c: '#facc15' },
                            ].map((h, hi) => (
                              <circle key={hi} cx={h.cx} cy={h.cy} r="9" fill={h.c} stroke="#020617" strokeWidth="2.5" style={{ pointerEvents: 'none' }} />
                            ))}
                          </g>
                        )}
                      </g>
                    );
                  })()}

                  {/* EDIT CORNERS MODE: 4 DRAGGABLE L-SHAPED CORNER BRACKETS */}
                  {editMode === 'corners' && draftCorners && (() => {
                    const arm = 48;
                    const defs = [
                      { k: 'tl', dx: arm, dy: arm, lbl: 'TL' },
                      { k: 'tr', dx: -arm, dy: arm, lbl: 'TR' },
                      { k: 'bl', dx: arm, dy: -arm, lbl: 'BL' },
                      { k: 'br', dx: -arm, dy: -arm, lbl: 'BR' },
                    ];
                    return defs.map((cd) => {
                      const pt = draftCorners[cd.k] || [0.5, 0.5];
                      const px = pt[0] * 1000;
                      const py = pt[1] * 1000;
                      return (
                        <g key={cd.k} style={{ cursor: 'move' }} onPointerDown={(e) => { e.stopPropagation(); geomDragRef.current = { kind: 'corner', edge: cd.k }; }}>
                          <path d={`M ${px + cd.dx} ${py} L ${px} ${py} L ${px} ${py + cd.dy}`} fill="none" stroke="#facc15" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
                          <circle cx={px} cy={py} r="14" fill="rgba(250,204,21,0.35)" stroke="#facc15" strokeWidth="2.5" />
                        </g>
                      );
                    });
                  })()}

                  {/* CONFIRMED DEFECT INDICATORS (HIDDEN DURING GEOMETRY EDIT) */}
                  {editMode === 'none' && visibleSideDefects.map(renderSvgMarker)}

                  {/* SUPERFICIAL HOLDER ARTIFACTS */}
                  {editMode === 'none' && sideArtifacts.map((a, ai) => {
                    const [ax, ay, aw, ah] = a.bbox_norm.map((v) => v * 1000);
                    return (
                      <rect
                        key={a.id || ai}
                        x={ax}
                        y={ay}
                        width={Math.max(14, aw)}
                        height={Math.max(14, ah)}
                        rx={5}
                        fill="rgba(245,158,11,0.10)"
                        stroke="#f59e0b"
                        strokeWidth="2.5"
                        strokeDasharray="6 4"
                      >
                        <title>{a.label || a.type}</title>
                      </rect>
                    );
                  })}
                </svg>

                {/* AUTHENTIC LEGENDS 10-LINE VIRTUAL CLEAR CENTERING CARD SVG OVERLAY (SOLID=ODD 1,3,5,7,9 • DASHED=EVEN 2,4,6,8,10) */}
                {showCenteringGauge && (() => {
                  const W = Math.max(100, fittedBox.w);
                  const H = Math.max(100, fittedBox.h);
                  const cardX = gaugeGeometry.ox * W;
                  const cardY = gaugeGeometry.oy * H;
                  const cardW = Math.max(40, gaugeGeometry.ow * W);
                  const cardH = Math.max(40, gaugeGeometry.oh * H);
                  const cx = cardX + cardW * 0.5;
                  const cy = cardY + cardH * 0.5;
                  const pxPerInX = cardW / gaugeGeometry.physWIn;
                  const pxPerInY = cardH / gaugeGeometry.physHIn;

                  // 10 Concentric graduated lines (1..10) spaced uniformly in physical inches:
                  // Standard (2.5"x3.5"): 0.024" per line (Line 1 = 0.024" .. Line 10 = 0.240")
                  // Mini (1.5"x2.625")   : 0.0155" per line (Line 1 = 0.0155" .. Line 10 = 0.155")
                  const unitStepIn = gaugeGeometry.isMini ? 0.0155 : 0.024;
                  const steps10 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => ({
                    n,
                    isOdd: n % 2 === 1, // SOLID = ODD, DASHED = EVEN
                    inVal: n * unitStepIn,
                    dx: n * unitStepIn * pxPerInX,
                    dy: n * unitStepIn * pxPerInY,
                  }));

                  const maxDx = steps10[9].dx;
                  const maxDy = steps10[9].dy;
                  const cornerArmX = Math.max(16, Math.min(cardW * 0.15, maxDx + 10));
                  const cornerArmY = Math.max(16, Math.min(cardH * 0.15, maxDy + 10));
                  const cornerGap = Math.max(4, Math.min(cardW, cardH) * 0.018);
                  const bullseyeR = Math.max(11, Math.min(cardW, cardH) * 0.042);
                  const dotR = Math.max(2.4, bullseyeR * 0.22);

                  // Theme palette for crisp readability on any card stock
                  const isClassic = gaugeColorMode === 'classic_black';
                  const isCyan = gaugeColorMode === 'cyan';
                  const outerCol = isClassic ? '#0f172a' : isCyan ? '#22d3ee' : '#f8fafc';
                  const oddCol = isClassic ? '#0f172a' : isCyan ? '#22d3ee' : '#38bdf8';
                  const evenCol = isClassic ? '#1e293b' : isCyan ? '#a5f3fc' : '#f8fafc';
                  const haloCol = isClassic ? 'rgba(255,255,255,0.92)' : '#020617';
                  const numFillOdd = isClassic ? '#020617' : '#38bdf8';
                  const numFillEven = isClassic ? '#0f172a' : '#fef08a';

                  const txtStyle = {
                    paintOrder: 'stroke',
                    stroke: haloCol,
                    strokeWidth: isClassic ? '2.6px' : '2.8px',
                    strokeLinecap: 'round',
                    strokeLinejoin: 'round',
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                    fontWeight: 900,
                  };

                  // Staggered diagonal label coordinates (matching the physical Legends gauge)
                  const topLeftBaseX = cardX + maxDx + 6;
                  const topRightBaseX = cardX + cardW - maxDx - 6;
                  const horizStepX = Math.max(5.5, Math.min(13, (cardW - 2 * maxDx - 24) / 11));
                  const leftTopBaseY = cardY + maxDy + 8;
                  const leftBotBaseY = cardY + cardH - maxDy - 6;
                  const vertStepY = Math.max(5.2, Math.min(11.5, (cardH - 2 * maxDy - 32) / 22));
                  const fontSizeNum = Math.max(7.2, Math.min(9.5, Math.min(cardW, cardH) * 0.025));

                  return (
                    <svg
                      viewBox={`0 0 ${W} ${H}`}
                      className="absolute inset-0 w-full h-full pointer-events-none select-none"
                      style={{ opacity: Math.max(0.2, Math.min(0.9, gaugeOpacity / 100)) }}
                    >
                      <g transform={`rotate(${gaugeGeometry.totalAngle}, ${cx}, ${cy})`}>
                        {/* Clear Acrylic Card Tint */}
                        <rect
                          x={cardX}
                          y={cardY}
                          width={cardW}
                          height={cardH}
                          rx={4}
                          fill={isClassic ? 'rgba(255, 255, 255, 0.05)' : 'rgba(14, 165, 233, 0.03)'}
                        />

                        {/* Heavy Outer Frame with Legends Corner Brackets & Subtle Corner Breaks */}
                        <path
                          d={`M ${cardX} ${cardY + cornerArmY} L ${cardX} ${cardY} L ${cardX + cornerArmX} ${cardY}
                              M ${cardX + cornerArmX + cornerGap} ${cardY} L ${cardX + cardW - cornerArmX - cornerGap} ${cardY}
                              M ${cardX + cardW - cornerArmX} ${cardY} L ${cardX + cardW} ${cardY} L ${cardX + cardW} ${cardY + cornerArmY}
                              M ${cardX + cardW} ${cardY + cornerArmY + cornerGap} L ${cardX + cardW} ${cardY + cardH - cornerArmY - cornerGap}
                              M ${cardX + cardW} ${cardY + cardH - cornerArmY} L ${cardX + cardW} ${cardY + cardH} L ${cardX + cardW - cornerArmX} ${cardY + cardH}
                              M ${cardX + cardW - cornerArmX - cornerGap} ${cardY + cardH} L ${cardX + cornerArmX + cornerGap} ${cardY + cardH}
                              M ${cardX + cornerArmX} ${cardY + cardH} L ${cardX} ${cardY + cardH} L ${cardX} ${cardY + cardH - cornerArmY}
                              M ${cardX} ${cardY + cardH - cornerArmY - cornerGap} L ${cardX} ${cardY + cornerArmY + cornerGap}`}
                          fill="none"
                          stroke={outerCol}
                          strokeWidth="3.2"
                          strokeLinecap="square"
                        />

                        {/* 10 Concentric Inner Graduated Frames: SOLID = ODD (1,3,5,7,9), DASHED = EVEN (2,4,6,8,10) */}
                        {steps10.map((st) => {
                          const rx = cardX + st.dx;
                          const ry = cardY + st.dy;
                          const rw = Math.max(8, cardW - 2 * st.dx);
                          const rh = Math.max(8, cardH - 2 * st.dy);
                          const strokeCol = st.isOdd ? oddCol : evenCol;
                          return (
                            <rect
                              key={`ring-${st.n}`}
                              x={rx}
                              y={ry}
                              width={rw}
                              height={rh}
                              fill="none"
                              stroke={strokeCol}
                              strokeWidth={st.isOdd ? '1.25' : '1.05'}
                              strokeDasharray={st.isOdd ? undefined : '4.5 3.2'}
                            />
                          );
                        })}

                        {/* Full Horizontal & Vertical Center Crosshairs (Interrupted by Center Bullseye Circle) */}
                        <line x1={cardX} y1={cy} x2={cx - bullseyeR} y2={cy} stroke={outerCol} strokeWidth="1.45" />
                        <line x1={cx + bullseyeR} y1={cy} x2={cardX + cardW} y2={cy} stroke={outerCol} strokeWidth="1.45" />
                        <line x1={cx} y1={cardY} x2={cx} y2={cy - bullseyeR} stroke={outerCol} strokeWidth="1.45" />
                        <line x1={cx} y1={cy + bullseyeR} x2={cx} y2={cardY + cardH} stroke={outerCol} strokeWidth="1.45" />

                        {/* Center Bullseye Circle & Target Dot */}
                        <circle cx={cx} cy={cy} r={bullseyeR} fill="rgba(2, 6, 23, 0.22)" stroke={outerCol} strokeWidth="1.65" />
                        <circle cx={cx} cy={cy} r={dotR} fill={outerCol} />

                        {/* Staggered Diagonal Line Numbers (1..10) on Top, Bottom, Left & Right */}
                        {steps10.map((st) => {
                          const nCol = st.isOdd ? numFillOdd : numFillEven;
                          const kIdx = Math.floor((st.n - 1) / 2); // 0..4 for odd/even diagonal staircases
                          const topY = cardY + st.dy + fontSizeNum * 0.35;
                          const botY = cardY + cardH - st.dy + fontSizeNum * 0.35;
                          const leftX = cardX + st.dx;
                          const rightX = cardX + cardW - st.dx;

                          // Top: Odd (1,3,5,7,9) on Top-Left diagonal; Even (2,4,6,8,10) on Top-Right diagonal
                          const topX = st.isOdd
                            ? topLeftBaseX + kIdx * horizStepX * 1.45
                            : topRightBaseX - kIdx * horizStepX * 1.45;
                          // Bottom: Even (2,4,6,8,10) on Bottom-Left diagonal; Odd (1,3,5,7,9) on Bottom-Right diagonal
                          const botX = !st.isOdd
                            ? topLeftBaseX + kIdx * horizStepX * 1.45
                            : topRightBaseX - kIdx * horizStepX * 1.45;

                          // Left & Right Vertical Lines: Upper & Lower 1..10 diagonal staircases
                          const upperSideY = leftTopBaseY + (st.n - 1) * vertStepY;
                          const lowerSideY = leftBotBaseY - (st.n - 1) * vertStepY;

                          return (
                            <g key={`nums-${st.n}`}>
                              <text x={topX} y={topY} textAnchor="middle" fontSize={fontSizeNum} fill={nCol} style={txtStyle}>{st.n}</text>
                              <text x={botX} y={botY} textAnchor="middle" fontSize={fontSizeNum} fill={nCol} style={txtStyle}>{st.n}</text>
                              <text x={leftX} y={upperSideY} textAnchor="middle" fontSize={fontSizeNum * 0.92} fill={nCol} style={txtStyle}>{st.n}</text>
                              <text x={leftX} y={lowerSideY} textAnchor="middle" fontSize={fontSizeNum * 0.92} fill={nCol} style={txtStyle}>{st.n}</text>
                              <text x={rightX} y={upperSideY} textAnchor="middle" fontSize={fontSizeNum * 0.92} fill={nCol} style={txtStyle}>{st.n}</text>
                              <text x={rightX} y={lowerSideY} textAnchor="middle" fontSize={fontSizeNum * 0.92} fill={nCol} style={txtStyle}>{st.n}</text>
                            </g>
                          );
                        })}

                        {/* Legends Header & Footer Callouts (50/50 through 65/35 + Dashed/Solid Legend) */}
                        <text x={cx} y={cardY - 4} textAnchor="middle" fontSize={Math.max(8, fontSizeNum)} fill="#38bdf8" style={txtStyle}>
                          LEGENDS CENTERING GAUGE • {gaugeGeometry.isMini ? 'MINI 1.5×2.625' : 'STD 2.5×3.5'} • L/R {liveCentStats.lr} | T/B {liveCentStats.tb}
                        </text>
                        <text x={cx} y={cy + bullseyeR + 13} textAnchor="middle" fontSize={Math.max(7.2, fontSizeNum * 0.88)} fill="#e2e8f0" style={txtStyle}>
                          SOLID = ODD (1,3,5,7,9) • DASHED = EVEN (2,4,6,8,10)
                        </text>
                        <text x={cx} y={cy + bullseyeR + 24} textAnchor="middle" fontSize={Math.max(7.2, fontSizeNum * 0.88)} fill="#67e8f9" style={txtStyle}>
                          50/50 (N-N) • 53/47 (9-8) • 55/45 (6-5) • 58/42 (7-5) • 60/40 (3-2 / 6-4) • 65/35 (9-5)
                        </text>
                      </g>
                    </svg>
                  );
                })()}
              </div>
            )}

            {/* LEGENDS CENTERING PERCENTAGES REFERENCE CARD POPOVER (MATCHING PHYSICAL CHART: RED = 60/40 OR BETTER) */}
            {showCenteringGauge && showLegendsChart && (
              <div className="absolute top-9 right-2.5 z-20 w-72 bg-slate-950/95 backdrop-blur-md border border-cyan-500/60 rounded-xl p-2.5 shadow-2xl text-[10px] select-none">
                <div className="flex items-center justify-between border-b border-slate-800 pb-1 mb-1.5">
                  <div>
                    <div className="font-black text-white uppercase tracking-wide text-[10.5px]">📏 Centering Percentages</div>
                    <div className="text-[9px] text-slate-400 font-semibold">RIGHT/LEFT + TOP/BOTTOM LINE PAIRS</div>
                  </div>
                  <button type="button" onClick={() => setShowLegendsChart(false)} className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold">✕</button>
                </div>
                <div className="grid grid-cols-3 gap-x-2 gap-y-0.5 font-mono text-[9.5px]">
                  {[
                    ['2-1: 66/34', false], ['6-4: 60/40', true],  ['8-8: 50/50', true],
                    ['2-2: 50/50', true],  ['6-5: 55/45', true],  ['9-4: 69/31', false],
                    ['3-1: 75/25', false], ['6-6: 50/50', true],  ['9-5: 64/36', false],
                    ['3-2: 60/40', true],  ['7-3: 70/30', false], ['9-6: 60/40', true],
                    ['3-3: 50/50', true],  ['7-4: 64/36', false], ['9-7: 56/44', true],
                    ['4-2: 67/33', false], ['7-5: 58/42', true],  ['9-8: 53/47', true],
                    ['4-3: 57/43', true],  ['7-6: 54/46', true],  ['9-9: 50/50', true],
                    ['4-4: 50/50', true],  ['7-7: 50/50', true],  ['10-5: 67/33', false],
                    ['5-3: 63/37', false], ['8-5: 62/38', false], ['10-6: 63/37', false],
                    ['5-4: 56/44', true],  ['8-6: 57/43', true],  ['10-7: 59/41', true],
                    ['5-5: 50/50', true],  ['8-7: 53/47', true],  ['10-8: 56/44', true],
                    ['6-3: 67/33', false], ['10-9: 53/47', true], ['10-10: 50/50', true],
                  ].map(([pairTxt, isBetter6040], idx) => (
                    <div key={idx} className={`font-bold ${isBetter6040 ? 'text-rose-400' : 'text-slate-300'}`}>
                      {pairTxt}
                    </div>
                  ))}
                </div>
                <div className="mt-1.5 pt-1 border-t border-slate-800 text-center font-extrabold text-[9.5px] text-rose-400 uppercase tracking-wider">
                  RED INDICATES 60/40 OR BETTER
                </div>
              </div>
            )}

            {/* CRISP HTML CENTERING RATIO BADGE (NEVER CLIPPED IN PORTRAIT OR LANDSCAPE) */}
            {(activeLayers.centering || editMode === 'centering' || showCenteringGauge) && sideCent && (
              <div className="absolute top-1.5 left-1/2 -translate-x-1/2 px-2.5 py-0.5 rounded-xl bg-slate-950/90 border border-cyan-500/70 text-cyan-200 font-mono text-[10.5px] font-bold shadow pointer-events-none whitespace-nowrap">
                {activeSide} Centering: L/R {liveCentStats.lr} • T/B {liveCentStats.tb}
                {showCenteringGauge ? ` • Gauge ${gaugeGeometry.isMini ? 'Mini' : 'Std'} (${gaugeGeometry.totalAngle >= 0 ? `+${gaugeGeometry.totalAngle.toFixed(1)}°` : `${gaugeGeometry.totalAngle.toFixed(1)}°`})` : ''}
              </div>
            )}

            {editMode !== 'none' && (
              <div className="absolute bottom-1.5 left-1/2 -translate-x-1/2 px-2.5 py-0.5 rounded-xl bg-slate-950/90 border border-amber-500/70 text-amber-200 text-[10.5px] font-semibold pointer-events-none whitespace-nowrap">
                {editMode === 'centering' ? 'Drag cyan (outer) & yellow (inner) edge handles, then Save & Recalculate' : 'Drag TL / TR / BL / BR corner brackets onto card tips, then Save & Recalculate'}
              </div>
            )}

            {loadingDiag && (
              <div className="absolute bottom-2 left-2 px-2.5 py-1 rounded-xl bg-slate-950/90 border border-sky-700 text-sky-300 text-xs font-bold">
                ⏳ Analyzing surface &amp; centering geometry...
              </div>
            )}
            {diagError && (
              <div className="absolute bottom-2 left-2 px-2.5 py-1 rounded-xl bg-rose-950/90 border border-rose-600 text-rose-200 text-xs font-bold">
                ❌ {diagError}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANE: PSA/BGS CARDS + CLICKABLE NOTES TOGGLES + COMPACT DEFECT GRID + ENLARGED LOUPE OVERLAY */}
        <div className={`lg:col-span-6 ${skin.cardBg} border ${skin.border} rounded-2xl p-2.5 flex flex-col gap-2 min-h-0 h-full overflow-hidden relative`}>
          {/* TOP: AUTHENTIC PSA & BECKETT SUMMARY CARDS (NON-TOGGLE) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 shrink-0">
            {renderPsaCard()}
            {renderBgsCard()}
          </div>

          {/* MIDDLE: 4 CLICKABLE GRADING NOTES BOXES (CATEGORY TOGGLES) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 shrink-0 text-[11px]">
            {noteBoxes.map((nb) => {
              const isOn = Boolean(activeLayers[nb.key]);
              return (
                <button
                  key={nb.key}
                  type="button"
                  onClick={() => {
                    setIsolatedDefectId('');
                    toggleLayer(nb.key);
                  }}
                  className={`text-left rounded-xl p-2.5 border transition ${
                    isOn
                      ? 'bg-slate-950/90 border-sky-500/70 ring-1 ring-sky-500/30'
                      : 'bg-slate-950/40 border-slate-800/70 opacity-55 hover:opacity-85'
                  }`}
                >
                  <div className="flex items-center justify-between gap-1 mb-0.5">
                    <span className="font-bold text-slate-200 uppercase text-[10px]">{nb.icon} {nb.title}</span>
                    <span className={`text-[9.5px] font-bold px-1.5 py-0.2 rounded ${isOn ? 'bg-sky-950 text-sky-300 border border-sky-700/60' : 'bg-slate-900 text-slate-500'}`}>
                      {isOn ? '✓ Shown' : 'Hidden'}
                    </span>
                  </div>
                  <div className="text-slate-300 leading-snug">{nb.text}</div>
                </button>
              );
            })}
          </div>

          {Array.isArray(notesByCat.advisories) && notesByCat.advisories.length > 0 && (
            <div className="bg-amber-950/40 border border-amber-700/60 rounded-xl px-3 py-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-amber-200 shrink-0">
              <span>⚠️ {notesByCat.advisories.join(' • ')}</span>
              <button type="button" onClick={() => setShowArtifacts((s) => !s)} className="px-2 py-0.5 rounded-lg bg-amber-900/70 hover:bg-amber-800 text-[10px] font-bold">
                {showArtifacts ? 'Hide Artifacts' : 'Show Ignored Artifacts'}
              </button>
            </div>
          )}

          {/* BOTTOM: COMPACT ACTIVE-SIDE DEFECT GRID (FIXED TILE PROPORTIONS, INTERNAL SCROLL ONLY) */}
          <div className="flex-1 min-h-0 bg-slate-950/85 border border-slate-800 rounded-2xl p-2.5 flex flex-col gap-2 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] shrink-0">
              <span className="font-bold text-white uppercase tracking-wider">
                🔍 {activeSide} Detected Issues ({activeSideDefectsAll.length})
              </span>
              <div className="flex items-center gap-2">
                {anyFilteredOrIsolated && (
                  <button type="button" onClick={showAllMarkers} className="px-2 py-0.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-[10px] font-bold">
                    👁️ Show All
                  </button>
                )}
                <span className="text-slate-400">Click any tile to isolate &amp; inspect</span>
              </div>
            </div>

            {activeSideDefectsAll.length === 0 ? (
              <div className="flex-1 flex items-center justify-center rounded-xl border border-dashed border-slate-800 text-xs text-emerald-300/90 px-4">
                ✨ Clean {activeSide} — no permanent corner, edge, or surface defects detected.
              </div>
            ) : (
              <div className="flex-1 min-h-0 grid grid-cols-3 xl:grid-cols-4 gap-2.5 auto-rows-max content-start overflow-y-auto pr-1">
                {activeSideDefectsAll.map((d, di) => {
                  const isCatActive = Boolean(activeLayers[String(d.category || 'surface')]);
                  const isIso = isolatedDefectId === d.id;
                  const cropUrl = buildCropUrl(activeSide, d.bbox_norm || [0.35, 0.35, 0.2, 0.2], 0.04, 200);
                  return (
                    <button
                      key={d.id || di}
                      type="button"
                      onClick={() => {
                        setLoupeZoom(1.0);
                        setIsolatedDefectId(d.id);
                      }}
                      className={`rounded-xl border overflow-hidden flex flex-col text-left transition ${
                        isIso
                          ? 'border-amber-400 ring-2 ring-amber-400/60 bg-slate-900'
                          : isCatActive
                          ? 'border-rose-600/70 bg-slate-900 hover:border-rose-400'
                          : 'border-slate-800 bg-slate-900/60 opacity-35 grayscale hover:opacity-70'
                      }`}
                    >
                      <div className="relative w-full aspect-square bg-slate-950">
                        {cropUrl && <img src={cropUrl} alt={d.label || d.type} className="w-full h-full object-cover" />}
                        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full pointer-events-none">
                          {d.marker_style === 'box' ? (
                            <rect x="22" y="22" width="56" height="56" rx="6" fill="none" stroke="#ef4444" strokeWidth="4" />
                          ) : d.marker_style === 'arrow' ? (
                            <g>
                              <circle cx="50" cy="50" r="24" fill="none" stroke="#ef4444" strokeWidth="4" />
                              <line x1="80" y1="80" x2="52" y2="52" stroke="#ef4444" strokeWidth="4" />
                            </g>
                          ) : (
                            <circle cx="50" cy="50" r="28" fill="none" stroke="#ef4444" strokeWidth="4" />
                          )}
                        </svg>
                        <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-slate-950/85 text-[9px] font-bold uppercase text-slate-200">{d.category || 'surface'}</span>
                        <span className="absolute top-1 right-1 px-1.5 py-0.5 rounded bg-rose-950/90 text-[9px] font-mono font-bold text-rose-200">-{Number(d.penalty ?? d.severity ?? 0.5).toFixed(1)}</span>
                      </div>
                      <div className="p-1.5 text-[10.5px] font-semibold text-slate-200 leading-tight line-clamp-2">
                        {d.label || d.type}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* RIGHT-SIDE ENLARGED LOUPE POPUP OVERLAY (LEFT MAIN CARD REMAINS VISIBLE) */}
          {isolatedDefect && (
            <div className="absolute inset-2 z-20 bg-slate-950/95 backdrop-blur-md border-2 border-amber-400/80 rounded-2xl p-4 flex flex-col gap-3 shadow-2xl">
              <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-2 shrink-0">
                <div className="min-w-0">
                  <div className="text-[10px] font-mono uppercase text-amber-300">🔍 Enlarged Defect Loupe — {isolatedDefect.side}</div>
                  <div className="text-sm font-extrabold text-white truncate">{isolatedDefect.label || isolatedDefect.type}</div>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="flex items-center bg-slate-900 border border-slate-700 rounded-lg px-1.5 py-0.5 text-xs gap-1">
                    <button type="button" onClick={() => setLoupeZoom((z) => Math.max(1.0, Number((z - 0.5).toFixed(1))))} className="px-1 font-bold text-slate-300 hover:text-white">−</button>
                    <span className="font-mono text-[11px] text-sky-300 w-10 text-center">{Math.round(loupeZoom * 100)}%</span>
                    <button type="button" onClick={() => setLoupeZoom((z) => Math.min(4.0, Number((z + 0.5).toFixed(1))))} className="px-1 font-bold text-slate-300 hover:text-white">+</button>
                  </div>
                  <button type="button" onClick={() => setIsolatedDefectId('')} className="px-2.5 py-1 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-200">✕ Close</button>
                </div>
              </div>

              <div className="flex-1 min-h-0 flex items-center justify-center bg-black/70 border border-slate-800 rounded-xl overflow-hidden relative">
                <div className="relative w-64 h-64 overflow-hidden rounded-xl" style={{ transform: `scale(${loupeZoom})`, transformOrigin: 'center center' }}>
                  <img
                    src={buildCropUrl(isolatedDefect.side || activeSide, isolatedDefect.bbox_norm || [0.35, 0.35, 0.2, 0.2], 0.04, 384)}
                    alt={isolatedDefect.label || isolatedDefect.type}
                    className="w-full h-full object-cover"
                  />
                  <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full pointer-events-none">
                    {isolatedDefect.marker_style === 'box' ? (
                      <rect x="22" y="22" width="56" height="56" rx="6" fill="none" stroke="#ef4444" strokeWidth="3.5" />
                    ) : isolatedDefect.marker_style === 'arrow' ? (
                      <g>
                        <circle cx="50" cy="50" r="22" fill="none" stroke="#ef4444" strokeWidth="3.5" />
                        <line x1="80" y1="80" x2="52" y2="52" stroke="#ef4444" strokeWidth="3.5" />
                      </g>
                    ) : (
                      <circle cx="50" cy="50" r="26" fill="none" stroke="#ef4444" strokeWidth="3.5" />
                    )}
                  </svg>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs space-y-1.5 shrink-0">
                <div className="font-bold text-white">{isolatedDefect.label || isolatedDefect.type}</div>
                <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-300 font-mono">
                  <span>Category: <strong className="text-sky-300 uppercase">{isolatedDefect.category || 'surface'}</strong></span>
                  <span>Side: <strong className="text-white">{isolatedDefect.side}</strong></span>
                  <span>Confidence: <strong className="text-emerald-300">{Math.round(Number(isolatedDefect.confidence || 0.8) * 100)}%</strong></span>
                  <span>Penalty: <strong className="text-rose-400">-{Number(isolatedDefect.penalty ?? isolatedDefect.severity ?? 0.5).toFixed(1)}</strong></span>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                <button type="button" onClick={showAllMarkers} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-sky-300">
                  👁️ Show All Markers
                </button>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      fetch(`${NODE_API_BASE}/grading/flag-error`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                          targetType,
                          sku,
                          batchName: effectiveBatch,
                          errorType: 'not_a_defect_artwork',
                          side: isolatedDefect.side || activeSide,
                          targetItemId: isolatedDefect.id,
                          notes: '1-click artwork/photo dismissal from loupe',
                        }),
                      })
                        .then((r) => r.json())
                        .then((res) => {
                          if (res?.success) {
                            if (res.diagnostics) setDiagnostics(res.diagnostics);
                            if (onCardUpdated) onCardUpdated(res);
                            setIsolatedDefectId('');
                            const gb = res.gradesBefore || {};
                            const ga = res.gradesAfter || {};
                            if (pushNotification) {
                              pushNotification(
                                `Dismissed Artwork False Positive — SKU ${sku}`,
                                `PSA ${gb.Est_PSA || '?'} → ${ga.Est_PSA || '?'} | BGS ${gb.Est_BGS || '?'} → ${ga.Est_BGS || '?'}`,
                                'Grading',
                                'success'
                              );
                            }
                          }
                        });
                    }}
                    className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow"
                  >
                    ✓ Not a Defect
                  </button>
                  <button
                    type="button"
                    onClick={() => { setFlagPresetId(isolatedDefect.id); setShowFlagModal(true); }}
                    className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold shadow"
                  >
                    🚩 Flag / Report Error
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {showFlagModal && (
        <FlagGradingErrorModal
          card={card}
          targetType={targetType}
          batchName={effectiveBatch}
          diagnostics={diagnostics}
          initialSide={activeSide}
          initialTargetItemId={flagPresetId || isolatedDefectId}
          skin={skin}
          onClose={() => setShowFlagModal(false)}
          onSubmitted={(res) => {
            if (res.diagnostics) setDiagnostics(res.diagnostics);
            if (onCardUpdated) onCardUpdated(res);
            setIsolatedDefectId('');
            const gb = res.gradesBefore || {};
            const ga = res.gradesAfter || {};
            if (pushNotification) {
              pushNotification(
                res.resetOverrides ? `Overrides Reset — SKU ${sku}` : `Grade Re-Evaluated — SKU ${sku}`,
                `PSA ${gb.Est_PSA || '?'} → ${ga.Est_PSA || '?'} | BGS ${gb.Est_BGS || '?'} → ${ga.Est_BGS || '?'}`,
                'Grading',
                'success'
              );
            }
          }}
        />
      )}
    </div>
  );
}

export default function App() {
  const [skinKey, setSkinKey] = useState(() => resolveChromePulseSkinKey(localStorage.getItem('tabulas_skin')));
  const skin = CHROME_PULSE_SKINS[skinKey] || CHROME_PULSE_SKINS.screenshot_signature_3d;
  const [devMode, setDevMode] = useState(() => localStorage.getItem('tabulas_dev_mode') === 'true');

  const [activePage, setActivePage] = useState('dashboard');
  const [navPinned, setNavPinned] = useState(false);
  const [navHovered, setNavHovered] = useState(false);
  const [hoveredCatId, setHoveredCatId] = useState(null);
  const [unlockedHiddenPages, setUnlockedHiddenPages] = useState({});

  const activeCategoryId = useMemo(
    () => (
      activePage === 'live_monitor' || activePage === 'dashboard'
        ? ''
        : (NAV_CATEGORIES.find((c) => c.items.some((it) => it.id === activePage))?.id || 'inventory_mgmt')
    ),
    [activePage]
  );

  const [showMonitor, setShowMonitor] = useState(false);
  const [monitorPinned, setMonitorPinned] = useState(false);
  const [previousPageBeforeMonitor, setPreviousPageBeforeMonitor] = useState('dashboard');
  const [dashboardSummary, setDashboardSummary] = useState({
    neverScrapedSets: [],
    setsNeedingImages: [],
    gradingCandidatesCount: 0,
    gradingUpsideTotal: 0,
    unprintedLabelsCount: 0,
    sellableMissingDraftsCount: 0,
    generatedAt: '',
  });
  const [dashboardDonutMode, setDashboardDonutMode] = useState('set');
  const [showAllNeverScraped, setShowAllNeverScraped] = useState(false);
  const [customTodos, setCustomTodos] = useState(() => {
    try {
      const raw = localStorage.getItem('tabulas_custom_todos_v1');
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (_e) {
      return [];
    }
  });
  const [customTodoInput, setCustomTodoInput] = useState('');
  useEffect(() => {
    try {
      localStorage.setItem('tabulas_custom_todos_v1', JSON.stringify(customTodos));
    } catch (_e) {}
  }, [customTodos]);

  const addCustomTodo = () => {
    const txt = String(customTodoInput || '').trim();
    if (!txt) return;
    setCustomTodos((prev) => [{ id: `todo_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, text: txt, done: false, createdAt: new Date().toLocaleDateString() }, ...prev]);
    setCustomTodoInput('');
  };
  const toggleCustomTodo = (id) => {
    setCustomTodos((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
  };
  const deleteCustomTodo = (id) => {
    setCustomTodos((prev) => prev.filter((t) => t.id !== id));
  };
  const clearCompletedCustomTodos = () => {
    setCustomTodos((prev) => prev.filter((t) => !t.done));
  };
  const [invertTerminalLogs, setInvertTerminalLogs] = useState(true);
  const [selectedMonitorLane, setSelectedMonitorLane] = useState('slot_1');
  const [showArchivedRollbacks, setShowArchivedRollbacks] = useState(false);
  const [archivedRollbackSnaps, setArchivedRollbackSnaps] = useState([]);

  const openMonitorPage = (laneKey = null) => {
    if (laneKey) setSelectedMonitorLane(laneKey);
    if (activePage !== 'live_monitor') setPreviousPageBeforeMonitor(activePage);
    setShowMonitor(false);
    setActivePage('live_monitor');
  };

  const openLogsFolder = () => {
    fetch(`${NODE_API_BASE}/logs/open-folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then((r) => r.json())
      .then((res) => {
        if (!res?.success) pushNotification('Logs Folder', res?.error || 'Could not open Logs folder.', 'System', 'warning');
      })
      .catch(() => pushNotification('Logs Folder', `Logs live at ${STORAGE_ROOT}\\Logs\\Logs\\`, 'System', 'info'));
  };

  const [notifications, setNotifications] = useState([]);
  const [showNotifPopup, setShowNotifPopup] = useState(false);
  const [activeToasts, setActiveToasts] = useState([]);
  const notifContainerRef = useRef(null);

  useEffect(() => {
    const onDocClick = (e) => {
      if (showNotifPopup && notifContainerRef.current && !notifContainerRef.current.contains(e.target)) {
        setShowNotifPopup(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [showNotifPopup]);

  const [backendConnected, setBackendConnected] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [inventoryDirty, setInventoryDirty] = useState(false);
  const [incomingScans, setIncomingScans] = useState([]);
  const [batches, setBatches] = useState([]);
  const [trackedSets, setTrackedSets] = useState([]);
  const [trackedSetsDirty, setTrackedSetsDirty] = useState(false);
  const trackedSetsDirtyRef = useRef(false);
  trackedSetsDirtyRef.current = trackedSetsDirty;
  const [directoryRows, setDirectoryRows] = useState([]);
  const [setCart, setSetCart] = useState([]);
  const [showCartSidebar, setShowCartSidebar] = useState(false);
  const [cartPinned, setCartPinned] = useState(false);
  const [marketData, setMarketData] = useState({ tiers: { PSA: [], BGS: [] }, comps: [], history: [], alerts: [], alertSettings: {} });
  const [lotsData, setLotsData] = useState({ lots: [], cardLevel: [] });
  const [listingDrafts, setListingDrafts] = useState([]);
  const [soldCards, setSoldCards] = useState([]);
  const [expensesLedger, setExpensesLedger] = useState([]);
  const [editingExpenseIdx, setEditingExpenseIdx] = useState(null);
  const [expenseRowDraft, setExpenseRowDraft] = useState(null);
  const [expenseIsNewDraft, setExpenseIsNewDraft] = useState(false);
  const [expenseCatFilter, setExpenseCatFilter] = useState('All Categories');
  const [expenseSearch, setExpenseSearch] = useState('');
  const [pricingStrategy, setPricingStrategy] = useState({
    market_markup_pct: 50.0, make_offer_markup_pct: 75.0, rookie_serial_bonus_pct: 15.0,
    gem_mint_pregrade_bonus_pct: 20.0, global_min_price_floor: 1.49, target_min_net_profit_per_card: 0.65,
    per_card_supplies_cost: 0.18, per_order_packaging_cost: 0.35, per_order_shipping_cost: 0.0,
    marketplace_fee_pct: 13.25, fixed_transaction_fee: 0.30,
  });
  const [strategyRecs, setStrategyRecs] = useState({ summary: {}, recommendations: [] });
  const [schedules, setSchedules] = useState([]);
  const [moduleList, setModuleList] = useState([]);
  const [updaterInfo, setUpdaterInfo] = useState({ status: 'UP_TO_DATE', current_version: APP_VERSION, pending_count: 0, message: 'Click "Check for Updates".', packages: [], snapshots: [] });
  const [liveLanes, setLiveLanes] = useState({});
  const [liveLogs, setLiveLogs] = useState({});
  const [selectedTrackedUrls, setSelectedTrackedUrls] = useState([]);
  const [trackedSearch, setTrackedSearch] = useState('');
  const [trackedSportF, setTrackedSportF] = useState('All Sports');
  const [trackedYearF, setTrackedYearF] = useState('All Years');
  const [trackedMfgF, setTrackedMfgF] = useState('All Manufacturers');
  const [trackedDupOnly, setTrackedDupOnly] = useState(false);
  const [trackedSortBy, setTrackedSortBy] = useState('Folder_Name');
  const [trackedSortDir, setTrackedSortDir] = useState('asc');
  const [showManualAddInv, setShowManualAddInv] = useState(false);
  const [manualCard, setManualCard] = useState({ Set: '2026 Topps Baseball', Subset: 'Base', CardNumber: '', Player: '', Team: '', PrintRun: '', HoldTag: 'For Sale', RawPrice: '1.00', Qty: 1 });
  const [showCompsExplorer, setShowCompsExplorer] = useState(false);
  const [compsSearch, setCompsSearch] = useState('');
  const [showRollbackSnapshots, setShowRollbackSnapshots] = useState(false);
  const [showSkinPopover, setShowSkinPopover] = useState(false);
  const [toggledCats, setToggledCats] = useState({});
  const skinPopoverRef = useRef(null);

  useEffect(() => {
    const onOutsideSkinClick = (e) => {
      if (showSkinPopover && skinPopoverRef.current && !skinPopoverRef.current.contains(e.target)) {
        setShowSkinPopover(false);
      }
    };
    document.addEventListener('mousedown', onOutsideSkinClick);
    return () => document.removeEventListener('mousedown', onOutsideSkinClick);
  }, [showSkinPopover]);
  const [alertCfg, setAlertCfg] = useState({
    min_grade_net_gain: 15.0, min_grade_roi_pct: 35.0, price_spike_pct: 25.0,
    email_enabled: false, delivery_method: 'ntfy_topic', ntfy_topic: 'tabulas_mroux_cards',
    webhook_url: '', recipient_email: 'michael.j.roux@gmail.com',
  });
  const [invPage, setInvPage] = useState(1);
  const [invPageSize, setInvPageSize] = useState(250);
  const [chkPage, setChkPage] = useState(1);
  const [chkLimit, setChkLimit] = useState(350);
  const [dirPage, setDirPage] = useState(1);
  const [dirPageSize, setDirPageSize] = useState(250);
  const [compPage, setCompPage] = useState(1);
  const [compPageSize, setCompPageSize] = useState(250);
  const [preselectSubsets, setPreselectSubsets] = useState(['Base']);
  const [manualSubsets, setManualSubsets] = useState(['Base']);

  const [chkData, setChkData] = useState({ rows: [], knownSets: ['2026 Topps Baseball'], knownYears: [], knownSubsets: [], totalRecords: 0, totalMatchingCount: 0, glossary: DEFAULT_GLOSSARY });
  const [chkSetF, setChkSetF] = useState('All Sets');
  const [chkYearF, setChkYearF] = useState('All Years');
  const [chkSubsetF, setChkSubsetF] = useState('All Subsets');
  const [chkAttrF, setChkAttrF] = useState('All Attributes');
  const [chkStatusF, setChkStatusF] = useState('All Cards');
  const [chkSearchF, setChkSearchF] = useState('');

  const [selectedIncomingBatch, setSelectedIncomingBatch] = useState('ALL');
  const [preselectSet, setPreselectSet] = useState('🌐 Mixed / Auto-Detect Set');
  const [preselectSubset, setPreselectSubset] = useState('🌐 Auto-Detect Subset / Parallel');
  const [defaultRawPrice, setDefaultRawPrice] = useState('1.00');
  const [ingestParallelHeavy, setIngestParallelHeavy] = useState(false);
  const [ingestAutoSplitFlatbed, setIngestAutoSplitFlatbed] = useState(true);
  const [ingestCardSightFb, setIngestCardSightFb] = useState(true);
  const [activeBatchName, setActiveBatchName] = useState('');
  const activeBatchNameRef = useRef('');
  const prevLaneStatesRef = useRef({});
  const [batchSelectedSkus, setBatchSelectedSkus] = useState([]);
  const [batchDraftEdits, setBatchDraftEdits] = useState({});
  const [batchReviewFilter, setBatchReviewFilter] = useState('all');
  const [batchConfFilter, setBatchConfFilter] = useState('all');
  const [batchSubsetFilter, setBatchSubsetFilter] = useState('All Subsets');
  const [batchSearchQ, setBatchSearchQ] = useState('');
  const [batchPage, setBatchPage] = useState(1);
  const [batchPageSize, setBatchPageSize] = useState(250);
  const [batchMoveAndArchive, setBatchMoveAndArchive] = useState(true);
  const [confirmClearBatchName, setConfirmClearBatchName] = useState('');
  const [selectedCommitBatches, setSelectedCommitBatches] = useState([]);
  const [committingBatches, setCommittingBatches] = useState(false);
  const [confirmDeleteBatchSkus, setConfirmDeleteBatchSkus] = useState(false);
  const [confirmDeleteRowSku, setConfirmDeleteRowSku] = useState('');
  const [guidedScopeMode, setGuidedScopeMode] = useState('selected_or_flagged');
  const [guidedSearchQ, setGuidedSearchQ] = useState('');
  const [guidedPage, setGuidedPage] = useState(1);
  const [guidedPageSize, setGuidedPageSize] = useState(15);
  const [deepDiveIdx, setDeepDiveIdx] = useState(0);
  const mainScrollRef = useRef(null);
  const [liveClockSec, setLiveClockSec] = useState(() => Date.now() / 1000);

  useEffect(() => {
    activeBatchNameRef.current = activeBatchName;
  }, [activeBatchName]);

  const [invSetFilter, setInvSetFilter] = useState('All Sets');
  const [invHoldFilter, setInvHoldFilter] = useState('All Hold Tags');
  const [invStatusFilter, setInvStatusFilter] = useState('All Statuses');
  const [invSearch, setInvSearch] = useState('');
  const [selectedInvSkus, setSelectedInvSkus] = useState([]);
  const [invEditorIdx, setInvEditorIdx] = useState(0);
  const [invEditorImgBust, setInvEditorImgBust] = useState(0);
  const [batchImgBust, setBatchImgBust] = useState(0);
  const [reprocessingInvSkus, setReprocessingInvSkus] = useState({});
  const [reprocessingBatchSkus, setReprocessingBatchSkus] = useState({});
  const activeInvEditorSkuRef = useRef('');
  const [invEditorMode, setInvEditorMode] = useState('individual');
  const [invEditorDrafts, setInvEditorDrafts] = useState({});
  const [invEditorSearchQ, setInvEditorSearchQ] = useState('');
  const [invEditorPage, setInvEditorPage] = useState(1);
  const [invEditorPageSize, setInvEditorPageSize] = useState(15);
  const [showInvEditMenu, setShowInvEditMenu] = useState(false);
  const invEditMenuRef = useRef(null);
  const [bulkEditChecks, setBulkEditChecks] = useState({});
  const [bulkEditVals, setBulkEditVals] = useState({
    Set: '', Subset: 'Base', Team: '', 'Print Run': '', Attributes: '',
    Status: 'In Stock', Hold_Tag: 'For Sale', Raw_Price: '1.00', Rec_Sale_Price: '1.49',
    Label_Printed: 'False', Needs_Review: 'False', Grading_Notes: '',
  });

  useEffect(() => {
    const onOutsideInvEdit = (e) => {
      if (showInvEditMenu && invEditMenuRef.current && !invEditMenuRef.current.contains(e.target)) {
        setShowInvEditMenu(false);
      }
    };
    document.addEventListener('mousedown', onOutsideInvEdit);
    return () => document.removeEventListener('mousedown', onOutsideInvEdit);
  }, [showInvEditMenu]);

  const [labelTemplate, setLabelTemplate] = useState('R037L');
  const [labelXOff, setLabelXOff] = useState(0.0);
  const [labelYOff, setLabelYOff] = useState(0.0);
  const [labelDrawOutlines, setLabelDrawOutlines] = useState(false);
  const [showLabelSettingsGear, setShowLabelSettingsGear] = useState(false);
  const [labelIntakeBatch, setLabelIntakeBatch] = useState('All Intake Batches');
  const [peeledCellsByPage, setPeeledCellsByPage] = useState({ 1: {} });
  const [labelPreviewPage, setLabelPreviewPage] = useState(1);
  const [lastLabelPdf, setLastLabelPdf] = useState(null);
  const [reprintMode, setReprintMode] = useState('unprinted_only');
  const [reprintSkuInput, setReprintSkuInput] = useState('');
  const [stagedReprintSkus, setStagedReprintSkus] = useState([]);
  const [labelQueueSearch, setLabelQueueSearch] = useState('');
  const [sampleLabelInitialized, setSampleLabelInitialized] = useState(false);
  const [sampleLabel, setSampleLabel] = useState({ SKU: '1000001', Set: '2026 Topps Baseball', CardNumber: '1', Player: 'Aaron Judge', Team: 'New York Yankees', Subset: 'Gold Foil', PrintRun: '50', League: 'MLB' });

  // Card-Level Inventory State
  const [cardLevelRows, setCardLevelRows] = useState([]);
  const [cardLevelEdits, setCardLevelEdits] = useState({});
  const [clSetF, setClSetF] = useState('All Sets');
  const [clSurplusOnly, setClSurplusOnly] = useState(false);
  const [clSearch, setClSearch] = useState('');
  const [clPage, setClPage] = useState(1);
  const [clPageSize, setClPageSize] = useState(250);

  const [cleanSlateChecklists, setCleanSlateChecklists] = useState(false);
  const [forceFullReverify, setForceFullReverify] = useState(false);
  const [planPreview, setPlanPreview] = useState(null);
  const [plansByMode, setPlansByMode] = useState(null);
  const [planPreviewLoading, setPlanPreviewLoading] = useState(false);
  const [planPreviewMode, setPlanPreviewMode] = useState('checklist_only');
  const [showMaintenanceWidget, setShowMaintenanceWidget] = useState(false);

  const fetchScraperPlanPreview = (modeKey, targetMap, forceRefreshOverride) => {
    const useMode = modeKey || planPreviewMode || 'checklist_only';
    const useForce = typeof forceRefreshOverride === 'boolean' ? forceRefreshOverride : forceFullReverify;
    setPlanPreviewMode(useMode);
    setPlanPreviewLoading(true);
    fetch(`${NODE_API_BASE}/scraper/plan-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: useMode,
        target_queue: targetMap || null,
        force_refresh: useForce,
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res && res.success) {
          if (res.plans_by_mode && typeof res.plans_by_mode === 'object') {
            setPlansByMode(res.plans_by_mode);
            setPlanPreview(res.plans_by_mode[useMode] || res.plan || null);
          } else if (res.plan) {
            setPlanPreview(res.plan);
          }
        }
      })
      .catch(() => {})
      .finally(() => setPlanPreviewLoading(false));
  };

  const selectPlanPreviewMode = (mk, targetMap) => {
    setPlanPreviewMode(mk);
    if (plansByMode && plansByMode[mk]) {
      setPlanPreview(plansByMode[mk]);
      return;
    }
    fetchScraperPlanPreview(mk, targetMap);
  };

  const [dirSearch, setDirSearch] = useState('');
  const [dirSportFilter, setDirSportFilter] = useState('All Sports');
  const [dirMfgFilter, setDirMfgFilter] = useState('All Manufacturers');
  const [dirCategoryFilter, setDirCategoryFilter] = useState('All Categories');
  const [dirEraFilter, setDirEraFilter] = useState('All Eras');
  const [dirHideTracked, setDirHideTracked] = useState(false);
  const [showQuickAddWidget, setShowQuickAddWidget] = useState(false);
  const [showCrawlWidget, setShowCrawlWidget] = useState(false);
  const [crawlOpts, setCrawlOpts] = useState(() => ({
    sports: ['Baseball', 'Football', 'Basketball'],
    startYear: 2020,
    endYear: new Date().getFullYear(),
    fetchImagePct: true,
    maxImagePctFetches: 150,
  }));
  const [quickAdd, setQuickAdd] = useState({ url: '', folder: '', sport: 'Baseball', year: String(new Date().getFullYear()), manufacturer: 'Topps' });

  const [availabilityExpanded, setAvailabilityExpanded] = useState(false);
  const [gradeRecSetFilter, setGradeRecSetFilter] = useState('All Sets');
  const [inspectorIdx, setInspectorIdx] = useState(0);
  const [inspectorMode, setInspectorMode] = useState('deep_dive');
  const [recalculatingStrategy, setRecalculatingStrategy] = useState(false);

  const [lotCatF, setLotCatF] = useState('All Categories');
  const [lotSportF, setLotSportF] = useState('All Sports');
  const [lotSetF, setLotSetF] = useState('All Sets');
  const [lotTeamF, setLotTeamF] = useState('');
  const [lotPlayerF, setLotPlayerF] = useState('');

  const [writerSku, setWriterSku] = useState('');
  const [editingDraftId, setEditingDraftId] = useState('');
  const [writerCopy, setWriterCopy] = useState({ SEO_Title_80Char: '', Description_Body: '', Recommended_Price: '' });
  const [listingContentOpts, setListingContentOpts] = useState({ ...DEFAULT_LISTING_CONTENT_OPTS });
  const [setBlurbSet, setSetBlurbSet] = useState('');
  const [setBlurbText, setSetBlurbText] = useState('');
  const [setBlurbDirty, setSetBlurbDirty] = useState(false);
  const [showBatchWriterPanel, setShowBatchWriterPanel] = useState(false);
  const [batchWriterOpts, setBatchWriterOpts] = useState({
    scope: 'for_sale',
    setName: 'All Sets',
    sourceBatch: 'All Batches',
    platform: 'eBay & CollX',
    forceRefreshBio: false,
  });

  const [showRecordSaleForm, setShowRecordSaleForm] = useState(false);
  const [newSale, setNewSale] = useState({
    Sale_Date: new Date().toISOString().slice(0, 10),
    SKU: '', Set: '', Subset: 'Base', Card_Number: '', Player: '',
    Platform: 'eBay', Sale_Price: '5.00', Shipping_Collected: '1.25',
    Marketplace_Fees: '0.96', Shipping_Cost: '0.73', Seller_Paid_Shipping: false, Cost_Basis: '0.50', Notes: '',
  });

  const [completionSet, setCompletionSet] = useState('2026 Topps Baseball');
  const [completionModeIdx, setCompletionModeIdx] = useState(0);
  const [completionExclSN, setCompletionExclSN] = useState(false);
  const [completionData, setCompletionData] = useState({ modes: [], owned: [], missing: [], bySubset: [], byPlayer: [] });
  const [completionLoading, setCompletionLoading] = useState(false);
  const [compTableView, setCompTableView] = useState('missing');
  const [compSearch, setCompSearch] = useState('');
  const [compSubsetF, setCompSubsetF] = useState('All Subsets');
  const [showCompBreakdown, setShowCompBreakdown] = useState(false);
  const [compBreakdownTab, setCompBreakdownTab] = useState('subset');
  const [compBreakdownSearch, setCompBreakdownSearch] = useState('');

  const [plannerSet, setPlannerSet] = useState('2026 Topps Baseball');
  const [plannerSubset, setPlannerSubset] = useState('All Subsets');
  const [plannerPlayer, setPlannerPlayer] = useState('');
  const [plannerMaxBudget, setPlannerMaxBudget] = useState(0);
  const [plannerExclSN, setPlannerExclSN] = useState(false);
  const [plannerData, setPlannerData] = useState({ rows: [], summary: { owned_count: 0, total_count: 0, missing_count: 0, estimated_total_cost: 0 }, subsets: [], players: [] });

  const [analyticsTab, setAnalyticsTab] = useState('inventory');
  const [devAuditResults, setDevAuditResults] = useState([]);
  const [rotFixScope, setRotFixScope] = useState('all');
  const [rotFixSet, setRotFixSet] = useState('All Sets');
  const [replaceImgTarget, setReplaceImgTarget] = useState(null);
  const [rateLearnerStats, setRateLearnerStats] = useState({ endpoints: [], totalSaved404Probes: 0, stateFile: '' });
  const [settingsLayout, setSettingsLayout] = useState({
    skins: { collapsed: false, wide: false },
    alerts: { collapsed: false, wide: false },
    scheduler: { collapsed: false, wide: false },
    storage: { collapsed: false, wide: false },
    hardware: { collapsed: false, wide: true },
    devtools: { collapsed: false, wide: true },
    telemetry: { collapsed: false, wide: true },
  });
  const [computeStatus, setComputeStatus] = useState(null);
  const [computeBench, setComputeBench] = useState(null);
  const [runningComputeBench, setRunningComputeBench] = useState(false);
  const toggleSettingsMod = (modKey, prop) => {
    setSettingsLayout((prev) => ({
      ...prev,
      [modKey]: { ...(prev[modKey] || { collapsed: false, wide: false }), [prop]: !prev[modKey]?.[prop] },
    }));
  };
  const setAllSettingsCollapsed = (isCollapsed) => {
    setSettingsLayout((prev) => {
      const next = {};
      Object.keys(prev).forEach((k) => { next[k] = { ...prev[k], collapsed: isCollapsed }; });
      return next;
    });
  };
  const resetSettingsCollage = () => {
    setSettingsLayout({
      skins: { collapsed: false, wide: false },
      alerts: { collapsed: false, wide: false },
      scheduler: { collapsed: false, wide: false },
      storage: { collapsed: false, wide: false },
      hardware: { collapsed: false, wide: true },
      devtools: { collapsed: false, wide: true },
      telemetry: { collapsed: false, wide: true },
    });
  };

  const refreshComputeStatus = (forceRefresh = false) => {
    fetch(`${NODE_API_BASE}/compute/status${forceRefresh ? '?refresh=true' : ''}`)
      .then((r) => r.json())
      .then((d) => d && !d.error && setComputeStatus(d))
      .catch(() => {});
  };

  const pushNotification = (title, message, category = 'System', severity = 'info') => {
    const nowMs = Date.now();
    const id = `NTF-${nowMs}-${Math.floor(Math.random() * 1000)}`;
    const ts = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const obj = { Notification_ID: id, Timestamp: ts, Category: category, Title: title, Message: message, Severity: severity, Cleared: 'False' };
    setActiveToasts((prev) => {
      const nextCount = Math.min(3, prev.length + 1);
      const baseTtl = nextCount >= 3 ? 2000 : nextCount === 2 ? 2800 : 4000;
      const errBonus = nextCount >= 3 ? 1000 : nextCount === 2 ? 1000 : 1200;
      const newTtl = severity === 'error' ? baseTtl + errBonus : baseTtl;
      const acceleratedPrev = prev.map((t) => {
        const capForT = t.Severity === 'error' ? baseTtl + errBonus : baseTtl;
        const capExp = Math.max(nowMs + 450, (t._createdAt || nowMs) + capForT);
        return { ...t, _expiresAt: Math.min(t._expiresAt || capExp, capExp) };
      });
      const newToast = { ...obj, _createdAt: nowMs, _expiresAt: nowMs + newTtl };
      return [newToast, ...acceleratedPrev].slice(0, 3);
    });
    setNotifications((prev) => [obj, ...prev]);
    fetch(`${NODE_API_BASE}/notifications`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) }).catch(() => {});
  };

  useEffect(() => {
    if (activeToasts.length === 0) return;
    const nowMs = Date.now();
    const nextExpiry = Math.min(...activeToasts.map((t) => t._expiresAt || (nowMs + 4000)));
    const waitMs = Math.max(50, nextExpiry - nowMs);
    const timer = setTimeout(() => {
      const cutoff = Date.now();
      setActiveToasts((prev) => prev.filter((t) => (t._expiresAt || 0) > cutoff + 25));
    }, waitMs);
    return () => clearTimeout(timer);
  }, [activeToasts]);

  const clearNotification = (notificationId = '', clearAll = false) => {
    fetch(`${NODE_API_BASE}/notifications/clear`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notificationId, clearAll }) })
      .then((r) => r.json())
      .then((res) => res && Array.isArray(res.notifications) && setNotifications(res.notifications))
      .catch(() => {});
  };

  const openHiddenPage = (pageId) => {
    setUnlockedHiddenPages((p) => ({ ...p, [pageId]: true }));
    setActivePage(pageId);
  };

  const changeSkin = (key) => { setSkinKey(key); localStorage.setItem('tabulas_skin', key); };
  const toggleDevMode = (val) => { setDevMode(val); localStorage.setItem('tabulas_dev_mode', String(val)); };

  const fetchFilteredChecklists = (overrides = {}) => {
    const params = new URLSearchParams();
    const s = overrides.set ?? chkSetF;
    const y = overrides.year ?? chkYearF;
    const sub = overrides.subset ?? chkSubsetF;
    const a = overrides.attribute ?? chkAttrF;
    const st = overrides.status ?? chkStatusF;
    const q = overrides.q ?? chkSearchF;
    const pg = overrides.page ?? chkPage;
    const lim = overrides.limit ?? chkLimit;
    if (s && s !== 'All Sets') params.set('set', s);
    if (y && y !== 'All Years') params.set('year', y);
    if (sub && sub !== 'All Subsets') params.set('subset', sub);
    if (a && a !== 'All Attributes') params.set('attribute', a);
    if (st && st !== 'All Cards') params.set('status', st);
    if (q) params.set('q', q);
    params.set('page', String(pg));
    params.set('limit', String(lim));
    fetch(`${NODE_API_BASE}/checklists?${params.toString()}`).then((r) => r.json()).then((d) => d && setChkData(d)).catch(() => {});
  };

  const loadBatchesFromDisk = (preferredBatch = null) => {
    const targetB = preferredBatch !== null ? preferredBatch : activeBatchNameRef.current;
    const url = targetB ? `${NODE_API_BASE}/batches?batch=${encodeURIComponent(targetB)}` : `${NODE_API_BASE}/batches`;
    fetch(url).then((r) => r.json()).then((bList) => {
      if (!Array.isArray(bList)) return;
      setBatches(bList);
      const validSet = new Set(bList.map((x) => x.batchName));
      setSelectedCommitBatches((prev) => prev.filter((bn) => validSet.has(bn)));
      if (bList.length === 0) {
        setActiveBatchName('');
      } else if (targetB === '__ALL__') {
        setActiveBatchName('__ALL__');
      } else {
        const hasTarget = targetB && validSet.has(targetB);
        setActiveBatchName(hasTarget ? targetB : bList[0].batchName);
      }
    }).catch(() => {});
  };

  const refreshAllHubData = (preferredBatch = null, opts = {}) => {
    fetch(`${NODE_API_BASE}/status`).then((r) => r.json()).then((d) => {
      if (d && d.ok) {
        setBackendConnected(true);
        if (Array.isArray(d.modules)) setModuleList(d.modules);
        if (d.updater) setUpdaterInfo(d.updater);
      }
    }).catch(() => setBackendConnected(false));

    fetch(`${NODE_API_BASE}/inventory`).then((r) => r.json()).then((rows) => {
      if (Array.isArray(rows)) {
        setInventory(rows);
        setInventoryDirty(false);
        const firstUnsold = rows.find((r) => String(r.Status || '').trim().toLowerCase() !== 'sold');
        const defaultSku = firstUnsold ? firstUnsold.SKU : (rows[0]?.SKU || '');
        if (defaultSku) setWriterSku((prev) => prev || defaultSku);
      }
    }).catch(() => {});
    fetch(`${NODE_API_BASE}/incoming-scans`).then((r) => r.json()).then((d) => Array.isArray(d) && setIncomingScans(d)).catch(() => {});
    loadBatchesFromDisk(preferredBatch);
    if (!opts.preserveChecklist) fetchFilteredChecklists();
    fetch(`${NODE_API_BASE}/config/tracked-sets`).then((r) => r.json()).then((d) => {
      if (Array.isArray(d) && !trackedSetsDirtyRef.current) setTrackedSets(d);
    }).catch(() => {});
    fetch(`${NODE_API_BASE}/directory`).then((r) => r.json()).then((d) => Array.isArray(d) && setDirectoryRows(d)).catch(() => {});
    fetch(`${NODE_API_BASE}/config/set-cart`).then((r) => r.json()).then((c) => { if (Array.isArray(c)) { setSetCart(c); if (c.length > 0) setShowCartSidebar(true); } }).catch(() => {});
    fetch(`${NODE_API_BASE}/market-data`).then((r) => r.json()).then((m) => {
      if (m) {
        setMarketData(m);
        if (m.alertSettings) setAlertCfg((prev) => ({ ...prev, ...m.alertSettings }));
      }
    }).catch(() => {});
    fetch(`${NODE_API_BASE}/sales/lots`).then((r) => r.json()).then((l) => l && setLotsData(l)).catch(() => {});
    fetch(`${NODE_API_BASE}/sales/strategy-recommendations`).then((r) => r.json()).then((sr) => sr && setStrategyRecs(sr)).catch(() => {});
    fetch(`${NODE_API_BASE}/sales-data`).then((r) => r.json()).then((sd) => sd && Array.isArray(sd.listingDrafts) && setListingDrafts(sd.listingDrafts)).catch(() => {});
    fetch(`${NODE_API_BASE}/expenses`).then((r) => r.json()).then((ex) => {
      if (ex) {
        if (Array.isArray(ex.expenses_ledger)) setExpensesLedger(ex.expenses_ledger);
        if (ex.pricing_strategy) setPricingStrategy((p) => ({ ...p, ...ex.pricing_strategy }));
      }
    }).catch(() => {});
    fetch(`${NODE_API_BASE}/sold-cards`).then((r) => r.json()).then((sc) => sc && Array.isArray(sc.rows) && setSoldCards(sc.rows)).catch(() => {});
    fetch(`${NODE_API_BASE}/schedules`).then((r) => r.json()).then((sc) => Array.isArray(sc) && setSchedules(sc)).catch(() => {});
    fetch(`${NODE_API_BASE}/notifications`).then((r) => r.json()).then((nt) => nt && Array.isArray(nt.notifications) && setNotifications(nt.notifications)).catch(() => {});
    fetch(`${NODE_API_BASE}/rate-learner`).then((r) => r.json()).then((rl) => rl && setRateLearnerStats(rl)).catch(() => {});
    fetch(`${NODE_API_BASE}/dashboard/summary`).then((r) => r.json()).then((ds) => {
      if (ds && typeof ds === 'object') setDashboardSummary(ds);
    }).catch(() => {});
    refreshComputeStatus(false);
    fetch(`${NODE_API_BASE}/inventory/card-level`).then((r) => r.json()).then((cl) => {
      if (cl && Array.isArray(cl.rows)) {
        setCardLevelRows(cl.rows);
        setCardLevelEdits({});
      }
    }).catch(() => {});
  };

  const refreshAllHubDataRef = useRef(refreshAllHubData);
  refreshAllHubDataRef.current = refreshAllHubData;

  useEffect(() => { refreshAllHubData(); }, []);

  useEffect(() => {
    const poll = () => {
      fetch(`${NODE_API_BASE}/lanes`).then((r) => r.json()).then((d) => {
        if (d && d.lanes) {
          const prevMap = prevLaneStatesRef.current || {};
          const finishedJobs = [];
          Object.entries(d.lanes).forEach(([lk, st]) => {
            const prevSt = prevMap[lk];
            const curStatus = st?.status || 'IDLE';
            const curUpd = st?.updated_at || '';
            if (prevSt) {
              const transitionedOutOfRun = prevSt.status === 'RUNNING' && curStatus !== 'RUNNING';
              const completedQuickly = prevSt.status !== 'RUNNING' && curStatus === 'COMPLETED' && curUpd && curUpd !== prevSt.updated_at;
              if (transitionedOutOfRun || completedQuickly) {
                finishedJobs.push({ lane: lk, status: curStatus, title: st?.title || lk, jobType: st?.job_type || '' });
              }
            }
            prevMap[lk] = { status: curStatus, updated_at: curUpd, job_type: st?.job_type || '' };
          });
          prevLaneStatesRef.current = prevMap;

          setLiveLanes(d.lanes);
          setLiveLogs(d.logs || {});

          if (finishedJobs.length > 0) {
            const hasNewIngest = finishedJobs.some((fj) => fj.jobType === 'scan_ingest');
            const finishedInvReprocLanes = new Set(finishedJobs.filter((fj) => fj.jobType === 'reprocess_inventory_skus').map((fj) => fj.lane));
            const finishedBatchReprocLanes = new Set(finishedJobs.filter((fj) => fj.jobType === 'reprocess_batch_cards').map((fj) => fj.lane));
            if (finishedJobs.some((fj) => fj.jobType === 'fix_card_rotations')) {
              setInvEditorImgBust((v) => v + 1);
              setBatchImgBust((v) => v + 1);
            }
            if (finishedJobs.some((fj) => ['install_directml', 'download_dinov2_model', 'build_neural_index'].includes(fj.jobType))) {
              refreshComputeStatus(true);
            }

            if (finishedInvReprocLanes.size > 0) {
              const clearedInvSkus = [];
              setReprocessingInvSkus((prev) => {
                const next = { ...prev };
                Object.keys(next).forEach((sk) => {
                  if (finishedInvReprocLanes.has(next[sk])) {
                    clearedInvSkus.push(sk);
                    delete next[sk];
                  }
                });
                return next;
              });
              if (clearedInvSkus.length > 0) {
                setInvEditorDrafts((dPrev) => {
                  const cp = { ...dPrev };
                  clearedInvSkus.forEach((sk) => delete cp[sk]);
                  return cp;
                });
              }
              // Instantly hydrate Inventory & active Inventory Editor cards from the newly scanned data!
              fetch(`${NODE_API_BASE}/inventory`).then((r) => r.json()).then((rows) => {
                if (!Array.isArray(rows)) return;
                setInventory(rows);
                setInventoryDirty(false);
                setInvEditorImgBust((v) => v + 1);
              }).catch(() => {});
            }

            if (finishedBatchReprocLanes.size > 0) {
              setReprocessingBatchSkus((prev) => {
                const next = { ...prev };
                const clearedSkus = [];
                Object.keys(next).forEach((sk) => {
                  if (finishedBatchReprocLanes.has(next[sk])) {
                    clearedSkus.push(sk);
                    delete next[sk];
                  }
                });
                if (clearedSkus.length > 0) {
                  setBatchDraftEdits((edPrev) => {
                    const cp = { ...edPrev };
                    clearedSkus.forEach((sk) => delete cp[sk]);
                    return cp;
                  });
                }
                return next;
              });
              setBatchImgBust((v) => v + 1);
            }

            // Auto-refresh all Hub data (selecting the newest batch if scan_ingest just finished, preserving active checklist filters!)
            refreshAllHubDataRef.current(hasNewIngest ? '' : activeBatchNameRef.current, { preserveChecklist: true });
            finishedJobs.forEach((fj) => {
              if (fj.jobType === 'system_startup') return;
              const ok = fj.status === 'COMPLETED';
              pushNotification(
                ok ? `✅ Completed: ${fj.title}` : `⚠️ ${fj.status}: ${fj.title}`,
                ok ? 'Page updated automatically with latest results.' : `Process ended with status: ${fj.status}.`,
                PROCESS_LANES[fj.lane]?.shortName || 'Worker',
                ok ? 'success' : 'warning'
              );
            });
          }
        }
      }).catch(() => {});
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (activePage !== 'unified_checklist_viewer') return;
    const timer = setTimeout(() => fetchFilteredChecklists(), chkSearchF ? 240 : 0);
    return () => clearTimeout(timer);
  }, [activePage, chkSetF, chkYearF, chkSubsetF, chkAttrF, chkStatusF, chkSearchF, chkPage, chkLimit]);

  useEffect(() => { setChkPage(1); }, [chkSetF, chkYearF, chkSubsetF, chkAttrF, chkStatusF, chkSearchF]);
  useEffect(() => { setInvPage(1); }, [invSetFilter, invHoldFilter, invStatusFilter, invSearch]);
  useEffect(() => { setDirPage(1); }, [dirSportFilter, dirMfgFilter, dirCategoryFilter, dirEraFilter, dirSearch, dirHideTracked]);
  useEffect(() => { setCompPage(1); }, [completionSet, completionModeIdx, completionExclSN, compTableView, compSubsetF, compSearch]);
  useEffect(() => { setBatchPage(1); }, [activeBatchName, batchReviewFilter, batchConfFilter, batchSubsetFilter, batchSearchQ]);

  useEffect(() => {
    if (activePage === 'general_settings' && devMode) {
      fetch(`${NODE_API_BASE}/rate-learner`).then((r) => r.json()).then((rl) => rl && setRateLearnerStats(rl)).catch(() => {});
    }
  }, [activePage, devMode]);

  const isIngestLaneRunning = Object.values(liveLanes).some(
    (l) => l?.status === 'RUNNING' && ['scan_ingest', 'reidentify_batch', 'regrade_batch', 'reprocess_batch_cards', 'commit_batches'].includes(l?.job_type)
  );
  const isCommitRunning = Object.values(liveLanes).some(
    (l) => l?.status === 'RUNNING' && l?.job_type === 'commit_batches'
  );

  useEffect(() => { setClPage(1); }, [clSetF, clSurplusOnly, clSearch]);

  const prefillSampleLabelFromCard = (card) => {
    if (!card) return;
    setSampleLabel({
      SKU: String(card.SKU || '').trim(),
      Set: String(card.Set || '').trim(),
      CardNumber: String(card['Card Number'] || '').replace(/^#/, '').trim(),
      Player: String(card.Player || '').trim(),
      Team: String(card.Team || '').trim(),
      Subset: String(card.Subset || 'Base').trim() || 'Base',
      PrintRun: String(card['Print Run'] || '').replace(/[^0-9]/g, ''),
      League: inferLeagueCodeFromSet(card.Set),
    });
  };

  useEffect(() => {
    if (activePage !== 'label_hub' || sampleLabelInitialized || inventory.length === 0) return;
    const firstUnprinted = inventory.find((c) => String(c.Label_Printed).toLowerCase() !== 'true') || inventory[0];
    if (firstUnprinted) {
      prefillSampleLabelFromCard(firstUnprinted);
      setSampleLabelInitialized(true);
    }
  }, [activePage, inventory, sampleLabelInitialized]);

  useEffect(() => {
    if (activePage !== 'listing_writer') return;
    const activeCard = inventory.find((c) => c.SKU === writerSku);
    const targetSet = activeCard?.Set || '';
    if (!targetSet || targetSet === setBlurbSet) return;
    setSetBlurbSet(targetSet);
    setSetBlurbDirty(false);
    fetch(`${NODE_API_BASE}/sales/set-blurb?set=${encodeURIComponent(targetSet)}`)
      .then((r) => r.json())
      .then((res) => res && setSetBlurbText(res.blurb || ''))
      .catch(() => {});
  }, [activePage, writerSku, inventory, setBlurbSet]);
  useEffect(() => {
    if (!isIngestLaneRunning) return;
    if (!['scan_ingestion', 'guided_batch_review', 'batch_deep_dive'].includes(activePage)) return;
    const id = setInterval(() => {
      if (Object.keys(batchDraftEdits).length === 0) {
        loadBatchesFromDisk(activeBatchNameRef.current || '');
      }
    }, 1500);
    return () => clearInterval(id);
  }, [isIngestLaneRunning, activePage, batchDraftEdits]);

  useEffect(() => {
    if (activePage !== 'set_completion' || !completionSet) return;
    let cancelled = false;
    setCompletionLoading(true);
    const p = new URLSearchParams({ set: completionSet, modeIdx: String(completionModeIdx), excludeSN: String(completionExclSN) });
    fetch(`${NODE_API_BASE}/completion?${p.toString()}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled && d) setCompletionData(d); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setCompletionLoading(false); });
    return () => { cancelled = true; };
  }, [activePage, completionSet, completionModeIdx, completionExclSN]);

  useEffect(() => {
    if (activePage !== 'card_purchase_planner' || !plannerSet) return;
    const timer = setTimeout(() => {
      const p = new URLSearchParams({ set: plannerSet, subset: plannerSubset, player: plannerPlayer, maxBudget: String(plannerMaxBudget), excludeSN: String(plannerExclSN) });
      fetch(`${NODE_API_BASE}/purchase-planner?${p.toString()}`).then((r) => r.json()).then((d) => d && setPlannerData(d)).catch(() => {});
    }, plannerPlayer ? 240 : 0);
    return () => clearTimeout(timer);
  }, [activePage, plannerSet, plannerSubset, plannerPlayer, plannerMaxBudget, plannerExclSN]);

  useEffect(() => {
    if (!preselectSet || preselectSet.includes('Mixed')) {
      setPreselectSubsets(['Base']);
      setPreselectSubset('🌐 Auto-Detect Subset / Parallel');
      return;
    }
    fetch(`${NODE_API_BASE}/checklists/lookup?set=${encodeURIComponent(preselectSet)}&limit=10`)
      .then((r) => r.json())
      .then((d) => d && Array.isArray(d.subsets) && setPreselectSubsets(d.subsets.length > 0 ? d.subsets : ['Base']))
      .catch(() => setPreselectSubsets(['Base']));
  }, [preselectSet]);

  useEffect(() => {
    if (!showManualAddInv || !manualCard.Set) return;
    fetch(`${NODE_API_BASE}/checklists/lookup?set=${encodeURIComponent(manualCard.Set)}&limit=10`)
      .then((r) => r.json())
      .then((d) => d && Array.isArray(d.subsets) && setManualSubsets(d.subsets.length > 0 ? d.subsets : ['Base']))
      .catch(() => setManualSubsets(['Base']));
  }, [showManualAddInv, manualCard.Set]);

  const triggerJob = (_legacyLane, title, jobType, payloadObj = {}) => {
    fetch(`${NODE_API_BASE}/jobs/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lane: null, jobType, title, payload: payloadObj, executionMode: 'queue' }),
    })
      .then((r) => r.json())
      .then((res) => {
        const assignedSlot = res?.lane || 'slot_1';
        setSelectedMonitorLane(assignedSlot);
        const slotLbl = PROCESS_LANES[assignedSlot]?.shortName || assignedSlot;
        if (res?.queued) {
          pushNotification(
            `Queued (#${res.queuePosition || 1}) — ${title}`,
            `Waiting in ${slotLbl} behind an active job so files never collide.`,
            'Queue',
            'info'
          );
        } else {
          pushNotification(
            title,
            `Running in parallel on ${slotLbl} (PID ${res?.pid || 'active'}).`,
            'Worker',
            'success'
          );
        }
      })
      .catch((e) => pushNotification('Job Error', e.message, 'Worker', 'error'));
  };

  // Derived Collections
  const dynamicSetsNewestFirst = useMemo(() => {
    const s = new Set(chkData.knownSets || ['2026 Topps Baseball']);
    inventory.forEach((r) => r.Set && s.add(r.Set));
    trackedSets.forEach((r) => r.Folder_Name && s.add(r.Folder_Name.replace(/_/g, ' ')));
    return sortSetsNewestFirst(Array.from(s));
  }, [chkData.knownSets, inventory, trackedSets]);

  const ownedSetsNewestFirst = useMemo(() => {
    const s = new Set();
    inventory.forEach((r) => r.Set && s.add(r.Set));
    return sortSetsNewestFirst(Array.from(s));
  }, [inventory]);

  const currentBatchObj = useMemo(() => batches.find((b) => b.batchName === activeBatchName) || batches[0] || null, [batches, activeBatchName]);
  const batchCards = currentBatchObj?.cards || [];

  const filteredInventory = useMemo(() => inventory.filter((c) => {
    if (invSetFilter !== 'All Sets' && c.Set !== invSetFilter) return false;
    if (invHoldFilter !== 'All Hold Tags' && c.Hold_Tag !== invHoldFilter) return false;
    if (invStatusFilter !== 'All Statuses' && c.Status !== invStatusFilter) return false;
    if (invSearch.trim()) {
      const q = invSearch.toLowerCase();
      if (!`${c.SKU} ${c.Set} ${c.Subset} ${c['Card Number']} ${c.Player} ${c.Team} ${c.Attributes}`.toLowerCase().includes(q)) return false;
    }
    return true;
  }), [inventory, invSetFilter, invHoldFilter, invStatusFilter, invSearch]);

  const gradingCandidates = useMemo(() => inventory.filter((c) => {
    if (gradeRecSetFilter !== 'All Sets' && c.Set !== gradeRecSetFilter) return false;
    const act = String(c.Recommended_Action || '').toUpperCase();
    return act.startsWith('GRADE') || act.startsWith('PC SLAB');
  }), [inventory, gradeRecSetFilter]);

  const targetScraperQueueMap = useMemo(() => {
    const m = {};
    const selSet = new Set(selectedTrackedUrls);
    const pool = selSet.size > 0 ? trackedSets.filter((ts) => selSet.has(ts.TCDB_URL)) : trackedSets;
    pool.forEach((ts) => { if (ts.TCDB_URL && ts.Folder_Name) m[ts.TCDB_URL] = ts.Folder_Name; });
    return m;
  }, [trackedSets, selectedTrackedUrls]);

  const anyLaneRunning = Object.values(liveLanes).some((l) => l?.status === 'RUNNING');

  useEffect(() => {
    if (!anyLaneRunning) return;
    const id = setInterval(() => setLiveClockSec(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [anyLaneRunning]);

  const getLaneElapsedSec = (st) => {
    if (!st) return 0;
    if (st.status === 'RUNNING' && safeNum(st.start_epoch, 0) > 0) {
      return Math.max(safeNum(st.elapsed_seconds, 0), Math.round(liveClockSec - safeNum(st.start_epoch, 0)));
    }
    return safeNum(st.elapsed_seconds, 0);
  };

  const getSubElapsedSec = (st) => {
    if (!st) return 0;
    if (st.status === 'RUNNING' && safeNum(st.sub_start_epoch, 0) > 0) {
      return Math.max(safeNum(st.sub_elapsed_seconds, 0), Math.round(liveClockSec - safeNum(st.sub_start_epoch, 0)));
    }
    return safeNum(st.sub_elapsed_seconds, 0);
  };

  const financialSummary = useMemo(() => {
    const totalExpenses = expensesLedger.reduce((acc, r) => acc + safeNum(r.Cost, 0), 0);
    const cogsBoxes = expensesLedger.filter((r) => /box|pack|case|cogs|single/i.test(String(r.Category || ''))).reduce((acc, r) => acc + safeNum(r.Cost, 0), 0);
    const grossSales = soldCards.reduce((acc, r) => acc + safeNum(r.Sale_Price, 0), 0);
    const shipCollected = soldCards.reduce((acc, r) => acc + safeNum(r.Shipping_Collected, 0), 0);
    const totalFees = soldCards.reduce((acc, r) => acc + safeNum(r.Marketplace_Fees, 0), 0);
    const sellerPaidShipTotal = soldCards.reduce((acc, r) => acc + (String(r.Seller_Paid_Shipping).toLowerCase() === 'true' ? safeNum(r.Shipping_Cost, 0) : 0), 0);
    const totalRevenue = grossSales + shipCollected;
    const netProfit = totalRevenue - totalFees - sellerPaidShipTotal - totalExpenses;

    const inStock = inventory.filter((c) => c.Status !== 'Sold');
    const totalRawVal = inStock.reduce((acc, c) => acc + safeNum(c.Raw_Price, 0), 0);
    const totalRecVal = inStock.reduce((acc, c) => acc + safeNum(c.Rec_Sale_Price, safeNum(c.Raw_Price, 0)), 0);
    const totalOptimalEv = inStock.reduce((acc, c) => acc + Math.max(safeNum(c.Raw_Price, 0), safeNum(c.EV_PSA, 0), safeNum(c.EV_BGS, 0)), 0);
    const avgSalePrice = soldCards.length > 0 ? grossSales / soldCards.length : 0;
    const unitCostBasis = totalExpenses / Math.max(1, inStock.length);

    return {
      totalExpenses, cogsBoxes, grossSales, shipCollected, totalFees, sellerPaidShipTotal,
      totalRevenue, netProfit, inStockCount: inStock.length, totalRawVal, totalRecVal,
      totalOptimalEv, avgSalePrice, unitCostBasis,
    };
  }, [expensesLedger, soldCards, inventory]);

  const economicalTiers = useMemo(() => {
    const pickBest = (list) => {
      const open = (list || []).filter((t) => String(t.status).toLowerCase() === 'open');
      const pool = open.length > 0 ? open : (list || []);
      return [...pool].sort((a, b) => safeNum(a.price, 999) - safeNum(b.price, 999))[0] || null;
    };
    return { PSA: pickBest(marketData.tiers?.PSA), BGS: pickBest(marketData.tiers?.BGS) };
  }, [marketData.tiers]);

  const LABEL_IDENTITY_FIELDS = new Set(['Set', 'Subset', 'Card Number', 'Player', 'Team', 'Print Run']);

  const updateInventoryRowInline = (sku, field, value) => {
    setInventory((prev) =>
      prev.map((r) => {
        if (r.SKU !== sku) return r;
        const nextRow = { ...r, [field]: value };
        if (field === 'Raw_Price') {
          nextRow.Valuation_Source = String(value || '').trim() ? 'Manual' : 'Uncomped';
        }
        // Auto-flag Label_Printed = False whenever any label-visible card field changes
        if (LABEL_IDENTITY_FIELDS.has(field) && String(r[field] || '') !== String(value || '')) {
          nextRow.Label_Printed = 'False';
        }
        return nextRow;
      })
    );
    setInventoryDirty(true);
  };

  const computeRecommendedPriceForRow = (row) => {
    const raw = safeNum(row.Raw_Price, 1.0);
    const minP = safeNum(row.Min_Sale_Price, safeNum(pricingStrategy.global_min_price_floor, 1.49));
    const isOffer = String(row.Hold_Tag || '').includes('Offer');
    let pct = isOffer
      ? Math.max(safeNum(pricingStrategy.market_markup_pct, 50), safeNum(pricingStrategy.make_offer_markup_pct, 75))
      : safeNum(pricingStrategy.market_markup_pct, 50);
    if (row['Print Run'] || (row.Subset && row.Subset !== 'Base')) pct += safeNum(pricingStrategy.rookie_serial_bonus_pct, 15);
    if (Math.max(safeNum(row.Est_PSA, 0), safeNum(row.Est_BGS, 0)) >= 9.5) pct += safeNum(pricingStrategy.gem_mint_pregrade_bonus_pct, 20);
    return Math.max(minP, raw * (1 + pct / 100)).toFixed(2);
  };

  const autoAssignRecPrice = (targetSkus = null) => {
    const targetSet = targetSkus ? new Set(targetSkus) : null;
    setInventory((prev) => prev.map((r) => (!targetSet || targetSet.has(r.SKU) ? { ...r, Rec_Sale_Price: computeRecommendedPriceForRow(r) } : r)));
    setInventoryDirty(true);
    pushNotification('Recommended Prices Assigned', `Updated Sale Price for ${targetSet ? targetSet.size : inventory.length} card(s).`, 'Inventory', 'info');
  };

  const persistInventoryToDisk = (rowsToSave = inventory, msgTitle = 'Inventory Saved') => {
    return fetch(`${NODE_API_BASE}/inventory`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(rowsToSave) })
      .then((r) => r.json())
      .then((res) => {
        if (res && res.success) {
          setInventory(res.rows || rowsToSave);
          setInventoryDirty(false);
          pushNotification(msgTitle, `Saved ${(res.rows || rowsToSave).length.toLocaleString()} SKU(s) (${res.renamedFiles || 0} _Cards renamed).`, 'Inventory', 'success');
          return true;
        }
        pushNotification('Save Error', res?.error || 'Failed to persist inventory to disk.', 'Inventory', 'error');
        return false;
      })
      .catch((e) => {
        pushNotification('Save Error', e.message, 'Inventory', 'error');
        return false;
      });
  };

  const openInventoryEditorForSkus = (skus, mode = 'individual') => {
    const list = Array.isArray(skus) ? skus : [skus];
    if (list.length === 0) return;
    const first = inventory.find((c) => list.includes(c.SKU));
    if (!first) return;
    setSelectedInvSkus(list);
    setInvEditorIdx(0);
    setInvEditorPage(1);
    setInvEditorSearchQ('');
    setInvEditorDrafts({});
    setInvEditorMode(mode || 'individual');
    setShowInvEditMenu(false);
    setBulkEditChecks({});
    setBulkEditVals({
      Set: first.Set || '',
      Subset: first.Subset || 'Base',
      Team: first.Team || '',
      'Print Run': first['Print Run'] || '',
      Attributes: first.Attributes || '',
      Status: first.Status || 'In Stock',
      Hold_Tag: first.Hold_Tag || 'For Sale',
      Raw_Price: first.Raw_Price || '1.00',
      Rec_Sale_Price: first.Rec_Sale_Price || first.Raw_Price || '1.49',
      Label_Printed: String(first.Label_Printed).toLowerCase() === 'true' ? 'True' : 'False',
      Needs_Review: String(first.Needs_Review).toLowerCase() === 'true' ? 'True' : 'False',
      Grading_Notes: first.Grading_Notes || '',
    });
    activeInvEditorSkuRef.current = String(first.SKU || '').trim();
    openHiddenPage('inventory_editor');
  };

  const rotateInventoryCardImage = (setName, fileName) =>
    fetch(`${NODE_API_BASE}/inventory/rotate-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ setName: setName || '', fileName, degrees: 90 }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          pushNotification('Image Rotated', `Rotated ${fileName} 90° clockwise.`, 'Inventory', 'info');
        } else {
          pushNotification('Rotate Failed', res?.error || 'Unable to rotate image.', 'Inventory', 'error');
        }
      })
      .catch((err) => pushNotification('Rotate Error', err.message, 'Inventory', 'error'));

  const triggerInventoryReprocess = (skuList, lockedSetVal = '') => {
    const cleanList = Array.from(new Set((skuList || []).map((s) => String(s).trim()).filter(Boolean)));
    if (cleanList.length === 0) return;
    fetch(`${NODE_API_BASE}/inventory/reprocess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skus: cleanList, lockedSet: lockedSetVal || '', regradeToo: true }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          const assignedSlot = res.lane || 'slot_1';
          if (res.lanes?.lanes) {
            setLiveLanes(res.lanes.lanes);
            setLiveLogs(res.lanes.logs || {});
          }
          setSelectedMonitorLane(assignedSlot);
          setReprocessingInvSkus((prev) => {
            const next = { ...prev };
            cleanList.forEach((s) => { next[s] = assignedSlot; });
            return next;
          });
          pushNotification(
            cleanList.length === 1 ? `🔄 Reprocessing SKU ${cleanList[0]}` : `🔄 Reprocessing ${cleanList.length} Inventory SKU(s)`,
            `Running immediately on ${PROCESS_LANES[assignedSlot]?.shortName || assignedSlot}. Page will update automatically when done.`,
            'Inventory',
            'info'
          );
        } else {
          pushNotification('Reprocess Failed', res?.error || 'Unable to launch inventory reprocess.', 'Inventory', 'error');
        }
      })
      .catch((err) => pushNotification('Reprocess Error', err.message, 'Inventory', 'error'));
  };

  const triggerBatchCardsReprocess = (batchName, skuList, lockedSetVal = '') => {
    const cleanList = Array.from(new Set((skuList || []).map((s) => String(s).trim()).filter(Boolean)));
    if (!batchName || cleanList.length === 0) return Promise.resolve();
    return fetch(`${NODE_API_BASE}/batches/reprocess-card`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batchName, skus: cleanList, lockedSet: lockedSetVal || '', regradeToo: true }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res?.success) {
          const assignedSlot = res.lane || 'slot_1';
          if (res.lanes?.lanes) {
            setLiveLanes(res.lanes.lanes);
            setLiveLogs(res.lanes.logs || {});
          }
          setSelectedMonitorLane(assignedSlot);
          setReprocessingBatchSkus((prev) => {
            const next = { ...prev };
            cleanList.forEach((s) => { next[s] = assignedSlot; });
            return next;
          });
          pushNotification(
            cleanList.length === 1 ? `🔄 Reprocessing SKU ${cleanList[0]}` : `🔄 Reprocessing ${cleanList.length} Batch Card(s)`,
            `Dispatched to ${PROCESS_LANES[assignedSlot]?.shortName || assignedSlot}. Card will refresh automatically when finished.`,
            'Batch',
            'info'
          );
        } else {
          pushNotification('Reprocess Failed', res?.error || 'Unable to launch batch reprocess.', 'Batch', 'error');
        }
      })
      .catch((err) => pushNotification('Reprocess Error', err.message, 'Batch', 'error'));
  };

  const saveExpensesAndPricing = (applyToInv = false, strategyOverride = null, ledgerOverride = null) => {
    const stratToSave = strategyOverride || pricingStrategy;
    const ledgerToSave = Array.isArray(ledgerOverride) ? ledgerOverride : expensesLedger;
    fetch(`${NODE_API_BASE}/expenses`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expenses_ledger: ledgerToSave, pricing_strategy: stratToSave, applyToInventory: applyToInv }),
    }).then((r) => r.json()).then((res) => {
      if (res && res.success) {
        if (res.inventoryRows) setInventory(res.inventoryRows);
        fetch(`${NODE_API_BASE}/sales/strategy-recommendations`).then((r) => r.json()).then((sr) => sr && setStrategyRecs(sr)).catch(() => {});
        pushNotification(applyToInv ? 'Strategy Applied' : 'Expenses.csv Saved', `Saved ${ledgerToSave.length} expense row(s) to Data\\Bookkeeping\\Expenses.csv.`, 'Bookkeeping', 'success');
      }
    }).catch(() => {});
  };

  const handleRecalculateSalesStrategy = () => {
    if (recalculatingStrategy) return;
    setRecalculatingStrategy(true);
    fetch(`${NODE_API_BASE}/sales/recalculate-strategy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ triggerSource: 'manual' }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res && res.success) {
          if (Array.isArray(res.inventoryRows)) setInventory(res.inventoryRows);
          if (res.config && res.config.pricing_strategy) {
            setPricingStrategy((p) => ({ ...p, ...res.config.pricing_strategy }));
          }
          setStrategyRecs({
            summary: res.summary || {},
            recommendations: res.recommendations || [],
            total_verified_market_value: res.total_verified_market_value ?? 0,
            total_projected_listing_value: res.total_projected_listing_value ?? 0,
            comped_cards_count: res.comped_cards_count ?? 0,
            uncomped_cards_count: res.uncomped_cards_count ?? 0,
            last_recalculated_at: res.lastRecalculatedAt || '',
            last_recalc_trigger: res.triggerSource || 'manual',
          });
          fetch(`${NODE_API_BASE}/sales/lots`).then((r) => r.json()).then((l) => l && setLotsData(l)).catch(() => {});
          pushNotification(
            'Sales Strategy Recalculated',
            `Updated ${res.updatedCards || 0} card(s) from cached comps • Verified Market ${fmtCurrency(res.total_verified_market_value || 0)} • Projected List ${fmtCurrency(res.total_projected_listing_value || 0)}`,
            'Sales Strategy',
            'success'
          );
        } else {
          pushNotification('Recalculation Failed', res?.error || 'Could not recalculate Sales Strategy.', 'Sales Strategy', 'error');
        }
      })
      .catch((err) => pushNotification('Recalculation Error', err.message, 'Sales Strategy', 'error'))
      .finally(() => setRecalculatingStrategy(false));
  };

  const stageSetIntoCart = (item) => {
    const next = [...setCart.filter((x) => x.TCDB_URL !== item.TCDB_URL), item];
    setSetCart(next);
    setShowCartSidebar(true);
    fetch(`${NODE_API_BASE}/config/set-cart`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next) }).catch(() => {});
  };

  const handleCheckForUpdates = () => {
    fetch(`${NODE_API_BASE}/updater/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'check' }) })
      .then((r) => r.json())
      .then((res) => {
        if (Array.isArray(res.modules)) setModuleList(res.modules);
        setUpdaterInfo((prev) => ({
          status: res.status || 'UP_TO_DATE',
          current_version: res.current_version || APP_VERSION,
          pending_count: res.pending_count || 0,
          message: res.message || 'Checked ./Updates.',
          packages: res.all_packages || [],
          snapshots: res.snapshots || [],
          archived_snapshots_count: res.archived_snapshots_count ?? prev.archived_snapshots_count ?? 0,
        }));
        pushNotification('Update Check Complete', res.message || 'Checked ./Updates.', 'Updater', res.pending_count > 0 ? 'warning' : 'info');
      })
      .catch((e) => pushNotification('Update Check Failed', e.message, 'Updater', 'error'));
  };

  const handleApplyPendingUpdates = () => {
    fetch(`${NODE_API_BASE}/updater/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'apply', dryRun: false }) })
      .then((r) => r.json())
      .then((res) => {
        if (res.success && res.status === 'UPDATED') {
          if (res.restartRequired) {
            pushNotification('Updates Applied — App Restart Recommended', `${res.message} Backend server file (launch_tabulas_hub.py) was updated; close and relaunch Tabulas Hub to activate new API routes. Reloading UI in 2.5s...`, 'Updater', 'warning');
            setTimeout(() => window.location.reload(), 2500);
          } else {
            pushNotification('Updates Applied — Reloading App', `${res.message} Reloading in 1.5s...`, 'Updater', 'success');
            setTimeout(() => window.location.reload(), 1500);
          }
        } else {
          pushNotification('Updater Status', res.message || 'No pending updates to apply.', 'Updater', res.success ? 'info' : 'error');
          refreshAllHubData();
        }
      })
      .catch((e) => pushNotification('Apply Update Failed', e.message, 'Updater', 'error'));
  };

  const handleRollbackVersion = (targetVer) => {
    fetch(`${NODE_API_BASE}/updater/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'rollback', targetVersion: targetVer }) })
      .then((r) => r.json())
      .then((res) => {
        if (res.success) {
          const extra = res.restartRequired ? ' Close and relaunch Tabulas Hub to finish reloading server routes.' : '';
          pushNotification('Rollback Complete — Reloading App', `${res.message}${extra} Reloading in 1.8s...`, 'Updater', 'warning');
          setTimeout(() => window.location.reload(), 1800);
        } else {
          pushNotification('Rollback Failed', res.error || 'Unable to roll back.', 'Updater', 'error');
        }
      })
      .catch((e) => pushNotification('Rollback Error', e.message, 'Updater', 'error'));
  };

  const getOrderedLanes = () => {
    const entries = Object.entries(PROCESS_LANES);
    const running = entries.filter(([lk]) => (liveLanes[lk]?.status || 'IDLE') === 'RUNNING');
    const idle = entries.filter(([lk]) => (liveLanes[lk]?.status || 'IDLE') !== 'RUNNING');
    running.sort(([a], [b]) => (a === selectedMonitorLane ? -1 : b === selectedMonitorLane ? 1 : 0));
    return { ordered: [...running, ...idle], primaryRunningKey: running[0]?.[0] || '' };
  };

  const renderMonitorBody = (isMonitorPage = false) => {
    const { ordered, primaryRunningKey } = getOrderedLanes();
    const clearSelectedLaneLog = () =>
      fetch(`${NODE_API_BASE}/lanes/clear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lane: selectedMonitorLane }),
      })
        .then((r) => r.json())
        .then((res) => {
          if (res?.lanes?.logs) setLiveLogs(res.lanes.logs);
          else setLiveLogs((prev) => ({ ...prev, [selectedMonitorLane]: '--- Monitor cleared ---' }));
        })
        .catch(() => {});

    return (
      <div className="flex flex-col gap-3 h-full min-h-0">
        {/* Clean 2-Row Sidebar Header OR Integrated Monitor Page Header */}
        {isMonitorPage ? (
          <div className={`flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b ${skin.border} shrink-0`}>
            <div className="flex items-center gap-2.5">
              <button
                onClick={() => setActivePage(previousPageBeforeMonitor || 'dashboard')}
                className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200"
              >
                ⬅ Back
              </button>
              <span className="text-sm font-extrabold uppercase tracking-wide text-white">🖥️ Live Multi-Lane Task Monitor</span>
              {anyLaneRunning && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-600 animate-pulse">
                  LIVE
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={clearSelectedLaneLog} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-amber-900/70 text-amber-300 border border-slate-700 text-xs font-semibold">
                🧹 Clear
              </button>
              <button onClick={() => setInvertTerminalLogs(!invertTerminalLogs)} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 text-xs font-semibold">
                {invertTerminalLogs ? '⬇️ Newest Top' : '⬆️ Oldest Top'}
              </button>
              <button onClick={openLogsFolder} title={`Open ${STORAGE_ROOT}\\Logs\\Logs\\ in File Explorer`} className={`px-3 py-1.5 rounded-xl text-xs font-bold ${skin.accentBtn}`}>
                📂 View Logs
              </button>
            </div>
          </div>
        ) : (
          <div className={`space-y-2 pb-2.5 border-b ${skin.border} shrink-0`}>
            {/* Row 1: Title + LIVE pill + evenly spaced Pin / Expand / Close icon buttons */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-extrabold uppercase tracking-wide text-white truncate">🖥️ Live Task Monitor</span>
                {anyLaneRunning && (
                  <span className="px-1.5 py-0.5 rounded-full text-[9.5px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-600 animate-pulse shrink-0">
                    LIVE
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => setMonitorPinned(!monitorPinned)}
                  title={monitorPinned ? 'Unpin Monitor Sidebar' : 'Pin Monitor Sidebar'}
                  className={`w-7 h-7 rounded-lg border flex items-center justify-center transition ${monitorPinned ? skin.accentActive : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'}`}
                >
                  <ThumbtackPinIcon pinned={monitorPinned} className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => openMonitorPage()}
                  title="Expand to Integrated Monitor Workspace Page"
                  className="w-7 h-7 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center justify-center text-xs"
                >
                  ⛶
                </button>
                <button
                  onClick={() => setShowMonitor(false)}
                  title="Close Monitor Sidebar"
                  className="w-7 h-7 rounded-lg bg-slate-800 hover:bg-rose-700 text-slate-300 hover:text-white border border-slate-700 flex items-center justify-center text-xs"
                >
                  ✖
                </button>
              </div>
            </div>
            {/* Row 2: Clean 3-column evenly spaced action toolbar */}
            <div className="grid grid-cols-3 gap-1.5">
              <button onClick={clearSelectedLaneLog} className="py-1.5 px-2 rounded-lg bg-slate-800 hover:bg-amber-900/70 text-amber-300 border border-slate-700 text-[11px] font-semibold">
                🧹 Clear
              </button>
              <button onClick={() => setInvertTerminalLogs(!invertTerminalLogs)} className="py-1.5 px-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700 text-[11px] font-semibold">
                {invertTerminalLogs ? '⬇️ Newest' : '⬆️ Oldest'}
              </button>
              <button onClick={openLogsFolder} title={`Open ${STORAGE_ROOT}\\Logs\\Logs\\ in File Explorer`} className="py-1.5 px-2 rounded-lg bg-sky-900/80 hover:bg-sky-700 text-sky-200 border border-sky-700 text-[11px] font-bold">
                📂 View Logs
              </button>
            </div>
          </div>
        )}

        {/* Dynamic Process Bubbles — ONLY Active/Queued Workers Shown (Unused Workers Hidden!) */}
        {(() => {
          const isSlotInUse = (lk) => {
            const st = liveLanes[lk] || {};
            return st.status === 'RUNNING' || (Array.isArray(st.queued_jobs) && st.queued_jobs.length > 0);
          };
          const activeEntries = ordered.filter(([lk]) => isSlotInUse(lk));
          const recentLogEntries = ordered.filter(([lk]) => {
            const st = liveLanes[lk] || {};
            return !isSlotInUse(lk) && st.status && st.status !== 'IDLE' && Boolean(st.process_name || (st.title && !String(st.title).endsWith(': Idle')));
          });

          const renderLaneCard = ([lk, meta], layoutMode = 'sidebar') => {
            const st = liveLanes[lk] || {};
            const isRun = st.status === 'RUNNING';
            const isPrimaryRun = isRun && lk === primaryRunningKey;
            const isSel = selectedMonitorLane === lk;
            const hasSub = isRun && safeNum(st.sub_total, 0) > 0;
            const hasCards = safeNum(st.total_cards, 0) > 0;
            const hasSubsets = safeNum(st.total_subsets, 0) > 0;
            const cpsVal = safeNum(st.cards_per_sec, 0);
            const speedBadge = cpsVal >= 1 ? `${cpsVal.toFixed(1)} cards/s` : (cpsVal > 0 ? `${(cpsVal * 60).toFixed(1)} cards/min` : '');
            const hasRealTitle = Boolean(st.process_name || (st.title && !String(st.title).endsWith(': Idle')));
            const procIcon = (isRun || hasRealTitle) && st.job_icon ? st.job_icon : meta.icon;
            const procTitle = (isRun || hasRealTitle) ? (st.process_name || st.title || meta.shortName) : meta.shortName;
            const activeSetLbl = st.active_set_name && st.active_set_name !== procTitle ? st.active_set_name : '';
            const subDisplayName = st.sub_name || st.sub_label || 'Active Subset';

            const cardVisualClass = isPrimaryRun
              ? `${skin.accentActive} ring-1 ring-cyan-400/50 shadow-lg`
              : isRun
              ? (isSel ? 'bg-emerald-950/55 border-emerald-400/70 text-emerald-100 ring-1 ring-emerald-400/40 shadow-lg' : 'bg-emerald-950/35 border-emerald-500/40 text-emerald-100 shadow')
              : isSel
              ? 'bg-slate-800/85 border-slate-500 text-slate-200'
              : 'bg-slate-950/60 border-slate-800/80 text-slate-400 opacity-75 hover:opacity-100';

            if (layoutMode === 'idle_pill') {
              return (
                <button
                  key={lk}
                  onClick={() => setSelectedMonitorLane(lk)}
                  title={`${procTitle} (${meta.shortName}): ${st.status || 'IDLE'}`}
                  className={`flex-1 min-w-[150px] px-3 py-2 rounded-xl border text-left transition-all flex items-center justify-between gap-2 overflow-hidden ${cardVisualClass}`}
                >
                  <span className="text-[11px] font-bold text-slate-200 truncate">
                    {procIcon} {procTitle}
                  </span>
                  <span className={`font-mono text-[10px] shrink-0 ${st.status === 'COMPLETED' ? 'text-emerald-400 font-bold' : 'text-slate-500'}`}>
                    {st.status === 'COMPLETED' ? '✅ DONE' : (st.status || 'IDLE')}
                    {getLaneElapsedSec(st) > 0 ? ` • ⏱️ ${fmtEta(getLaneElapsedSec(st))}` : ''}
                  </span>
                </button>
              );
            }

            const widthCls =
              layoutMode === 'running_row'
                ? isPrimaryRun
                  ? 'flex-[1.55] min-w-[300px]'
                  : 'flex-1 min-w-[260px]'
                : 'w-full';

            return (
              <div
                key={lk}
                onClick={() => setSelectedMonitorLane(lk)}
                className={`${widthCls} min-w-0 overflow-hidden p-3 rounded-xl border cursor-pointer transition-all duration-200 flex flex-col justify-start gap-2 ${cardVisualClass}`}
              >
                <div className="flex items-start justify-between gap-2 text-[11px] min-w-0">
                  <span className={`font-bold leading-snug break-words whitespace-normal min-w-0 ${isRun ? 'text-white' : 'text-slate-300'}`}>
                    {procIcon} {procTitle}
                  </span>
                  <span className={`font-mono text-[10px] shrink-0 ${isRun ? 'text-emerald-300 font-extrabold' : 'text-slate-500'}`}>
                    {isRun ? `🟢 ${st.percent || 0}%` : (st.status || 'IDLE')}
                  </span>
                </div>

                {isRun ? (
                  <div className="space-y-2 min-w-0">
                    {/* TIER 1: OVERALL CARD-BASED PROGRESS + ACTIVE SET NAME */}
                    <div className="space-y-1 min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-1 text-[10px] font-mono text-slate-200">
                        <span>
                          {hasCards
                            ? `Overall (${Number(st.completed_cards || 0).toLocaleString()}/${Number(st.total_cards).toLocaleString()} Cards${st.total_sets > 1 ? ` • Set ${st.set_index || 1}/${st.total_sets}` : ''})`
                            : hasSubsets
                            ? `Overall (${st.completed_subsets || 0}/${st.total_subsets} Subsets${st.total_sets > 1 ? ` • Set ${st.set_index || 1}/${st.total_sets}` : ''})`
                            : `Overall (${st.current || 0}/${st.total || 1})`}
                        </span>
                        <span className="flex items-center gap-2 shrink-0">
                          <span className="text-slate-300 font-semibold">⏱️ {fmtEta(getLaneElapsedSec(st))}</span>
                          <span className="text-cyan-300 font-bold">ETA {fmtEta(st.eta_seconds)}</span>
                        </span>
                      </div>
                      {activeSetLbl && (
                        <div className="flex flex-wrap items-baseline justify-between gap-1.5 min-w-0">
                          <span className="text-[11px] font-bold text-white leading-snug break-words whitespace-normal min-w-0">
                            {activeSetLbl}
                          </span>
                          {(hasSubsets || speedBadge) && (
                            <span className="text-[9.5px] font-mono text-slate-400 shrink-0">
                              {hasSubsets ? `Sub ${st.completed_subsets || 0}/${st.total_subsets}` : ''}
                              {hasSubsets && speedBadge ? ' • ' : ''}
                              {speedBadge}
                            </span>
                          )}
                        </div>
                      )}
                      <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-cyan-400 to-blue-500 transition-all duration-300" style={{ width: `${st.percent || 0}%` }} />
                      </div>
                    </div>

                    {/* TIER 2: ACTIVE PARALLEL / SUBSET CARD PROGRESS & LEARNING ETA */}
                    {hasSub && (
                      <div className="space-y-1 min-w-0">
                        <div className="flex flex-wrap items-start justify-between gap-1 text-[10px] font-mono text-amber-300 min-w-0">
                          <span className="leading-snug break-words whitespace-normal min-w-0">
                            ↳ {subDisplayName} ({Number(st.sub_current || 0).toLocaleString()}/{Number(st.sub_total).toLocaleString()} Cards)
                          </span>
                          <span className="flex items-center gap-2 shrink-0">
                            {getSubElapsedSec(st) > 0 && <span className="text-amber-200/80">⏱️ {fmtEta(getSubElapsedSec(st))}</span>}
                            <span className="font-bold">ETA {fmtEta(st.sub_eta_seconds)}</span>
                          </span>
                        </div>
                        <div className="w-full h-1 bg-slate-900 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-amber-400 to-emerald-400 transition-all duration-300" style={{ width: `${st.sub_percent || 0}%` }} />
                        </div>
                      </div>
                    )}

                    {/* CURRENT CARD / URL (WRAPS CLEANLY INSIDE CARD) + STOP BUTTON */}
                    <div className="flex items-start justify-between gap-2 text-[10px] text-slate-300 pt-0.5 min-w-0">
                      <span className="flex-1 min-w-0 leading-snug [overflow-wrap:anywhere] whitespace-normal">
                        {st.current_item}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          fetch(`${NODE_API_BASE}/jobs/stop`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lane: lk }) }).catch(() => {});
                        }}
                        className="px-2 py-0.5 rounded bg-rose-900/90 text-rose-100 hover:bg-rose-700 font-bold shrink-0"
                      >
                        Stop
                      </button>
                    </div>
                  </div>
                ) : (
                    layoutMode === 'all_idle_grid' && (
                    <div className="text-[10px] text-slate-500 break-words whitespace-normal line-clamp-1">
                      {st.status === 'COMPLETED'
                        ? `✅ ${st.title}${getLaneElapsedSec(st) > 0 ? ` (⏱️ ${fmtEta(getLaneElapsedSec(st))})` : ''}`
                        : (getLaneElapsedSec(st) > 0 ? `${st.status} (⏱️ ${fmtEta(getLaneElapsedSec(st))})` : 'Idle')}
                    </div>
                  )
                )}

                {Array.isArray(st.queued_jobs) && st.queued_jobs.length > 0 && (
                  <div className="mt-auto pt-1.5 border-t border-slate-800/80 space-y-1 min-w-0">
                    <div className="flex items-center justify-between text-[10px] text-sky-300 font-bold">
                      <span>📥 Queued ({st.queued_jobs.length})</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          fetch(`${NODE_API_BASE}/jobs/queue/clear`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lane: lk }) }).catch(() => {});
                        }}
                        className="text-[9.5px] text-rose-400 hover:text-rose-200"
                      >
                        Clear
                      </button>
                    </div>
                    {st.queued_jobs.map((qItem, qi) => (
                      <div key={qItem.queue_id || qi} className="flex items-center justify-between gap-1.5 text-[10px] bg-slate-900/90 px-1.5 py-0.5 rounded min-w-0">
                        <span className="flex-1 min-w-0 break-words whitespace-normal text-slate-300">#{qi + 1} {qItem.title}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            fetch(`${NODE_API_BASE}/jobs/queue/remove`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lane: lk, queueId: qItem.queue_id }) }).catch(() => {});
                          }}
                          className="text-rose-400 hover:text-rose-200 shrink-0"
                          title="Remove from queue"
                        >
                          ✖
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          };

          if (!isMonitorPage) {
            if (activeEntries.length === 0) {
              return (
                <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/90 text-[11px] text-slate-400 space-y-2 shrink-0">
                  <div className="flex items-center justify-between">
                    <span>💤 All 8 parallel workers are idle.</span>
                    <span className="font-mono text-[10px] text-slate-500">0/8 active</span>
                  </div>
                  {recentLogEntries.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-slate-800/80">
                      <span className="text-[10px] text-slate-500 mr-1">Recent logs:</span>
                      {recentLogEntries.slice(0, 4).map(([lk, meta]) => {
                        const st = liveLanes[lk] || {};
                        const lbl = st.process_name || st.title || meta.shortName;
                        return (
                          <button
                            key={lk}
                            onClick={() => setSelectedMonitorLane(lk)}
                            className={`px-2 py-0.5 rounded-lg border text-[10px] truncate max-w-[160px] ${selectedMonitorLane === lk ? skin.accentActive : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-white'}`}
                          >
                            {st.job_icon || meta.icon} {lbl}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }
            return (
              <div className="space-y-2 overflow-y-auto max-h-[48%] pr-0.5 shrink-0">
                {activeEntries.map((entry) => renderLaneCard(entry, 'sidebar'))}
              </div>
            );
          }

          if (activeEntries.length === 0) {
            return (
              <div className="px-4 py-3 rounded-xl bg-slate-950/75 border border-slate-800 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0">
                <span>💤 All 8 parallel workers are currently idle and ready for tasks.</span>
                {recentLogEntries.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[10.5px] text-slate-500">Recent finished logs:</span>
                    {recentLogEntries.slice(0, 5).map(([lk, meta]) => {
                      const st = liveLanes[lk] || {};
                      const lbl = st.process_name || st.title || meta.shortName;
                      return (
                        <button
                          key={lk}
                          onClick={() => setSelectedMonitorLane(lk)}
                          className={`px-2.5 py-1 rounded-lg border text-[11px] font-semibold truncate max-w-[220px] ${selectedMonitorLane === lk ? skin.accentActive : 'bg-slate-900 border-slate-800 text-slate-300 hover:text-white'}`}
                        >
                          {st.job_icon || meta.icon} {lbl} ({st.status})
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          }

          return (
            <div className="flex flex-wrap lg:flex-nowrap gap-3 items-stretch shrink-0">
              {activeEntries.map((entry) => renderLaneCard(entry, 'running_row'))}
            </div>
          );
        })()}

        {/* Live Lane Terminal Output */}
        <pre className="flex-1 min-h-0 bg-slate-950 border border-slate-800 rounded-xl p-3 text-[11px] font-mono text-emerald-300 overflow-y-auto whitespace-pre-wrap break-words">
          {(() => {
            const lines = (liveLogs[selectedMonitorLane] || 'Ready.').split(/\r?\n/).filter(Boolean);
            return (invertTerminalLogs ? [...lines].reverse() : lines).join('\n');
          })()}
        </pre>
      </div>
    );
  };

  const navExpanded = navPinned || navHovered || showSkinPopover;

  return (
    <div className={`h-screen w-screen overflow-hidden flex ${skin.appBg} ${skin.textMain} font-sans select-none`}>
      {/* LEFT CHROME-PULSE AUTO-COLLAPSING & PINNABLE NAVIGATION RAIL */}
      <div
        onMouseEnter={() => setNavHovered(true)}
        onMouseLeave={() => { setNavHovered(false); setHoveredCatId(null); if (!showSkinPopover) setToggledCats({}); }}
        className={`relative z-30 h-full shrink-0 transition-all duration-200 ease-out ${navPinned ? 'w-64' : 'w-[74px]'}`}
      >
        <aside
          className={`h-full ${skin.railBg} border-r ${skin.border} flex flex-col transition-all duration-200 ease-out shadow-2xl ${
            navExpanded ? 'w-64' : 'w-[74px]'
          } ${!navPinned && navHovered ? 'absolute left-0 top-0 bottom-0 z-40' : 'relative'}`}
        >
          <div className={`px-2.5 py-2.5 border-b ${skin.border} flex items-center ${navExpanded ? 'justify-between gap-2' : 'justify-center'} shrink-0`}>
            <button
              type="button"
              onClick={() => setActivePage('dashboard')}
              title="Tabulas Home Dashboard"
              className={`flex items-center ${navExpanded ? 'gap-2.5 flex-1 px-1.5 py-1' : 'justify-center p-1'} min-w-0 rounded-2xl border text-left transition-all cursor-pointer ${
                activePage === 'dashboard'
                  ? `${skin.accentActive} ring-1 ring-white/25 shadow-md`
                  : 'border-transparent hover:bg-slate-800/75'
              }`}
            >
              <div className={`w-11 h-11 rounded-2xl ${skin.iconBg} border flex items-center justify-center text-2xl shadow-lg shrink-0 transition-transform ${activePage === 'dashboard' ? 'scale-[1.03]' : 'hover:scale-105'}`}>🗃️</div>
              {navExpanded && (
                <div className="min-w-0">
                  <div className="text-sm font-extrabold tracking-tight text-white truncate">Tabulas Hub</div>
                  <div className={`text-[10px] font-mono ${skin.accentText}`}>v{updaterInfo.current_version || APP_VERSION}{devMode ? ' • DEV' : ''}</div>
                </div>
              )}
            </button>
            {navExpanded && (
              <button
                onClick={() => setNavPinned(!navPinned)}
                title={navPinned ? 'Unpin Nav Rail (Auto-Collapse)' : 'Pin Nav Rail Open'}
                className={`w-7 h-7 rounded-lg border flex items-center justify-center shrink-0 transition ${navPinned ? skin.accentActive : 'bg-slate-800/80 border-slate-700 text-slate-400 hover:text-white'}`}
              >
                <ThumbtackPinIcon pinned={navPinned} className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <nav className="flex-1 overflow-y-auto p-2 space-y-2">
            {NAV_CATEGORIES.map((cat) => {
              const visibleItems = cat.items.filter((it) => {
                if (it.devOnly) return devMode;
                if (it.hiddenUntilLaunched) return devMode || unlockedHiddenPages[it.id] || activePage === it.id;
                return true;
              });
              const isCatActive = cat.id === activeCategoryId;
              const isCatExpanded = navExpanded && (toggledCats[cat.id] !== undefined ? toggledCats[cat.id] : (isCatActive || hoveredCatId === cat.id));
              const catBadge =
                cat.id === 'inventory_mgmt' && batches.length > 0 ? batches.length :
                cat.id === 'sales_hub' && gradingCandidates.length > 0 ? gradingCandidates.length :
                cat.id === 'settings' && updaterInfo.pending_count > 0 ? updaterInfo.pending_count : 0;

              return (
                <div key={cat.id} onMouseEnter={() => setHoveredCatId(cat.id)} className="space-y-1">
                  <button
                    onClick={() => {
                      if (!isCatActive && visibleItems[0]) {
                        setActivePage(visibleItems[0].id);
                        setToggledCats({ [cat.id]: true });
                      } else {
                        setToggledCats({ [cat.id]: !isCatExpanded });
                      }
                    }}
                    className={`relative w-full flex items-center ${navExpanded ? 'justify-between px-2' : 'justify-center'} py-1.5 rounded-xl border transition-all duration-150 ${
                      isCatActive ? `${skin.accentActive} shadow-md border-l-4` : 'border-transparent hover:bg-slate-800/70 text-slate-300'
                    }`}
                    title={cat.label}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className={`relative w-10 h-10 rounded-2xl ${skin.iconBg} border flex items-center justify-center text-xl shadow-md shrink-0 transition-transform hover:scale-105`}>
                        <span>{cat.icon}</span>
                        {catBadge > 0 && (
                          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-600 text-white text-[10px] font-extrabold flex items-center justify-center shadow">
                            {catBadge > 99 ? '99+' : catBadge}
                          </span>
                        )}
                      </div>
                      {navExpanded && <span className="text-xs font-bold truncate">{cat.label}</span>}
                    </div>
                    {navExpanded && <span className="text-xs opacity-70">{isCatExpanded ? '⌄' : '›'}</span>}
                  </button>

                  {isCatExpanded && (
                    <div className="pl-3 space-y-1">
                      {visibleItems.map((item) => {
                        const isAct = activePage === item.id;
                        return (
                          <button
                            key={item.id}
                            onClick={() => setActivePage(item.id)}
                            className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs border transition-all ${
                              isAct ? `${skin.accentActive} font-bold translate-x-0.5 border-l-4` : 'border-transparent text-slate-300 hover:bg-slate-800/80 hover:text-white'
                            }`}
                          >
                            <span className="flex items-center gap-2 truncate">
                              <span className="text-sm">{item.icon}</span>
                              <span className="truncate">{item.label}</span>
                            </span>
                            {item.hiddenUntilLaunched && !devMode && (
                              <span
                                onClick={(e) => { e.stopPropagation(); setUnlockedHiddenPages((p) => ({ ...p, [item.id]: false })); if (activePage === item.id) setActivePage('inventory'); }}
                                className="text-[10px] text-slate-400 hover:text-rose-400 ml-1"
                              >
                                ✖
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>

          {/* Compact DEV Mode Pill (Live Disk API hidden unless disconnected/error in Top Bar) */}
          {devMode && (
            <div className="px-2.5 pb-2 shrink-0 flex justify-center">
              <span className="px-2.5 py-1 rounded-xl text-[10px] font-extrabold bg-fuchsia-950 text-fuchsia-300 border border-fuchsia-600/60 truncate">
                {navExpanded ? '🧪 DEV MODE ON' : '🧪'}
              </span>
            </div>
          )}

          <div ref={skinPopoverRef} className={`relative p-2.5 border-t ${skin.border} shrink-0`}>
            <button
              onClick={() => setShowSkinPopover((prev) => !prev)}
              title={`Switch Chrome-Pulse Skin (Current: ${skin.name})`}
              className={`w-full flex items-center ${navExpanded ? 'justify-between px-2.5 py-2' : 'justify-center py-1.5'} rounded-xl border transition-all ${
                showSkinPopover ? skin.accentActive : 'bg-slate-950/70 hover:bg-slate-800/80 border-slate-700/80 text-slate-200'
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div
                  style={{ background: skin.swatch }}
                  className="w-8 h-8 rounded-xl ring-2 ring-white/30 flex items-center justify-center text-base shadow-lg shrink-0"
                >
                  🎨
                </div>
                {navExpanded && (
                  <div className="text-left min-w-0 flex-1">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Theme Skin</div>
                    <div className={`text-[11px] font-bold leading-tight whitespace-normal break-words ${skin.accentText}`}>{skin.name}</div>
                  </div>
                )}
              </div>
              {navExpanded && <span className="text-xs opacity-70">{showSkinPopover ? '▲' : '▼'}</span>}
            </button>

            {showSkinPopover && (
              <div className="absolute left-full bottom-0 pl-2 z-50">
                <div className="w-80 bg-slate-900/95 backdrop-blur-xl border border-slate-700 rounded-2xl shadow-2xl p-3 space-y-2">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                    <span className="text-xs font-bold text-white">🎨 Chrome-Pulse 3D Skins (9)</span>
                    <button onClick={() => setShowSkinPopover(false)} className="text-[10px] text-slate-400 hover:text-white">✖</button>
                  </div>
                  <div className="grid grid-cols-1 gap-1.5 max-h-80 overflow-y-auto pr-0.5">
                    {Object.entries(CHROME_PULSE_SKINS).map(([k, sObj]) => {
                      const isSelSkin = skinKey === k;
                      return (
                        <button
                          key={k}
                          onClick={() => { changeSkin(k); setShowSkinPopover(false); }}
                          className={`w-full flex items-center justify-between px-2.5 py-2 rounded-xl border text-left transition ${
                            isSelSkin ? `${sObj.accentActive} border-2` : 'bg-slate-950/80 border-slate-800 text-slate-300 hover:bg-slate-800/80'
                          }`}
                        >
                          <span className="flex items-center gap-2.5 min-w-0">
                            <span className="w-4 h-4 rounded-full shadow ring-1 ring-white/40 shrink-0" style={{ background: sObj.swatch }} />
                            <span className="min-w-0">
                              <span className="block text-xs font-bold truncate">{sObj.name}</span>
                              {sObj.tagline && <span className="block text-[9.5px] text-slate-400 truncate">{sObj.tagline}</span>}
                            </span>
                          </span>
                          {isSelSkin && <span className="text-xs font-bold shrink-0 ml-1">✓</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* CENTER WORKSPACE + TOP BAR */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <header className={`${skin.railBg} border-b ${skin.border} px-4 py-2 flex items-center justify-between gap-3 shrink-0 z-20`}>
          {/* Connecting / Error-Only API Status Pill (Hidden Once Connected & Healthy) */}
          {backendConnected === null && (
            <span className="px-2.5 py-1 rounded-xl text-[11px] font-semibold bg-slate-900/90 text-slate-300 border border-slate-700/80 flex items-center gap-1.5 shrink-0">
              <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
              <span>Connecting...</span>
            </span>
          )}
          {backendConnected === false && (
            <button
              onClick={() => refreshAllHubData()}
              title="Local Python Disk API is unreachable — click to retry connection"
              className="px-2.5 py-1 rounded-xl text-[11px] font-extrabold bg-rose-950/90 hover:bg-rose-900 text-rose-200 border border-rose-500/80 flex items-center gap-1.5 shrink-0 animate-pulse shadow"
            >
              <span className="w-2 h-2 rounded-full bg-rose-400" />
              <span>API Disconnected</span>
            </button>
          )}
          {/* Compact Dynamic Process Bubbles (Shown on All Non-Monitor Pages) */}
          <div className="flex-1 flex items-center gap-1.5 min-w-0 overflow-x-auto no-scrollbar">
            {activePage === 'live_monitor' ? (
              <span className="text-xs font-extrabold uppercase tracking-wider text-white flex items-center gap-2">
                🖥️ Live Multi-Lane Monitor Workspace
              </span>
            ) : (
              (() => {
                const { ordered, primaryRunningKey } = getOrderedLanes();
                const activeTopBar = ordered.filter(([lk]) => {
                  const st = liveLanes[lk] || {};
                  return st.status === 'RUNNING' || (Array.isArray(st.queued_jobs) && st.queued_jobs.length > 0);
                });
                if (activeTopBar.length === 0) return null;
                return activeTopBar.map(([lk, meta]) => {
                  const st = liveLanes[lk] || {};
                  const isRun = st.status === 'RUNNING';
                  const isPrim = isRun && lk === primaryRunningKey;
                  const bIcon = st.job_icon || meta.icon;
                  const bTitle = st.process_name || st.title || meta.shortName;
                  const tip = `${bTitle}: ${st.percent || 0}%${safeNum(st.total_cards, 0) > 0 ? ` (${Number(st.completed_cards || 0).toLocaleString()}/${Number(st.total_cards).toLocaleString()} Cards)` : ''}${st.sub_name ? ` | ${st.sub_name} (${Number(st.sub_current || 0).toLocaleString()}/${Number(st.sub_total).toLocaleString()})` : ''} | Elapsed ${fmtEta(getLaneElapsedSec(st))} | ETA ${fmtEta(st.eta_seconds)}`;
                  return (
                    <button
                      key={lk}
                      title={`${tip} — Click to open Full-Page Monitor`}
                      onClick={() => openMonitorPage(lk)}
                      className={`rounded-xl border transition-all flex items-center gap-1.5 shrink-0 ${
                        isPrim
                          ? `${skin.accentActive} px-2.5 py-1 shadow-md`
                          : 'bg-emerald-950/60 border-emerald-600/60 text-emerald-200 px-2.5 py-1'
                      }`}
                    >
                      <span className="text-xs">{bIcon}</span>
                      <div className="flex items-center gap-1.5 text-[10.5px]">
                        <span className="font-bold text-white max-w-[165px] truncate">{bTitle}</span>
                        <span className="font-mono font-extrabold text-emerald-300">{st.percent || 0}%</span>
                        <div className="w-10 h-1.5 bg-slate-900 rounded-full overflow-hidden hidden xl:block">
                          <div className="h-full bg-gradient-to-r from-cyan-400 to-emerald-400" style={{ width: `${st.percent || 0}%` }} />
                        </div>
                        <span className="font-mono text-[10px] text-slate-300 shrink-0">
                          ⏱️ {fmtEta(getLaneElapsedSec(st))}
                        </span>
                        <span className="font-mono text-[10px] text-cyan-300 font-bold shrink-0">
                          ETA {fmtEta(st.eta_seconds)}
                        </span>
                      </div>
                    </button>
                  );
                });
              })()
            )}
          </div>

          <div className="flex items-center gap-2">
            <div ref={notifContainerRef} className="relative">
              <button
                onClick={() => setShowNotifPopup(!showNotifPopup)}
                className="relative w-10 h-10 rounded-2xl bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-lg flex items-center justify-center shadow transition hover:scale-105"
                title="Notifications"
              >
                🔔
                {notifications.length > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-600 text-white text-[10px] font-extrabold flex items-center justify-center">
                    {notifications.length > 99 ? '99+' : notifications.length}
                  </span>
                )}
              </button>
              {showNotifPopup && (
                <div className="absolute right-0 mt-2 w-96 bg-slate-900/95 backdrop-blur-xl border border-slate-700 rounded-2xl shadow-2xl z-50 overflow-hidden">
                  <div className="p-3 border-b border-slate-800 flex items-center justify-between">
                    <span className="text-xs font-bold text-white">🔔 Notifications ({notifications.length})</span>
                    <div className="flex items-center gap-2">
                      {notifications.length > 0 && <button onClick={() => clearNotification('', true)} className="text-[11px] text-amber-300 hover:text-amber-200 font-semibold">Clear All</button>}
                      <button onClick={() => { setShowNotifPopup(false); openHiddenPage('notification_history'); }} className="text-[11px] text-sky-400 hover:underline font-semibold">Full History ↗</button>
                    </div>
                  </div>
                  <div className="max-h-72 overflow-y-auto divide-y divide-slate-800">
                    {notifications.length === 0 ? (
                      <div className="p-4 text-xs text-slate-500 text-center">No active notifications. Archived in Notifications_History.csv.</div>
                    ) : (
                      notifications.slice(0, 15).map((n) => (
                        <div key={n.Notification_ID} className="p-2.5 hover:bg-slate-800/50 flex items-start justify-between gap-2 text-xs">
                          <div className="min-w-0">
                            <div className="font-bold text-white truncate">{n.Title}</div>
                            <div className="text-[11px] text-slate-300">{n.Message}</div>
                            <div className="text-[10px] text-slate-500 font-mono mt-0.5">{n.Timestamp} • {n.Category}</div>
                          </div>
                          <button onClick={() => clearNotification(n.Notification_ID, false)} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 shrink-0">Clear</button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {setCart.length > 0 && (
              <button
                onClick={() => {
                  const nextOpen = !showCartSidebar;
                  setShowCartSidebar(nextOpen);
                  if (nextOpen && !monitorPinned) setShowMonitor(false);
                }}
                className="px-3 py-1.5 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-200 text-xs font-bold"
              >
                🛒 Set Cart ({setCart.length})
              </button>
            )}

            {activePage !== 'live_monitor' && (
              <button
                onClick={() => {
                  const nextMon = !showMonitor;
                  setShowMonitor(nextMon);
                  if (nextMon && !cartPinned) setShowCartSidebar(false);
                }}
                className={`px-3 py-1.5 rounded-xl border text-xs font-bold ${anyLaneRunning ? 'bg-emerald-950/80 border-emerald-600 text-emerald-300' : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'}`}
              >
                {showMonitor ? '▶️ Hide Monitor' : `🖥️ Monitor${anyLaneRunning ? ' (Live)' : ''}`}
              </button>
            )}
          </div>
        </header>

        {replaceImgTarget && (
          <ReplaceCardImagesModal
            target={replaceImgTarget}
            skin={skin}
            onClose={() => setReplaceImgTarget(null)}
            onReplaced={(res) => {
              const sidesTxt = (res.replacedSides || []).join(' & ') || 'Image';
              const gradeTxt = res.newPSA ? ` | Grade: PSA ${res.oldPSA || '?'}→${res.newPSA} / BGS ${res.oldBGS || '?'}→${res.newBGS}` : '';
              if (replaceImgTarget.type === 'inventory') {
                if (Array.isArray(res.rows)) setInventory(res.rows);
                setInvEditorImgBust((v) => v + 1);
                setInvEditorDrafts((prev) => {
                  const cp = { ...prev };
                  delete cp[replaceImgTarget.sku];
                  return cp;
                });
              } else {
                if (Array.isArray(res.cards)) {
                  setBatches((prev) =>
                    prev.map((b) =>
                      b.batchName === replaceImgTarget.batchName
                        ? { ...b, cards: res.cards, needsReviewCount: res.cards.filter((x) => String(x.Needs_Review).toLowerCase() === 'true').length }
                        : b
                    )
                  );
                }
                setBatchImgBust((v) => v + 1);
                setBatchDraftEdits((prev) => {
                  const cp = { ...prev };
                  delete cp[replaceImgTarget.sku];
                  return cp;
                });
                loadBatchesFromDisk(replaceImgTarget.batchName);
              }
              pushNotification(
                `🖼️ Replaced ${sidesTxt} (SKU ${replaceImgTarget.sku})`,
                `Saved clean scan(s), rebuilt 8-Corner Sheet${gradeTxt}.`,
                replaceImgTarget.type === 'inventory' ? 'Inventory' : 'Batch',
                'success'
              );
            }}
          />
        )}

        {activeToasts.length > 0 && (
          <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-md">
            {activeToasts.slice(0, 3).map((t) => {
              const sevBorder =
                t.Severity === 'error'
                  ? 'border-rose-500/70'
                  : t.Severity === 'warning'
                  ? 'border-amber-500/70'
                  : t.Severity === 'success'
                  ? 'border-emerald-500/65'
                  : 'border-cyan-500/60';
              return (
                <div key={t.Notification_ID} className={`bg-slate-900/95 border ${sevBorder} shadow-2xl rounded-2xl p-3 flex items-start justify-between gap-3 text-xs backdrop-blur-xl`}>
                  <div className="min-w-0">
                    <div className="font-bold text-white">{t.Title}</div>
                    <div className="text-slate-300 text-[11px]">{t.Message}</div>
                  </div>
                  <button onClick={() => setActiveToasts((p) => p.filter((x) => x.Notification_ID !== t.Notification_ID))} className="text-slate-400 hover:text-white shrink-0">✖</button>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex-1 flex min-h-0 relative overflow-hidden">
          <main
            ref={mainScrollRef}
            className={`flex-1 flex flex-col min-w-0 min-h-0 ${
              (activePage === 'inventory_editor' && invEditorMode === 'deep_dive') ||
              activePage === 'batch_deep_dive' ||
              (activePage === 'grading_inspector' && inspectorMode === 'deep_dive')
                ? 'overflow-hidden p-2.5 gap-2'
                : 'overflow-y-auto p-4 gap-4'
            }`}
          >
            <TabulasErrorBoundary resetKey={`${activePage}-${activeBatchName}-${deepDiveIdx}`} onReset={() => setActivePage('dashboard')}>
            {/* 0. HOME DASHBOARD (DEFAULT STARTUP SCREEN — ALWAYS REACHABLE VIA TOP-LEFT LOGO) */}
            {activePage === 'dashboard' && (() => {
              const inStockCards = inventory.filter((c) => String(c.Status || '').trim().toLowerCase() !== 'sold');
              const cardOptVal = (c) => Math.max(safeNum(c.Raw_Price, 0), safeNum(c.EV_PSA, 0), safeNum(c.EV_BGS, 0));

              const pcCount = inStockCards.filter((c) => {
                const ht = String(c.Hold_Tag || '').toLowerCase();
                const st = String(c.Status || '').toLowerCase();
                return ht.includes('personal collection') || ht.includes('(pc)') || ht === 'pc' || st === 'pc / hold';
              }).length;
              const forSaleCount = Math.max(0, inStockCards.length - pcCount);
              const avgCardVal = inStockCards.length > 0 ? financialSummary.totalOptimalEv / inStockCards.length : 0;

              const hasDashSummary = Boolean(dashboardSummary && dashboardSummary.generatedAt);
              const dashGradingCount = hasDashSummary
                ? Number(dashboardSummary.gradingCandidatesCount || 0)
                : gradingCandidates.length;
              const dashGradingUpside = hasDashSummary
                ? safeNum(dashboardSummary.gradingUpsideTotal, 0)
                : gradingCandidates.reduce((a, c) => a + Math.max(0, safeNum(c.Max_Net_Gain, 0)), 0);
              const dashUnprintedCount = hasDashSummary
                ? Number(dashboardSummary.unprintedLabelsCount || 0)
                : inventory.filter((c) => String(c.Label_Printed || '').trim().toLowerCase() !== 'true').length;
              const dashMissingDraftsCount = hasDashSummary
                ? Number(dashboardSummary.sellableMissingDraftsCount || 0)
                : 0;
              const neverScrapedSets = Array.isArray(dashboardSummary?.neverScrapedSets) ? dashboardSummary.neverScrapedSets : [];
              const setsNeedingImages = Array.isArray(dashboardSummary?.setsNeedingImages) ? dashboardSummary.setsNeedingImages : [];
              const totalRemainingRefImages = setsNeedingImages.reduce((a, s) => a + Math.max(0, Number(s.remainingImages || 0)), 0);

              const activeLabelTpl = LABEL_TEMPLATES[labelTemplate] || LABEL_TEMPLATES.R037L;
              const dashCellsPerSheet = Math.max(1, (activeLabelTpl?.rows || 10) * (activeLabelTpl?.cols || 3));
              const estLabelSheets = dashUnprintedCount > 0 ? Math.ceil(dashUnprintedCount / dashCellsPerSheet) : 0;

              const nf = computeStatus?.neural_foundation || {};
              const cachedEmbeddingsCount = Number(nf.cached_embeddings_count || 0);
              const primaryGpuName = computeStatus?.primary_gpu?.name || 'Detecting GPU...';
              const activeProvider = computeStatus?.active_ocr_provider || 'CPUExecutionProvider';
              const shortProvider = activeProvider.replace('ExecutionProvider', '');

              // Collection Breakdown Donut Data (By Set / By Sport)
              const dashSetCounts = {};
              const dashSportCounts = {};
              inStockCards.forEach((c) => {
                const sName = c.Set || 'Unknown Set';
                dashSetCounts[sName] = (dashSetCounts[sName] || 0) + 1;
                const sp = inferSportFromSet(sName);
                dashSportCounts[sp] = (dashSportCounts[sp] || 0) + 1;
              });
              const sortedDashSets = Object.entries(dashSetCounts).sort((a, b) => b[1] - a[1]);
              const dashSetDonut = sortedDashSets.slice(0, 6).map(([label, value]) => ({ label, value }));
              if (sortedDashSets.length > 6) {
                dashSetDonut.push({
                  label: `Other (${sortedDashSets.length - 6} sets)`,
                  value: sortedDashSets.slice(6).reduce((a, [, v]) => a + v, 0),
                });
              }
              const dashSportDonut = Object.entries(dashSportCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([label, value]) => ({ label, value }));
              const activeDonutData = dashboardDonutMode === 'sport' ? dashSportDonut : dashSetDonut;

              // Top 5 Most Valuable In-Stock Cards by Optimal EV
              const top5ValuableCards = [...inStockCards]
                .sort((a, b) => cardOptVal(b) - cardOptVal(a))
                .slice(0, 5);

              // Value Trend Mini-Chart (last 20 snapshots)
              const histPts = (marketData.history || []).slice(-20);
              const latestHist = histPts.length > 0 ? histPts[histPts.length - 1] : null;
              const prevHist = histPts.length > 1 ? histPts[histPts.length - 2] : null;
              const histDeltaEv = (latestHist && prevHist)
                ? (safeNum(latestHist.Total_Optimal_EV, 0) - safeNum(prevHist.Total_Optimal_EV, 0))
                : null;

              // Active Parallel Workers
              const { ordered: dashOrderedLanes } = getOrderedLanes();
              const runningDashLanes = dashOrderedLanes.filter(([lk]) => {
                const st = liveLanes[lk] || {};
                return st.status === 'RUNNING' || (Array.isArray(st.queued_jobs) && st.queued_jobs.length > 0);
              });

              // Smart Interactive Task To-Do Hub (Priority-Sorted: urgent -> action -> maintenance)
              const incomingPdfTotal = incomingScans.reduce((a, b) => a + Number(b.pdfCount || 0), 0);
              const alertCount = (marketData.alerts || []).length;
              const autoTasks = [];

              if (Number(updaterInfo.pending_count || 0) > 0) {
                autoTasks.push({
                  id: 'pending_updates',
                  priority: 'urgent',
                  priorityOrder: 1,
                  icon: '🔄',
                  title: `Pending Software Updates (${updaterInfo.pending_count})`,
                  detail: `New release package${updaterInfo.pending_count === 1 ? '' : 's'} detected in Updates/ ready to inspect and install.`,
                  primaryLabel: 'Check for Updates',
                  onPrimary: () => setActivePage('about'),
                });
              }
              if (incomingScans.length > 0) {
                autoTasks.push({
                  id: 'incoming_scans',
                  priority: 'urgent',
                  priorityOrder: 2,
                  icon: '📂',
                  title: `Incoming Scans Ready to Process (${incomingScans.length} folder${incomingScans.length === 1 ? '' : 's'} • ${incomingPdfTotal.toLocaleString()} PDF${incomingPdfTotal === 1 ? '' : 's'})`,
                  detail: incomingScans.slice(0, 3).map((b) => `${b.batchName} (${b.pdfCount || 0})`).join(' · '),
                  primaryLabel: 'Open Processor',
                  onPrimary: () => setActivePage('scan_ingestion'),
                });
              }
              batches.forEach((b) => {
                const flagged = Number(b.needsReviewCount || 0);
                const totalC = Number(b.cardCount || 0);
                autoTasks.push({
                  id: `uncommitted_batch_${b.batchName}`,
                  priority: flagged > 0 ? 'urgent' : 'action',
                  priorityOrder: flagged > 0 ? 3 : 5,
                  icon: '🚩',
                  title: `Uncommitted Batch: ${b.batchName}`,
                  detail: `${totalC.toLocaleString()} card${totalC === 1 ? '' : 's'} staged${flagged > 0 ? ` • 🚩 ${flagged.toLocaleString()} flagged for review` : ' • Ready to review & commit'}`,
                  primaryLabel: 'Guided Review',
                  onPrimary: () => { setActiveBatchName(b.batchName); openHiddenPage('guided_batch_review'); },
                  secondaryLabel: 'Open Batch',
                  onSecondary: () => { setActiveBatchName(b.batchName); setActivePage('scan_ingestion'); },
                });
              });
              if (alertCount > 0) {
                autoTasks.push({
                  id: 'market_alerts',
                  priority: 'urgent',
                  priorityOrder: 4,
                  icon: '🔔',
                  title: `Market Price & Grading Alerts (${alertCount.toLocaleString()})`,
                  detail: 'Price spikes or new profitable grading opportunities detected in your portfolio.',
                  primaryLabel: 'View Alerts',
                  onPrimary: () => setActivePage('grading_engine'),
                });
              }
              if (dashUnprintedCount > 0) {
                autoTasks.push({
                  id: 'unprinted_labels',
                  priority: 'action',
                  priorityOrder: 6,
                  icon: '🏷️',
                  title: `Unprinted Inventory Labels (${dashUnprintedCount.toLocaleString()})`,
                  detail: `~${estLabelSheets.toLocaleString()} sheet${estLabelSheets === 1 ? '' : 's'} queued using ${activeLabelTpl?.name || labelTemplate} (${dashCellsPerSheet}/sheet).`,
                  primaryLabel: 'Print Labels',
                  onPrimary: () => setActivePage('label_hub'),
                });
              }
              if (neverScrapedSets.length > 0) {
                const visiblePreview = showAllNeverScraped ? neverScrapedSets : neverScrapedSets.slice(0, 4);
                autoTasks.push({
                  id: 'never_scraped_sets',
                  priority: 'action',
                  priorityOrder: 7,
                  icon: '🏛️',
                  title: `Tracked Sets Missing Checklists (${neverScrapedSets.length.toLocaleString()})`,
                  detail: visiblePreview.map((s) => s.setName).join(' · ') + (!showAllNeverScraped && neverScrapedSets.length > 4 ? ` (+${neverScrapedSets.length - 4} more)` : ''),
                  expandableCount: neverScrapedSets.length > 4 ? neverScrapedSets.length : 0,
                  primaryLabel: 'Open Checklist Builder',
                  onPrimary: () => setActivePage('checklist_builder'),
                });
              }
              if (dashMissingDraftsCount > 0) {
                autoTasks.push({
                  id: 'missing_listing_drafts',
                  priority: 'action',
                  priorityOrder: 8,
                  icon: '✍️',
                  title: `Sellable Cards Missing Listing Drafts (${dashMissingDraftsCount.toLocaleString()})`,
                  detail: 'In-stock For Sale / Make Offer cards without a generated eBay/Marketplace draft yet.',
                  primaryLabel: 'Open Listing Writer',
                  onPrimary: () => setActivePage('listing_writer'),
                });
              }
              if (setsNeedingImages.length > 0) {
                const topImgSets = setsNeedingImages.slice(0, 3).map((s) => `${s.setName} (${Number(s.remainingImages || 0).toLocaleString()} left)`).join(' · ');
                autoTasks.push({
                  id: 'sets_needing_images',
                  priority: 'maintenance',
                  priorityOrder: 9,
                  icon: '🖼️',
                  title: `Reference Images Ready to Download (${setsNeedingImages.length} set${setsNeedingImages.length === 1 ? '' : 's'} • ${totalRemainingRefImages.toLocaleString()} fronts)`,
                  detail: topImgSets,
                  primaryLabel: 'Open Checklist Builder',
                  onPrimary: () => setActivePage('checklist_builder'),
                });
              }
              if (computeStatus && !nf.dinov2_installed) {
                autoTasks.push({
                  id: 'dinov2_check',
                  priority: 'maintenance',
                  priorityOrder: 10,
                  icon: '🧬',
                  title: 'DINOv2 Neural Index Not Installed',
                  detail: 'Download the local DINOv2-small ONNX model (~88 MB) for GPU-accelerated deep visual card matching.',
                  primaryLabel: 'Open GPU Settings',
                  onPrimary: () => setActivePage('general_settings'),
                });
              }
              autoTasks.sort((a, b) => a.priorityOrder - b.priorityOrder);

              const completedCustomCount = customTodos.filter((t) => t.done).length;
              const priorityBadgeStyle = {
                urgent: { label: '🔴 Urgent', cls: 'bg-rose-950/90 text-rose-200 border-rose-500/60' },
                action: { label: '🟠 Action', cls: 'bg-amber-950/90 text-amber-200 border-amber-500/60' },
                maintenance: { label: '🔵 Maintenance', cls: 'bg-sky-950/90 text-sky-200 border-sky-500/60' },
              };

              return (
                <div className="space-y-4">
                  {/* 1. HEADER BAR & QUICK-LAUNCH STRIP */}
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-2.5 min-w-0">
                        <h1 className="text-lg font-extrabold tracking-tight text-white">
                          🗃️ Tabulas Card Hub — Home Dashboard
                        </h1>
                        <span className={`px-2 py-0.5 rounded-lg text-[10.5px] font-mono font-bold border ${skin.accentActive}`}>
                          v{updaterInfo.current_version || APP_VERSION}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActivePage('general_settings')}
                        title="Open Hardware & GPU Acceleration Settings"
                        className="flex flex-wrap items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-950/80 hover:bg-slate-900 border border-slate-700/80 text-[11px] transition text-left"
                      >
                        <span className="font-bold text-emerald-300">⚡ {primaryGpuName}</span>
                        <span className="text-slate-600">•</span>
                        <span className={`font-mono font-semibold ${skin.accentText}`}>{shortProvider}</span>
                        <span className="text-slate-600">•</span>
                        <span className="font-mono text-slate-300">🧬 {cachedEmbeddingsCount.toLocaleString()} DINOv2</span>
                      </button>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <button type="button" onClick={() => setActivePage('scan_ingestion')} className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${skin.accentBtn}`}>
                        📥 Process Scans
                      </button>
                      <button type="button" onClick={() => setActivePage('inventory')} className="px-3 py-1.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-slate-100 text-xs font-semibold transition">
                        🗂️ Inventory
                      </button>
                      <button type="button" onClick={() => setActivePage('label_hub')} className="px-3 py-1.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-slate-100 text-xs font-semibold transition">
                        🏷️ Label Hub
                      </button>
                      <button type="button" onClick={() => setActivePage('checklist_builder')} className="px-3 py-1.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-slate-100 text-xs font-semibold transition">
                        🏛️ Checklist Builder
                      </button>
                      <button type="button" onClick={() => setActivePage('listing_writer')} className="px-3 py-1.5 rounded-xl bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-slate-100 text-xs font-semibold transition">
                        ✍️ Listing Writer
                      </button>
                      <button type="button" onClick={() => openMonitorPage()} className={`px-3 py-1.5 rounded-xl border text-xs font-semibold transition ${anyLaneRunning ? 'bg-emerald-950/80 hover:bg-emerald-900 border-emerald-500/70 text-emerald-200' : 'bg-slate-900/90 hover:bg-slate-800 border-slate-700/80 text-slate-100'}`}>
                        🖥️ Live Monitor{anyLaneRunning ? ` (${runningDashLanes.length})` : ''}
                      </button>
                    </div>
                  </div>

                  {/* 2. TOP VISUAL KPI CARDS (6 INTERACTIVE METRIC CARDS) */}
                  <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
                    <button
                      type="button"
                      onClick={() => setActivePage('inventory')}
                      className={`${skin.cardBg} border ${skin.border} hover:brightness-110 rounded-2xl p-3.5 text-left transition-all flex flex-col justify-between gap-1.5 group`}
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold">
                        <span>🗂️ Collection Size</span>
                        <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">↗</span>
                      </div>
                      <div className="text-xl font-extrabold text-white font-mono leading-tight">
                        {financialSummary.inStockCount.toLocaleString()}
                      </div>
                      <div className="text-[10.5px] text-slate-400 leading-snug">
                        {cardLevelRows.length.toLocaleString()} unique • {pcCount.toLocaleString()} PC / {forSaleCount.toLocaleString()} Sale
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActivePage('collection_value')}
                      className={`${skin.cardBg} border ${skin.border} hover:brightness-110 rounded-2xl p-3.5 text-left transition-all flex flex-col justify-between gap-1.5 group`}
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold">
                        <span>💎 Optimal EV</span>
                        <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">↗</span>
                      </div>
                      <div className="text-xl font-extrabold text-emerald-400 font-mono leading-tight">
                        {fmtCurrency(financialSummary.totalOptimalEv)}
                      </div>
                      <div className="text-[10.5px] text-slate-400 leading-snug">
                        Raw {fmtCurrency(financialSummary.totalRawVal)} • Avg {fmtCurrency(avgCardVal)}
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActivePage('accounting')}
                      className={`${skin.cardBg} border ${skin.border} hover:brightness-110 rounded-2xl p-3.5 text-left transition-all flex flex-col justify-between gap-1.5 group`}
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold">
                        <span>💵 Sales &amp; Profit</span>
                        <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">↗</span>
                      </div>
                      <div className={`text-xl font-extrabold font-mono leading-tight ${financialSummary.netProfit >= 0 ? 'text-cyan-300' : 'text-rose-400'}`}>
                        {fmtCurrency(financialSummary.netProfit)}
                      </div>
                      <div className="text-[10.5px] text-slate-400 leading-snug">
                        Rev {fmtCurrency(financialSummary.totalRevenue)} ({soldCards.length}) • Exp {fmtCurrency(financialSummary.totalExpenses)}
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActivePage('grading_engine')}
                      className={`${skin.cardBg} border ${skin.border} hover:brightness-110 rounded-2xl p-3.5 text-left transition-all flex flex-col justify-between gap-1.5 group`}
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold">
                        <span>🏅 Grading EV</span>
                        <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">↗</span>
                      </div>
                      <div className="text-xl font-extrabold text-amber-300 font-mono leading-tight">
                        {dashGradingCount.toLocaleString()}
                      </div>
                      <div className="text-[10.5px] text-emerald-300 font-mono leading-snug">
                        +{fmtCurrency(dashGradingUpside)} net upside
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActivePage('label_hub')}
                      className={`${skin.cardBg} border ${skin.border} hover:brightness-110 rounded-2xl p-3.5 text-left transition-all flex flex-col justify-between gap-1.5 group`}
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold">
                        <span>🏷️ Label Queue</span>
                        <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">↗</span>
                      </div>
                      <div className={`text-xl font-extrabold font-mono leading-tight ${dashUnprintedCount > 0 ? 'text-sky-300' : 'text-emerald-400'}`}>
                        {dashUnprintedCount.toLocaleString()}
                      </div>
                      <div className="text-[10.5px] text-slate-400 leading-snug">
                        {dashUnprintedCount > 0 ? `~${estLabelSheets.toLocaleString()} sheet${estLabelSheets === 1 ? '' : 's'} (${dashCellsPerSheet}/pg)` : 'All labels printed ✓'}
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActivePage('checklist_builder')}
                      className={`${skin.cardBg} border ${skin.border} hover:brightness-110 rounded-2xl p-3.5 text-left transition-all flex flex-col justify-between gap-1.5 group`}
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold">
                        <span>🏛️ Set Library</span>
                        <span className="opacity-0 group-hover:opacity-100 transition text-[10px]">↗</span>
                      </div>
                      <div className="text-xl font-extrabold text-white font-mono leading-tight">
                        {trackedSets.length.toLocaleString()} <span className="text-xs font-semibold text-slate-400">sets</span>
                      </div>
                      <div className="text-[10.5px] text-slate-400 leading-snug">
                        {Number(chkData.totalRecords || 0).toLocaleString()} rows • {cachedEmbeddingsCount.toLocaleString()} AI emb
                      </div>
                    </button>
                  </div>

                  {/* 3 & 4. MAIN 12-COL RESPONSIVE GRID (TASK TO-DO HUB + ANALYTICS SPOTLIGHT) */}
                  <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
                    {/* LEFT / PRIMARY COLUMN (7 of 12 cols): SMART TASK TO-DO HUB + PERSONAL CHECKLIST */}
                    <div className="xl:col-span-7 space-y-4">
                      {/* SMART INTERACTIVE TASK TO-DO HUB */}
                      <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <h2 className="text-sm font-extrabold text-white">✅ Smart Action &amp; Workflow To-Do Hub</h2>
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${autoTasks.length > 0 ? 'bg-amber-950/80 text-amber-200 border-amber-500/60' : 'bg-emerald-950/80 text-emerald-200 border-emerald-500/60'}`}>
                              {autoTasks.length} {autoTasks.length === 1 ? 'Task' : 'Tasks'}
                            </span>
                          </div>
                          {dashboardSummary?.generatedAt && (
                            <span className="text-[10px] font-mono text-slate-500">Synced {dashboardSummary.generatedAt.slice(11)}</span>
                          )}
                        </div>

                        {autoTasks.length === 0 ? (
                          <div className="rounded-xl bg-emerald-950/35 border border-emerald-500/40 p-6 text-center space-y-1.5">
                            <div className="text-2xl">✅</div>
                            <div className="text-sm font-bold text-emerald-200">All caught up! No pending workflow tasks.</div>
                            <div className="text-xs text-slate-400">Scans, uncommitted batches, labels, checklists, and listing drafts are all up to date.</div>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {autoTasks.map((task) => {
                              const pMeta = priorityBadgeStyle[task.priority] || priorityBadgeStyle.action;
                              return (
                                <div
                                  key={task.id}
                                  className="rounded-xl bg-slate-950/75 border border-slate-800 hover:border-slate-700 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition"
                                >
                                  <div className="min-w-0 space-y-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className={`px-2 py-0.5 rounded-md text-[9.5px] font-extrabold border shrink-0 ${pMeta.cls}`}>
                                        {pMeta.label}
                                      </span>
                                      <span className="text-xs font-bold text-white break-words">
                                        {task.icon} {task.title}
                                      </span>
                                    </div>
                                    {task.detail && (
                                      <div className="text-[11px] text-slate-400 leading-snug break-words">
                                        {task.detail}
                                        {task.expandableCount > 0 && (
                                          <button
                                            type="button"
                                            onClick={() => setShowAllNeverScraped((prev) => !prev)}
                                            className={`ml-1.5 font-semibold hover:underline ${skin.accentText}`}
                                          >
                                            {showAllNeverScraped ? 'Show less' : `Show all ${task.expandableCount}`}
                                          </button>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-1.5 shrink-0">
                                    {task.secondaryLabel && (
                                      <button
                                        type="button"
                                        onClick={task.onSecondary}
                                        className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[11px] font-semibold transition"
                                      >
                                        {task.secondaryLabel}
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      onClick={task.onPrimary}
                                      className={`px-3 py-1.5 rounded-lg text-[11px] font-bold transition ${task.priority === 'urgent' ? skin.accentBtn : `${skin.accentActive} border hover:brightness-110`}`}
                                    >
                                      {task.primaryLabel} →
                                    </button>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      {/* PERSONAL HOBBY TO-DO CHECKLIST (LOCALSTORAGE) */}
                      <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
                            📝 Personal Hobby To-Do Checklist
                          </h3>
                          {completedCustomCount > 0 && (
                            <button
                              type="button"
                              onClick={clearCompletedCustomTodos}
                              className="text-[11px] font-semibold text-amber-300 hover:text-amber-200 transition"
                            >
                              🧹 Clear Completed ({completedCustomCount})
                            </button>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={customTodoInput}
                            onChange={(e) => setCustomTodoInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomTodo(); } }}
                            placeholder="Add a quick reminder (e.g., Sleeve Bowman Chrome autos, ship eBay order...)"
                            className="flex-1 min-w-0 bg-slate-950/90 border border-slate-700 focus:border-cyan-400 rounded-xl px-3 py-1.5 text-xs text-white placeholder-slate-500 outline-none"
                          />
                          <button
                            type="button"
                            onClick={addCustomTodo}
                            disabled={!String(customTodoInput || '').trim()}
                            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold disabled:opacity-40 transition shrink-0 ${skin.accentBtn}`}
                          >
                            + Add
                          </button>
                        </div>
                        {customTodos.length === 0 ? (
                          <div className="text-[11px] text-slate-500 py-1.5">
                            No personal reminders yet — saved automatically in your browser.
                          </div>
                        ) : (
                          <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                            {customTodos.map((item) => (
                              <div
                                key={item.id}
                                className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-xl bg-slate-950/75 border border-slate-800 text-xs"
                              >
                                <label className="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(item.done)}
                                    onChange={() => toggleCustomTodo(item.id)}
                                    className="rounded border-slate-600 accent-emerald-500 shrink-0"
                                  />
                                  <span className={`truncate ${item.done ? 'line-through text-slate-500' : 'text-slate-200'}`}>
                                    {item.text}
                                  </span>
                                </label>
                                <div className="flex items-center gap-2 shrink-0">
                                  {item.createdAt && <span className="text-[10px] font-mono text-slate-500 hidden sm:inline">{item.createdAt}</span>}
                                  <button
                                    type="button"
                                    onClick={() => deleteCustomTodo(item.id)}
                                    title="Delete reminder"
                                    className="text-slate-500 hover:text-rose-400 text-xs px-1"
                                  >
                                    ✕
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* RIGHT COLUMN (5 of 12 cols): VISUAL ANALYTICS & SPOTLIGHT */}
                    <div className="xl:col-span-5 space-y-4">
                      {/* COLLECTION BREAKDOWN DONUT CARD */}
                      <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
                            🍩 Collection Breakdown
                          </h3>
                          <div className="flex items-center gap-2">
                            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-[10.5px]">
                              <button
                                type="button"
                                onClick={() => setDashboardDonutMode('set')}
                                className={`px-2 py-0.5 rounded-md font-bold transition ${dashboardDonutMode === 'set' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                              >
                                By Set
                              </button>
                              <button
                                type="button"
                                onClick={() => setDashboardDonutMode('sport')}
                                className={`px-2 py-0.5 rounded-md font-bold transition ${dashboardDonutMode === 'sport' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                              >
                                By Sport
                              </button>
                            </div>
                            <button
                              type="button"
                              onClick={() => setActivePage('collection_value')}
                              className={`text-[11px] font-semibold hover:underline ${skin.accentText}`}
                            >
                              Full Breakdown →
                            </button>
                          </div>
                        </div>
                        <SvgDonutChart
                          data={activeDonutData}
                          centerLabel={inStockCards.length.toLocaleString()}
                          centerSub={dashboardDonutMode === 'sport' ? 'Sports' : 'Cards'}
                        />
                      </div>

                      {/* COLLECTION VALUE TREND MINI-CHART */}
                      <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
                              📈 Portfolio Value Trend
                            </h3>
                            {histDeltaEv !== null && (
                              <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-mono font-bold border ${histDeltaEv >= 0 ? 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60' : 'bg-rose-950/80 text-rose-300 border-rose-600/60'}`}>
                                {histDeltaEv >= 0 ? '+' : ''}{fmtCurrency(histDeltaEv)}
                              </span>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => setActivePage('collection_value')}
                            className={`text-[11px] font-semibold hover:underline ${skin.accentText}`}
                          >
                            View Trends →
                          </button>
                        </div>

                        {histPts.length === 0 ? (
                          <div className="text-xs text-slate-400 py-6 text-center bg-slate-950/60 rounded-xl border border-slate-800/80">
                            No valuation snapshots yet — run a Market Refresh to start plotting portfolio trends.
                          </div>
                        ) : (() => {
                          const rawMax = Math.max(10, ...histPts.map((h) => Math.max(safeNum(h.Total_Raw_Value), safeNum(h.Total_Optimal_EV))));
                          const maxV = Math.ceil(rawMax * 1.12);
                          const W = 420, H = 112, padL = 8, padR = 8, padT = 10, padB = 18;
                          const plotW = W - padL - padR;
                          const plotH = H - padT - padB;
                          const toX = (i) => (histPts.length === 1 ? padL + plotW * 0.5 : padL + (i / (histPts.length - 1)) * plotW);
                          const toY = (v) => padT + plotH - (Math.max(0, v) / maxV) * plotH;
                          const evLine = histPts.map((h, i) => `${toX(i)},${toY(safeNum(h.Total_Optimal_EV))}`).join(' ');
                          const rawLine = histPts.map((h, i) => `${toX(i)},${toY(safeNum(h.Total_Raw_Value))}`).join(' ');
                          const areaPoly = histPts.length >= 2 ? `${toX(0)},${padT + plotH} ${evLine} ${toX(histPts.length - 1)},${padT + plotH}` : '';

                          return (
                            <div className="space-y-1.5">
                              <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-28 bg-slate-950/90 rounded-xl border border-slate-800">
                                <defs>
                                  <linearGradient id="dashEvGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.32" />
                                    <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
                                  </linearGradient>
                                </defs>
                                {areaPoly && <polygon fill="url(#dashEvGrad)" points={areaPoly} />}
                                {histPts.length >= 2 && <polyline fill="none" stroke="#38bdf8" strokeWidth="1.8" strokeDasharray="3 2" points={rawLine} />}
                                {histPts.length >= 2 && <polyline fill="none" stroke="#10b981" strokeWidth="2.4" points={evLine} />}
                                {histPts.map((h, i) => (
                                  <circle key={i} cx={toX(i)} cy={toY(safeNum(h.Total_Optimal_EV))} r="2.8" fill="#10b981">
                                    <title>{`${h.Date} — Optimal EV: ${fmtCurrency(h.Total_Optimal_EV)} | Raw: ${fmtCurrency(h.Total_Raw_Value)}`}</title>
                                  </circle>
                                ))}
                                <text x={padL + 2} y={H - 4} fill="#64748b" fontSize="9.5" fontFamily="monospace">
                                  {String(histPts[0]?.Date || '').slice(0, 10)}
                                </text>
                                <text x={W - padR - 2} y={H - 4} textAnchor="end" fill="#64748b" fontSize="9.5" fontFamily="monospace">
                                  {String(histPts[histPts.length - 1]?.Date || '').slice(0, 10)}
                                </text>
                              </svg>
                              <div className="flex items-center justify-between text-[10.5px] text-slate-400">
                                <span className="flex items-center gap-3">
                                  <span className="flex items-center gap-1 text-emerald-300"><span className="w-2 h-2 rounded-full bg-emerald-400" />Optimal EV</span>
                                  <span className="flex items-center gap-1 text-sky-300"><span className="w-2 h-2 rounded-full bg-sky-400" />Raw Value</span>
                                </span>
                                <span className="font-mono">{histPts.length} snapshot{histPts.length === 1 ? '' : 's'}</span>
                              </div>
                            </div>
                          );
                        })()}
                      </div>

                      {/* TOP 5 MOST VALUABLE CARDS SPOTLIGHT */}
                      <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
                            🏆 Top 5 Most Valuable Cards
                          </h3>
                          <button
                            type="button"
                            onClick={() => setActivePage('collection_value')}
                            className={`text-[11px] font-semibold hover:underline ${skin.accentText}`}
                          >
                            Top 10 →
                          </button>
                        </div>
                        {top5ValuableCards.length === 0 ? (
                          <div className="text-xs text-slate-500 py-4 text-center">No in-stock cards in Inventory yet.</div>
                        ) : (
                          <div className="space-y-1.5">
                            {top5ValuableCards.map((c, idx) => {
                              const optV = cardOptVal(c);
                              const estPsa = safeNum(c.Est_PSA, 0);
                              const estBgs = safeNum(c.Est_BGS, 0);
                              return (
                                <button
                                  key={c.SKU || idx}
                                  type="button"
                                  onClick={() => c.SKU && openInventoryEditorForSkus([c.SKU], 'individual')}
                                  title={`Open ${c.SKU} in Inventory Editor`}
                                  className="w-full rounded-xl bg-slate-950/75 hover:bg-slate-900 border border-slate-800 hover:border-slate-600 px-3 py-2 flex items-center justify-between gap-2 text-left transition"
                                >
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5 text-xs font-bold text-white truncate">
                                      <span className={`font-mono text-[10.5px] ${skin.accentText}`}>#{idx + 1}</span>
                                      <span className="truncate">{c.Player || 'Unknown Player'}</span>
                                      {c['Card Number'] && <span className="text-[10.5px] font-mono text-slate-400 shrink-0">#{String(c['Card Number']).replace(/^#/, '')}</span>}
                                    </div>
                                    <div className="text-[10.5px] text-slate-400 truncate">
                                      {c.Set || 'Unknown Set'} • {c.Subset || 'Base'}
                                    </div>
                                  </div>
                                  <div className="flex flex-col items-end shrink-0">
                                    <span className="text-xs font-extrabold font-mono text-emerald-400">{fmtCurrency(optV)}</span>
                                    {(estPsa > 0 || estBgs > 0) && (
                                      <span className="text-[9.5px] font-mono text-amber-300">
                                        {estPsa > 0 ? `PSA ${estPsa}` : ''}{estPsa > 0 && estBgs > 0 ? ' / ' : ''}{estBgs > 0 ? `BGS ${estBgs}` : ''}
                                      </span>
                                    )}
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* FULL-WIDTH BOTTOM ROW: ACTIVE WORKERS & RECENT ACTIVITY FEED */}
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <h3 className="text-xs font-extrabold uppercase tracking-wider text-white">
                          {runningDashLanes.length > 0 ? `⚡ Active Parallel Workers (${runningDashLanes.length})` : '🕒 Recent Activity Feed'}
                        </h3>
                        {runningDashLanes.length > 0 && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-600 animate-pulse">
                            LIVE
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-[11px] font-semibold">
                        <button type="button" onClick={() => openMonitorPage()} className={`hover:underline ${skin.accentText}`}>
                          🖥️ Open Monitor
                        </button>
                        <button type="button" onClick={() => openHiddenPage('notification_history')} className="text-sky-400 hover:underline">
                          🔔 Full Notification History →
                        </button>
                      </div>
                    </div>

                    {runningDashLanes.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                        {runningDashLanes.map(([lk, meta]) => {
                          const st = liveLanes[lk] || {};
                          const pct = Math.max(0, Math.min(100, Number(st.percent || 0)));
                          return (
                            <button
                              key={lk}
                              type="button"
                              onClick={() => openMonitorPage(lk)}
                              className="rounded-xl bg-slate-950/85 hover:bg-slate-900 border border-emerald-600/50 p-3 text-left space-y-2 transition"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-bold text-white truncate">
                                  {st.job_icon || meta.icon} {st.process_name || st.title || meta.shortName}
                                </span>
                                <span className="font-mono text-xs font-extrabold text-emerald-300 shrink-0">{pct}%</span>
                              </div>
                              <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                                <div className="h-full bg-gradient-to-r from-cyan-400 to-emerald-400 transition-all" style={{ width: `${pct}%` }} />
                              </div>
                              <div className="flex items-center justify-between gap-2 text-[10.5px] font-mono text-slate-400">
                                <span className="truncate">{st.current_item || st.status || 'Running...'}</span>
                                <span className="shrink-0 text-cyan-300">
                                  ⏱️ {fmtEta(getLaneElapsedSec(st))} • ETA {fmtEta(st.eta_seconds)}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    ) : notifications.length === 0 ? (
                      <div className="text-xs text-slate-500 py-3 text-center">
                        All 8 parallel worker slots are idle and no recent notifications are queued.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-5 gap-2.5">
                        {notifications.slice(0, 5).map((n) => (
                          <div
                            key={n.Notification_ID}
                            className="rounded-xl bg-slate-950/75 border border-slate-800 p-2.5 space-y-1 min-w-0"
                          >
                            <div className="flex items-center justify-between gap-1.5 text-[10px]">
                              <span className={`px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 font-bold truncate ${skin.accentText}`}>
                                {n.Category || 'System'}
                              </span>
                              <span className="font-mono text-slate-500 shrink-0">{String(n.Timestamp || '').slice(11, 19)}</span>
                            </div>
                            <div className="text-xs font-bold text-white truncate" title={n.Title}>{n.Title}</div>
                            <div className="text-[11px] text-slate-400 line-clamp-2" title={n.Message}>{n.Message}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* INTEGRATED MONITOR WORKSPACE PAGE (LEFT RAIL & TOP BAR REMAIN VISIBLE) */}
            {activePage === 'live_monitor' && (
              <div className={`flex-1 flex flex-col min-h-0 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                {renderMonitorBody(true)}
              </div>
            )}

            {/* 1. BATCH SCAN PROCESSOR & MULTI-BATCH / ALL-BATCHES UNCOMMITTED REVIEW */}
            {activePage === 'scan_ingestion' && (() => {
              const isAllBatchesView = activeBatchName === '__ALL__' && batches.length > 0;
              const allBatchesTotalCards = batches.reduce((acc, b) => acc + Number(b.cardCount || 0), 0);
              const allBatchesTotalFlagged = batches.reduce((acc, b) => acc + Number(b.needsReviewCount || 0), 0);
              const activeViewCards = isAllBatchesView
                ? batches.flatMap((b) => (b.cards || []).map((c) => ({ ...c, _BatchName: c._BatchName || b.batchName })))
                : (batchCards || []).map((c) => ({ ...c, _BatchName: c._BatchName || currentBatchObj?.batchName || '' }));

              const mergedBatchCards = activeViewCards.map((c) => (batchDraftEdits[c.SKU] ? { ...c, ...batchDraftEdits[c.SKU] } : c));
              const dirtyEditCount = Object.keys(batchDraftEdits).filter((k) => activeViewCards.some((c) => c.SKU === k)).length;
              const batchSubsetsList = Array.from(new Set(mergedBatchCards.map((c) => c.Subset_Parallel || 'Base').filter(Boolean))).sort();

              const t1Count = mergedBatchCards.filter((c) => parseCardIdTier(c).code === 'T1_LOCK').length;
              const t2Count = mergedBatchCards.filter((c) => parseCardIdTier(c).code === 'T2_VISUAL').length;
              const flaggedBatchSkus = mergedBatchCards.filter((c) => String(c.Needs_Review).toLowerCase() === 'true').map((c) => c.SKU);
              const below190Skus = mergedBatchCards.filter((c) => safeNum(c.OCR_Confidence, 0) < 185).map((c) => c.SKU);
              const nonBaseBatchSkus = mergedBatchCards.filter((c) => {
                const su = String(c.Subset_Parallel || 'Base').trim().toUpperCase();
                return su !== '' && su !== 'BASE' && su !== 'BASE SET';
              }).map((c) => c.SKU);
              const guidedScopeCount = batchSelectedSkus.length > 0 ? batchSelectedSkus.length : (flaggedBatchSkus.length > 0 ? flaggedBatchSkus.length : mergedBatchCards.length);

              const validSelectedCommitBatches = selectedCommitBatches.filter((bn) => batches.some((b) => b.batchName === bn));
              const commitTargetBatchNames = validSelectedCommitBatches.length > 0
                ? validSelectedCommitBatches
                : isAllBatchesView
                ? batches.map((b) => b.batchName)
                : (currentBatchObj ? [currentBatchObj.batchName] : []);
              const commitTargetCardsCount = batches
                .filter((b) => commitTargetBatchNames.includes(b.batchName))
                .reduce((acc, b) => acc + Number(b.cardCount || 0), 0);

              const filteredBatchCards = mergedBatchCards.filter((c) => {
                const tier = parseCardIdTier(c);
                const isFlagged = String(c.Needs_Review).toLowerCase() === 'true';
                const subUp = String(c.Subset_Parallel || 'Base').trim().toUpperCase();
                const isBaseRow = subUp === '' || subUp === 'BASE' || subUp === 'BASE SET';
                if (batchReviewFilter === 'flagged' && !isFlagged) return false;
                if (batchReviewFilter === 'verified' && isFlagged) return false;
                if (batchConfFilter === 't1_lock' && tier.ocr < 185) return false;
                if (batchConfFilter === 'below_190' && tier.ocr >= 185) return false;
                if (batchConfFilter === 'low_vis_75' && (tier.visPct === null || tier.visPct >= 75)) return false;
                if (batchConfFilter === 't2_visual' && tier.code !== 'T2_VISUAL') return false;
                if (batchConfFilter === 't3_plus' && !['T3_REREAD', 'T4_VISUAL', 'T5_AI', 'UNCONFIRMED'].includes(tier.code)) return false;
                if (batchConfFilter === 'low_120' && tier.ocr >= 120) return false;
                if (batchConfFilter === 'par_corrected' && !tier.parCorrected) return false;
                if (batchSubsetFilter === '__NON_BASE__' && isBaseRow) return false;
                if (batchSubsetFilter !== 'All Subsets' && batchSubsetFilter !== '__NON_BASE__' && (c.Subset_Parallel || 'Base') !== batchSubsetFilter) return false;
                if (batchSearchQ.trim()) {
                  const q = batchSearchQ.toLowerCase();
                  if (!`${c.SKU} ${c._BatchName || ''} ${c.Set} ${c.Subset_Parallel} ${c.Card_Number} ${c.Player} ${c.Team} ${c.OCR_Signals} ${c.Grading_Notes}`.toLowerCase().includes(q)) return false;
                }
                return true;
              });

              const totalBatchPages = Math.max(1, Math.ceil(filteredBatchCards.length / batchPageSize));
              const safeBatchPage = Math.min(batchPage, totalBatchPages);
              const pageSliceBatch = filteredBatchCards.slice((safeBatchPage - 1) * batchPageSize, safeBatchPage * batchPageSize);

              const updateBatchRowInline = (sku, field, value) => {
                const orig = activeViewCards.find((x) => x.SKU === sku) || {};
                setBatchDraftEdits((prev) => ({
                  ...prev,
                  [sku]: { ...orig, ...(prev[sku] || {}), [field]: value },
                }));
              };

              const flushDirtyEditsAcrossBatches = () => {
                const groupedByBatch = {};
                Object.keys(batchDraftEdits).forEach((sku) => {
                  const orig = activeViewCards.find((c) => c.SKU === sku);
                  if (!orig) return;
                  const bn = orig._BatchName || currentBatchObj?.batchName || '';
                  if (!bn) return;
                  if (!groupedByBatch[bn]) groupedByBatch[bn] = [];
                  groupedByBatch[bn].push(batchDraftEdits[sku]);
                });
                const entries = Object.entries(groupedByBatch);
                if (entries.length === 0) return Promise.resolve({ ok: true, count: 0, renamed: 0 });
                return Promise.all(
                  entries.map(([bn, cardsArr]) =>
                    fetch(`${NODE_API_BASE}/batches/update`, {
                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ batchName: bn, cards: cardsArr }),
                    }).then((r) => r.json())
                  )
                ).then((results) => {
                  const failed = results.find((res) => !res?.success);
                  if (failed) return { ok: false, error: failed.error || 'Could not save edits.' };
                  const renTot = results.reduce((a, r) => a + Number(r.renamedCount || 0), 0);
                  const updTot = entries.reduce((a, [, arr]) => a + arr.length, 0);
                  return { ok: true, count: updTot, renamed: renTot };
                });
              };

              const executeCommitBatches = (namesList) => {
                if (!namesList || namesList.length === 0 || committingBatches || isCommitRunning) return;
                setCommittingBatches(true);
                const runCommit = () =>
                  fetch(`${NODE_API_BASE}/batches/commit`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ batchNames: namesList, moveImages: batchMoveAndArchive }),
                  })
                    .then((r) => r.json())
                    .then((res) => {
                      if (res?.success) {
                        setBatchDraftEdits({});
                        setBatchSelectedSkus([]);
                        setSelectedCommitBatches([]);
                        if (res.asyncJob) {
                          const assignedSlot = res.lane || 'slot_1';
                          if (res.lanes?.lanes) {
                            setLiveLanes(res.lanes.lanes);
                            setLiveLogs(res.lanes.logs || {});
                          }
                          setSelectedMonitorLane(assignedSlot);
                          const slotLbl = PROCESS_LANES[assignedSlot]?.shortName || assignedSlot;
                          pushNotification(
                            `🎉 Committing ${namesList.length} Batch${namesList.length === 1 ? '' : 'es'} to Inventory`,
                            `Running in parallel on ${slotLbl} (${Number(res.estimatedCards || 0).toLocaleString()} cards). Track live progress in the Monitor!`,
                            'Batch',
                            'info'
                          );
                        } else {
                          if (Array.isArray(res.inventoryRows)) setInventory(res.inventoryRows);
                          if (Array.isArray(res.batches)) setBatches(res.batches);
                          refreshAllHubData('');
                          const batchWord = Number(res.committed_batches || namesList.length) === 1 ? 'batch' : 'batches';
                          pushNotification(
                            '✅ Committed to Inventory',
                            `Committed ${Number(res.committed_cards || 0).toLocaleString()} card(s) from ${res.committed_batches || namesList.length} ${batchWord} (kept separate by Source_Batch).`,
                            'Batch',
                            'success'
                          );
                        }
                      } else {
                        pushNotification('Commit Failed', res?.error || 'Could not commit batch(es) to Inventory.', 'Batch', 'error');
                      }
                    })
                    .catch((err) => pushNotification('Commit Error', err.message || 'Network error while committing.', 'Batch', 'error'))
                    .finally(() => setCommittingBatches(false));

                if (dirtyEditCount > 0) {
                  flushDirtyEditsAcrossBatches()
                    .then((saveRes) => {
                      if (!saveRes.ok) {
                        setCommittingBatches(false);
                        pushNotification('Save Before Commit Failed', saveRes.error, 'Batch', 'error');
                        return;
                      }
                      runCommit();
                    })
                    .catch((err) => {
                      setCommittingBatches(false);
                      pushNotification('Save Error', err.message, 'Batch', 'error');
                    });
                } else {
                  runCommit();
                }
              };

              const executeDeleteBatchCards = (itemsArr) => {
                if (!itemsArr || itemsArr.length === 0) return;
                fetch(`${NODE_API_BASE}/batches/delete-cards`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ items: itemsArr, deleteFiles: true, activeBatchName: activeBatchName || currentBatchObj?.batchName || '' }),
                })
                  .then((r) => r.json())
                  .then((res) => {
                    if (res?.success) {
                      const rmSet = new Set(res.removedSkus || itemsArr.map((x) => x.sku));
                      setBatchSelectedSkus((prev) => prev.filter((s) => !rmSet.has(s)));
                      setBatchDraftEdits((prev) => {
                        const cp = { ...prev };
                        rmSet.forEach((s) => delete cp[s]);
                        return cp;
                      });
                      setConfirmDeleteBatchSkus(false);
                      setConfirmDeleteRowSku('');
                      if (Array.isArray(res.batches)) setBatches(res.batches);
                      loadBatchesFromDisk(activeBatchName || currentBatchObj?.batchName || '');
                      pushNotification('Card(s) Removed from Batch', `Deleted ${res.removedCount || rmSet.size} card(s) and scan image(s).`, 'Batch', 'warning');
                    } else {
                      pushNotification('Remove Failed', res?.error || 'Could not remove card(s) from batch.', 'Batch', 'error');
                    }
                  })
                  .catch((err) => pushNotification('Remove Error', err.message, 'Batch', 'error'));
              };

              return (
                <div className="flex-1 flex flex-col gap-3 min-h-0">
                  {/* STEP 1A: INCOMING BATCH SCAN PROCESSOR */}
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5 shrink-0`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h2 className="text-sm font-bold text-white">📥 Batch Scan Processor ({incomingScans.length} Incoming Folder(s))</h2>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-300">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input type="checkbox" checked={ingestParallelHeavy} onChange={(e) => setIngestParallelHeavy(e.target.checked)} />
                          Parallel-Heavy Stack
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input type="checkbox" checked={ingestAutoSplitFlatbed} onChange={(e) => setIngestAutoSplitFlatbed(e.target.checked)} />
                          Auto-Split Flatbed PDFs
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input type="checkbox" checked={ingestCardSightFb} onChange={(e) => setIngestCardSightFb(e.target.checked)} />
                          Tier-5 CardSightAI Fallback
                        </label>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">1. Incoming Batch</label>
                        <select value={selectedIncomingBatch} onChange={(e) => setSelectedIncomingBatch(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                          <option value="ALL">ALL DISCOVERED ({incomingScans.length})</option>
                          {incomingScans.map((b) => <option key={b.batchName} value={b.batchName}>{b.batchName} ({b.pdfCount} PDFs)</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">2. Pre-Select Set</label>
                        <select value={preselectSet} onChange={(e) => setPreselectSet(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                          <option>🌐 Mixed / Auto-Detect Set</option>
                          {dynamicSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">3. Pre-Select Subset</label>
                        <select value={preselectSubset} onChange={(e) => setPreselectSubset(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                          <option>🌐 Auto-Detect Subset / Parallel</option>
                          {preselectSubsets.slice(0, 250).map((sub) => <option key={sub}>{sub}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-slate-400 mb-1">4. Default Raw Price ($)</label>
                        <div className="relative">
                          <span className="absolute left-2.5 top-1.5 text-xs text-emerald-400 font-bold">$</span>
                          <input type="number" step="0.25" min="0.25" value={defaultRawPrice} onChange={(e) => setDefaultRawPrice(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded-xl pl-6 pr-2 py-1.5 text-xs font-mono" />
                        </div>
                      </div>
                      <div className="flex items-end gap-1.5">
                        <button
                          onClick={() => triggerJob('ingest_inventory', `Batch Scan Processing (${selectedIncomingBatch})`, 'scan_ingest', {
                            batch_names: selectedIncomingBatch === 'ALL' ? [] : [selectedIncomingBatch],
                            locked_set: preselectSet.includes('Mixed') ? '' : preselectSet,
                            locked_subset: preselectSubset.includes('Auto-Detect') ? '' : preselectSubset,
                            parallel_heavy_mode: ingestParallelHeavy,
                            auto_split_flatbed: ingestAutoSplitFlatbed,
                            enable_cardsight_fallback: ingestCardSightFb,
                            default_raw_price: safeNum(defaultRawPrice, 1.0),
                          })}
                          className={`flex-1 py-2 px-2.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}
                        >
                          🚀 Process
                        </button>
                        <button
                          onClick={() => fetch(`${NODE_API_BASE}/batches/split-flatbed`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batchName: selectedIncomingBatch }) }).then((r) => r.json()).then((res) => { if (res.success) { refreshAllHubData(); pushNotification('Flatbed Split Complete', `Created ${res.createdCount || 0} individual Front/Back card PDF(s).`, 'Scan', 'success'); } })}
                          title="Split multi-card flatbed PDFs into individual 2-page card PDFs"
                          className="py-2 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold shrink-0"
                        >
                          ✂️ Split
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* STEP 1B: UNCOMMITTED BATCHES WITH "ALL" TAB + MULTI-BATCH COMMIT SELECTION */}
                  <div className={`flex-1 min-h-0 flex flex-col ${skin.cardBg} border ${skin.border} rounded-2xl p-4 gap-2.5`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-white">🔎 Uncommitted Batches ({batches.length})</h3>
                        {isIngestLaneRunning && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-950 border border-emerald-600 text-emerald-300 animate-pulse">
                            🟢 Streaming Live
                          </span>
                        )}
                        <button
                          onClick={() => loadBatchesFromDisk(activeBatchName)}
                          title="Reload uncommitted batches from disk"
                          className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] text-sky-300 font-semibold"
                        >
                          🔄 Refresh
                        </button>
                      </div>

                      {currentBatchObj && (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <button onClick={() => openHiddenPage('guided_batch_review')} className={`px-3 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}>
                            🪟 Guided Review ({guidedScopeCount})
                          </button>
                          <button
                            onClick={() => { setDeepDiveIdx(0); openHiddenPage('batch_deep_dive'); }}
                            className="px-3 py-1.5 rounded-xl bg-indigo-950/90 hover:bg-indigo-800 border border-indigo-600/70 text-indigo-200 font-bold text-xs"
                          >
                            🔬 Deep-Dive Studio
                          </button>
                          {dirtyEditCount > 0 && (
                            <button
                              onClick={() => {
                                flushDirtyEditsAcrossBatches()
                                  .then((res) => {
                                    if (res.ok) {
                                      setBatchDraftEdits({});
                                      loadBatchesFromDisk(activeBatchName || currentBatchObj.batchName);
                                      pushNotification('Batch Edits Saved', `Applied ${res.count} edit(s) and renamed ${res.renamed} card set(s).`, 'Batch', 'success');
                                    } else {
                                      pushNotification('Save Failed', res.error, 'Batch', 'error');
                                    }
                                  })
                                  .catch((err) => pushNotification('Save Error', err.message, 'Batch', 'error'));
                              }}
                              className="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs animate-pulse"
                            >
                              💾 Apply Edits &amp; Rename ({dirtyEditCount})
                            </button>
                          )}
                          {batchSelectedSkus.length > 0 && (
                            confirmDeleteBatchSkus ? (
                              <span className="inline-flex items-center gap-1">
                                <button
                                  onClick={() => {
                                    const itemsToDel = batchSelectedSkus.map((sk) => {
                                      const cObj = activeViewCards.find((x) => x.SKU === sk);
                                      return { batchName: cObj?._BatchName || currentBatchObj.batchName, sku: sk };
                                    });
                                    executeDeleteBatchCards(itemsToDel);
                                  }}
                                  className="px-2.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold"
                                >
                                  ⚠️ Confirm Delete ({batchSelectedSkus.length})
                                </button>
                                <button onClick={() => setConfirmDeleteBatchSkus(false)} className="px-2 py-1.5 rounded-xl bg-slate-800 text-xs text-slate-300">Cancel</button>
                              </span>
                            ) : (
                              <button
                                onClick={() => setConfirmDeleteBatchSkus(true)}
                                title="Delete selected card(s) and their scan images from the uncommitted batch"
                                className="px-2.5 py-1.5 rounded-xl bg-rose-950/90 hover:bg-rose-800 text-rose-200 border border-rose-700 text-xs font-bold"
                              >
                                🗑️ Remove ({batchSelectedSkus.length})
                              </button>
                            )
                          )}
                          <button
                            onClick={() => {
                              if (isAllBatchesView) {
                                const byBatch = {};
                                const targetList = batchSelectedSkus.length > 0 ? batchSelectedSkus : below190Skus;
                                targetList.forEach((sk) => {
                                  const cObj = activeViewCards.find((x) => x.SKU === sk);
                                  const bn = cObj?._BatchName || '';
                                  if (bn) { if (!byBatch[bn]) byBatch[bn] = []; byBatch[bn].push(sk); }
                                });
                                Object.entries(byBatch).forEach(([bn, skList]) => {
                                  const bObj = batches.find((b) => b.batchName === bn);
                                  if (!bObj) return;
                                  triggerJob('ingest_inventory', `Re-Identify Batch (${bn})`, 'reidentify_batch', {
                                    batch_dir: bObj.folderPath,
                                    target_mode: batchSelectedSkus.length > 0 ? 'selected_skus' : 'flagged_and_suspect',
                                    selected_skus: skList,
                                    estimated_total: Math.max(1, skList.length),
                                  });
                                });
                              } else {
                                triggerJob('ingest_inventory', `Re-Identify Batch (${currentBatchObj.batchName})`, 'reidentify_batch', {
                                  batch_dir: currentBatchObj.folderPath,
                                  target_mode: batchSelectedSkus.length > 0 ? 'selected_skus' : 'flagged_and_suspect',
                                  selected_skus: batchSelectedSkus,
                                  estimated_total: Math.max(1, batchSelectedSkus.length || below190Skus.length || currentBatchObj.needsReviewCount || 1),
                                });
                              }
                            }}
                            className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-300 font-semibold text-xs"
                          >
                            🧠 Re-Identify {batchSelectedSkus.length > 0 ? `(${batchSelectedSkus.length})` : `Suspect (${below190Skus.length})`}
                          </button>
                          <button
                            onClick={() => {
                              const targets = isAllBatchesView ? batches : [currentBatchObj];
                              targets.forEach((bObj) => {
                                triggerJob('ingest_inventory', `Re-Grade Batch (${bObj.batchName})`, 'regrade_batch', {
                                  batch_dir: bObj.folderPath,
                                  regenerate_corner_sheets: true,
                                  estimated_total: Math.max(1, Number(bObj.cardCount || 1)),
                                });
                              });
                            }}
                            className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-300 font-semibold text-xs"
                          >
                            🔄 Re-Grade {isAllBatchesView ? 'All' : 'Batch'}
                          </button>
                          <button
                            disabled={committingBatches || isCommitRunning || commitTargetBatchNames.length === 0}
                            onClick={() => executeCommitBatches(commitTargetBatchNames)}
                            title={`Commit ${commitTargetBatchNames.join(', ')} to Inventory.csv (each batch keeps its own Source_Batch)`}
                            className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs shadow"
                          >
                            {committingBatches || isCommitRunning
                              ? '⏳ Committing in Worker...'
                              : validSelectedCommitBatches.length > 1
                              ? `🎉 Commit ${validSelectedCommitBatches.length} Selected Batches (${commitTargetCardsCount.toLocaleString()})`
                              : isAllBatchesView
                              ? `🎉 Commit All ${batches.length} Batches (${commitTargetCardsCount.toLocaleString()})`
                              : `🎉 Commit (${commitTargetCardsCount.toLocaleString()})`}
                          </button>
                          {!isAllBatchesView && batches.length > 1 && validSelectedCommitBatches.length === 0 && (
                            <button
                              disabled={committingBatches || isCommitRunning}
                              onClick={() => executeCommitBatches(batches.map((b) => b.batchName))}
                              title="Commit all uncommitted batches to Inventory.csv while keeping each batch separate via Source_Batch"
                              className="px-2.5 py-1.5 rounded-xl bg-emerald-950/90 hover:bg-emerald-700 border border-emerald-600/80 text-emerald-200 hover:text-white font-bold text-xs disabled:opacity-50"
                            >
                              🎉 Commit All ({batches.length})
                            </button>
                          )}
                          {!isAllBatchesView && (
                            confirmClearBatchName === currentBatchObj.batchName ? (
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => {
                                    setConfirmClearBatchName('');
                                    fetch(`${NODE_API_BASE}/batches/clear`, {
                                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                                      body: JSON.stringify({ batchName: currentBatchObj.batchName, clearAll: false }),
                                    }).then((r) => r.json()).then((res) => {
                                      if (res && res.success) {
                                        setBatchDraftEdits({});
                                        setBatchSelectedSkus([]);
                                        refreshAllHubData('');
                                        pushNotification('Batch Cleared', `Cleared '${currentBatchObj.batchName}' and restored raw PDFs.`, 'Batch', 'warning');
                                      } else {
                                        pushNotification('Clear Batch Failed', res?.error || 'Could not clear batch.', 'Batch', 'error');
                                      }
                                    }).catch((e) => pushNotification('Clear Batch Error', e.message, 'Batch', 'error'));
                                  }}
                                  className="px-2.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold"
                                >
                                  ⚠️ Confirm Clear
                                </button>
                                <button onClick={() => setConfirmClearBatchName('')} className="px-2 py-1.5 rounded-xl bg-slate-800 text-xs text-slate-300">Cancel</button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setConfirmClearBatchName(currentBatchObj.batchName)}
                                className="px-2.5 py-1.5 rounded-xl bg-rose-950 hover:bg-rose-800 text-rose-200 border border-rose-800 text-xs font-semibold"
                              >
                                🗑️ Clear
                              </button>
                            )
                          )}
                        </div>
                      )}
                    </div>

                    {/* "ALL BATCHES" TAB + INDIVIDUAL BATCH TABS WITH MULTI-BATCH COMMIT CHECKBOXES */}
                    {batches.length > 0 && (
                      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-800 shrink-0">
                        {batches.length > 1 && (
                          <button
                            onClick={() => {
                              if (isAllBatchesView) return;
                              setActiveBatchName('__ALL__');
                              setBatchSelectedSkus([]);
                              setBatchDraftEdits({});
                              setBatchSubsetFilter('All Subsets');
                              setConfirmClearBatchName('');
                              loadBatchesFromDisk('__ALL__');
                            }}
                            className={`px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap border transition flex items-center gap-1.5 ${
                              isAllBatchesView ? skin.accentActive : 'bg-slate-950/70 border-slate-800 text-slate-300 hover:text-white hover:border-slate-700'
                            }`}
                          >
                            <span>📚 All Batches ({batches.length})</span>
                            <span className="font-mono text-[10.5px] px-1.5 py-0.5 rounded bg-slate-900/90 text-sky-300">
                              {allBatchesTotalCards.toLocaleString()}
                            </span>
                            {allBatchesTotalFlagged > 0 && (
                              <span className="font-mono text-[10.5px] px-1.5 py-0.5 rounded bg-rose-950/90 border border-rose-700/70 text-rose-200">
                                🚩 {allBatchesTotalFlagged}
                              </span>
                            )}
                          </button>
                        )}
                        {batches.map((b) => {
                          const isTabAct = !isAllBatchesView && currentBatchObj?.batchName === b.batchName;
                          const isCheckedCommit = validSelectedCommitBatches.includes(b.batchName);
                          return (
                            <div
                              key={b.batchName}
                              className={`px-2.5 py-1 rounded-xl text-xs font-bold whitespace-nowrap border transition flex items-center gap-1.5 ${
                                isTabAct
                                  ? skin.accentActive
                                  : isCheckedCommit
                                  ? 'bg-emerald-950/40 border-emerald-600/70 text-emerald-200'
                                  : 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700'
                              }`}
                            >
                              {batches.length > 1 && (
                                <input
                                  type="checkbox"
                                  checked={isCheckedCommit}
                                  title={`Select '${b.batchName}' for multi-batch Commit`}
                                  onChange={() =>
                                    setSelectedCommitBatches((prev) =>
                                      prev.includes(b.batchName) ? prev.filter((x) => x !== b.batchName) : [...prev, b.batchName]
                                    )
                                  }
                                  className="accent-emerald-500 cursor-pointer"
                                />
                              )}
                              <button
                                type="button"
                                onClick={() => {
                                  if (isTabAct) return;
                                  setActiveBatchName(b.batchName);
                                  setBatchSelectedSkus([]);
                                  setBatchDraftEdits({});
                                  setBatchSubsetFilter('All Subsets');
                                  setConfirmClearBatchName('');
                                  loadBatchesFromDisk(b.batchName);
                                }}
                                className="flex items-center gap-1.5 py-0.5"
                              >
                                <span>📂 {b.batchName}</span>
                                <span className="font-mono text-[10.5px] px-1.5 py-0.5 rounded bg-slate-900/90 text-sky-300">
                                  {Number(b.cardCount || 0).toLocaleString()}
                                </span>
                                {Number(b.needsReviewCount || 0) > 0 && (
                                  <span className="font-mono text-[10.5px] px-1.5 py-0.5 rounded bg-rose-950/90 border border-rose-700/70 text-rose-200">
                                    🚩 {b.needsReviewCount}
                                  </span>
                                )}
                              </button>
                            </div>
                          );
                        })}
                        {batches.length > 1 && (
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedCommitBatches(
                                validSelectedCommitBatches.length === batches.length ? [] : batches.map((b) => b.batchName)
                              )
                            }
                            className="ml-auto px-2 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-[10.5px] font-semibold text-emerald-300 whitespace-nowrap shrink-0"
                          >
                            {validSelectedCommitBatches.length === batches.length ? '⬜ Uncheck Batches' : `☑️ Check All ${batches.length} Batches`}
                          </button>
                        )}
                      </div>
                    )}

                    {!currentBatchObj ? (
                      <p className="text-xs text-slate-400">No uncommitted batches waiting in Unprocessed_Cards\Batches.</p>
                    ) : (
                      <>
                        {/* BATCH CONFIDENCE SUMMARY + QUICK SELECTORS + ARCHIVE TOGGLE */}
                        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] bg-slate-950/75 border border-slate-800/90 rounded-xl px-3 py-2 shrink-0">
                          <div className="flex flex-wrap items-center gap-2 font-mono">
                            <span className="text-emerald-300 font-bold">🟢 T1 Lock (≥185): {t1Count.toLocaleString()}</span>
                            <span className="text-slate-600">•</span>
                            <span className="text-cyan-300 font-bold">🔵 T2 Visual: {t2Count.toLocaleString()}</span>
                            <span className="text-slate-600">•</span>
                            <span className="text-amber-300 font-bold">⚠️ &lt;185: {below190Skus.length.toLocaleString()}</span>
                            <span className="text-slate-600">•</span>
                            <span className="text-rose-300 font-bold">🚩 Review: {flaggedBatchSkus.length.toLocaleString()}</span>
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <button onClick={() => setBatchSelectedSkus(mergedBatchCards.map((c) => c.SKU))} className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10.5px] font-semibold">☑️ All ({mergedBatchCards.length})</button>
                            <button onClick={() => setBatchSelectedSkus(filteredBatchCards.map((c) => c.SKU))} className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10.5px] font-semibold">☑️ Filtered ({filteredBatchCards.length})</button>
                            <button onClick={() => setBatchSelectedSkus(flaggedBatchSkus)} className="px-2 py-0.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-200 text-[10.5px] font-semibold">🚩 Flagged ({flaggedBatchSkus.length})</button>
                            <button onClick={() => setBatchSelectedSkus(nonBaseBatchSkus)} className="px-2 py-0.5 rounded-lg bg-violet-950/80 hover:bg-violet-900 border border-violet-700 text-violet-200 text-[10.5px] font-semibold">✨ Non-Base ({nonBaseBatchSkus.length})</button>
                            <button onClick={() => setBatchSelectedSkus(below190Skus)} className="px-2 py-0.5 rounded-lg bg-amber-950/80 hover:bg-amber-900 border border-amber-800 text-amber-200 text-[10.5px] font-semibold">⚠️ &lt;185 ({below190Skus.length})</button>
                            <button onClick={() => setBatchSelectedSkus([])} className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10.5px] text-slate-300">⬜ Clear ({batchSelectedSkus.length})</button>
                            <label className="flex items-center gap-1 text-[10.5px] text-slate-400 ml-1 cursor-pointer" title="Move _F/_B/_C images to _My_Collection and archive raw PDFs on Commit">
                              <input type="checkbox" checked={batchMoveAndArchive} onChange={(e) => setBatchMoveAndArchive(e.target.checked)} />
                              Archive PDFs on Commit
                            </label>
                          </div>
                        </div>

                        {/* FILTERS ROW: REVIEW STATUS, ID CONFIDENCE / TIER, SUBSET, SEARCH, CLEAR */}
                        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 shrink-0">
                          <select value={batchReviewFilter} onChange={(e) => setBatchReviewFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                            <option value="all">All Review Statuses</option>
                            <option value="flagged">🚩 Needs Review Only ({flaggedBatchSkus.length})</option>
                            <option value="verified">✅ Verified / Good to Go ({mergedBatchCards.length - flaggedBatchSkus.length})</option>
                          </select>
                          <select value={batchConfFilter} onChange={(e) => setBatchConfFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                            <option value="all">All Confidence / Tiers</option>
                            <option value="t1_lock">🟢 Top-Tier Lock (OCR ≥ 185)</option>
                            <option value="below_190">⚠️ Below 185 (OCR &lt; 185)</option>
                            <option value="low_vis_75">👁️ Low Visual (&lt; 75%)</option>
                            <option value="t2_visual">🔵 Tier 2 Visual Confirmed (≥ 75%)</option>
                            <option value="t3_plus">🟠 Tier 3–5 (Re-Read / SetVis / AI)</option>
                            <option value="low_120">🔴 Low OCR (&lt; 120)</option>
                            <option value="par_corrected">✨ Parallel Self-Corrected</option>
                          </select>
                          <select value={batchSubsetFilter} onChange={(e) => setBatchSubsetFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                            <option>All Subsets</option>
                            <option value="__NON_BASE__">✨ Non-Base / Parallels Only ({nonBaseBatchSkus.length})</option>
                            {batchSubsetsList.map((sub) => <option key={sub}>{sub}</option>)}
                          </select>
                          <input value={batchSearchQ} onChange={(e) => setBatchSearchQ(e.target.value)} placeholder="Search SKU, Batch, Player, #, Signals..." className="md:col-span-2 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                          <button
                            onClick={() => { setBatchReviewFilter('all'); setBatchConfFilter('all'); setBatchSubsetFilter('All Subsets'); setBatchSearchQ(''); }}
                            className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
                          >
                            🧹 Clear Filters
                          </button>
                        </div>

                        {/* BATCH CARDS TABLE WITH CONFIDENCE SCORE / TIER, INLINE EDITING & PER-ROW DELETE */}
                        <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                          <table className="w-full text-left text-xs whitespace-nowrap">
                            <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                              <tr>
                                <th className="p-2">Sel</th>
                                <th className="p-2">SKU</th>
                                {isAllBatchesView && <th className="p-2">Batch</th>}
                                <th className="p-2">OCR Score / Tier</th>
                                <th className="p-2">Visual Conf.</th>
                                <th className="p-2">Review</th>
                                <th className="p-2">Set</th>
                                <th className="p-2">Subset / Parallel</th>
                                <th className="p-2">Card #</th>
                                <th className="p-2">Player</th>
                                <th className="p-2">Team</th>
                                <th className="p-2">Print Run</th>
                                <th className="p-2">Est PSA / BGS</th>
                                <th className="p-2">Grading Notes</th>
                                <th className="p-2 text-right">Del</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/80">
                              {pageSliceBatch.map((c) => {
                                const isSel = batchSelectedSkus.includes(c.SKU);
                                const isDirty = !!batchDraftEdits[c.SKU];
                                const tier = parseCardIdTier(c);
                                const rowBatch = c._BatchName || currentBatchObj.batchName;
                                const visTipStr = tier.visPct !== null ? `${tier.visPct}% (${tier.vis.toFixed(3)})` : 'No Reference Image';
                                const signalTip = `Batch: ${rowBatch}\nOCR Score: ${tier.ocr}\nVisual Confidence: ${visTipStr}\nSignals: ${c.OCR_Signals || 'None'}\nCandidates: ${c.Top_3_Template_Candidates || 'N/A'}`;
                                return (
                                  <tr key={`${rowBatch}-${c.SKU}`} className={isDirty ? 'bg-amber-950/30' : (isSel ? 'bg-cyan-950/35' : 'hover:bg-slate-800/40')}>
                                    <td className="p-1.5">
                                      <input
                                        type="checkbox"
                                        checked={isSel}
                                        onChange={() => setBatchSelectedSkus((p) => (p.includes(c.SKU) ? p.filter((x) => x !== c.SKU) : [...p, c.SKU]))}
                                      />
                                    </td>
                                    <td className="p-1.5 font-mono text-sky-400 font-bold">{c.SKU}</td>
                                    {isAllBatchesView && <td className="p-1.5 font-mono text-[10.5px] text-slate-400">{rowBatch}</td>}
                                    <td className="p-1.5" title={signalTip}>
                                      <div className="flex items-center gap-1">
                                        <span className={`px-1.5 py-0.5 rounded-md border font-mono text-[10.5px] font-bold cursor-help ${tier.badgeCls}`}>
                                          {tier.label} • {tier.ocr}
                                        </span>
                                        {tier.parCorrected && <span className="px-1 py-0.5 rounded bg-violet-950 border border-violet-600 text-violet-200 text-[9.5px] font-bold">✨ParFix</span>}
                                      </div>
                                    </td>
                                    <td className="p-1.5" title={signalTip}>
                                      <span className={`px-1.5 py-0.5 rounded-md border font-mono text-[10.5px] font-bold cursor-help ${tier.visBadgeCls}`}>
                                        {tier.visPct !== null ? `👁️ ${tier.visPct}%` : '— No Ref'}
                                      </span>
                                    </td>
                                    <td className="p-1.5">
                                      <select
                                        value={String(c.Needs_Review).toLowerCase() === 'true' ? 'True' : 'False'}
                                        onChange={(e) => updateBatchRowInline(c.SKU, 'Needs_Review', e.target.value)}
                                        className={`bg-slate-950 border rounded px-1.5 py-0.5 text-[11px] font-semibold ${String(c.Needs_Review).toLowerCase() === 'true' ? 'border-rose-700 text-rose-300' : 'border-slate-800 text-emerald-300'}`}
                                      >
                                        <option value="False">✅ False</option>
                                        <option value="True">🚩 True</option>
                                      </select>
                                    </td>
                                    <td className="p-1.5"><input value={c.Set || ''} onChange={(e) => updateBatchRowInline(c.SKU, 'Set', e.target.value)} className="w-36 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5" /></td>
                                    <td className="p-1.5"><input value={c.Subset_Parallel || ''} onChange={(e) => updateBatchRowInline(c.SKU, 'Subset_Parallel', e.target.value)} className="w-32 bg-transparent hover:bg-slate-950 border border-transparent focus:border-sky-700 rounded px-1 py-0.5 font-semibold text-white" /></td>
                                    <td className="p-1.5"><input value={c.Card_Number || ''} onChange={(e) => updateBatchRowInline(c.SKU, 'Card_Number', e.target.value)} className="w-16 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-mono" /></td>
                                    <td className="p-1.5"><input value={c.Player || ''} onChange={(e) => updateBatchRowInline(c.SKU, 'Player', e.target.value)} className="w-36 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-bold text-white" /></td>
                                    <td className="p-1.5"><input value={c.Team || ''} onChange={(e) => updateBatchRowInline(c.SKU, 'Team', e.target.value)} className="w-28 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 text-slate-300" /></td>
                                    <td className="p-1.5"><input value={c.Print_Run || ''} onChange={(e) => updateBatchRowInline(c.SKU, 'Print_Run', e.target.value)} className="w-14 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-mono text-amber-300" /></td>
                                    <td className="p-1.5 font-mono text-slate-200">PSA {c.Est_PSA || '—'} / BGS {c.Est_BGS || '—'}</td>
                                    <td className="p-1.5 text-[11px] text-slate-400 max-w-[240px] truncate" title={c.Grading_Notes || ''}>{c.Grading_Notes || '—'}</td>
                                    <td className="p-1.5 text-right">
                                      {confirmDeleteRowSku === c.SKU ? (
                                        <span className="inline-flex items-center gap-1">
                                          <button
                                            type="button"
                                            onClick={() => executeDeleteBatchCards([{ batchName: rowBatch, sku: c.SKU }])}
                                            className="px-1.5 py-0.5 rounded bg-rose-600 hover:bg-rose-500 text-white text-[10px] font-bold"
                                          >
                                            Del?
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => setConfirmDeleteRowSku('')}
                                            className="px-1 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]"
                                          >
                                            ✖
                                          </button>
                                        </span>
                                      ) : (
                                        <button
                                          type="button"
                                          onClick={() => setConfirmDeleteRowSku(c.SKU)}
                                          title={`Remove SKU ${c.SKU} from batch '${rowBatch}'`}
                                          className="px-1.5 py-0.5 rounded bg-rose-950/60 hover:bg-rose-800 text-rose-300 text-[11px]"
                                        >
                                          🗑️
                                        </button>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>

                        {/* PAGINATION FOOTER */}
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0">
                          <span>
                            Showing {filteredBatchCards.length === 0 ? 0 : ((safeBatchPage - 1) * batchPageSize + 1).toLocaleString()}–{Math.min(filteredBatchCards.length, safeBatchPage * batchPageSize).toLocaleString()} of {filteredBatchCards.length.toLocaleString()} matching card(s) in{' '}
                            <span className="font-mono text-sky-300">{isAllBatchesView ? `All ${batches.length} Uncommitted Batches` : currentBatchObj.batchName}</span>
                          </span>
                          <div className="flex items-center gap-2">
                            <select value={batchPageSize} onChange={(e) => { setBatchPageSize(parseInt(e.target.value, 10) || 250); setBatchPage(1); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                              <option value={100}>100 / page</option><option value={250}>250 / page</option><option value={500}>500 / page</option>
                            </select>
                            <button onClick={() => setBatchPage((p) => Math.max(1, p - 1))} disabled={safeBatchPage <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                            <span className="font-mono text-white">Page {safeBatchPage} / {totalBatchPages}</span>
                            <button onClick={() => setBatchPage((p) => Math.min(totalBatchPages, p + 1))} disabled={safeBatchPage >= totalBatchPages} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })()}

            {activePage === 'batch_deep_dive' && !currentBatchObj && (
              <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-8 text-center space-y-3`}>
                <div className="text-sm font-bold text-white">🔬 Deep-Dive Single-Card Review Studio</div>
                <p className="text-xs text-slate-400">No uncommitted batches are currently loaded. Ingest a batch first to inspect cards here.</p>
                <button onClick={() => setActivePage('scan_ingestion')} className={`px-4 py-1.5 rounded-xl text-xs font-bold ${skin.accentBtn}`}>
                  ⬅ Return to Batch Scan Processor
                </button>
              </div>
            )}

            {/* 2A. DEEP-DIVE SINGLE-CARD REVIEW STUDIO (MAXIMIZED VISUALS, REPROCESS, DELETE & PAGING) */}
            {activePage === 'batch_deep_dive' && currentBatchObj && (() => {
              const ddIsAll = activeBatchName === '__ALL__' && batches.length > 0;
              const ddPool = ddIsAll
                ? batches.flatMap((b) => (b.cards || []).map((c) => ({ ...c, _BatchName: c._BatchName || b.batchName })))
                : (batchCards || []).map((c) => ({ ...c, _BatchName: c._BatchName || currentBatchObj.batchName }));
              const ddFlaggedDefault = batchSelectedSkus.length > 0
                ? ddPool.filter((c) => batchSelectedSkus.includes(c.SKU))
                : (() => {
                    const fl = ddPool.filter((c) => String(c.Needs_Review).toLowerCase() === 'true');
                    return fl.length > 0 ? fl : ddPool;
                  })();
              const ddNonBaseCount = ddPool.filter((c) => {
                const su = String(c.Subset_Parallel || 'Base').trim().toUpperCase();
                return su !== '' && su !== 'BASE' && su !== 'BASE SET';
              }).length;

              let ddScoped = ddFlaggedDefault;
              if (guidedScopeMode === 'non_base_only') {
                ddScoped = ddPool.filter((c) => {
                  const su = String(c.Subset_Parallel || 'Base').trim().toUpperCase();
                  return su !== '' && su !== 'BASE' && su !== 'BASE SET';
                });
              } else if (guidedScopeMode === 'below_190') {
                ddScoped = ddPool.filter((c) => safeNum(c.OCR_Confidence, 0) < 185);
              } else if (guidedScopeMode === 'all_batch') {
                ddScoped = ddPool;
              }
              const ddSearched = ddScoped.filter((c) => {
                if (!guidedSearchQ.trim()) return true;
                const d = batchDraftEdits[c.SKU] || c;
                return `${c.SKU} ${c._BatchName || ''} ${d.Set} ${d.Subset_Parallel} ${d.Card_Number} ${d.Player} ${d.Team} ${c.OCR_Signals}`.toLowerCase().includes(guidedSearchQ.toLowerCase());
              });
              const safeDdIdx = Math.max(0, Math.min(deepDiveIdx, Math.max(0, ddSearched.length - 1)));
              const ddCard = ddSearched[safeDdIdx];
              const ddCardBatch = ddCard?._BatchName || currentBatchObj.batchName;

              const handleDdRotate = (fileName) =>
                fetch(`${NODE_API_BASE}/batches/rotate-image`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ batchName: ddCardBatch, fileName, degrees: 90 }),
                }).then((r) => r.json()).then((res) => {
                  if (res?.success) pushNotification('Image Rotated', `Rotated ${fileName} 90° clockwise.`, 'Batch', 'info');
                  else pushNotification('Rotate Failed', res?.error || 'Unable to rotate image.', 'Batch', 'error');
                }).catch((err) => pushNotification('Rotate Error', err.message, 'Batch', 'error'));

              const handleDdReprocess = (skuVal, lockedSetVal) =>
                triggerBatchCardsReprocess(ddCardBatch, [skuVal], lockedSetVal || '');

              const handleDdDelete = (cObj) => {
                const bn = cObj._BatchName || currentBatchObj.batchName;
                return fetch(`${NODE_API_BASE}/batches/delete-cards`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ items: [{ batchName: bn, sku: cObj.SKU }], deleteFiles: true, activeBatchName: activeBatchName || bn }),
                }).then((r) => r.json()).then((res) => {
                  if (res?.success) {
                    setBatchSelectedSkus((prev) => prev.filter((s) => s !== cObj.SKU));
                    setBatchDraftEdits((prev) => { const cp = { ...prev }; delete cp[cObj.SKU]; return cp; });
                    if (Array.isArray(res.batches)) setBatches(res.batches);
                    loadBatchesFromDisk(activeBatchName || bn);
                    pushNotification(`Removed SKU ${cObj.SKU}`, `Deleted card from batch '${bn}'.`, 'Batch', 'warning');
                  } else {
                    pushNotification('Remove Failed', res?.error || 'Could not delete card.', 'Batch', 'error');
                  }
                }).catch((err) => pushNotification('Remove Error', err.message, 'Batch', 'error'));
              };

              const handleDdSaveAdvance = (singleUpdate, opts = {}) => {
                const isConfirmOnly = Boolean(opts?.confirmOnly);
                const bn = singleUpdate._BatchName || ddCardBatch;
                const savedSubUp = String(singleUpdate.Subset_Parallel || 'Base').trim().toUpperCase();
                const dropsFromFlaggedScope = (
                  (guidedScopeMode === 'selected_or_flagged' &&
                    batchSelectedSkus.length === 0 &&
                    String(singleUpdate.Needs_Review || '').toLowerCase() === 'false') ||
                  (guidedScopeMode === 'non_base_only' && (savedSubUp === '' || savedSubUp === 'BASE' || savedSubUp === 'BASE SET'))
                );
                return fetch(`${NODE_API_BASE}/batches/update`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ batchName: bn, cards: [singleUpdate], confirmOnly: isConfirmOnly }),
                }).then((r) => r.json()).then((res) => {
                  if (res?.success) {
                    setBatchDraftEdits((prev) => { const cp = { ...prev }; delete cp[singleUpdate.SKU]; return cp; });
                    if (Array.isArray(res.cards)) {
                      setBatches((prev) => prev.map((b) => (b.batchName === bn ? { ...b, cards: res.cards.map((x) => ({ ...x, _BatchName: bn })), needsReviewCount: res.cards.filter((x) => String(x.Needs_Review).toLowerCase() === 'true').length } : b)));
                    }
                    loadBatchesFromDisk(activeBatchName || bn);
                    if (isConfirmOnly) {
                      pushNotification(`✅ Confirmed Correct (SKU ${singleUpdate.SKU})`, `Verified ${singleUpdate.Set} ${singleUpdate.Card_Number} ${singleUpdate.Player} [${singleUpdate.Subset_Parallel}].`, 'Batch', 'success');
                    } else {
                      pushNotification(`Saved SKU ${singleUpdate.SKU}`, `${singleUpdate.Set} ${singleUpdate.Card_Number} ${singleUpdate.Player} [${singleUpdate.Subset_Parallel}] (${res.renamedCount || 0} renamed).`, 'Batch', 'success');
                    }
                    if (!dropsFromFlaggedScope) {
                      setDeepDiveIdx((idx) => Math.min(Math.max(0, ddSearched.length - 1), idx + 1));
                    }
                  } else {
                    pushNotification(`Save Failed (SKU ${singleUpdate.SKU})`, res?.error || 'Could not update batch manifest.', 'Batch', 'error');
                  }
                }).catch((err) => pushNotification(`Save Error (SKU ${singleUpdate.SKU})`, err.message, 'Batch', 'error'));
              };

              return (
                <div className="flex-1 min-h-0 h-full flex flex-col overflow-hidden">
                  {!ddCard ? (
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-6 text-center space-y-3`}>
                      <div className="text-xs text-slate-400">
                        No cards match the selected Deep-Dive filter.
                      </div>
                      <div className="flex items-center justify-center gap-2">
                        <button type="button" onClick={() => { setGuidedScopeMode('all_batch'); setGuidedSearchQ(''); setDeepDiveIdx(0); }} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-sky-300">
                          Show All Cards in Batch ({ddPool.length})
                        </button>
                        <button type="button" onClick={() => setActivePage('guided_batch_review')} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200">
                          ⬅ Guided Review
                        </button>
                      </div>
                    </div>
                  ) : (
                    <GradingDeepDiveStudio
                      key={`batch-gdd-${ddCardBatch}-${ddCard.SKU}`}
                      card={ddCard}
                      targetType="batch"
                      batchName={ddCardBatch}
                      cardIndex={safeDdIdx}
                      totalCards={ddSearched.length}
                      onPrev={() => setDeepDiveIdx((i) => Math.max(0, i - 1))}
                      onNext={() => setDeepDiveIdx((i) => Math.min(Math.max(0, ddSearched.length - 1), i + 1))}
                      onBack={() => setActivePage('guided_batch_review')}
                      backLabel="Guided Review"
                      onSwitchIndividual={() => setActivePage('guided_batch_review')}
                      cardOptions={ddSearched.map((sc, si) => ({
                        index: si,
                        label: `${si + 1}/${ddSearched.length} • SKU ${sc.SKU} — #${String(sc.Card_Number || '').replace(/^#/, '')} ${sc.Player}`,
                      }))}
                      onSelectCardIndex={(idx) => setDeepDiveIdx(idx)}
                      onCardUpdated={(res) => {
                        if (Array.isArray(res?.cards)) {
                          setBatches((prev) => prev.map((b) => (b.batchName === ddCardBatch ? { ...b, cards: res.cards.map((x) => ({ ...x, _BatchName: ddCardBatch })) } : b)));
                        } else if (res?.card) {
                          setBatches((prev) => prev.map((b) => (b.batchName === ddCardBatch ? { ...b, cards: (b.cards || []).map((x) => (x.SKU === res.card.SKU ? { ...x, ...res.card, _BatchName: ddCardBatch } : x)) } : b)));
                        }
                      }}
                      skin={skin}
                      pushNotification={pushNotification}
                    />
                  )}
                </div>
              );
            })()}

            {/* 2. GUIDED BATCH REVIEW (FULL TYPE-AHEAD SEARCH, AUTOFILL, VALIDATED SUBSETS, DELETE & ALL-BATCHES SUPPORT) */}
            {activePage === 'guided_batch_review' && currentBatchObj && (() => {
              const gIsAll = activeBatchName === '__ALL__' && batches.length > 0;
              const gPool = gIsAll
                ? batches.flatMap((b) => (b.cards || []).map((c) => ({ ...c, _BatchName: c._BatchName || b.batchName })))
                : (batchCards || []).map((c) => ({ ...c, _BatchName: c._BatchName || currentBatchObj.batchName }));
              const gDefaultScope = batchSelectedSkus.length > 0
                ? gPool.filter((c) => batchSelectedSkus.includes(c.SKU))
                : (() => {
                    const fl = gPool.filter((c) => String(c.Needs_Review).toLowerCase() === 'true');
                    return fl.length > 0 ? fl : gPool;
                  })();
              const nonBaseCountAll = gPool.filter((c) => {
                const su = String(c.Subset_Parallel || 'Base').trim().toUpperCase();
                return su !== '' && su !== 'BASE' && su !== 'BASE SET';
              }).length;

              let scopedCards = gDefaultScope;
              if (guidedScopeMode === 'non_base_only') {
                scopedCards = gPool.filter((c) => {
                  const su = String(c.Subset_Parallel || 'Base').trim().toUpperCase();
                  return su !== '' && su !== 'BASE' && su !== 'BASE SET';
                });
              } else if (guidedScopeMode === 'below_190') {
                scopedCards = gPool.filter((c) => safeNum(c.OCR_Confidence, 0) < 185);
              } else if (guidedScopeMode === 'all_batch') {
                scopedCards = gPool;
              }
              const searchedGuided = scopedCards.filter((c) => {
                if (!guidedSearchQ.trim()) return true;
                const d = batchDraftEdits[c.SKU] || c;
                return `${c.SKU} ${c._BatchName || ''} ${d.Set} ${d.Subset_Parallel} ${d.Card_Number} ${d.Player} ${d.Team} ${c.OCR_Signals}`.toLowerCase().includes(guidedSearchQ.toLowerCase());
              });
              const gTotalPages = Math.max(1, Math.ceil(searchedGuided.length / guidedPageSize));
              const gSafePage = Math.min(guidedPage, gTotalPages);
              const gSlice = searchedGuided.slice((gSafePage - 1) * guidedPageSize, gSafePage * guidedPageSize);
              const dirtyGuidedSkus = Object.keys(batchDraftEdits).filter((k) => gPool.some((c) => c.SKU === k));

              const goGuidedPage = (nextPg) => {
                setGuidedPage(Math.max(1, Math.min(gTotalPages, nextPg)));
                if (mainScrollRef.current) mainScrollRef.current.scrollTo({ top: 0, behavior: 'smooth' });
              };

              const handleDeleteGuidedCard = (cObj) => {
                const bn = cObj._BatchName || currentBatchObj.batchName;
                return fetch(`${NODE_API_BASE}/batches/delete-cards`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ items: [{ batchName: bn, sku: cObj.SKU }], deleteFiles: true, activeBatchName: activeBatchName || bn }),
                }).then((r) => r.json()).then((res) => {
                  if (res?.success) {
                    setBatchSelectedSkus((prev) => prev.filter((s) => s !== cObj.SKU));
                    setBatchDraftEdits((prev) => { const cp = { ...prev }; delete cp[cObj.SKU]; return cp; });
                    if (Array.isArray(res.batches)) setBatches(res.batches);
                    loadBatchesFromDisk(activeBatchName || bn);
                    pushNotification(`Removed SKU ${cObj.SKU}`, `Deleted card from batch '${bn}'.`, 'Batch', 'warning');
                  } else {
                    pushNotification('Remove Failed', res?.error || 'Could not remove card.', 'Batch', 'error');
                  }
                }).catch((err) => pushNotification('Remove Error', err.message, 'Batch', 'error'));
              };

              return (
                <div className="space-y-4">
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <button onClick={() => setActivePage('scan_ingestion')} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold">⬅ Back to Batches</button>
                        <h2 className="text-sm font-bold text-white">🪟 Guided Batch Review — {gIsAll ? `All Batches (${batches.length})` : currentBatchObj.batchName} ({searchedGuided.length.toLocaleString()} Cards)</h2>
                        <button
                          onClick={() => { setDeepDiveIdx(0); openHiddenPage('batch_deep_dive'); }}
                          className="px-2.5 py-1 rounded-xl bg-indigo-950/90 hover:bg-indigo-800 border border-indigo-600/70 text-indigo-200 font-bold text-xs"
                        >
                          🔬 Deep-Dive Mode
                        </button>
                        <button
                          disabled={gSlice.length === 0}
                          onClick={() => {
                            const byB = {};
                            gSlice.forEach((x) => {
                              const bn = x._BatchName || currentBatchObj.batchName;
                              if (!byB[bn]) byB[bn] = [];
                              byB[bn].push(x.SKU);
                            });
                            Object.entries(byB).forEach(([bn, sks]) => triggerBatchCardsReprocess(bn, sks));
                          }}
                          title="Reprocess all cards shown on this Guided Review page immediately in a parallel worker"
                          className="px-2.5 py-1 rounded-xl bg-cyan-950/90 hover:bg-cyan-800 border border-cyan-600/70 text-cyan-200 font-bold text-xs disabled:opacity-40"
                        >
                          🔄 Reprocess Page ({gSlice.length})
                        </button>
                      </div>
                      <button
                        onClick={() => {
                          const isBulkConfirmOnly = dirtyGuidedSkus.length === 0;
                          const groupedUpd = {};
                          const targetCards = dirtyGuidedSkus.length > 0
                            ? dirtyGuidedSkus.map((sku) => {
                                const baseC = gPool.find((x) => x.SKU === sku) || {};
                                const { _reviewTouched, ...cleanDraft } = batchDraftEdits[sku] || {};
                                const explicitFlagTrue = Boolean(_reviewTouched) && String(cleanDraft.Needs_Review || '').toLowerCase() === 'true';
                                return { ...baseC, ...cleanDraft, SKU: sku, Needs_Review: explicitFlagTrue ? 'True' : 'False', Manual_Override: cleanDraft.Subset_Parallel || baseC.Subset_Parallel || 'Base' };
                              })
                            : gSlice.map((c) => ({ ...c, SKU: c.SKU, Needs_Review: 'False' }));
                          targetCards.forEach((tc) => {
                            const bn = tc._BatchName || currentBatchObj.batchName;
                            if (!groupedUpd[bn]) groupedUpd[bn] = [];
                            groupedUpd[bn].push(tc);
                          });
                          Promise.all(
                            Object.entries(groupedUpd).map(([bn, cardsArr]) =>
                              fetch(`${NODE_API_BASE}/batches/update`, {
                                method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ batchName: bn, cards: cardsArr, confirmOnly: isBulkConfirmOnly }),
                              }).then((r) => r.json())
                            )
                          ).then((results) => {
                            const fail = results.find((r) => !r?.success);
                            if (!fail) {
                              setBatchDraftEdits({});
                              loadBatchesFromDisk(activeBatchName || currentBatchObj.batchName);
                              const renTot = results.reduce((a, r) => a + Number(r.renamedCount || 0), 0);
                              if (isBulkConfirmOnly) {
                                pushNotification('✅ Page Confirmed Correct', `Confirmed ${targetCards.length} card(s) on this page as correct.`, 'Batch', 'success');
                              } else {
                                pushNotification('Guided Overrides Saved', `Updated ${targetCards.length} card(s) and renamed ${renTot} card set(s).`, 'Batch', 'success');
                              }
                            } else {
                              pushNotification('Guided Save Failed', fail.error || 'Could not update batch manifest.', 'Batch', 'error');
                            }
                          }).catch((err) => pushNotification('Guided Save Error', err.message, 'Batch', 'error'));
                        }}
                        className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow"
                      >
                        {dirtyGuidedSkus.length > 0
                          ? `💾 Apply ${dirtyGuidedSkus.length} Edited Overrides & Rename`
                          : `✅ Confirm All on Page (${gSlice.length}) Correct`}
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
                      <select value={guidedScopeMode} onChange={(e) => { setGuidedScopeMode(e.target.value); setGuidedPage(1); }} className="md:col-span-2 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                        <option value="selected_or_flagged">Selected / Flagged Cards ({gDefaultScope.length})</option>
                        <option value="non_base_only">✨ Non-Base / Parallels Only ({nonBaseCountAll})</option>
                        <option value="below_190">All Cards Below OCR 185 ({gPool.filter((c) => safeNum(c.OCR_Confidence, 0) < 185).length})</option>
                        <option value="all_batch">All Cards in View ({gPool.length})</option>
                      </select>
                      <input
                        value={guidedSearchQ}
                        onChange={(e) => { setGuidedSearchQ(e.target.value); setGuidedPage(1); }}
                        placeholder="Filter review cards (SKU, Batch, #, Player, Signals)..."
                        className="md:col-span-2 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs"
                      />
                      <select value={guidedPageSize} onChange={(e) => { setGuidedPageSize(parseInt(e.target.value, 10) || 15); setGuidedPage(1); }} className="bg-slate-950 border border-slate-700 rounded-xl px-2 py-1.5 text-xs">
                        <option value={10}>10 cards / page</option><option value={15}>15 cards / page</option><option value={25}>25 cards / page</option><option value={50}>50 cards / page</option>
                      </select>
                      <div className="flex items-center justify-end gap-1.5 text-xs">
                        <button onClick={() => setGuidedPage((p) => Math.max(1, p - 1))} disabled={gSafePage <= 1} className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀</button>
                        <span className="font-mono text-white">{gSafePage}/{gTotalPages}</span>
                        <button onClick={() => setGuidedPage((p) => Math.min(gTotalPages, p + 1))} disabled={gSafePage >= gTotalPages} className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">▶</button>
                      </div>
                    </div>
                  </div>

                  {gSlice.map((card) => {
                    const cBatch = card._BatchName || currentBatchObj.batchName;
                    return (
                      <GuidedReviewCardItem
                        key={`${cBatch}-${card.SKU}`}
                        card={card}
                        draft={batchDraftEdits[card.SKU] || card}
                        isDirty={!!batchDraftEdits[card.SKU]}
                        batchName={cBatch}
                        skin={skin}
                        dynamicSets={dynamicSetsNewestFirst}
                        externalImgBust={batchImgBust}
                        isReprocessingExternal={Boolean(reprocessingBatchSkus[card.SKU])}
                        onDraftChange={(nextCard) => setBatchDraftEdits((p) => ({ ...p, [card.SKU]: nextCard }))}
                        onReprocessOne={(skuVal, lockedSetVal) => triggerBatchCardsReprocess(cBatch, [skuVal], lockedSetVal || '')}
                        onDeleteOne={handleDeleteGuidedCard}
                        onReplaceImages={(cObj) => setReplaceImgTarget({
                          type: 'batch',
                          batchName: cBatch,
                          sku: cObj.SKU,
                          set: cObj.Set,
                          subset: cObj.Subset_Parallel,
                          cardNumber: cObj.Card_Number,
                          player: cObj.Player,
                        })}
                        onOpenDeepDive={(skuVal) => {
                          const foundI = searchedGuided.findIndex((x) => x.SKU === skuVal);
                          setDeepDiveIdx(foundI >= 0 ? foundI : 0);
                          openHiddenPage('batch_deep_dive');
                        }}
                        onRotateSide={(fileName) =>
                          fetch(`${NODE_API_BASE}/batches/rotate-image`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ batchName: cBatch, fileName, degrees: 90 }),
                          }).then((r) => r.json()).then((res) => {
                            if (res?.success) {
                              pushNotification('Image Rotated', `Rotated ${fileName} 90° clockwise.`, 'Batch', 'info');
                            } else {
                              pushNotification('Rotate Failed', res?.error || 'Unable to rotate image.', 'Batch', 'error');
                            }
                          }).catch((err) => pushNotification('Rotate Error', err.message, 'Batch', 'error'))
                        }
                        onSaveOne={(singleUpdate, opts = {}) => {
                          const isConfirmOnly = Boolean(opts?.confirmOnly);
                          return fetch(`${NODE_API_BASE}/batches/update`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ batchName: cBatch, cards: [singleUpdate], confirmOnly: isConfirmOnly }),
                          }).then((r) => r.json()).then((res) => {
                            if (res?.success) {
                              setBatchDraftEdits((prev) => {
                                const copy = { ...prev };
                                delete copy[card.SKU];
                                return copy;
                              });
                              if (Array.isArray(res.cards)) {
                                setBatches((prev) => prev.map((b) => (b.batchName === cBatch ? { ...b, cards: res.cards.map((x) => ({ ...x, _BatchName: cBatch })), needsReviewCount: res.cards.filter((x) => String(x.Needs_Review).toLowerCase() === 'true').length } : b)));
                              }
                              loadBatchesFromDisk(activeBatchName || cBatch);
                              if (isConfirmOnly) {
                                pushNotification(`✅ Confirmed Correct (SKU ${card.SKU})`, `Verified ${singleUpdate.Set} ${singleUpdate.Card_Number} ${singleUpdate.Player} [${singleUpdate.Subset_Parallel}].`, 'Batch', 'success');
                              } else {
                                pushNotification(`Saved SKU ${card.SKU}`, `${singleUpdate.Set} ${singleUpdate.Card_Number} ${singleUpdate.Player} [${singleUpdate.Subset_Parallel}] (${res.renamedCount || 0} renamed).`, 'Batch', 'success');
                              }
                            } else {
                              pushNotification(`Save Failed (SKU ${card.SKU})`, res?.error || 'Could not update batch manifest.', 'Batch', 'error');
                            }
                          }).catch((err) => pushNotification(`Save Error (SKU ${card.SKU})`, err.message, 'Batch', 'error'));
                        }}
                      />
                    );
                  })}

                  {/* BOTTOM PAGINATION BAR (NO NEED TO SCROLL BACK TO TOP) */}
                  {searchedGuided.length > 0 && (
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5 flex flex-wrap items-center justify-between gap-2 text-xs`}>
                      <span className="text-slate-400">
                        Showing {((gSafePage - 1) * guidedPageSize + 1).toLocaleString()}–{Math.min(searchedGuided.length, gSafePage * guidedPageSize).toLocaleString()} of {searchedGuided.length.toLocaleString()} review card(s)
                      </span>
                      <div className="flex flex-wrap items-center gap-2">
                        <button onClick={() => goGuidedPage(gSafePage - 1)} disabled={gSafePage <= 1} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-bold">◀ Prev Page</button>
                        <span className="font-mono text-white px-2">Page {gSafePage} / {gTotalPages}</span>
                        <button onClick={() => goGuidedPage(gSafePage + 1)} disabled={gSafePage >= gTotalPages} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-bold">Next Page ▶</button>
                        <button onClick={() => mainScrollRef.current && mainScrollRef.current.scrollTo({ top: 0, behavior: 'smooth' })} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-300 font-semibold">▲ Top</button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* 3. INVENTORY */}
            {activePage === 'inventory' && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                  <h2 className="text-sm font-bold text-white">
                    🗂️ Master Inventory ({filteredInventory.length.toLocaleString()} / {inventory.length.toLocaleString()} SKUs)
                  </h2>
                  <div className="flex flex-wrap items-center gap-2">
                    <button onClick={() => setSelectedInvSkus(inventory.map((c) => c.SKU))} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold">☑️ Select All ({inventory.length})</button>
                    <button onClick={() => setSelectedInvSkus(filteredInventory.map((c) => c.SKU))} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold">☑️ Select Filtered ({filteredInventory.length})</button>
                    <button onClick={() => setSelectedInvSkus([])} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs">⬜ Clear ({selectedInvSkus.length})</button>
                    <button onClick={() => setShowManualAddInv(!showManualAddInv)} className="px-2.5 py-1.5 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-200 font-bold text-xs">
                      {showManualAddInv ? '▲ Close Manual Entry' : '➕ Add Card'}
                    </button>
                    <div ref={invEditMenuRef} className="relative">
                      <button
                        type="button"
                        disabled={selectedInvSkus.length === 0}
                        onClick={() => {
                          if (selectedInvSkus.length === 1) {
                            openInventoryEditorForSkus(selectedInvSkus, 'individual');
                          } else {
                            setShowInvEditMenu((v) => !v);
                          }
                        }}
                        className={`px-3 py-1.5 rounded-xl font-bold text-xs disabled:opacity-40 flex items-center gap-1.5 ${skin.accentBtn}`}
                      >
                        <span>✏️ Edit ({selectedInvSkus.length})</span>
                        {selectedInvSkus.length > 1 && <span className="text-[10px]">▾</span>}
                      </button>
                      {showInvEditMenu && selectedInvSkus.length > 1 && (
                        <div className="absolute right-0 mt-1.5 w-64 bg-slate-900/95 backdrop-blur-xl border border-slate-700 rounded-2xl shadow-2xl p-1.5 z-50 space-y-1">
                          <button
                            type="button"
                            onClick={() => openInventoryEditorForSkus(selectedInvSkus, 'individual')}
                            className="w-full text-left px-3 py-2 rounded-xl hover:bg-slate-800 transition space-y-0.5"
                          >
                            <div className="text-xs font-bold text-sky-200">🪟 Individual Edit (Guided Review)</div>
                            <div className="text-[10px] text-slate-400">Edit each of the {selectedInvSkus.length} SKUs individually with side-by-side scans, autofill &amp; all fields</div>
                          </button>
                          <button
                            type="button"
                            onClick={() => openInventoryEditorForSkus(selectedInvSkus, 'deep_dive')}
                            className="w-full text-left px-3 py-2 rounded-xl hover:bg-slate-800 transition space-y-0.5"
                          >
                            <div className="text-xs font-bold text-indigo-200">🔬 Individual Deep-Dive (1-by-1)</div>
                            <div className="text-[10px] text-slate-400">Maximized single-card inspection with Prev / Next paging</div>
                          </button>
                          <div className="border-t border-slate-800 my-1" />
                          <button
                            type="button"
                            onClick={() => openInventoryEditorForSkus(selectedInvSkus, 'bulk')}
                            className="w-full text-left px-3 py-2 rounded-xl hover:bg-slate-800 transition space-y-0.5"
                          >
                            <div className="text-xs font-bold text-amber-200">📋 Bulk Edit ({selectedInvSkus.length} SKUs)</div>
                            <div className="text-[10px] text-slate-400">Selectively apply shared Set, Subset, Status, Hold Tag or Prices to all {selectedInvSkus.length} cards</div>
                          </button>
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => {
                        setReprintMode('reprint_only');
                        setStagedReprintSkus((prev) => Array.from(new Set([...prev, ...selectedInvSkus])));
                        setReprintSkuInput('');
                        setLabelPreviewPage(1);
                        const firstPick = inventory.find((c) => c.SKU === selectedInvSkus[0]);
                        if (firstPick) prefillSampleLabelFromCard(firstPick);
                        setActivePage('label_hub');
                        pushNotification('Labels Queued for Reprint', `Added ${selectedInvSkus.length} SKU(s) into Label Hub Reprint Queue.`, 'Labels', 'info');
                      }}
                      disabled={selectedInvSkus.length === 0}
                      className="px-2.5 py-1.5 rounded-xl bg-sky-950/80 hover:bg-sky-900 border border-sky-700 text-sky-200 font-semibold text-xs disabled:opacity-40"
                    >
                      🏷️ Reprint ({selectedInvSkus.length})
                    </button>
                    <button onClick={() => autoAssignRecPrice(selectedInvSkus.length > 0 ? selectedInvSkus : filteredInventory.map((c) => c.SKU))} className="px-3 py-1.5 rounded-xl bg-amber-950/80 hover:bg-amber-900 border border-amber-700 text-amber-200 font-bold text-xs">
                      ✨ Auto-Assign Price ({selectedInvSkus.length > 0 ? selectedInvSkus.length : filteredInventory.length})
                    </button>
                    <button
                      onClick={() => {
                        if (selectedInvSkus.length === 0) return;
                        fetch(`${NODE_API_BASE}/inventory/delete`, {
                          method: 'POST', headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ skus: selectedInvSkus, deleteCardImages: false }),
                        }).then((r) => r.json()).then((res) => {
                          if (res && res.success) {
                            setInventory(res.rows || []);
                            setSelectedInvSkus([]);
                            pushNotification('SKUs Deleted', `Removed ${res.deleted_rows || selectedInvSkus.length} SKU(s) from Inventory.csv.`, 'Inventory', 'warning');
                          } else {
                            pushNotification('Delete Failed', res?.error || 'Could not delete selected SKUs.', 'Inventory', 'error');
                          }
                        }).catch((e) => pushNotification('Delete Error', e.message, 'Inventory', 'error'));
                      }}
                      disabled={selectedInvSkus.length === 0}
                      className="px-2.5 py-1.5 rounded-xl bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-200 font-semibold text-xs disabled:opacity-40"
                    >
                      🗑️ Delete ({selectedInvSkus.length})
                    </button>
                    {inventoryDirty && (
                      <button onClick={() => persistInventoryToDisk(inventory, 'Inline Edits Saved')} className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs animate-pulse">
                        💾 Save Inline Edits
                      </button>
                    )}
                    <button onClick={() => triggerJob('ingest_inventory', `Re-Grade All Inventory (${inventory.length})`, 'regrade_inventory')} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs">🔄 Re-Grade All</button>
                  </div>
                </div>

                {showManualAddInv && (
                  <div className={`${skin.cardBg} border border-emerald-500/40 rounded-2xl p-3.5 space-y-2.5 shrink-0`}>
                    <div className="text-xs font-bold text-emerald-300">➕ Fast Manual Physical Card Entry (Auto-Assigns 7-Digit SKU &amp; Pricing)</div>
                    <div className="grid grid-cols-2 md:grid-cols-9 gap-2">
                      <select value={manualCard.Set} onChange={(e) => setManualCard({ ...manualCard, Set: e.target.value })} className="md:col-span-2 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs">
                        {dynamicSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                      </select>
                      <input list="manual-subsets-datalist" value={manualCard.Subset} onChange={(e) => setManualCard({ ...manualCard, Subset: e.target.value })} placeholder="Subset (Base)" className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" />
                      <datalist id="manual-subsets-datalist">{manualSubsets.slice(0, 250).map((s) => <option key={s} value={s} />)}</datalist>
                      <input
                        value={manualCard.CardNumber}
                        onChange={(e) => setManualCard({ ...manualCard, CardNumber: e.target.value })}
                        onBlur={() => {
                          if (!manualCard.Set || !manualCard.CardNumber.trim()) return;
                          const p = new URLSearchParams({ set: manualCard.Set, cardNumber: manualCard.CardNumber.trim(), subset: manualCard.Subset || 'Base' });
                          fetch(`${NODE_API_BASE}/checklists/lookup?${p.toString()}`).then((r) => r.json()).then((d) => {
                            if (d && d.exact && d.exact.player && d.exact.player !== 'Unknown Player') {
                              setManualCard((prev) => ({ ...prev, Player: d.exact.player, Team: d.exact.team || prev.Team, PrintRun: d.exact.print_run || prev.PrintRun }));
                            }
                          }).catch(() => {});
                        }}
                        placeholder="Card # (Auto-Fills)"
                        className="bg-slate-950 border border-sky-700/70 rounded-lg px-2 py-1.5 text-xs font-mono"
                      />
                      <input value={manualCard.Player} onChange={(e) => setManualCard({ ...manualCard, Player: e.target.value })} placeholder="Player" className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" />
                      <input value={manualCard.Team} onChange={(e) => setManualCard({ ...manualCard, Team: e.target.value })} placeholder="Team" className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" />
                      <input value={manualCard.PrintRun} onChange={(e) => setManualCard({ ...manualCard, PrintRun: e.target.value })} placeholder="#/ Print Run" className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" />
                      <input type="number" min="1" max="50" value={manualCard.Qty} onChange={(e) => setManualCard({ ...manualCard, Qty: Math.max(1, parseInt(e.target.value, 10) || 1) })} placeholder="Qty" className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" />
                      <button
                        onClick={() => {
                          if (!manualCard.CardNumber.trim() || !manualCard.Player.trim()) {
                            pushNotification('Missing Fields', 'Enter at least a Card # and Player Name.', 'Inventory', 'warning');
                            return;
                          }
                          const nowStr = new Date().toISOString().replace('T', ' ').slice(0, 16);
                          const newRows = Array.from({ length: manualCard.Qty || 1 }).map(() => ({
                            SKU: '', Status: 'In Stock', Hold_Tag: manualCard.HoldTag || 'For Sale',
                            Set: manualCard.Set, Subset: manualCard.Subset || 'Base',
                            'Card Number': manualCard.CardNumber.replace(/^#/, ''), Player: manualCard.Player,
                            Team: manualCard.Team, 'Print Run': manualCard.PrintRun, Attributes: '',
                            Raw_Price: manualCard.RawPrice || '1.00', Grading_Notes: 'Manual Entry',
                            Label_Printed: 'False', Needs_Review: 'False', Date_Added: nowStr, Source_Batch: 'Manual_Entry',
                          }));
                          persistInventoryToDisk([...inventory, ...newRows], `Added ${newRows.length} Manual Card(s)`);
                          setManualCard({ ...manualCard, CardNumber: '', Player: '', Team: '', PrintRun: '', Qty: 1 });
                        }}
                        className="rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs px-2 py-1.5"
                      >
                        ➕ Add
                      </button>
                    </div>
                  </div>
                )}

                <div className={`grid grid-cols-1 md:grid-cols-5 gap-2.5 ${skin.cardBg} border ${skin.border} p-3 rounded-2xl shrink-0`}>
                  <select value={invSetFilter} onChange={(e) => setInvSetFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Sets</option>
                    {ownedSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                  </select>
                  <select value={invHoldFilter} onChange={(e) => setInvHoldFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Hold Tags</option><option>For Sale</option><option>Make Me an Offer</option><option>Personal Collection (PC)</option>
                  </select>
                  <select value={invStatusFilter} onChange={(e) => setInvStatusFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Statuses</option><option>In Stock</option><option>Listed</option><option>Grading</option><option>Sold</option><option>PC / Hold</option>
                  </select>
                  <input value={invSearch} onChange={(e) => setInvSearch(e.target.value)} placeholder="Search SKU, Player, Card #, Subset, Team..." className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs" />
                  <button onClick={() => { setInvSetFilter('All Sets'); setInvHoldFilter('All Hold Tags'); setInvStatusFilter('All Statuses'); setInvSearch(''); }} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 font-semibold">
                    🧹 Clear Filters
                  </button>
                </div>

                <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-2xl bg-slate-900/60">
                  <table className="w-full text-left text-xs whitespace-nowrap">
                    <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 sticky top-0 z-10">
                      <tr>
                        <th className="p-2">Sel</th><th className="p-2">SKU</th><th className="p-2">Status</th><th className="p-2">Hold Tag</th><th className="p-2">Set</th><th className="p-2">Subset</th><th className="p-2">Card #</th><th className="p-2">Player</th><th className="p-2">Team</th><th className="p-2">Print Run</th><th className="p-2">Attributes</th><th className="p-2">Copy</th><th className="p-2">Centering</th><th className="p-2">PSA / BGS</th><th className="p-2">Raw ($)</th><th className="p-2">Min ($)</th><th className="p-2">Sale Price ($)</th><th className="p-2">Action</th><th className="p-2">Label?</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/70">
                      {(() => {
                        const invTotP = Math.max(1, Math.ceil(filteredInventory.length / invPageSize));
                        const safeInvP = Math.min(invPage, invTotP);
                        return filteredInventory.slice((safeInvP - 1) * invPageSize, safeInvP * invPageSize);
                      })().map((card) => {
                        const isSel = selectedInvSkus.includes(card.SKU);
                        return (
                          <tr key={card.SKU} className={isSel ? 'bg-cyan-950/35' : 'hover:bg-slate-800/40'}>
                            <td className="p-1.5"><input type="checkbox" checked={isSel} onChange={() => setSelectedInvSkus((p) => (p.includes(card.SKU) ? p.filter((x) => x !== card.SKU) : [...p, card.SKU]))} /></td>
                            <td className="p-1.5 font-mono text-sky-400 font-bold cursor-pointer hover:underline" onClick={() => openInventoryEditorForSkus([card.SKU])}>{card.SKU}</td>
                            <td className="p-1.5">
                              <select value={card.Status || 'In Stock'} onChange={(e) => updateInventoryRowInline(card.SKU, 'Status', e.target.value)} className="bg-slate-950 border border-slate-800 rounded px-1.5 py-0.5 text-[11px]">
                                <option>In Stock</option><option>Listed</option><option>Grading</option><option>Sold</option><option>PC / Hold</option>
                              </select>
                            </td>
                            <td className="p-1.5">
                              <select value={card.Hold_Tag || 'For Sale'} onChange={(e) => updateInventoryRowInline(card.SKU, 'Hold_Tag', e.target.value)} className="bg-slate-950 border border-slate-800 rounded px-1.5 py-0.5 text-[11px]">
                                <option>For Sale</option><option>Make Me an Offer</option><option>Personal Collection (PC)</option>
                              </select>
                            </td>
                            <td className="p-1.5"><input value={card.Set || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Set', e.target.value)} className="w-40 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5" /></td>
                            <td className="p-1.5"><input value={card.Subset || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Subset', e.target.value)} className="w-32 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-semibold text-white" /></td>
                            <td className="p-1.5"><input value={card['Card Number'] || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Card Number', e.target.value)} className="w-16 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-mono" /></td>
                            <td className="p-1.5"><input value={card.Player || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Player', e.target.value)} className="w-36 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-bold text-white" /></td>
                            <td className="p-1.5"><input value={card.Team || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Team', e.target.value)} className="w-28 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 text-slate-300" /></td>
                            <td className="p-1.5"><input value={card['Print Run'] || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Print Run', e.target.value)} className="w-14 bg-transparent hover:bg-slate-950 border border-transparent focus:border-slate-700 rounded px-1 py-0.5 font-mono text-amber-300" /></td>
                            <td className="p-1.5"><AttributeBadges attributesStr={card.Attributes} glossary={chkData.glossary} /></td>
                            <td className="p-1.5 font-mono text-slate-400">#{card.Copy_Number || '1'}</td>
                            <td className="p-1.5 font-mono text-[11px] text-slate-400">{card.Centering_LR || '—'}</td>
                            <td className="p-1.5 font-mono text-slate-200">{card.Est_PSA || '—'} / {card.Est_BGS || '—'}</td>
                            <td className="p-1.5"><input type="number" step="0.25" value={card.Raw_Price || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Raw_Price', e.target.value)} className="w-16 bg-slate-950 border border-slate-800 rounded px-1 py-0.5 font-mono" /></td>
                            <td className="p-1.5 font-mono text-slate-400">{fmtCurrency(card.Min_Sale_Price)}</td>
                            <td className="p-1.5">
                              <div className="flex items-center gap-1">
                                <input type="number" step="0.25" value={card.Rec_Sale_Price || ''} onChange={(e) => updateInventoryRowInline(card.SKU, 'Rec_Sale_Price', e.target.value)} className="w-16 bg-slate-950 border border-emerald-700/60 rounded px-1 py-0.5 font-mono text-emerald-300 font-bold" />
                                <button onClick={() => updateInventoryRowInline(card.SKU, 'Rec_Sale_Price', computeRecommendedPriceForRow(card))} title="Auto-Assign Recommended Sale Price" className="px-1.5 py-0.5 rounded bg-amber-950 hover:bg-amber-800 text-amber-300 text-[10px]">✨</button>
                              </div>
                            </td>
                            <td className="p-1.5 text-[11px] text-sky-300">{card.Recommended_Action}</td>
                            <td className="p-1.5 font-mono text-[11px]">{String(card.Label_Printed).toLowerCase() === 'true' ? '✅' : 'No'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {(() => {
                  const invTotP = Math.max(1, Math.ceil(filteredInventory.length / invPageSize));
                  const safeInvP = Math.min(invPage, invTotP);
                  return (
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0 px-1">
                      <span>
                        Showing {filteredInventory.length === 0 ? 0 : ((safeInvP - 1) * invPageSize + 1).toLocaleString()}–{Math.min(filteredInventory.length, safeInvP * invPageSize).toLocaleString()} of {filteredInventory.length.toLocaleString()} matching SKU(s)
                      </span>
                      <div className="flex items-center gap-2">
                        <select value={invPageSize} onChange={(e) => { setInvPageSize(parseInt(e.target.value, 10) || 250); setInvPage(1); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                          <option value={100}>100 / page</option><option value={250}>250 / page</option><option value={500}>500 / page</option>
                        </select>
                        <button onClick={() => setInvPage((p) => Math.max(1, Math.min(invTotP, p) - 1))} disabled={safeInvP <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                        <span className="font-mono text-white">Page {safeInvP} / {invTotP}</span>
                        <button onClick={() => setInvPage((p) => Math.min(invTotP, Math.min(invTotP, p) + 1))} disabled={safeInvP >= invTotP} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* 4. INVENTORY EDITOR — INDIVIDUAL (GUIDED REVIEW STYLE), DEEP-DIVE (1-BY-1) & SELECTIVE BULK EDIT */}
            {activePage === 'inventory_editor' && (() => {
              const editorCards = selectedInvSkus
                .map((sk) => inventory.find((x) => x.SKU === sk))
                .filter(Boolean);
              const searchedEdCards = editorCards.filter((c) => {
                if (!invEditorSearchQ.trim()) return true;
                const d = invEditorDrafts[c.SKU] || c;
                return `${c.SKU} ${d.Set} ${d.Subset} ${d['Card Number']} ${d.Player} ${d.Team} ${d.Status} ${d.Hold_Tag} ${d.Source_Batch}`.toLowerCase().includes(invEditorSearchQ.toLowerCase());
              });
              const dirtyEdSkus = Object.keys(invEditorDrafts).filter((sk) => editorCards.some((c) => c.SKU === sk));
              const edTotalPages = Math.max(1, Math.ceil(searchedEdCards.length / invEditorPageSize));
              const edSafePage = Math.min(invEditorPage, edTotalPages);
              const edSlice = searchedEdCards.slice((edSafePage - 1) * invEditorPageSize, edSafePage * invEditorPageSize);
              const safeDdEdIdx = Math.max(0, Math.min(invEditorIdx, Math.max(0, searchedEdCards.length - 1)));
              const ddEdCard = searchedEdCards[safeDdEdIdx] || null;
              if (ddEdCard) activeInvEditorSkuRef.current = String(ddEdCard.SKU || '').trim();
              const anyEditorSkuBusy = selectedInvSkus.some((sk) => Boolean(reprocessingInvSkus[sk]));

              const goInvEditorPage = (nextPg) => {
                setInvEditorPage(Math.max(1, Math.min(edTotalPages, nextPg)));
                if (mainScrollRef.current) mainScrollRef.current.scrollTo({ top: 0, behavior: 'smooth' });
              };

              const saveSingleInvCard = (updatedRow, advanceDeepDive = false) => {
                const nextInv = inventory.map((row) => (row.SKU === updatedRow.SKU ? { ...row, ...updatedRow } : row));
                return persistInventoryToDisk(nextInv, `Saved SKU ${updatedRow.SKU}`).then((ok) => {
                  if (ok) {
                    setInvEditorDrafts((prev) => { const cp = { ...prev }; delete cp[updatedRow.SKU]; return cp; });
                    if (advanceDeepDive) {
                      setInvEditorIdx((i) => Math.min(Math.max(0, searchedEdCards.length - 1), i + 1));
                    }
                  }
                  return ok;
                });
              };

              const saveAllDirtyInvCards = () => {
                if (dirtyEdSkus.length === 0) return;
                const nextInv = inventory.map((row) => (invEditorDrafts[row.SKU] ? { ...row, ...invEditorDrafts[row.SKU] } : row));
                setInvEditorDrafts({});
                persistInventoryToDisk(nextInv, `Saved ${dirtyEdSkus.length} Inventory Card(s)`);
              };

              const bulkCheckedKeys = Object.keys(bulkEditChecks).filter((k) => bulkEditChecks[k]);
              const setBulkField = (k, val) => {
                setBulkEditVals((prev) => ({ ...prev, [k]: val }));
                setBulkEditChecks((prev) => ({ ...prev, [k]: true }));
              };

              return (
                <div className={invEditorMode === 'deep_dive' ? 'flex-1 min-h-0 h-full flex flex-col overflow-hidden' : 'space-y-4'}>
                  {/* TOP CONTROL HEADER WITH MODE SWITCHER + PARALLEL REPROCESS (HIDDEN IN DEEP-DIVE SO ONLY ONE ~44PX BAR IS SHOWN) */}
                  {invEditorMode !== 'deep_dive' && (
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <button onClick={() => setActivePage('inventory')} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold">⬅ Back to Inventory</button>
                          <h2 className="text-sm font-bold text-white">
                            ✏️ Inventory Editor — {editorCards.length.toLocaleString()} Selected SKU(s)
                          </h2>
                          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-0.5 text-xs">
                            <button
                              type="button"
                              onClick={() => setInvEditorMode('individual')}
                              className={`px-2.5 py-1 rounded-lg font-bold transition ${invEditorMode === 'individual' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                            >
                              🪟 Individual
                            </button>
                            <button
                              type="button"
                              onClick={() => setInvEditorMode('deep_dive')}
                              className={`px-2.5 py-1 rounded-lg font-bold transition ${invEditorMode === 'deep_dive' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                            >
                              🔬 Deep-Dive
                            </button>
                            {editorCards.length > 1 && (
                              <button
                                type="button"
                                onClick={() => setInvEditorMode('bulk')}
                                className={`px-2.5 py-1 rounded-lg font-bold transition ${invEditorMode === 'bulk' ? skin.accentActive : 'text-slate-400 hover:text-white'}`}
                              >
                                📋 Bulk Edit
                              </button>
                            )}
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            disabled={editorCards.length === 0 || anyEditorSkuBusy}
                            onClick={() => triggerInventoryReprocess((invEditorMode === 'individual' ? edSlice : editorCards).map((ec) => ec.SKU))}
                            title="Rescan physical images in an available parallel worker and instantly update this page"
                            className="px-3 py-1.5 rounded-xl bg-cyan-950/90 hover:bg-cyan-800 border border-cyan-600/70 text-cyan-200 font-bold text-xs disabled:opacity-45"
                          >
                            {anyEditorSkuBusy
                              ? '⏳ Reprocessing in Worker...'
                              : invEditorMode === 'individual'
                              ? `🔄 Reprocess Page (${edSlice.length})`
                              : `🔄 Reprocess All (${editorCards.length})`}
                          </button>
                          {invEditorMode === 'individual' && dirtyEdSkus.length > 0 && (
                            <button
                              type="button"
                              onClick={saveAllDirtyInvCards}
                              className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow animate-pulse"
                            >
                              💾 Save All Edited ({dirtyEdSkus.length}) &amp; Rename
                            </button>
                          )}
                        </div>
                      </div>

                      {/* FILTER / PAGINATION BAR FOR INDIVIDUAL MODE */}
                      {invEditorMode === 'individual' && editorCards.length > 0 && (
                        <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
                          <input
                            value={invEditorSearchQ}
                            onChange={(e) => { setInvEditorSearchQ(e.target.value); setInvEditorPage(1); }}
                            placeholder="Filter selected cards (SKU, #, Player, Subset, Status)..."
                            className="md:col-span-3 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs"
                          />
                          <select value={invEditorPageSize} onChange={(e) => { setInvEditorPageSize(parseInt(e.target.value, 10) || 15); setInvEditorPage(1); }} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                            <option value={10}>10 cards / page</option><option value={15}>15 cards / page</option><option value={25}>25 cards / page</option><option value={50}>50 cards / page</option>
                          </select>
                          <div className="md:col-span-2 flex items-center justify-end gap-1.5 text-xs">
                            <button onClick={() => goInvEditorPage(edSafePage - 1)} disabled={edSafePage <= 1} className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                            <span className="font-mono text-white">Page {edSafePage} / {edTotalPages}</span>
                            <button onClick={() => goInvEditorPage(edSafePage + 1)} disabled={edSafePage >= edTotalPages} className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {editorCards.length === 0 ? (
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-6 text-center text-xs text-slate-400`}>
                      Select one or more cards from Master Inventory first.
                    </div>
                  ) : invEditorMode === 'individual' ? (
                    <>
                      {edSlice.map((card) => (
                        <InventoryGuidedCardItem
                          key={card.SKU}
                          card={card}
                          draft={invEditorDrafts[card.SKU] || card}
                          skin={skin}
                          dynamicSets={dynamicSetsNewestFirst}
                          externalImgBust={invEditorImgBust}
                          isReprocessingExternal={Boolean(reprocessingInvSkus[card.SKU])}
                          onDraftChange={(nextCard) => setInvEditorDrafts((p) => ({ ...p, [card.SKU]: nextCard }))}
                          onSaveOne={(upd) => saveSingleInvCard(upd, false)}
                          onRotateSide={(sName, fName) => rotateInventoryCardImage(sName, fName)}
                          onReprocessOne={(skuVal, sName) => triggerInventoryReprocess([skuVal], sName)}
                          onReplaceImages={(cObj) => setReplaceImgTarget({
                            type: 'inventory',
                            sku: cObj.SKU,
                            set: cObj.Set,
                            subset: cObj.Subset,
                            cardNumber: cObj['Card Number'],
                            player: cObj.Player,
                          })}
                          onAutoAssignPrice={(rowObj) => computeRecommendedPriceForRow(rowObj)}
                          onOpenDeepDive={(skuVal) => {
                            const idxHit = searchedEdCards.findIndex((x) => x.SKU === skuVal);
                            setInvEditorIdx(idxHit >= 0 ? idxHit : 0);
                            setInvEditorMode('deep_dive');
                          }}
                        />
                      ))}
                      {searchedEdCards.length > 0 && (
                        <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5 flex flex-wrap items-center justify-between gap-2 text-xs`}>
                          <span className="text-slate-400">
                            Showing {((edSafePage - 1) * invEditorPageSize + 1).toLocaleString()}–{Math.min(searchedEdCards.length, edSafePage * invEditorPageSize).toLocaleString()} of {searchedEdCards.length.toLocaleString()} selected SKU(s)
                          </span>
                          <div className="flex flex-wrap items-center gap-2">
                            <button onClick={() => goInvEditorPage(edSafePage - 1)} disabled={edSafePage <= 1} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-bold">◀ Prev Page</button>
                            <span className="font-mono text-white px-2">Page {edSafePage} / {edTotalPages}</span>
                            <button onClick={() => goInvEditorPage(edSafePage + 1)} disabled={edSafePage >= edTotalPages} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-bold">Next Page ▶</button>
                            <button onClick={() => mainScrollRef.current && mainScrollRef.current.scrollTo({ top: 0, behavior: 'smooth' })} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-300 font-semibold">▲ Top</button>
                          </div>
                        </div>
                      )}
                    </>
                  ) : invEditorMode === 'deep_dive' ? (
                    !ddEdCard ? (
                      <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-6 text-center space-y-3 text-xs text-slate-400`}>
                        <div>No cards match the filter.</div>
                        <div className="flex items-center justify-center gap-2">
                          <button type="button" onClick={() => { setInvEditorSearchQ(''); setInvEditorIdx(0); }} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-300 font-bold">Clear Search Filter</button>
                          <button type="button" onClick={() => setInvEditorMode('individual')} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold">🪟 Switch to Individual</button>
                        </div>
                      </div>
                    ) : (
                      <GradingDeepDiveStudio
                        key={`inv-gdd-${ddEdCard.SKU}`}
                        card={ddEdCard}
                        targetType="inventory"
                        cardIndex={safeDdEdIdx}
                        totalCards={searchedEdCards.length}
                        onPrev={() => setInvEditorIdx((i) => Math.max(0, i - 1))}
                        onNext={() => setInvEditorIdx((i) => Math.min(Math.max(0, searchedEdCards.length - 1), i + 1))}
                        onBack={() => setActivePage('inventory')}
                        backLabel="Inventory"
                        onSwitchIndividual={() => setInvEditorMode('individual')}
                        onSwitchBulk={editorCards.length > 1 ? () => setInvEditorMode('bulk') : undefined}
                        cardOptions={searchedEdCards.map((ec, ei) => ({
                          index: ei,
                          label: `${ei + 1}/${searchedEdCards.length} • SKU ${ec.SKU} — #${ec['Card Number']} ${ec.Player}`,
                        }))}
                        onSelectCardIndex={(idx) => setInvEditorIdx(idx)}
                        onCardUpdated={(res) => {
                          if (Array.isArray(res?.rows)) {
                            setInventory(res.rows);
                          } else if (res?.card) {
                            setInventory((prev) => prev.map((row) => (row.SKU === res.card.SKU ? { ...row, ...res.card } : row)));
                          }
                        }}
                        skin={skin}
                        pushNotification={pushNotification}
                      />
                    )
                  ) : (
                    /* SELECTIVE BULK EDIT MODE */
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-5 space-y-4`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <h3 className="text-sm font-bold text-amber-200">📋 Selective Bulk Edit — Applying to {editorCards.length} Selected SKU(s)</h3>
                          <p className="text-[11px] text-slate-400">Check or edit ONLY the fields you want to overwrite across all {editorCards.length} cards (each card keeps its own Card #, Player, and unchecked fields).</p>
                        </div>
                        <button
                          type="button"
                          disabled={bulkCheckedKeys.length === 0}
                          onClick={() => {
                            const patchObj = {};
                            bulkCheckedKeys.forEach((k) => { patchObj[k] = bulkEditVals[k]; });
                            const nextInv = inventory.map((row) => (selectedInvSkus.includes(row.SKU) ? { ...row, ...patchObj } : row));
                            persistInventoryToDisk(nextInv, `Bulk Updated ${bulkCheckedKeys.length} Field(s) Across ${selectedInvSkus.length} SKUs`);
                            setBulkEditChecks({});
                          }}
                          className={`px-4 py-2 rounded-xl font-bold text-xs disabled:opacity-40 ${skin.accentBtn}`}
                        >
                          💾 Apply {bulkCheckedKeys.length} Checked Field(s) to All {editorCards.length} SKUs
                        </button>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                        {[
                          { key: 'Set', label: 'Set', type: 'set' },
                          { key: 'Subset', label: 'Subset / Parallel', type: 'text' },
                          { key: 'Team', label: 'Team', type: 'text' },
                          { key: 'Print Run', label: 'Print Run', type: 'text' },
                          { key: 'Attributes', label: 'Attributes', type: 'text' },
                          { key: 'Status', label: 'Status', type: 'select', options: ['In Stock', 'Listed', 'Grading', 'Sold', 'PC / Hold'] },
                          { key: 'Hold_Tag', label: 'Hold Tag', type: 'select', options: ['For Sale', 'Make Me an Offer', 'Personal Collection (PC)'] },
                          { key: 'Raw_Price', label: 'Raw Price ($)', type: 'number' },
                          { key: 'Rec_Sale_Price', label: 'Sale Price ($)', type: 'number' },
                          { key: 'Label_Printed', label: 'Label Printed', type: 'select', options: ['False', 'True'] },
                          { key: 'Needs_Review', label: 'Needs Review', type: 'select', options: ['False', 'True'] },
                          { key: 'Grading_Notes', label: 'Grading Notes', type: 'text' },
                        ].map((fld) => {
                          const isChk = !!bulkEditChecks[fld.key];
                          return (
                            <div key={fld.key} className={`p-2.5 rounded-xl border transition ${isChk ? 'bg-amber-950/25 border-amber-500/60' : 'bg-slate-950/80 border-slate-800'}`}>
                              <label className="flex items-center gap-1.5 text-[11px] font-bold text-slate-200 mb-1 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={isChk}
                                  onChange={(e) => setBulkEditChecks((prev) => ({ ...prev, [fld.key]: e.target.checked }))}
                                />
                                <span>{fld.label}</span>
                              </label>
                              {fld.type === 'select' ? (
                                <select value={bulkEditVals[fld.key] ?? ''} onChange={(e) => setBulkField(fld.key, e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs">
                                  {fld.options.map((o) => <option key={o} value={o}>{o}</option>)}
                                </select>
                              ) : fld.type === 'set' ? (
                                <>
                                  <input list="bulk-sets-list" value={bulkEditVals.Set ?? ''} onChange={(e) => setBulkField('Set', e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" />
                                  <datalist id="bulk-sets-list">{dynamicSetsNewestFirst.map((s) => <option key={s} value={s} />)}</datalist>
                                </>
                              ) : (
                                <input type={fld.type} step={fld.type === 'number' ? '0.25' : undefined} value={bulkEditVals[fld.key] ?? ''} onChange={(e) => setBulkField(fld.key, e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" />
                              )}
                            </div>
                          );
                        })}
                      </div>

                      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-2">
                        <div className="text-[11px] font-bold text-slate-300">Selected Cards ({editorCards.length})</div>
                        <div className="max-h-56 overflow-auto">
                          <table className="w-full text-left text-[11px] whitespace-nowrap">
                            <thead className="text-slate-400 border-b border-slate-800 sticky top-0 bg-slate-950">
                              <tr><th className="p-1.5">SKU</th><th className="p-1.5">Set</th><th className="p-1.5">Subset</th><th className="p-1.5">Card #</th><th className="p-1.5">Player</th><th className="p-1.5">Status</th><th className="p-1.5">Hold Tag</th><th className="p-1.5">Raw / Sale</th></tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/70">
                              {editorCards.slice(0, 200).map((ec) => (
                                <tr key={ec.SKU}>
                                  <td className="p-1.5 font-mono text-sky-400 font-bold">{ec.SKU}</td>
                                  <td className="p-1.5">{ec.Set}</td>
                                  <td className="p-1.5 text-amber-200">{ec.Subset}</td>
                                  <td className="p-1.5 font-mono">#{ec['Card Number']}</td>
                                  <td className="p-1.5 font-bold text-white">{ec.Player}</td>
                                  <td className="p-1.5">{ec.Status}</td>
                                  <td className="p-1.5">{ec.Hold_Tag}</td>
                                  <td className="p-1.5 font-mono">${ec.Raw_Price} / <span className="text-emerald-400">${ec.Rec_Sale_Price}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* 4B. CARD-LEVEL INVENTORY (RESTORED — SET PRICES & PC RETAIN QTY AT CARD LEVEL) */}
            {activePage === 'card_level_inventory' && (() => {
              const mergedCl = cardLevelRows.map((r) => (cardLevelEdits[r.Card_Key] ? { ...r, ...cardLevelEdits[r.Card_Key] } : r));
              const dirtyClKeys = Object.keys(cardLevelEdits);
              const clSets = Array.from(new Set(mergedCl.map((r) => r.Set).filter(Boolean))).sort();

              const filteredCl = mergedCl.filter((r) => {
                if (clSetF !== 'All Sets' && r.Set !== clSetF) return false;
                if (clSurplusOnly && safeNum(r.Surplus_Sellable_Qty, 0) <= 0 && safeNum(r.Total_Copies, 0) < 2) return false;
                if (clSearch.trim()) {
                  const q = clSearch.toLowerCase();
                  if (!`${r.Set} ${r.Subset} ${r['Card Number']} ${r.Player} ${r.Team} ${r.Attributes}`.toLowerCase().includes(q)) return false;
                }
                return true;
              });

              const totClPages = Math.max(1, Math.ceil(filteredCl.length / clPageSize));
              const safeClPage = Math.min(clPage, totClPages);
              const sliceCl = filteredCl.slice((safeClPage - 1) * clPageSize, safeClPage * clPageSize);

              const totPhysicalCopies = mergedCl.reduce((a, r) => a + safeNum(r.Total_Copies, 0), 0);
              const totPcRetained = mergedCl.reduce((a, r) => a + safeNum(r.PC_Retained_Qty, 0), 0);
              const totSurplus = mergedCl.reduce((a, r) => a + safeNum(r.Surplus_Sellable_Qty, 0), 0);
              const totSellVal = mergedCl.reduce((a, r) => a + safeNum(r.Total_Sellable_Value, 0), 0);

              const updateClInline = (cardKey, field, val) => {
                const baseR = cardLevelRows.find((x) => x.Card_Key === cardKey) || {};
                setCardLevelEdits((prev) => ({
                  ...prev,
                  [cardKey]: { ...baseR, ...(prev[cardKey] || {}), [field]: val },
                }));
              };

              const commitCardLevelUpdates = (reallocate = false) => {
                const updates = dirtyClKeys.map((ck) => cardLevelEdits[ck]);
                fetch(`${NODE_API_BASE}/inventory/card-level/update`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ updates, reallocateHoldTags: reallocate }),
                })
                  .then((r) => r.json())
                  .then((res) => {
                    if (res?.success) {
                      if (Array.isArray(res.cardLevelRows)) setCardLevelRows(res.cardLevelRows);
                      if (Array.isArray(res.inventoryRows)) setInventory(res.inventoryRows);
                      setCardLevelEdits({});
                      pushNotification(
                        reallocate ? 'Card-Level Saved & Allocated' : 'Card-Level Prices Saved',
                        `Updated ${res.updatedCards || updates.length} unique card(s) across ${res.updatedSkus || 0} physical SKU(s).`,
                        'Inventory',
                        'success'
                      );
                    }
                  })
                  .catch((e) => pushNotification('Card-Level Save Error', e.message, 'Inventory', 'error'));
              };

              return (
                <div className="flex-1 flex flex-col gap-3 min-h-0">
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 shrink-0">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Unique Card Designs</div><div className="text-lg font-bold text-white">{mergedCl.length.toLocaleString()}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">In-Stock Copies</div><div className="text-lg font-bold text-sky-300">{totPhysicalCopies.toLocaleString()}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">PC Retained Copies</div><div className="text-lg font-bold text-amber-300">{totPcRetained.toLocaleString()}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Surplus For-Sale Qty</div><div className="text-lg font-bold text-emerald-300">{totSurplus.toLocaleString()}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Total Sellable Value</div><div className="text-lg font-bold text-emerald-400">{fmtCurrency(totSellVal)}</div></div>
                  </div>

                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5 space-y-2.5 shrink-0`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h2 className="text-sm font-bold text-white">🃏 Card-Level Inventory ({filteredCl.length.toLocaleString()} Unique Designs)</h2>
                        <p className="text-[11px] text-slate-400">Set Raw Price, Sale Price, and PC Retain Qty once per unique card — updates propagate cleanly across all physical copies in Inventory.csv.</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {dirtyClKeys.length > 0 && (
                          <button onClick={() => commitCardLevelUpdates(false)} className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs animate-pulse">
                            💾 Save Edits ({dirtyClKeys.length} Card{dirtyClKeys.length === 1 ? '' : 's'})
                          </button>
                        )}
                        <button onClick={() => commitCardLevelUpdates(true)} className={`px-3 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}>
                          ⚡ {dirtyClKeys.length > 0 ? 'Save & ' : ''}Auto-Allocate PC (Best Grade) vs. For Sale
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                      <select value={clSetF} onChange={(e) => setClSetF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                        <option>All Sets</option>
                        {sortSetsNewestFirst(clSets).map((s) => <option key={s}>{s}</option>)}
                      </select>
                      <input value={clSearch} onChange={(e) => setClSearch(e.target.value)} placeholder="Search Player, Card #, Subset, Team..." className="md:col-span-2 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                      <label className="flex items-center gap-1.5 text-xs text-slate-300 px-2 cursor-pointer">
                        <input type="checkbox" checked={clSurplusOnly} onChange={(e) => setClSurplusOnly(e.target.checked)} />
                        Duplicates / Surplus Only
                      </label>
                      <button onClick={() => { setClSetF('All Sets'); setClSurplusOnly(false); setClSearch(''); }} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">
                        🧹 Clear Filters
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-2xl bg-slate-900/60">
                    <table className="w-full text-left text-xs whitespace-nowrap">
                      <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                        <tr>
                          <th className="p-2">Set</th><th className="p-2">Subset</th><th className="p-2">Card #</th><th className="p-2">Player</th><th className="p-2">Team</th><th className="p-2">Copies</th><th className="p-2">PC Retain Qty</th><th className="p-2">PC / Sale</th><th className="p-2">Surplus</th><th className="p-2">Best PSA / BGS</th><th className="p-2">Raw ($)</th><th className="p-2">Sale Price ($)</th><th className="p-2">Sellable Value</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/70">
                        {sliceCl.map((r) => {
                          const isDirty = Boolean(cardLevelEdits[r.Card_Key]);
                          return (
                            <tr key={r.Card_Key} className={isDirty ? 'bg-amber-950/30' : 'hover:bg-slate-800/40'}>
                              <td className="p-1.5">{r.Set}</td>
                              <td className="p-1.5 font-semibold text-white">{r.Subset}</td>
                              <td className="p-1.5 font-mono">#{r['Card Number']}</td>
                              <td className="p-1.5 font-bold text-white">{r.Player}</td>
                              <td className="p-1.5 text-slate-300">{r.Team}</td>
                              <td className="p-1.5 font-mono font-bold text-sky-300">{r.Total_Copies}</td>
                              <td className="p-1.5">
                                <input
                                  type="number" min="0" max="99"
                                  value={r.Target_Retain_Qty ?? 1}
                                  onChange={(e) => updateClInline(r.Card_Key, 'Target_Retain_Qty', Math.max(0, parseInt(e.target.value, 10) || 0))}
                                  className="w-16 bg-slate-950 border border-slate-700 rounded px-1.5 py-0.5 font-mono text-amber-300"
                                />
                              </td>
                              <td className="p-1.5 font-mono text-[11px] text-slate-300">{r.PC_Retained_Qty} PC / {r.For_Sale_Qty} Sale</td>
                              <td className="p-1.5 font-mono font-bold text-emerald-400">{r.Surplus_Sellable_Qty}</td>
                              <td className="p-1.5 font-mono text-slate-200">{r.Best_PSA || '—'} / {r.Best_BGS || '—'}</td>
                              <td className="p-1.5">
                                <input
                                  type="number" step="0.25"
                                  value={r.Unit_Raw_Price ?? ''}
                                  onChange={(e) => updateClInline(r.Card_Key, 'Unit_Raw_Price', e.target.value)}
                                  className="w-20 bg-slate-950 border border-slate-700 rounded px-1.5 py-0.5 font-mono"
                                />
                              </td>
                              <td className="p-1.5">
                                <input
                                  type="number" step="0.25"
                                  value={r.Unit_Rec_Sale_Price ?? ''}
                                  onChange={(e) => updateClInline(r.Card_Key, 'Unit_Rec_Sale_Price', e.target.value)}
                                  className="w-20 bg-slate-950 border border-emerald-700/70 rounded px-1.5 py-0.5 font-mono text-emerald-300 font-bold"
                                />
                              </td>
                              <td className="p-1.5 font-mono text-emerald-400 font-bold">{fmtCurrency(r.Total_Sellable_Value)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0 px-1">
                    <span>Showing {filteredCl.length === 0 ? 0 : ((safeClPage - 1) * clPageSize + 1).toLocaleString()}–{Math.min(filteredCl.length, safeClPage * clPageSize).toLocaleString()} of {filteredCl.length.toLocaleString()} unique cards</span>
                    <div className="flex items-center gap-2">
                      <select value={clPageSize} onChange={(e) => { setClPageSize(parseInt(e.target.value, 10) || 250); setClPage(1); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                        <option value={100}>100 / page</option><option value={250}>250 / page</option><option value={500}>500 / page</option>
                      </select>
                      <button onClick={() => setClPage((p) => Math.max(1, p - 1))} disabled={safeClPage <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                      <span className="font-mono text-white">Page {safeClPage} / {totClPages}</span>
                      <button onClick={() => setClPage((p) => Math.min(totClPages, p + 1))} disabled={safeClPage >= totClPages} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 5. LABEL HUB (INTAKE BATCH PRINTING, GEAR OFFSETS, PREFILLED TRUE-ASPECT EDITOR, ADDITIVE REPRINTS & LIVE BATCH LIST) */}
            {activePage === 'label_hub' && (() => {
              const tpl = LABEL_TEMPLATES[labelTemplate] || LABEL_TEMPLATES.R037L;
              const cellsPerPage = tpl.rows * tpl.cols;
              const invBySku = new Map(inventory.map((c) => [String(c.SKU || '').trim(), c]));

              // Build Intake Batch summary from Inventory.Source_Batch
              const batchStatsMap = {};
              inventory.forEach((c) => {
                const bn = String(c.Source_Batch || 'Unspecified Batch').trim() || 'Unspecified Batch';
                if (!batchStatsMap[bn]) batchStatsMap[bn] = { total: 0, unprinted: 0 };
                batchStatsMap[bn].total += 1;
                if (String(c.Label_Printed).toLowerCase() !== 'true') batchStatsMap[bn].unprinted += 1;
              });
              const intakeBatchNames = Object.keys(batchStatsMap).sort((a, b) => {
                const diffUnp = (batchStatsMap[b]?.unprinted || 0) - (batchStatsMap[a]?.unprinted || 0);
                return diffUnp !== 0 ? diffUnp : b.localeCompare(a);
              });

              const scopedInventory = labelIntakeBatch === 'All Intake Batches'
                ? inventory
                : inventory.filter((c) => (String(c.Source_Batch || 'Unspecified Batch').trim() || 'Unspecified Batch') === labelIntakeBatch);
              const unprintedPool = scopedInventory.filter((c) => String(c.Label_Printed).toLowerCase() !== 'true');
              const stagedSet = new Set(stagedReprintSkus);

              // Resolve live print queue in exact order
              let queuedCards = unprintedPool;
              if (reprintMode === 'intake_batch_all') {
                queuedCards = scopedInventory;
              } else if (reprintMode === 'reprint_only') {
                queuedCards = stagedReprintSkus.map((s) => invBySku.get(s)).filter(Boolean);
              } else if (reprintMode === 'append_reprints') {
                const seenQ = new Set(unprintedPool.map((c) => String(c.SKU).trim()));
                const extras = stagedReprintSkus.filter((s) => !seenQ.has(s)).map((s) => invBySku.get(s)).filter(Boolean);
                queuedCards = [...unprintedPool, ...extras];
              }

              const queuedSkuList = queuedCards.map((c) => String(c.SKU).trim()).filter(Boolean);

              const handleAddReprintSkus = () => {
                const expanded = expandSkuRangeTokens(reprintSkuInput);
                if (expanded.length === 0) return;
                const matched = expanded.filter((s) => invBySku.has(s));
                const missingCnt = expanded.length - matched.length;
                if (matched.length === 0) {
                  pushNotification('No Matching SKUs Found', `None of the entered SKU(s) matched Inventory.csv.`, 'Labels', 'warning');
                  return;
                }
                setStagedReprintSkus((prev) => Array.from(new Set([...prev, ...matched])));
                setReprintSkuInput('');
                const firstAdded = invBySku.get(matched[0]);
                if (firstAdded) prefillSampleLabelFromCard(firstAdded);
                pushNotification(
                  `Added ${matched.length} Label(s) to Print Batch`,
                  missingCnt > 0 ? `${matched.length} valid SKU(s) added (${missingCnt} not found in Inventory).` : `Queued ${matched.length} SKU(s) for printing.`,
                  'Labels',
                  'success'
                );
              };

              const handleMarkSkusPrinted = (skusToMark, labelDesc = '') => {
                const cleanSkus = Array.from(new Set((skusToMark || []).map((s) => String(s).trim()).filter(Boolean)));
                if (cleanSkus.length === 0) return;
                fetch(`${NODE_API_BASE}/labels/mark-printed`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ skus: cleanSkus }),
                })
                  .then((r) => r.json())
                  .then((res) => {
                    if (res?.success) {
                      if (Array.isArray(res.rows)) setInventory(res.rows);
                      const markedSet = new Set(cleanSkus);
                      setStagedReprintSkus((prev) => prev.filter((s) => !markedSet.has(s)));
                      pushNotification(
                        'Labels Marked Printed',
                        `Marked ${res.markedCount || cleanSkus.length} SKU(s)${labelDesc ? ` (${labelDesc})` : ''} as Label_Printed = True.`,
                        'Labels',
                        'success'
                      );
                    }
                  })
                  .catch((e) => pushNotification('Mark Printed Error', e.message, 'Labels', 'error'));
              };

              const getValidSkipsForPage = (pgNum) => {
                const mapP = peeledCellsByPage[pgNum] || {};
                return Object.entries(mapP)
                  .filter(([k, v]) => {
                    if (!v) return false;
                    const [rr, cc] = k.split('-').map(Number);
                    return rr >= 1 && rr <= tpl.rows && cc >= 1 && cc <= tpl.cols;
                  })
                  .map(([k]) => k.split('-').map(Number));
              };

              const buildUsedCellsByPagePayload = () => {
                const payloadMap = {};
                Object.keys(peeledCellsByPage).forEach((pgK) => {
                  const arr = getValidSkipsForPage(Number(pgK));
                  if (arr.length > 0) payloadMap[String(pgK)] = arr;
                });
                return payloadMap;
              };

              // Compute exact per-page card offsets across Page 1, 2, 3...
              const pageStarts = { 1: 0 };
              const pageCounts = { 1: 0 };
              let remCards = queuedCards.length;
              let estPages = 0;
              let cursorAcc = 0;
              while (remCards > 0 && estPages < 60) {
                estPages += 1;
                pageStarts[estPages] = cursorAcc;
                const availOnPg = Math.max(0, cellsPerPage - getValidSkipsForPage(estPages).length);
                const placed = Math.min(remCards, availOnPg);
                pageCounts[estPages] = placed;
                cursorAcc += placed;
                remCards -= placed;
              }
              const maxNavPage = Math.max(1, estPages, ...Object.keys(peeledCellsByPage).map((k) => Number(k) || 1));
              const safePreviewPage = Math.max(1, Math.min(labelPreviewPage, maxNavPage));
              const activePageMap = peeledCellsByPage[safePreviewPage] || {};
              const activePageSkipsCount = getValidSkipsForPage(safePreviewPage).length;
              const totalSkipsAllPages = Object.keys(peeledCellsByPage).reduce((acc, k) => acc + getValidSkipsForPage(Number(k)).length, 0);
              const activePageStartIdx = pageStarts[safePreviewPage] ?? queuedCards.length;
              const activePageCards = queuedCards.slice(activePageStartIdx, activePageStartIdx + (pageCounts[safePreviewPage] || 0));
              const activePageSkus = activePageCards.map((c) => String(c.SKU).trim());

              const toggleCellOnPage = (pgNum, r, c) => {
                const cellKey = `${r}-${c}`;
                setPeeledCellsByPage((prev) => ({
                  ...prev,
                  [pgNum]: { ...(prev[pgNum] || {}), [cellKey]: !prev[pgNum]?.[cellKey] },
                }));
              };

              // Sample Label Editor inventory matching & dirty check
              const matchedSampleInv = invBySku.get(String(sampleLabel.SKU || '').trim()) || null;
              const sampleHasInvEdits = Boolean(
                matchedSampleInv && (
                  String(sampleLabel.Set || '').trim() !== String(matchedSampleInv.Set || '').trim() ||
                  String(sampleLabel.CardNumber || '').replace(/^#/, '').trim() !== String(matchedSampleInv['Card Number'] || '').replace(/^#/, '').trim() ||
                  String(sampleLabel.Player || '').trim() !== String(matchedSampleInv.Player || '').trim() ||
                  String(sampleLabel.Team || '').trim() !== String(matchedSampleInv.Team || '').trim() ||
                  String(sampleLabel.Subset || 'Base').trim() !== String(matchedSampleInv.Subset || 'Base').trim() ||
                  String(sampleLabel.PrintRun || '').replace(/[^0-9]/g, '') !== String(matchedSampleInv['Print Run'] || '').replace(/[^0-9]/g, '')
                )
              );
              const sampleStyle = getLabelSubsetBadgeStyle(sampleLabel.Subset);
              const shortSampleSet = String(sampleLabel.Set || '').replace(/\b(Baseball|Football|Basketball|Hockey|Soccer)\b/gi, '').trim();

              const filteredQueueList = queuedCards.filter((c) => {
                if (!labelQueueSearch.trim()) return true;
                const q = labelQueueSearch.toLowerCase();
                return `${c.SKU} ${c.Set} ${c.Subset} ${c['Card Number']} ${c.Player} ${c.Team} ${c.Source_Batch}`.toLowerCase().includes(q);
              });

              let cardCursor = activePageStartIdx;

              return (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
                  {/* LEFT COLUMN: TEMPLATE + GEAR OFFSETS, INTAKE BATCH / REPRINT MODE, TRUE-ASPECT EDITOR + BUTTONS, LIVE QUEUE LIST */}
                  <div className={`lg:col-span-5 ${skin.cardBg} border ${skin.border} rounded-2xl p-4 flex flex-col gap-3 min-h-0 overflow-y-auto`}>
                    <div className="flex items-center justify-between gap-2 shrink-0">
                      <h2 className="text-sm font-bold text-white">🏷️ Label Hub</h2>
                      <span className="text-[10.5px] font-mono text-slate-400">
                        {tpl.widthIn}" × {tpl.heightIn}" • {cellsPerPage}/sheet
                      </span>
                    </div>

                    {/* 1. STICKER SHEET TEMPLATE + GEAR ICON FOR HIDDEN X/Y OFFSETS */}
                    <div className="space-y-1.5 shrink-0">
                      <label className="block text-[11px] text-slate-400">Sticker Sheet Template</label>
                      <div className="flex items-center gap-1.5">
                        <select
                          value={labelTemplate}
                          onChange={(e) => { setLabelTemplate(e.target.value); setPeeledCellsByPage({ 1: {} }); setLabelPreviewPage(1); }}
                          className="flex-1 min-w-0 bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs"
                        >
                          {Object.entries(LABEL_TEMPLATES).map(([k, v]) => <option key={k} value={k}>{k} — {v.name}</option>)}
                        </select>
                        <button
                          type="button"
                          onClick={() => setShowLabelSettingsGear((v) => !v)}
                          title="Printer X/Y Offset Calibration & Cell Outline Settings"
                          className={`px-2.5 py-1.5 rounded-xl border text-xs font-bold shrink-0 transition flex items-center gap-1 ${
                            showLabelSettingsGear || labelXOff !== 0 || labelYOff !== 0
                              ? skin.accentActive
                              : 'bg-slate-950 hover:bg-slate-800 border-slate-700 text-slate-300'
                          }`}
                        >
                          <span>⚙️</span>
                          {(labelXOff !== 0 || labelYOff !== 0) && (
                            <span className="font-mono text-[10px]">({labelXOff},{labelYOff})</span>
                          )}
                        </button>
                      </div>
                      {showLabelSettingsGear && (
                        <div className="p-2.5 bg-slate-950/90 border border-cyan-500/35 rounded-xl space-y-2 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-cyan-300">⚙️ Printer Offset Calibration</span>
                            <button
                              type="button"
                              onClick={() => { setLabelXOff(0.0); setLabelYOff(0.0); setLabelDrawOutlines(false); }}
                              className="text-[10px] text-slate-400 hover:text-white underline"
                            >
                              Reset 0.0
                            </button>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <div><label className="block text-[10px] text-slate-400 mb-0.5">X Offset (mm)</label><input type="number" step="0.2" value={labelXOff} onChange={(e) => setLabelXOff(parseFloat(e.target.value) || 0)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
                            <div><label className="block text-[10px] text-slate-400 mb-0.5">Y Offset (mm)</label><input type="number" step="0.2" value={labelYOff} onChange={(e) => setLabelYOff(parseFloat(e.target.value) || 0)} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs font-mono" /></div>
                          </div>
                          <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                            <input type="checkbox" checked={labelDrawOutlines} onChange={(e) => setLabelDrawOutlines(e.target.checked)} />
                            Draw faint sticker cell outlines on production PDF
                          </label>
                        </div>
                      )}
                    </div>

                    {/* 2. INTAKE BATCH + BATCH/REPRINT MODE + ADDITIVE REPRINT INPUT */}
                    <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2 shrink-0">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div>
                          <label className="block text-[10.5px] font-bold text-emerald-300 mb-1">📂 Intake Batch Filter</label>
                          <select
                            value={labelIntakeBatch}
                            onChange={(e) => { setLabelIntakeBatch(e.target.value); setLabelPreviewPage(1); }}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
                          >
                            <option value="All Intake Batches">All Intake Batches ({inventory.filter((c) => String(c.Label_Printed).toLowerCase() !== 'true').length} unprinted)</option>
                            {intakeBatchNames.map((bn) => (
                              <option key={bn} value={bn}>
                                {bn} ({batchStatsMap[bn].unprinted} unp / {batchStatsMap[bn].total})
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10.5px] font-bold text-sky-300 mb-1">📋 Batch / Reprint Mode</label>
                          <select
                            value={reprintMode}
                            onChange={(e) => { setReprintMode(e.target.value); setLabelPreviewPage(1); }}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
                          >
                            <option value="unprinted_only">Unprinted Labels Only ({unprintedPool.length})</option>
                            <option value="intake_batch_all">All Labels in Selected Batch ({scopedInventory.length})</option>
                            <option value="append_reprints">Append Specific Labels to Unprinted ({unprintedPool.length} + {stagedReprintSkus.length})</option>
                            <option value="reprint_only">Reprint Specific Labels Only ({stagedReprintSkus.length})</option>
                          </select>
                        </div>
                      </div>

                      {(reprintMode === 'append_reprints' || reprintMode === 'reprint_only') && (
                        <div className="space-y-1.5 pt-1">
                          <div className="flex items-center gap-1.5">
                            <input
                              value={reprintSkuInput}
                              onChange={(e) => setReprintSkuInput(e.target.value)}
                              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddReprintSkus(); } }}
                              placeholder="Enter SKU(s) or ranges (e.g. 1000001, 1000010-1000020)"
                              className="flex-1 min-w-0 bg-slate-900 border border-sky-700/70 rounded-lg px-2.5 py-1.5 text-xs font-mono"
                            />
                            <button
                              type="button"
                              onClick={handleAddReprintSkus}
                              className={`px-3 py-1.5 rounded-lg font-bold text-xs shrink-0 ${skin.accentBtn}`}
                            >
                              ➕ Add
                            </button>
                          </div>
                          {stagedReprintSkus.length > 0 && (
                            <div className="flex items-center justify-between text-[10.5px] text-slate-400">
                              <span>Added Reprint SKUs: <span className="font-mono text-sky-300 font-bold">{stagedReprintSkus.length}</span></span>
                              <button
                                type="button"
                                onClick={() => setStagedReprintSkus([])}
                                className="text-rose-400 hover:text-rose-200 font-semibold"
                              >
                                Clear Added ({stagedReprintSkus.length})
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* 3. INTERACTIVE LABEL EDITOR & TRUE-ASPECT PREVIEW + PDF ACTION BUTTONS NEXT TO SAMPLE */}
                    <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2.5 shrink-0">
                      <div className="flex flex-wrap items-center justify-between gap-1.5">
                        <span className="text-[11px] font-bold text-amber-300">
                          🧪 Interactive Label Editor {matchedSampleInv ? `(Inventory SKU ${matchedSampleInv.SKU})` : '(Custom Sample)'}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {sampleHasInvEdits && (
                            <button
                              type="button"
                              onClick={() => {
                                const nextInv = inventory.map((r) =>
                                  String(r.SKU).trim() === String(matchedSampleInv.SKU).trim()
                                    ? {
                                        ...r,
                                        Set: sampleLabel.Set,
                                        'Card Number': String(sampleLabel.CardNumber || '').replace(/^#/, ''),
                                        Player: sampleLabel.Player,
                                        Team: sampleLabel.Team,
                                        Subset: sampleLabel.Subset || 'Base',
                                        'Print Run': sampleLabel.PrintRun,
                                        Label_Printed: 'False',
                                      }
                                    : r
                                );
                                persistInventoryToDisk(nextInv, `Updated SKU ${matchedSampleInv.SKU} from Label Editor`);
                              }}
                              title="Save these edits back to Inventory.csv (also renames _Cards files & flags Label_Printed = False)"
                              className="px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold animate-pulse"
                            >
                              💾 Save to Inventory
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              fetch(`${NODE_API_BASE}/labels/generate`, {
                                method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ mode: 'sample', templateKey: labelTemplate, xOffsetMm: labelXOff, yOffsetMm: labelYOff, usedCellsPage1: getValidSkipsForPage(1), sampleCard: { SKU: sampleLabel.SKU, Set: sampleLabel.Set, 'Card Number': sampleLabel.CardNumber, Player: sampleLabel.Player, Team: sampleLabel.Team, Subset: sampleLabel.Subset, 'Print Run': sampleLabel.PrintRun } }),
                              }).then((r) => r.json()).then((res) => { if (res.success) { setLastLabelPdf(res); pushNotification('Sample Label PDF Ready', `Rendered ${res.pdfName}`, 'Labels', 'success'); } });
                            }}
                            className="px-2 py-0.5 rounded bg-amber-950 hover:bg-amber-800 text-amber-200 border border-amber-700 text-[10px] font-bold"
                          >
                            1-Label Test PDF
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                        <input
                          value={sampleLabel.SKU}
                          onChange={(e) => {
                            const val = e.target.value;
                            const hit = invBySku.get(val.trim());
                            if (hit) prefillSampleLabelFromCard(hit);
                            else setSampleLabel({ ...sampleLabel, SKU: val });
                          }}
                          placeholder="SKU (Auto-Prefills)"
                          title="Type any Inventory SKU to auto-prefill all fields"
                          className="bg-slate-900 border border-sky-700/70 rounded px-2 py-1 font-mono"
                        />
                        <input value={sampleLabel.CardNumber} onChange={(e) => setSampleLabel({ ...sampleLabel, CardNumber: e.target.value })} placeholder="Card #" className="bg-slate-900 border border-slate-700 rounded px-2 py-1 font-mono" />
                        <input value={sampleLabel.Set} onChange={(e) => setSampleLabel({ ...sampleLabel, Set: e.target.value, League: inferLeagueCodeFromSet(e.target.value) })} placeholder="Set" className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
                        <input value={sampleLabel.Player} onChange={(e) => setSampleLabel({ ...sampleLabel, Player: e.target.value })} placeholder="Player" className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
                        <input value={sampleLabel.Team} onChange={(e) => setSampleLabel({ ...sampleLabel, Team: e.target.value })} placeholder="Team" className="bg-slate-900 border border-slate-700 rounded px-2 py-1" />
                        <div className="flex gap-1">
                          <input value={sampleLabel.Subset} onChange={(e) => setSampleLabel({ ...sampleLabel, Subset: e.target.value })} placeholder="Subset" className="flex-1 min-w-0 bg-slate-900 border border-slate-700 rounded px-2 py-1" />
                          <input value={sampleLabel.PrintRun} onChange={(e) => setSampleLabel({ ...sampleLabel, PrintRun: e.target.value })} placeholder="#/" className="w-12 bg-slate-900 border border-slate-700 rounded px-1.5 py-1 font-mono" />
                        </div>
                      </div>

                      {/* TRUE-ASPECT-RATIO LABEL SAMPLE + ALIGNMENT & GENERATE PDF BUTTONS SIDE-BY-SIDE */}
                      <div className="flex flex-wrap sm:flex-nowrap items-center gap-2.5 pt-0.5">
                        <div className="flex flex-col items-start shrink-0">
                          <div
                            style={{ aspectRatio: tpl.aspectRatio, height: '76px' }}
                            className={`bg-white text-slate-900 rounded-md px-2 py-1.5 flex items-center gap-2 shadow-md overflow-hidden ${sampleStyle.borderCls}`}
                          >
                            <div className="flex flex-col items-center justify-center pr-1.5 border-r border-slate-300 shrink-0 h-full">
                              <div className="w-8 h-8 bg-slate-900 text-white text-[7px] font-mono flex items-center justify-center rounded-[2px]">QR</div>
                              <div className="text-[7.5px] font-extrabold mt-0.5 font-mono leading-none whitespace-nowrap">
                                {sampleLabel.SKU} <span className="text-blue-800">{sampleLabel.League}</span>
                              </div>
                            </div>
                            <div className="flex-1 min-w-0 leading-[1.15]">
                              <div className="text-[8.5px] font-bold text-slate-700 truncate">{shortSampleSet || sampleLabel.Set} • #{sampleLabel.CardNumber}</div>
                              <div className="text-[10.5px] font-extrabold text-black truncate">{sampleLabel.Player || 'Player Name'}</div>
                              <div className="text-[8px] text-slate-600 truncate">{sampleLabel.Team}</div>
                              <div className="mt-0.5 flex items-center gap-1 overflow-hidden">
                                <span className={`text-[8px] font-bold px-1 rounded truncate ${sampleStyle.pillCls}`}>{sampleLabel.Subset || 'Base'}</span>
                                {sampleLabel.PrintRun && (
                                  <span className="text-[8px] font-bold px-1 rounded bg-rose-700 text-white shrink-0">
                                    {sampleLabel.PrintRun === '1' ? '1/1' : `#/${sampleLabel.PrintRun}`}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="text-[9.5px] font-mono text-slate-500 mt-1">
                            True {tpl.widthIn}" × {tpl.heightIn}" ratio ({labelTemplate})
                          </div>
                        </div>

                        <div className="flex-1 min-w-[140px] flex flex-col gap-1.5">
                          <button
                            type="button"
                            disabled={queuedSkuList.length === 0}
                            onClick={() => {
                              fetch(`${NODE_API_BASE}/labels/generate`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                  mode: 'production',
                                  templateKey: labelTemplate,
                                  xOffsetMm: labelXOff,
                                  yOffsetMm: labelYOff,
                                  drawOutlines: labelDrawOutlines,
                                  usedCellsPage1: getValidSkipsForPage(1),
                                  usedCellsByPage: buildUsedCellsByPagePayload(),
                                  sourceBatch: labelIntakeBatch,
                                  reprintMode,
                                  reprintSkus: stagedReprintSkus,
                                  exactSkus: queuedSkuList,
                                }),
                              }).then((r) => r.json()).then((res) => {
                                if (res.success) {
                                  setLastLabelPdf(res);
                                  pushNotification('Labels PDF Generated', `Rendered ${res.cardsPrinted} label(s) across ${res.pagesRendered} page(s).`, 'Labels', 'success');
                                }
                              });
                            }}
                            className={`w-full py-2 px-2.5 rounded-xl font-bold text-xs disabled:opacity-40 ${skin.accentBtn}`}
                          >
                            🖨️ Generate PDF ({queuedSkuList.length} • {estPages || 0} pg)
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              fetch(`${NODE_API_BASE}/labels/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'alignment', templateKey: labelTemplate, xOffsetMm: labelXOff, yOffsetMm: labelYOff, usedCellsPage1: getValidSkipsForPage(1) }) })
                                .then((r) => r.json()).then((res) => { if (res.success) { setLastLabelPdf(res); pushNotification('Alignment Sheet Ready', `Generated ${res.pdfName}`, 'Labels', 'success'); } });
                            }}
                            className="w-full py-1.5 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200"
                          >
                            🧭 Alignment Test PDF
                          </button>
                        </div>
                      </div>
                    </div>

                    {lastLabelPdf && (
                      <div className="p-2.5 bg-emerald-950/50 border border-emerald-700 rounded-xl flex flex-wrap items-center justify-between gap-2 text-xs shrink-0">
                        <div className="font-bold text-emerald-300 truncate">📄 Ready: {lastLabelPdf.pdfName}</div>
                        <div className="flex gap-1.5 shrink-0">
                          <a href={`${API_ORIGIN}${lastLabelPdf.pdfUrl}`} target="_blank" rel="noreferrer" className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold">⬇️ Open PDF</a>
                          {Array.isArray(lastLabelPdf.printedSkus) && lastLabelPdf.printedSkus.length > 0 && (
                            <button onClick={() => handleMarkSkusPrinted(lastLabelPdf.printedSkus, 'PDF batch')} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 font-semibold">
                              ✅ Mark {lastLabelPdf.printedSkus.length} Printed
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 4. LIVE SYNCED PRINT BATCH QUEUE LIST + MARK PRINTED CONTROLS */}
                    <div className="flex-1 min-h-[190px] flex flex-col gap-2 p-3 bg-slate-950/80 border border-slate-800 rounded-xl">
                      <div className="flex flex-wrap items-center justify-between gap-1.5 shrink-0">
                        <span className="text-[11px] font-bold text-white">
                          📋 Labels in Print Batch ({queuedCards.length.toLocaleString()})
                        </span>
                        <div className="flex flex-wrap items-center gap-1">
                          <button
                            type="button"
                            disabled={activePageSkus.length === 0}
                            onClick={() => handleMarkSkusPrinted(activePageSkus, `Page ${safePreviewPage}`)}
                            title={`Mark the ${activePageSkus.length} label(s) on Page ${safePreviewPage} as Printed`}
                            className="px-2 py-0.5 rounded-lg bg-sky-950/80 hover:bg-sky-800 border border-sky-700 text-sky-200 text-[10px] font-bold disabled:opacity-40"
                          >
                            ✅ Mark P{safePreviewPage} ({activePageSkus.length})
                          </button>
                          <button
                            type="button"
                            disabled={queuedSkuList.length === 0}
                            onClick={() => handleMarkSkusPrinted(queuedSkuList, labelIntakeBatch)}
                            title="Mark all labels in this print batch as Printed in Inventory.csv"
                            className="px-2 py-0.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-[10px] font-bold disabled:opacity-40"
                          >
                            ✅ Mark All Printed ({queuedSkuList.length})
                          </button>
                        </div>
                      </div>

                      <input
                        value={labelQueueSearch}
                        onChange={(e) => setLabelQueueSearch(e.target.value)}
                        placeholder="Filter print batch (SKU, Player, #, Subset, Batch)..."
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-[11px] shrink-0"
                      />

                      <div className="flex-1 min-h-0 overflow-y-auto border border-slate-800/90 rounded-lg">
                        <table className="w-full text-left text-[11px] whitespace-nowrap">
                          <thead className="bg-slate-900 text-slate-400 sticky top-0 z-10">
                            <tr>
                              <th className="p-1.5">SKU</th>
                              <th className="p-1.5">Card</th>
                              <th className="p-1.5">Subset</th>
                              <th className="p-1.5">Status</th>
                              <th className="p-1.5 text-right">Act</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/70">
                            {filteredQueueList.length === 0 ? (
                              <tr>
                                <td colSpan={5} className="p-4 text-center text-slate-500">
                                  No labels queued in this batch. Commit a batch or add reprint SKUs above.
                                </td>
                              </tr>
                            ) : (
                              filteredQueueList.slice(0, 300).map((c) => {
                                const skuStr = String(c.SKU).trim();
                                const isAddedReprint = stagedSet.has(skuStr);
                                const isAlreadyPrinted = String(c.Label_Printed).toLowerCase() === 'true';
                                const isSelectedSample = String(sampleLabel.SKU).trim() === skuStr;
                                return (
                                  <tr
                                    key={skuStr}
                                    onClick={() => prefillSampleLabelFromCard(c)}
                                    title="Click to load into Interactive Label Editor above"
                                    className={`cursor-pointer ${isSelectedSample ? 'bg-cyan-950/45' : 'hover:bg-slate-800/50'}`}
                                  >
                                    <td className="p-1.5 font-mono text-sky-400 font-bold">{skuStr}</td>
                                    <td className="p-1.5 text-white font-semibold max-w-[135px] truncate">#{c['Card Number']} {c.Player}</td>
                                    <td className="p-1.5 text-amber-200 max-w-[95px] truncate">{c.Subset || 'Base'}</td>
                                    <td className="p-1.5">
                                      {isAddedReprint ? (
                                        <span className="px-1.5 py-0.5 rounded bg-sky-950 border border-sky-700 text-sky-200 text-[9.5px] font-bold">🔁 Reprint</span>
                                      ) : isAlreadyPrinted ? (
                                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 text-[9.5px]">Printed</span>
                                      ) : (
                                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 border border-emerald-700 text-emerald-300 text-[9.5px] font-bold">🆕 Unprinted</span>
                                      )}
                                    </td>
                                    <td className="p-1.5 text-right" onClick={(e) => e.stopPropagation()}>
                                      <div className="inline-flex items-center gap-1">
                                        {!isAlreadyPrinted && (
                                          <button
                                            type="button"
                                            onClick={() => handleMarkSkusPrinted([skuStr], `SKU ${skuStr}`)}
                                            title={`Mark SKU ${skuStr} as Printed`}
                                            className="px-1.5 py-0.5 rounded bg-emerald-950 hover:bg-emerald-700 text-emerald-300 text-[10px] font-bold"
                                          >
                                            ✅
                                          </button>
                                        )}
                                        {isAddedReprint && (
                                          <button
                                            type="button"
                                            onClick={() => setStagedReprintSkus((prev) => prev.filter((x) => x !== skuStr))}
                                            title="Remove from added reprints"
                                            className="px-1 py-0.5 rounded bg-rose-950 hover:bg-rose-800 text-rose-300 text-[10px]"
                                          >
                                            ✖
                                          </button>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                );
                              })
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>

                  {/* RIGHT COLUMN: MULTI-PAGE PARTIAL SHEET LIVE LABEL PREVIEW */}
                  <div className={`lg:col-span-7 ${skin.cardBg} border ${skin.border} rounded-2xl p-4 flex flex-col gap-3 min-h-0`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                      <div>
                        <h3 className="text-sm font-bold text-white">Page {safePreviewPage} of {maxNavPage} — Partial Sheet Live Label Preview</h3>
                        <p className="text-[11px] text-slate-400">
                          Queued: <span className="font-mono font-bold text-emerald-300">{queuedCards.length.toLocaleString()}</span> • Skipped P{safePreviewPage}: <span className="font-mono font-bold text-rose-300">{activePageSkipsCount}</span> (Total Skipped: {totalSkipsAllPages}) • Pages: <span className="font-mono font-bold text-sky-300">{estPages}</span>
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <button onClick={() => setLabelPreviewPage((p) => Math.max(1, p - 1))} disabled={safePreviewPage <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-bold">◀ Prev</button>
                        <span className="font-mono text-xs text-white px-1.5">Pg {safePreviewPage}/{maxNavPage}</span>
                        <button onClick={() => setLabelPreviewPage((p) => Math.min(maxNavPage, p + 1))} disabled={safePreviewPage >= maxNavPage} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-xs font-bold">Next ▶</button>
                        <button onClick={() => setPeeledCellsByPage((prev) => ({ ...prev, [safePreviewPage]: {} }))} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-amber-300 font-semibold">Reset P{safePreviewPage}</button>
                        <button onClick={() => { setPeeledCellsByPage({ 1: {} }); setLabelPreviewPage(1); }} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-300">Reset All</button>
                      </div>
                    </div>
                    <div
                      className="flex-1 min-h-0 grid gap-1.5 overflow-y-auto p-2.5 bg-slate-950 rounded-xl border border-slate-800"
                      style={{ gridTemplateColumns: `repeat(${tpl.cols}, minmax(0, 1fr))` }}
                    >
                      {Array.from({ length: tpl.rows }).map((_, rIdx) =>
                        Array.from({ length: tpl.cols }).map((__, cIdx) => {
                          const r = rIdx + 1;
                          const c = cIdx + 1;
                          const skip = !!activePageMap[`${r}-${c}`];
                          const card = !skip && cardCursor < queuedCards.length ? queuedCards[cardCursor++] : null;
                          const cellStyle = card ? getLabelSubsetBadgeStyle(card.Subset) : null;
                          const prClean = card ? String(card['Print Run'] || '').replace(/[^0-9]/g, '') : '';
                          const prTag = prClean === '1' ? '1/1' : (prClean ? `#/${prClean}` : '');
                          const shortSet = card ? String(card.Set || '').replace(/\b(Baseball|Football|Basketball|Hockey|Soccer)\b/gi, '').trim() : '';

                          if (skip) {
                            return (
                              <button
                                key={`${safePreviewPage}-${r}-${c}`}
                                onClick={() => toggleCellOnPage(safePreviewPage, r, c)}
                                title={`Page ${safePreviewPage} R${r}:C${c} skipped. Click to restore.`}
                                className="h-[58px] rounded-lg border border-dashed border-rose-700/80 bg-rose-950/35 hover:bg-rose-950/60 text-rose-400 flex flex-col items-center justify-center p-1 transition"
                              >
                                <span className="font-mono text-[10px] font-bold">R{r}:C{c}</span>
                                <span className="text-[9px] font-bold uppercase tracking-wider">[SKIP]</span>
                              </button>
                            );
                          }

                          if (!card) {
                            return (
                              <button
                                key={`${safePreviewPage}-${r}-${c}`}
                                onClick={() => toggleCellOnPage(safePreviewPage, r, c)}
                                title={`Empty slot Page ${safePreviewPage} R${r}:C${c}. Click to mark peeled/skip.`}
                                className="h-[58px] rounded-lg border border-emerald-900/60 bg-emerald-950/20 hover:bg-emerald-950/45 text-emerald-400/70 flex flex-col items-center justify-center p-1 transition"
                              >
                                <span className="font-mono text-[10px]">R{r}:C{c}</span>
                                <span className="text-[9px]">Available</span>
                              </button>
                            );
                          }

                          return (
                            <button
                              key={`${safePreviewPage}-${r}-${c}`}
                              onClick={() => toggleCellOnPage(safePreviewPage, r, c)}
                              title={`Page ${safePreviewPage} R${r}:C${c} — SKU ${card.SKU}: ${card.Set} #${card['Card Number']} ${card.Player} [${card.Subset}]. Click to mark peeled/skip.`}
                              className={`relative h-[58px] bg-white text-slate-900 rounded-lg p-1.5 text-left flex items-center gap-1.5 shadow-sm hover:ring-2 hover:ring-rose-500 transition overflow-hidden ${cellStyle.borderCls}`}
                            >
                              <span className="absolute top-0.5 right-1 font-mono text-[8px] text-slate-400">R{r}:C{c}</span>
                              <div className="flex flex-col items-center pr-1 border-r border-slate-300 shrink-0 w-[34px]">
                                <div className="w-5 h-5 bg-slate-900 text-white text-[6px] font-mono flex items-center justify-center rounded-[2px]">QR</div>
                                <div className="font-mono text-[7px] font-bold text-slate-800 leading-none mt-0.5 truncate max-w-full">{card.SKU}</div>
                              </div>
                              <div className="flex-1 min-w-0 leading-[1.12]">
                                <div className="text-[8px] font-bold text-slate-700 truncate pr-6">{shortSet} • #{card['Card Number']}</div>
                                <div className="text-[9px] font-extrabold text-black truncate">{card.Player}</div>
                                <div className="mt-0.5 flex items-center gap-0.5 overflow-hidden">
                                  <span className={`text-[7.5px] font-bold px-1 rounded truncate ${cellStyle.pillCls}`}>
                                    {card.Subset || 'Base'}
                                  </span>
                                  {prTag && <span className="text-[7.5px] font-bold px-1 rounded bg-rose-700 text-white shrink-0">{prTag}</span>}
                                </div>
                              </div>
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 6. CHECKLIST BUILDER (WITH WRENCH MAINTENANCE WIDGET & TRACKED SETS QUEUE) */}
            {activePage === 'checklist_builder' && (() => {
              const targetCount = Object.keys(targetScraperQueueMap).length;
              const scopeLbl = selectedTrackedUrls.length > 0 ? `${targetCount} Selected` : `All ${targetCount}`;

              const extractSid = (u) => {
                const m = String(u || '').match(/\/sid\/(\d+)/i);
                return m ? m[1] : '';
              };
              const canonSetNorm = (fn) => String(fn || '').toLowerCase().replace(/\b(and|&)\b/g, '').replace(/[^a-z0-9]/g, '');

              const sidCounts = {};
              const canonCounts = {};
              trackedSets.forEach((ts) => {
                const sid = extractSid(ts.TCDB_URL);
                if (sid) sidCounts[sid] = (sidCounts[sid] || 0) + 1;
                const ck = `${String(ts.Sport || '').toLowerCase()}|${canonSetNorm(ts.Folder_Name)}`;
                canonCounts[ck] = (canonCounts[ck] || 0) + 1;
              });

              const enrichedTracked = trackedSets.map((ts) => {
                const sid = extractSid(ts.TCDB_URL);
                const ck = `${String(ts.Sport || '').toLowerCase()}|${canonSetNorm(ts.Folder_Name)}`;
                const isDupSid = !!(sid && sidCounts[sid] > 1);
                const isDupName = canonCounts[ck] > 1;
                return { ...ts, _sid: sid, _isDup: isDupSid || isDupName, _dupReason: isDupSid ? `SID ${sid}` : (isDupName ? 'Name' : '') };
              });

              const totalDupRows = enrichedTracked.filter((t) => t._isDup).length;
              const trackedSports = Array.from(new Set(trackedSets.map((t) => t.Sport).filter(Boolean))).sort();
              const trackedYears = Array.from(new Set(trackedSets.map((t) => t.Year).filter(Boolean))).sort().reverse();
              const trackedMfgs = Array.from(new Set(trackedSets.map((t) => t.Manufacturer).filter(Boolean))).sort();

              const toggleTrackedSort = (colKey) => {
                if (trackedSortBy === colKey) {
                  setTrackedSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
                } else {
                  setTrackedSortBy(colKey);
                  setTrackedSortDir('asc');
                }
              };
              const sortInd = (colKey) => (trackedSortBy === colKey ? (trackedSortDir === 'asc' ? ' ▲' : ' ▼') : '');

              const filteredTracked = enrichedTracked
                .filter((ts) => {
                  if (trackedSportF !== 'All Sports' && ts.Sport !== trackedSportF) return false;
                  if (trackedYearF !== 'All Years' && ts.Year !== trackedYearF) return false;
                  if (trackedMfgF !== 'All Manufacturers' && ts.Manufacturer !== trackedMfgF) return false;
                  if (trackedDupOnly && !ts._isDup) return false;
                  if (trackedSearch.trim() && !`${ts.Folder_Name} ${ts.Sport} ${ts.Year} ${ts.Manufacturer} ${ts._sid} ${ts.TCDB_URL}`.toLowerCase().includes(trackedSearch.toLowerCase())) return false;
                  return true;
                })
                .sort((a, b) => {
                  const dir = trackedSortDir === 'asc' ? 1 : -1;
                  if (trackedSortBy === '_sid') return (parseInt(a._sid || '0', 10) - parseInt(b._sid || '0', 10)) * dir;
                  const va = String(a[trackedSortBy] || '').toLowerCase();
                  const vb = String(b[trackedSortBy] || '').toLowerCase();
                  return va.localeCompare(vb, undefined, { numeric: true }) * dir;
                });
              return (
                <div className="flex-1 flex flex-col gap-3 min-h-0">
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 shrink-0`}>
                    <div className="flex items-center justify-between">
                      <div>
                        <h2 className="text-sm font-bold text-white">🕷️ Unified TCDB Checklist &amp; Image Builder ({trackedSets.length} Tracked Sets)</h2>
                        <p className="text-xs text-slate-400 mt-0.5">Builds 11-column checklists with TCDB_CIDs and downloads Front &amp; Back template images to {SET_LIBRARY_ROOT}. Check rows below to target specific sets.</p>
                      </div>
                      <button onClick={() => setShowMaintenanceWidget(!showMaintenanceWidget)} className={`px-3 py-1.5 rounded-xl border text-xs font-bold flex items-center gap-1.5 transition ${showMaintenanceWidget ? skin.accentActive : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'}`}>
                        🔧 Maintenance {totalDupRows > 0 ? `(${totalDupRows} Dup)` : ''} {showMaintenanceWidget ? '⌄' : '›'}
                      </button>
                    </div>
                    {showMaintenanceWidget && (
                      <div className="p-3.5 bg-slate-950/85 border border-amber-500/30 rounded-xl space-y-2.5">
                        <div className="text-xs font-bold text-amber-300">🛠️ Checklist &amp; Reference Library Maintenance Tools</div>
                        <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
                          <button
                            onClick={() => triggerJob('set_scraper', 'Clean & Dedupe Tracked Sets & Directory', 'deduplicate_tracked_sets', { estimated_total: Math.max(1, trackedSets.length) })}
                            className="py-2 px-3 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs shadow"
                          >
                            🧹 Clean &amp; Dedupe Tracked Sets {totalDupRows > 0 ? `(${totalDupRows})` : ''}
                          </button>
                          <button onClick={() => triggerJob('set_scraper', 'Clean Reference Library Folders & Filenames', 'clean_reference_library', { estimated_total: Math.max(1, trackedSets.length) })} className={`py-2 px-3 rounded-xl font-bold text-xs ${skin.accentBtn}`}>🗂️ Clean Ref Library Folders &amp; Names</button>
                          <button onClick={() => triggerJob('set_scraper', 'Repair Existing Checklist CSVs', 'repair_checklists', { estimated_total: Math.max(1, trackedSets.length) })} className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-300 font-bold text-xs">🔧 Repair LL / CPC / Var CSVs</button>
                          <button onClick={() => triggerJob('set_scraper', 'Sync Set Library Download Status', 'sync_set_library_status', { estimated_total: Math.max(1, trackedSets.length) })} className="py-2 px-3 rounded-xl bg-emerald-700 hover:bg-emerald-600 text-white font-bold text-xs">🔄 Sync Download Status</button>
                          <button onClick={() => triggerJob('set_scraper', 'Rebuild Visual Feature Cache (.pkl)', 'rebuild_feature_cache', { estimated_total: 1 })} className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-300 font-bold text-xs">🧠 Rebuild Feature Cache</button>
                          <button onClick={() => triggerJob('system', 'Build / Update DINOv2 Neural Index (GPU)', 'build_neural_index', { batch_size: 32, force_rebuild: false, estimated_total: 1000 })} className="py-2 px-3 rounded-xl bg-indigo-950/90 hover:bg-indigo-800 border border-indigo-600/70 text-indigo-200 font-bold text-xs">🧬 Update Neural Index</button>
                        </div>
                      </div>
                    )}
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-4">
                        <label className="flex items-center gap-2 text-xs text-slate-300">
                          <input type="checkbox" checked={cleanSlateChecklists} onChange={(e) => setCleanSlateChecklists(e.target.checked)} />
                          🧹 Clean-Slate Build (Archive existing CSVs in Checklists\ before building)
                        </label>
                        <label className="flex items-center gap-2 text-xs text-slate-300">
                          <input
                            type="checkbox"
                            checked={forceFullReverify}
                            onChange={(e) => {
                              const nextVal = e.target.checked;
                              setForceFullReverify(nextVal);
                              if (planPreview) {
                                fetchScraperPlanPreview(planPreviewMode, targetScraperQueueMap, nextVal);
                              }
                            }}
                          />
                          🔄 Force Full Re-Verify (Ignore Incremental Checkpoints)
                        </label>
                      </div>
                      <button
                        onClick={() => fetchScraperPlanPreview(planPreviewMode, targetScraperQueueMap)}
                        disabled={planPreviewLoading}
                        className="px-3 py-1.5 rounded-xl bg-sky-700/80 hover:bg-sky-600 disabled:opacity-50 text-white font-bold text-xs border border-sky-500/40"
                      >
                        {planPreviewLoading ? '⏳ Computing Plan...' : '📋 Preview Plan (Dry Run)'}
                      </button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2">
                      <button onClick={() => triggerJob('set_scraper', `Build Checklists Only (${scopeLbl})`, 'tcdb_checklist_scrape', { selected_tcdb_sets: targetScraperQueueMap, clean_slate_reset: cleanSlateChecklists, incremental: !forceFullReverify, force_refresh: forceFullReverify, estimated_total: Math.max(1, targetCount) })} className="py-2.5 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs">
                        🏛️ Checklists Only ({scopeLbl})
                      </button>
                      <button onClick={() => triggerJob('set_scraper', `Download Images Only (${scopeLbl})`, 'tcdb_download_all_images', { target_queue: targetScraperQueueMap, estimated_total: Math.max(1, targetCount) })} className={`py-2.5 px-3 rounded-xl font-bold text-xs ${skin.accentBtn}`}>
                        📥 Images Only ({scopeLbl})
                      </button>
                      <button onClick={() => triggerJob('set_scraper', `Build Checklists + Images Card-by-Card (${scopeLbl})`, 'tcdb_checklist_and_images', { target_queue: targetScraperQueueMap, clean_slate_reset: cleanSlateChecklists, incremental: !forceFullReverify, force_refresh: forceFullReverify, estimated_total: Math.max(1, targetCount) })} className="py-2.5 px-3 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 text-white font-bold text-xs shadow-lg">
                        ⚡ Checklists + Images ({scopeLbl})
                      </button>
                      <button onClick={() => triggerJob('set_scraper', `High-Res R-Tier Upgrade (${scopeLbl})`, 'tcdb_upgrade', { target_queue: targetScraperQueueMap, estimated_total: Math.max(1, targetCount) })} className="py-2.5 px-3 rounded-xl bg-amber-600/90 hover:bg-amber-500 text-white font-bold text-xs shadow">
                        🔄 High-Res Upgrade ({scopeLbl})
                      </button>
                      <button onClick={() => triggerJob('set_scraper', `Missing Backs Audit (${scopeLbl})`, 'tcdb_missing_back', { target_queue: targetScraperQueueMap, estimated_total: Math.max(1, targetCount) })} className="py-2.5 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold">
                        🔎 Missing Backs ({scopeLbl})
                      </button>
                    </div>
                    {(planPreview || planPreviewLoading) && (
                      <div className="relative p-3 rounded-xl bg-slate-950/90 border border-sky-500/40 space-y-2.5 text-xs overflow-hidden">
                        {planPreviewLoading && (
                          <div className="absolute inset-0 z-10 bg-slate-950/80 backdrop-blur-[1px] flex items-center justify-center gap-2.5">
                            <span className="inline-block w-4 h-4 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
                            <span className="text-sky-200 font-bold text-xs">Computing execution plan across tracked sets...</span>
                          </div>
                        )}
                        {planPreview && (
                          <>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-extrabold text-sky-300">📋 Execution Preview ({planPreview.total_sets} set{planPreview.total_sets === 1 ? '' : 's'}):</span>
                            {[
                              ['checklist_only', 'Checklists Only'],
                              ['checklist_and_images', 'Checklists + Images'],
                              ['images_only', 'Images Only'],
                              ['upgrade', 'High-Res Upgrade'],
                              ['missing_back', 'Missing Backs'],
                            ].map(([mk, ml]) => (
                              <button
                                key={mk}
                                onClick={() => selectPlanPreviewMode(mk, targetScraperQueueMap)}
                                className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold border ${planPreview.mode === mk ? 'bg-sky-600 text-white border-sky-400' : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'}`}
                              >
                                {ml}
                              </button>
                            ))}
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => {
                                const m = planPreview.mode || 'checklist_only';
                                if (m === 'checklist_only') triggerJob('set_scraper', `Build Checklists Only (${scopeLbl})`, 'tcdb_checklist_scrape', { selected_tcdb_sets: targetScraperQueueMap, clean_slate_reset: cleanSlateChecklists, incremental: !forceFullReverify, force_refresh: forceFullReverify, estimated_total: Math.max(1, targetCount) });
                                else if (m === 'images_only') triggerJob('set_scraper', `Download Images Only (${scopeLbl})`, 'tcdb_download_all_images', { target_queue: targetScraperQueueMap, estimated_total: Math.max(1, targetCount) });
                                else if (m === 'checklist_and_images') triggerJob('set_scraper', `Build Checklists + Images Card-by-Card (${scopeLbl})`, 'tcdb_checklist_and_images', { target_queue: targetScraperQueueMap, clean_slate_reset: cleanSlateChecklists, incremental: !forceFullReverify, force_refresh: forceFullReverify, estimated_total: Math.max(1, targetCount) });
                                else if (m === 'upgrade') triggerJob('set_scraper', `High-Res R-Tier Upgrade (${scopeLbl})`, 'tcdb_upgrade', { target_queue: targetScraperQueueMap, estimated_total: Math.max(1, targetCount) });
                                else if (m === 'missing_back') triggerJob('set_scraper', `Missing Backs Audit (${scopeLbl})`, 'tcdb_missing_back', { target_queue: targetScraperQueueMap, estimated_total: Math.max(1, targetCount) });
                                setPlanPreview(null);
                              }}
                              className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px]"
                            >
                              ▶ Execute Plan
                            </button>
                            <button onClick={() => setPlanPreview(null)} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px]">✕ Close</button>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2 text-[11px]">
                          <span className="px-2.5 py-1 rounded-lg bg-emerald-950/70 border border-emerald-700/60 text-emerald-300 font-semibold">✅ {(planPreview.subsets_unchanged_skipped || 0).toLocaleString()} subsets unchanged & skipped</span>
                          <span className="px-2.5 py-1 rounded-lg bg-amber-950/70 border border-amber-700/60 text-amber-300 font-semibold">🔄 {(planPreview.subsets_to_update || 0).toLocaleString()} subsets to update</span>
                          <span className="px-2.5 py-1 rounded-lg bg-violet-950/70 border border-violet-700/60 text-violet-300 font-semibold">🖼️ {(planPreview.missing_images_queued || 0).toLocaleString()} missing images queued</span>
                          <span className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 text-slate-300 font-semibold">🌐 ~{(planPreview.estimated_http_requests || 0).toLocaleString()} reqs @ {planPreview.safe_rpm || 23.5} req/m</span>
                          <span className="px-2.5 py-1 rounded-lg bg-sky-950/70 border border-sky-700/60 text-sky-300 font-bold">⏱️ ETA ~{planPreview.estimated_eta_display || '0s'}</span>
                        </div>
                        {Array.isArray(planPreview.per_set) && planPreview.per_set.length > 0 && (
                          <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-800">
                            <table className="w-full text-left text-[11px]">
                              <thead className="bg-slate-900/90 text-slate-400 sticky top-0">
                                <tr>
                                  <th className="py-1 px-2">Set</th>
                                  <th className="py-1 px-2 text-right">Skip Subsets</th>
                                  <th className="py-1 px-2 text-right">Update Subsets</th>
                                  <th className="py-1 px-2 text-right">Missing F/B</th>
                                  <th className="py-1 px-2 text-right">Est. Reqs</th>
                                  <th className="py-1 px-2 text-right">ETA</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800/70">
                                {planPreview.per_set.map((ps, pi) => (
                                  <tr key={pi} className="hover:bg-slate-900/60">
                                    <td className="py-1 px-2 text-slate-200 font-medium truncate max-w-[240px]">{ps.set_name}</td>
                                    <td className="py-1 px-2 text-right text-emerald-400">{ps.subsets_skipped}</td>
                                    <td className="py-1 px-2 text-right text-amber-400">{ps.subsets_to_update}</td>
                                    <td className="py-1 px-2 text-right text-violet-300">{ps.missing_fronts}/{ps.missing_backs}</td>
                                    <td className="py-1 px-2 text-right text-slate-300">{ps.estimated_requests}</td>
                                    <td className="py-1 px-2 text-right text-sky-300">{ps.estimated_eta_display}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                          </>
                        )}
                      </div>
                    )}
                    <div className="text-[11px] text-slate-400">
                      📥 <b>Auto-Queue Protection Active:</b> Starting additional tasks in this silo automatically queues them sequentially behind the active job so two TCDB workers never collide.
                    </div>
                  </div>

                  {/* Tracked Sets Queue Table */}
                  <div className={`flex-1 min-h-0 flex flex-col gap-2.5 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-xs font-bold text-white uppercase">📋 Tracked Sets Queue ({filteredTracked.length} / {trackedSets.length})</h3>
                        <button onClick={() => setSelectedTrackedUrls(filteredTracked.map((t) => t.TCDB_URL))} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] font-semibold">☑️ Select Filtered ({filteredTracked.length})</button>
                        <button onClick={() => setSelectedTrackedUrls([])} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px]">⬜ Clear ({selectedTrackedUrls.length})</button>
                        <button
                          onClick={() => setTrackedDupOnly((v) => !v)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border transition ${trackedDupOnly ? 'bg-rose-600 text-white border-rose-400' : (totalDupRows > 0 ? 'bg-amber-950/80 text-amber-300 border-amber-700 hover:bg-amber-900' : 'bg-slate-800 text-slate-400 border-slate-700')}`}
                        >
                          ⚠️ Duplicates Only ({totalDupRows})
                        </button>
                      </div>
                      <button
                        onClick={() => fetch(`${NODE_API_BASE}/config/tracked-sets`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(trackedSets) })
                          .then((r) => r.json())
                          .then((res) => {
                            if (res && res.success) {
                              setTrackedSets(res.trackedSets || trackedSets);
                              setTrackedSetsDirty(false);
                              pushNotification('Tracked Sets Saved', `Saved ${(res.trackedSets || trackedSets).length} set(s) to tracked_sets.json.`, 'Scraper', 'success');
                            } else {
                              pushNotification('Save Queue Failed', res?.error || 'Could not save tracked sets.', 'Scraper', 'error');
                            }
                          })
                          .catch((e) => pushNotification('Save Queue Error', e.message, 'Scraper', 'error'))}
                        className={`px-3 py-1.5 rounded-xl font-bold text-xs ${trackedSetsDirty ? 'bg-amber-500 hover:bg-amber-400 text-slate-950 animate-pulse shadow-lg shadow-amber-950/60' : 'bg-emerald-600 hover:bg-emerald-500 text-white'}`}
                      >
                        {trackedSetsDirty ? '💾 Save Queue (Unsaved Changes)' : '💾 Save Queue'}
                      </button>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2 shrink-0">
                      <select value={trackedSportF} onChange={(e) => setTrackedSportF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2 py-1 text-xs">
                        <option>All Sports</option>
                        {trackedSports.map((sp) => <option key={sp}>{sp}</option>)}
                      </select>
                      <select value={trackedYearF} onChange={(e) => setTrackedYearF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2 py-1 text-xs">
                        <option>All Years</option>
                        {trackedYears.map((yr) => <option key={yr}>{yr}</option>)}
                      </select>
                      <select value={trackedMfgF} onChange={(e) => setTrackedMfgF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2 py-1 text-xs">
                        <option>All Manufacturers</option>
                        {trackedMfgs.map((m) => <option key={m}>{m}</option>)}
                      </select>
                      <input value={trackedSearch} onChange={(e) => setTrackedSearch(e.target.value)} placeholder="Search Folder, SID, URL..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1 text-xs" />
                      <button
                        onClick={() => { setTrackedSportF('All Sports'); setTrackedYearF('All Years'); setTrackedMfgF('All Manufacturers'); setTrackedDupOnly(false); setTrackedSearch(''); }}
                        className="px-2.5 py-1 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
                      >
                        🧹 Clear Filters
                      </button>
                    </div>
                    <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                      <table className="w-full text-left text-xs whitespace-nowrap">
                        <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10 select-none">
                          <tr>
                            <th className="p-2">Sel</th>
                            <th onClick={() => toggleTrackedSort('Folder_Name')} className="p-2 cursor-pointer hover:text-white">Folder Name{sortInd('Folder_Name')}</th>
                            <th onClick={() => toggleTrackedSort('_sid')} className="p-2 cursor-pointer hover:text-white">SID{sortInd('_sid')}</th>
                            <th onClick={() => toggleTrackedSort('Sport')} className="p-2 cursor-pointer hover:text-white">Sport{sortInd('Sport')}</th>
                            <th onClick={() => toggleTrackedSort('Year')} className="p-2 cursor-pointer hover:text-white">Year{sortInd('Year')}</th>
                            <th onClick={() => toggleTrackedSort('Manufacturer')} className="p-2 cursor-pointer hover:text-white">Mfg{sortInd('Manufacturer')}</th>
                            <th onClick={() => toggleTrackedSort('Last_Scraped')} className="p-2 cursor-pointer hover:text-white">Last Scraped{sortInd('Last_Scraped')}</th>
                            <th className="p-2">TCDB</th>
                            <th className="p-2">Del</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                          {filteredTracked.map((ts) => {
                            const isSel = selectedTrackedUrls.includes(ts.TCDB_URL);
                            return (
                              <tr key={ts.TCDB_URL} className={ts._isDup ? 'bg-amber-950/35 hover:bg-amber-950/50' : (isSel ? 'bg-cyan-950/35' : 'hover:bg-slate-800/40')}>
                                <td className="p-1.5"><input type="checkbox" checked={isSel} onChange={() => setSelectedTrackedUrls((p) => p.includes(ts.TCDB_URL) ? p.filter((u) => u !== ts.TCDB_URL) : [...p, ts.TCDB_URL])} /></td>
                                <td className="p-1.5 font-mono font-semibold text-white">
                                  {ts.Folder_Name}{' '}
                                  {ts._isDup && (
                                    <span title={`Duplicate detected (${ts._dupReason})`} className="ml-1 px-1.5 py-0.5 rounded bg-rose-900/90 border border-rose-600 text-rose-200 text-[9.5px] font-bold">
                                      ⚠️ DUP ({ts._dupReason})
                                    </span>
                                  )}
                                </td>
                                <td className="p-1.5 font-mono text-slate-400">{ts._sid || '—'}</td>
                                <td className="p-1.5">{ts.Sport}</td>
                                <td className="p-1.5 font-mono">{ts.Year}</td>
                                <td className="p-1.5">{ts.Manufacturer}</td>
                                <td className="p-1.5 font-mono text-emerald-400">{ts.Last_Scraped || 'NEVER'}</td>
                                <td className="p-1.5"><a href={ts.TCDB_URL} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">Open ↗</a></td>
                                <td className="p-1.5"><button onClick={() => { setTrackedSets((prev) => prev.filter((x) => x.TCDB_URL !== ts.TCDB_URL)); setSelectedTrackedUrls((prev) => prev.filter((u) => u !== ts.TCDB_URL)); setTrackedSetsDirty(true); }} title="Remove from queue (click Save Queue to persist)" className="text-rose-400 hover:text-rose-200 px-1">🗑️</button></td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 7. UNIFIED CHECKLIST VIEWER */}
            {activePage === 'unified_checklist_viewer' && (
              <div className={`flex-1 flex flex-col gap-3 min-h-0 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                  <div>
                    <h2 className="text-sm font-bold text-white">
                      📊 Unified Checklist Viewer — Showing {chkData.rows.length.toLocaleString()} of{' '}
                      <span className={skin.accentText}>{(chkData.totalMatchingCount || 0).toLocaleString()}</span> matching records
                      <span className="text-slate-400 font-normal"> (out of {(chkData.totalRecords || 0).toLocaleString()} total)</span>
                    </h2>
                    <p className="text-[11px] text-slate-400">Hover over any Attribute badge (e.g. RC, LL, CPC, ASR, #/99) to see its TCDB definition.</p>
                  </div>
                  <button onClick={() => { setChkSetF('All Sets'); setChkYearF('All Years'); setChkSubsetF('All Subsets'); setChkAttrF('All Attributes'); setChkStatusF('All Cards'); setChkSearchF(''); }} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">🧹 Clear Filters</button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-6 gap-2 shrink-0">
                  <select value={chkYearF} onChange={(e) => setChkYearF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Years</option>
                    {(chkData.knownYears || []).map((y) => <option key={y}>{y}</option>)}
                  </select>
                  <select value={chkSetF} onChange={(e) => { setChkSetF(e.target.value); setChkSubsetF('All Subsets'); }} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Sets</option>
                    {dynamicSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                  </select>
                  <select value={chkSubsetF} onChange={(e) => setChkSubsetF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Subsets</option>
                    {(chkData.knownSubsets || []).slice(0, 300).map((sub) => <option key={sub}>{sub}</option>)}
                  </select>
                  <select value={chkAttrF} onChange={(e) => setChkAttrF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Attributes</option>
                    {Object.entries(chkData.glossary || DEFAULT_GLOSSARY).map(([code, desc]) => <option key={code} value={code}>{code} — {desc}</option>)}
                  </select>
                  <select value={chkStatusF} onChange={(e) => setChkStatusF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                    <option>All Cards</option><option>Downloaded (Front &amp; Back)</option><option>Missing Back Only</option><option>Not Downloaded Yet</option>
                  </select>
                  <input value={chkSearchF} onChange={(e) => setChkSearchF(e.target.value)} placeholder="Search CID, Player, Card #, Team..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                </div>
                <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                  <table className="w-full text-left text-xs whitespace-nowrap">
                    <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                      <tr><th className="p-2">Set</th><th className="p-2">Subset</th><th className="p-2">Card #</th><th className="p-2">Player</th><th className="p-2">Team</th><th className="p-2">Attributes</th><th className="p-2">TCDB_CID</th><th className="p-2">Front</th><th className="p-2">Back</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {(chkData.rows || []).map((r, i) => (
                        <tr key={i} className="hover:bg-slate-800/40">
                          <td className="p-2">{r.Set}</td>
                          <td className="p-2 font-semibold">{r.Subset}</td>
                          <td className="p-2 font-mono">#{r['Card Number']}</td>
                          <td className="p-2 font-bold text-white">{r.Player}</td>
                          <td className="p-2 text-slate-300">{r.Team}</td>
                          <td className="p-2"><AttributeBadges attributesStr={r.Attributes} glossary={chkData.glossary} /></td>
                          <td className="p-2 font-mono text-amber-300">{r.TCDB_CID ? `TCDB${r.TCDB_CID}` : '—'}</td>
                          <td className="p-2">{String(r.Front_Downloaded).toLowerCase() === 'yes' ? '✅' : '—'}</td>
                          <td className="p-2">{String(r.Back_Downloaded).toLowerCase() === 'yes' ? '✅' : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0 pt-1">
                  <span>
                    Page {chkPage} of {Math.max(1, Math.ceil((chkData.totalMatchingCount || 0) / chkLimit))} ({(chkData.totalMatchingCount || 0).toLocaleString()} matching records)
                  </span>
                  <div className="flex items-center gap-2">
                    <select value={chkLimit} onChange={(e) => { setChkLimit(parseInt(e.target.value, 10) || 350); setChkPage(1); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                      <option value={150}>150 / page</option><option value={350}>350 / page</option><option value={1000}>1,000 / page</option>
                    </select>
                    <button onClick={() => setChkPage((p) => Math.max(1, p - 1))} disabled={chkPage <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                    <button onClick={() => setChkPage((p) => Math.min(Math.max(1, Math.ceil((chkData.totalMatchingCount || 0) / chkLimit)), p + 1))} disabled={chkPage >= Math.max(1, Math.ceil((chkData.totalMatchingCount || 0) / chkLimit))} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                  </div>
                </div>
              </div>
            )}

            {/* 8. SET BROWSER (CRAWL OPTIONS POP-DOWN + AUTO-UPDATING ERA TABS + CATEGORY FILTER) */}
            {activePage === 'set_browser' && (() => {
              const curCalYear = new Date().getFullYear();
              const trkUrls = new Set(trackedSets.map((t) => t.TCDB_URL));
              const cartUrls = new Set(setCart.map((c) => c.TCDB_URL));

              // Compute auto-updating Era for every set dynamically based on current calendar year & released sets
              const rowsWithDynamicEra = directoryRows.map((d) => ({
                ...d,
                _dynEra: computeDynamicEraForYear(d.Year, curCalYear),
              }));

              // Pre-Era filter pass (Sport, Manufacturer, Category, Hide Tracked, Search) drives live counts on Era tabs
              const baseFilteredDir = rowsWithDynamicEra.filter((d) => {
                if (dirSportFilter !== 'All Sports' && d.Sport !== dirSportFilter) return false;
                if (dirMfgFilter !== 'All Manufacturers' && d.Manufacturer !== dirMfgFilter) return false;
                if (dirCategoryFilter !== 'All Categories' && (d.Category || 'Major Release') !== dirCategoryFilter) return false;
                if (dirHideTracked && trkUrls.has(d.TCDB_URL)) return false;
                if (dirSearch.trim() && !`${d.Set_Name} ${d.Year} ${d.SID} ${d.Folder_Name} ${d.Category} ${d.Manufacturer}`.toLowerCase().includes(dirSearch.toLowerCase())) return false;
                return true;
              });

              const eraCountsMap = {};
              baseFilteredDir.forEach((d) => {
                eraCountsMap[d._dynEra] = (eraCountsMap[d._dynEra] || 0) + 1;
              });
              const sortedEraKeys = Object.keys(eraCountsMap).sort((a, b) => eraSortWeight(b) - eraSortWeight(a));
              const activeEraTab = dirEraFilter !== 'All Eras' && eraCountsMap[dirEraFilter] ? dirEraFilter : 'All Eras';
              const finalDirRows = activeEraTab === 'All Eras' ? baseFilteredDir : baseFilteredDir.filter((d) => d._dynEra === activeEraTab);
              const totPages = Math.max(1, Math.ceil(finalDirRows.length / dirPageSize));
              const safeDirPage = Math.min(dirPage, totPages);
              const pageSliceDir = finalDirRows.slice((safeDirPage - 1) * dirPageSize, safeDirPage * dirPageSize);

              const crawlStartYrNum = parseInt(crawlOpts.startYear, 10) || curCalYear;
              const crawlEndYrNum = parseInt(crawlOpts.endYear, 10) || curCalYear;
              const crawlTotalSteps = (crawlOpts.sports || []).reduce((acc, sp) => {
                const effStart = Math.max(Math.min(crawlStartYrNum, crawlEndYrNum), SPORT_FIRST_CARD_YEAR[sp] || 1880);
                const effEnd = Math.max(crawlStartYrNum, crawlEndYrNum);
                return acc + (effEnd >= effStart ? effEnd - effStart + 1 : 0);
              }, 0);
              const toggleCrawlSport = (sp) => {
                setCrawlOpts((prev) => {
                  const has = (prev.sports || []).includes(sp);
                  return { ...prev, sports: has ? prev.sports.filter((x) => x !== sp) : [...prev.sports, sp] };
                });
              };

              return (
                <div className="flex-1 flex flex-col gap-3 min-h-0">
                  <div className={`flex-1 min-h-0 flex flex-col gap-3 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                      <h2 className="text-sm font-bold text-white">🌐 TCDB Master Set Directory ({directoryRows.length.toLocaleString()} Sets Cached)</h2>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => { setShowQuickAddWidget(!showQuickAddWidget); setShowCrawlWidget(false); }}
                          className={`px-3 py-1.5 rounded-xl border text-xs font-bold ${showQuickAddWidget ? skin.accentActive : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'}`}
                        >
                          ➕ Quick-Add Set {showQuickAddWidget ? '⌄' : '›'}
                        </button>
                        <button onClick={() => setShowCartSidebar(!showCartSidebar)} className="px-3 py-1.5 rounded-xl bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-200 text-xs font-bold">🛒 Staged Cart ({setCart.length})</button>
                        <button
                          onClick={() => triggerJob('set_browser', 'Fix & Clean Set Directory (Manufacturers, Categories & Naming)', 'repair_tcdb_directory', { fetch_missing_image_pct: false, estimated_total: 2 })}
                          title="Fixes Manufacturers, Categories, uniform Set/Folder names, and syncs local Image_Pct with verbose logging"
                          className="px-3 py-1.5 rounded-xl bg-amber-950/80 hover:bg-amber-800 border border-amber-700 text-amber-200 text-xs font-bold"
                        >
                          🔧 Fix &amp; Clean Directory
                        </button>
                        <button
                          onClick={() => triggerJob('set_browser', 'Fast ViewAll.cfm Img % & Category Backfill', 'repair_tcdb_directory', { fetch_missing_image_pct: true, max_live_fetches: 0, estimated_total: 60 })}
                          title="Ultra-fast single-pass ViewAll.cfm backfill (1 HTTP request per Sport+Year refreshes exact TCDB Categories & Image_Pct across hundreds of sets!)"
                          className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-emerald-300 text-xs font-semibold"
                        >
                          📊 Fast Backfill Img %
                        </button>
                        <button
                          onClick={() => { setShowCrawlWidget(!showCrawlWidget); setShowQuickAddWidget(false); }}
                          className={`px-3 py-1.5 rounded-xl border text-xs font-bold transition ${showCrawlWidget ? skin.accentActive : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-sky-300'}`}
                        >
                          🕷️ Crawl Directory {showCrawlWidget ? '⌄' : '›'}
                        </button>
                      </div>
                    </div>

                    {/* POP-DOWN: FULL CRAWL DIRECTORY OPTIONS PANEL */}
                    {showCrawlWidget && (
                      <div className="p-4 bg-slate-950/90 border border-sky-500/35 rounded-xl space-y-3 shrink-0 shadow-lg">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="text-xs font-bold text-sky-300">🕷️ Configure TCDB Master Set Directory Crawl</div>
                            <div className="text-[10.5px] text-slate-400">Choose any combination of sports and years (saves incremental checkpoints every 10 pages).</div>
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5">
                            <button onClick={() => setCrawlOpts((p) => ({ ...p, sports: [...ALL_TCDB_SPORTS] }))} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10.5px] font-semibold text-sky-200">All 9 Sports</button>
                            <button onClick={() => setCrawlOpts((p) => ({ ...p, sports: ['Baseball', 'Football', 'Basketball', 'Hockey'] }))} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10.5px] font-semibold text-slate-200">Major 4</button>
                            <button onClick={() => setCrawlOpts((p) => ({ ...p, sports: [] }))} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[10.5px] text-slate-400">Clear</button>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-1.5">
                          {ALL_TCDB_SPORTS.map((sp) => {
                            const activeSp = (crawlOpts.sports || []).includes(sp);
                            const minYr = SPORT_FIRST_CARD_YEAR[sp] || 1880;
                            return (
                              <button
                                key={sp}
                                onClick={() => toggleCrawlSport(sp)}
                                title={`${sp} earliest card year on TCDB: ${minYr} (years prior to ${minYr} are skipped automatically)`}
                                className={`px-2.5 py-1 rounded-lg border text-xs font-semibold transition ${activeSp ? skin.accentActive : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'}`}
                              >
                                {activeSp ? '☑️' : '⬜'} {sp} <span className="font-mono text-[10px] opacity-75">({minYr}+)</span>
                              </button>
                            );
                          })}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
                          <div className="md:col-span-2">
                            <label className="block text-[10.5px] text-slate-400 mb-1">Start Year</label>
                            <input
                              type="number" min="1880" max={curCalYear + 1}
                              value={crawlOpts.startYear}
                              onChange={(e) => setCrawlOpts((p) => ({ ...p, startYear: parseInt(e.target.value, 10) || 1900 }))}
                              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono"
                            />
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-[10.5px] text-slate-400 mb-1">End Year</label>
                            <input
                              type="number" min="1880" max={curCalYear + 1}
                              value={crawlOpts.endYear}
                              onChange={(e) => setCrawlOpts((p) => ({ ...p, endYear: parseInt(e.target.value, 10) || curCalYear }))}
                              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono"
                            />
                          </div>
                          <div className="md:col-span-4 space-y-1">
                            <div className="text-[10.5px] text-slate-400">Quick Year Range Presets</div>
                            <div className="flex flex-wrap gap-1">
                              {[
                                [`${curCalYear}–${curCalYear + 1}`, curCalYear, curCalYear + 1],
                                ['2020–Now', 2020, curCalYear],
                                ['2000–Now', 2000, curCalYear],
                                ['1980–Now', 1980, curCalYear],
                                ['Full (1880–Now)', 1880, curCalYear],
                              ].map(([lbl, sy, ey]) => (
                                <button
                                  key={lbl}
                                  onClick={() => setCrawlOpts((p) => ({ ...p, startYear: sy, endYear: ey }))}
                                  className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[10.5px] text-slate-200 font-medium"
                                >
                                  {lbl}
                                </button>
                              ))}
                            </div>
                          </div>
                          <div className="md:col-span-2 p-2 rounded-lg bg-emerald-950/35 border border-emerald-700/40 text-[10px] text-emerald-200 leading-snug space-y-1">
                            <label className="flex items-center gap-1.5 font-bold text-emerald-100 cursor-pointer">
                              <input type="checkbox" checked={!!crawlOpts.fetchImagePct} onChange={(e) => setCrawlOpts((p) => ({ ...p, fetchImagePct: e.target.checked }))} />
                              <span>⚡ Fetch Live Img % &amp; Categories</span>
                            </label>
                            <div className="text-emerald-200/80">Single-pass HTML extracts exact Categories &amp; <code>Img %</code> with zero extra requests.</div>
                          </div>
                          <div className="md:col-span-2">
                            <button
                              disabled={(crawlOpts.sports || []).length === 0 || crawlTotalSteps <= 0}
                              onClick={() => {
                                const sy = Math.min(parseInt(crawlOpts.startYear, 10) || 2020, parseInt(crawlOpts.endYear, 10) || curCalYear);
                                const ey = Math.max(parseInt(crawlOpts.startYear, 10) || 2020, parseInt(crawlOpts.endYear, 10) || curCalYear);
                                const spList = crawlOpts.sports || ['Baseball'];
                                triggerJob(
                                  'set_browser',
                                  `TCDB Directory Crawl (${spList.length === ALL_TCDB_SPORTS.length ? 'All 9 Sports' : spList.join(', ')} ${sy}-${ey})`,
                                  'crawl_tcdb_directory',
                                  {
                                    sports: spList,
                                    start_year: sy,
                                    end_year: ey,
                                    fetch_set_image_pct: !!crawlOpts.fetchImagePct,
                                    max_image_pct_fetches: parseInt(crawlOpts.maxImagePctFetches, 10) || 0,
                                    estimated_total: Math.max(1, crawlTotalSteps),
                                  }
                                );
                                setShowCrawlWidget(false);
                              }}
                              className={`w-full py-2 px-3 rounded-xl font-bold text-xs disabled:opacity-40 ${skin.accentBtn}`}
                            >
                              🚀 Launch ({crawlTotalSteps.toLocaleString()} valid pg)
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {showQuickAddWidget && (
                      <div className="p-3.5 bg-slate-950/90 border border-cyan-500/30 rounded-xl grid grid-cols-2 md:grid-cols-5 gap-2 shrink-0">
                        <input value={quickAdd.url} onChange={(e) => setQuickAdd({ ...quickAdd, url: e.target.value })} placeholder="TCDB ViewSet URL..." className="md:col-span-2 bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs" />
                        <input value={quickAdd.folder} onChange={(e) => setQuickAdd({ ...quickAdd, folder: e.target.value })} placeholder="Folder Name" className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs" />
                        <select value={quickAdd.sport} onChange={(e) => setQuickAdd({ ...quickAdd, sport: e.target.value })} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs">{ALL_TCDB_SPORTS.map((sp) => <option key={sp}>{sp}</option>)}</select>
                        <button onClick={() => { if (!quickAdd.url || !quickAdd.folder) return; stageSetIntoCart({ Set_Name: quickAdd.folder.replace(/_/g, ' '), Folder_Name: quickAdd.folder.replace(/\s+/g, '_'), Sport: quickAdd.sport, Year: quickAdd.year, Manufacturer: quickAdd.manufacturer, TCDB_URL: quickAdd.url }); setQuickAdd({ ...quickAdd, url: '', folder: '' }); }} className={`rounded-lg font-bold text-xs ${skin.accentBtn}`}>➕ Stage</button>
                      </div>
                    )}

                    {/* FILTER ROW: SPORT, MANUFACTURER, CATEGORY (REPLACES ERA), SEARCH, HIDE TRACKED, CLEAR */}
                    <div className="grid grid-cols-2 md:grid-cols-6 gap-2 shrink-0">
                      <select value={dirSportFilter} onChange={(e) => setDirSportFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                        <option>All Sports</option>
                        {Array.from(new Set(directoryRows.map((d) => d.Sport).filter(Boolean))).sort().map((sp) => <option key={sp}>{sp}</option>)}
                      </select>
                      <select value={dirMfgFilter} onChange={(e) => setDirMfgFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                        <option>All Manufacturers</option>
                        {Array.from(new Set(directoryRows.map((d) => d.Manufacturer).filter(Boolean))).sort().map((m) => <option key={m}>{m}</option>)}
                      </select>
                      <select value={dirCategoryFilter} onChange={(e) => setDirCategoryFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                        <option>All Categories</option>
                        {Array.from(new Set(directoryRows.map((d) => d.Category || 'Major Release').filter(Boolean))).sort().map((cat) => <option key={cat}>{cat}</option>)}
                      </select>
                      <input value={dirSearch} onChange={(e) => setDirSearch(e.target.value)} placeholder="Search Set Name, Year, SID..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                      <label className="flex items-center gap-1.5 text-xs text-slate-300 px-2"><input type="checkbox" checked={dirHideTracked} onChange={(e) => setDirHideTracked(e.target.checked)} /> Hide Tracked</label>
                      <button onClick={() => { setDirSportFilter('All Sports'); setDirMfgFilter('All Manufacturers'); setDirCategoryFilter('All Categories'); setDirEraFilter('All Eras'); setDirSearch(''); setDirHideTracked(false); }} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">🧹 Clear Filters</button>
                    </div>

                    {/* AUTO-UPDATING ERA TABS BAR */}
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-800 shrink-0">
                      <button
                        onClick={() => setDirEraFilter('All Eras')}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap border transition ${activeEraTab === 'All Eras' ? skin.accentActive : 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700'}`}
                      >
                        All Eras ({baseFilteredDir.length.toLocaleString()})
                      </button>
                      {sortedEraKeys.map((era) => (
                        <button
                          key={era}
                          onClick={() => setDirEraFilter(era)}
                          className={`px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap border transition ${activeEraTab === era ? skin.accentActive : 'bg-slate-950/70 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700'}`}
                        >
                          {era} ({(eraCountsMap[era] || 0).toLocaleString()})
                        </button>
                      ))}
                    </div>

                    <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                      <table className="w-full text-left text-xs whitespace-nowrap">
                        <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                          <tr><th className="p-2">Stage</th><th className="p-2">Status</th><th className="p-2">Year</th><th className="p-2">Sport</th><th className="p-2">Set Name</th><th className="p-2">Manufacturer</th><th className="p-2">Category</th><th className="p-2">Img %</th><th className="p-2">Folder Name</th><th className="p-2">SID</th><th className="p-2">TCDB</th></tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                          {pageSliceDir.map((d, i) => {
                            const isTrk = trkUrls.has(d.TCDB_URL);
                            const isInCart = cartUrls.has(d.TCDB_URL);
                            return (
                              <tr key={d.SID || i} className="hover:bg-slate-800/40">
                                <td className="p-2"><button onClick={() => stageSetIntoCart({ Set_Name: d.Set_Name, Folder_Name: d.Folder_Name || sanitizeFolderName(d.Set_Name), Sport: d.Sport, Year: d.Year, Manufacturer: d.Manufacturer, TCDB_URL: d.TCDB_URL })} className="px-2 py-0.5 rounded-lg bg-sky-900/70 hover:bg-sky-700 text-sky-200 text-[10px] font-bold">+ Stage</button></td>
                                <td className="p-2">{isTrk ? <span className="text-emerald-400 font-bold">✅ Tracked</span> : isInCart ? <span className="text-amber-300 font-bold">🛒 In Cart</span> : <span className="text-slate-400">Available</span>}</td>
                                <td className="p-2 font-mono">{d.Year}</td>
                                <td className="p-2">{d.Sport}</td>
                                <td className="p-2 font-semibold text-white">{d.Set_Name}</td>
                                <td className="p-2">{d.Manufacturer}</td>
                                <td className="p-2 text-slate-300">{d.Category || 'Major Release'}</td>
                                <td className="p-2 font-mono text-sky-300">{d.Image_Pct || '—'}</td>
                                <td className="p-2 font-mono text-slate-300">{d.Folder_Name}</td>
                                <td className="p-2 font-mono text-slate-400">{d.SID}</td>
                                <td className="p-2"><a href={d.TCDB_URL} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">Open ↗</a></td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0">
                      <span>Showing {finalDirRows.length === 0 ? 0 : ((safeDirPage - 1) * dirPageSize + 1).toLocaleString()}–{Math.min(finalDirRows.length, safeDirPage * dirPageSize).toLocaleString()} of {finalDirRows.length.toLocaleString()} sets in {activeEraTab}</span>
                      <div className="flex items-center gap-2">
                        <select value={dirPageSize} onChange={(e) => { setDirPageSize(parseInt(e.target.value, 10) || 250); setDirPage(1); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                          <option value={100}>100 / page</option><option value={250}>250 / page</option><option value={500}>500 / page</option>
                        </select>
                        <button onClick={() => setDirPage((p) => Math.max(1, p - 1))} disabled={safeDirPage <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                        <span className="font-mono text-white">Page {safeDirPage} / {totPages}</span>
                        <button onClick={() => setDirPage((p) => Math.min(totPages, p + 1))} disabled={safeDirPage >= totPages} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 9. GRADING RECOMMENDATION ENGINE */}
            {activePage === 'grading_engine' && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                  <h2 className="text-sm font-bold text-white">🎯 Grading Recommendation Engine &amp; Live Grading Availability</h2>
                  <div className="flex flex-wrap items-center gap-2">
                    <button onClick={() => { setInspectorIdx(0); openHiddenPage('grading_inspector'); }} disabled={gradingCandidates.length === 0} className={`px-3 py-1.5 rounded-xl font-bold text-xs disabled:opacity-40 ${skin.accentBtn}`}>🔬 Launch Candidate Inspector ({gradingCandidates.length})</button>
                    <button onClick={() => setShowCompsExplorer(!showCompsExplorer)} className={`px-3 py-1.5 rounded-xl border text-xs font-semibold ${showCompsExplorer ? skin.accentActive : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'}`}>📊 Comps Cache ({marketData.comps?.length || 0})</button>
                    <button onClick={() => fetch(`${NODE_API_BASE}/market/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'purge_comps' }) }).then((r) => r.json()).then((res) => { if (res.success) { refreshAllHubData(); pushNotification('Comps Purged & Recalculated', `Reset ${res.resetCount || 0} mismatched comp(s) across inventory.`, 'Market', 'success'); } })} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-300 text-xs font-semibold">🧹 Purge Mismatched Comps</button>
                    <button onClick={() => fetch(`${NODE_API_BASE}/market/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'refresh_tiers' }) }).then((r) => r.json()).then((res) => { if (res.success) { setMarketData((m) => ({ ...m, tiers: res.tiers })); pushNotification('Grading Tiers Updated', 'Refreshed live PSA & BGS availability.', 'Market', 'success'); } })} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold">🔄 Refresh Tiers</button>
                    <button onClick={() => triggerJob('market_analytics', 'Refresh Market Comps & Grading Availability', 'refresh_market_valuations')} className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs">🚀 Refresh Comps &amp; ROI</button>
                  </div>
                </div>

                {showCompsExplorer && (
                  <div className="p-3 bg-slate-950/90 border border-sky-700/40 rounded-xl space-y-2 shrink-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-sky-300">📊 SportsCardsPro Market Comps Cache ({marketData.comps?.length || 0} Designs)</span>
                      <input value={compsSearch} onChange={(e) => setCompsSearch(e.target.value)} placeholder="Search cached comps..." className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs" />
                    </div>
                    <div className="max-h-48 overflow-auto border border-slate-800 rounded-lg">
                      <table className="w-full text-left text-[11px] whitespace-nowrap">
                        <thead className="bg-slate-900 text-slate-400 sticky top-0"><tr><th className="p-1.5">Set</th><th className="p-1.5">Card #</th><th className="p-1.5">Player</th><th className="p-1.5">Subset</th><th className="p-1.5">Raw</th><th className="p-1.5">Source</th><th className="p-1.5">PSA 9</th><th className="p-1.5">BGS 9.5</th><th className="p-1.5">PSA 10</th><th className="p-1.5">Links</th></tr></thead>
                        <tbody className="divide-y divide-slate-800">
                          {(marketData.comps || []).filter((cm) => !compsSearch.trim() || `${cm.Set} ${cm['Card Number']} ${cm.Player} ${cm.Subset}`.toLowerCase().includes(compsSearch.toLowerCase())).slice(0, 150).map((cm, ci) => (
                            <tr key={ci} className="hover:bg-slate-800/40">
                              <td className="p-1.5">{cm.Set}</td>
                              <td className="p-1.5 font-mono">#{cm['Card Number']}</td>
                              <td className="p-1.5 font-bold text-white">{cm.Player}</td>
                              <td className="p-1.5">{cm.Subset}</td>
                              <td className="p-1.5 font-mono">{safeNum(cm.Ungraded, 0) > 0 ? fmtCurrency(cm.Ungraded) : <span className="text-slate-500">Uncomped</span>}</td>
                              <td className="p-1.5 text-[10px] text-slate-300">{cm.Valuation_Source || 'Legacy'}</td>
                              <td className="p-1.5 font-mono">{safeNum(cm.Grade_9, 0) > 0 ? fmtCurrency(cm.Grade_9) : '—'}</td>
                              <td className="p-1.5 font-mono">{safeNum(cm.BGS_9_5, 0) > 0 ? fmtCurrency(cm.BGS_9_5) : '—'}</td>
                              <td className="p-1.5 font-mono text-emerald-400 font-bold">{safeNum(cm.PSA_10, 0) > 0 ? fmtCurrency(cm.PSA_10) : '—'}</td>
                              <td className="p-1.5 flex gap-2">
                                {(cm.Card_URL || cm.Source_URL) && <a href={cm.Card_URL || cm.Source_URL} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">Card ↗</a>}
                                {cm.Comp_URL && <a href={cm.Comp_URL} target="_blank" rel="noreferrer" className="text-amber-300 hover:underline">Comp ↗</a>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5 shrink-0 space-y-3`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-3 text-xs">
                      <span className="font-bold text-white">🏛️ Grading Availability:</span>
                      <span className="px-2.5 py-1 rounded-lg bg-rose-950/70 border border-rose-700/60 text-rose-200 font-mono">
                        🟥 PSA Best Open: {economicalTiers.PSA ? `${economicalTiers.PSA.tier} (${fmtCurrency(economicalTiers.PSA.price)} • Max ${safeNum(economicalTiers.PSA.max_value) >= 900000 ? 'Unlim.' : fmtCurrency(economicalTiers.PSA.max_value)} • ${economicalTiers.PSA.turnaround})` : 'N/A'}
                      </span>
                      <span className="px-2.5 py-1 rounded-lg bg-blue-950/70 border border-blue-700/60 text-blue-200 font-mono">
                        🟦 BGS Best Open: {economicalTiers.BGS ? `${economicalTiers.BGS.tier} (${fmtCurrency(economicalTiers.BGS.price)} • ${economicalTiers.BGS.turnaround})` : 'N/A'}
                      </span>
                    </div>
                    <button onClick={() => setAvailabilityExpanded(!availabilityExpanded)} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-300 text-xs font-bold border border-slate-700">
                      {availabilityExpanded ? '▲ Collapse Full Tables' : '▼ Show All Tiers'}
                    </button>
                  </div>
                  {availabilityExpanded && (
                    <div className="space-y-3 pt-1">
                      {['PSA', 'BGS'].map((grader) => {
                        const list = marketData.tiers?.[grader] || [];
                        const colWidthStyle = { width: `calc((100% - 116px) / ${Math.max(1, list.length)})` };
                        return (
                          <div key={grader} className="overflow-x-auto border border-slate-800 rounded-xl bg-slate-950/90">
                            <table className="w-full table-fixed text-center text-[11px]">
                              <thead className="border-b border-slate-800">
                                <tr>
                                  <th className="p-2 text-left text-slate-400 font-bold" style={{ width: '116px' }}>{grader === 'PSA' ? '🟥 PSA Tier' : '🟦 BGS Tier'}</th>
                                  {list.map((t, i) => {
                                    const mParen = grader === 'BGS' ? String(t.tier || '').match(/^(.+?)\s*(\(.+\))$/) : null;
                                    const mainTier = mParen ? mParen[1].trim() : t.tier;
                                    const subTier = grader === 'PSA'
                                      ? (safeNum(t.max_value) >= 900000 ? 'Unlim. Max' : `(${fmtCurrency(t.max_value).replace('.00', '')} Max)`)
                                      : (mParen ? mParen[2].trim() : '');
                                    return (
                                      <th key={i} className="p-2 align-bottom" style={colWidthStyle}>
                                        <div className="font-bold text-white leading-tight">{mainTier}</div>
                                        {subTier && <div className="text-[10px] text-slate-400 font-normal leading-tight mt-0.5">{subTier}</div>}
                                      </th>
                                    );
                                  })}
                                </tr>
                              </thead>
                              <tbody>
                                <tr className="border-b border-slate-800/70">
                                  <td className="p-2 text-left font-semibold text-slate-400" style={{ width: '116px' }}>Status / Fee</td>
                                  {list.map((t, i) => (
                                    <td key={i} className="p-2 font-mono font-bold text-white whitespace-nowrap" style={colWidthStyle}>
                                      {String(t.status).toLowerCase() === 'open' ? '🟢' : '🔴'} {fmtCurrency(t.price)}
                                    </td>
                                  ))}
                                </tr>
                                <tr>
                                  <td className="p-2 text-left font-semibold text-slate-400" style={{ width: '116px' }}>Turnaround</td>
                                  {list.map((t, i) => (
                                    <td key={i} className="p-2 text-slate-300 whitespace-nowrap" style={colWidthStyle}>{t.turnaround}</td>
                                  ))}
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className={`flex-1 min-h-0 flex flex-col gap-2.5 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                    <h3 className="text-xs font-bold text-white uppercase">Recommended Candidates ({gradingCandidates.length} — &lt; 7.0 Grade Guard Active)</h3>
                    <div className="flex items-center gap-2">
                      <select value={gradeRecSetFilter} onChange={(e) => setGradeRecSetFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1 text-xs">
                        <option>All Sets</option>
                        {ownedSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                      </select>
                      <button onClick={() => setGradeRecSetFilter('All Sets')} className="px-2.5 py-1 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-300">🧹 Clear Filters</button>
                    </div>
                  </div>
                  <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                    <table className="w-full text-left text-xs whitespace-nowrap">
                      <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                        <tr><th className="p-2">Inspect</th><th className="p-2">SKU</th><th className="p-2">Set</th><th className="p-2">Card #</th><th className="p-2">Player</th><th className="p-2">Subset</th><th className="p-2">Est PSA/BGS</th><th className="p-2">Raw</th><th className="p-2">Est Slab</th><th className="p-2">Net Gain</th><th className="p-2">Recommendation</th></tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {gradingCandidates.map((c, idx) => (
                          <tr key={c.SKU} className="hover:bg-slate-800/40">
                            <td className="p-2"><button onClick={() => { setInspectorIdx(idx); openHiddenPage('grading_inspector'); }} className="px-2 py-0.5 rounded-lg bg-sky-900/70 hover:bg-sky-700 text-sky-200 text-[10px] font-bold">🔬 Inspect</button></td>
                            <td className="p-2 font-mono text-sky-400">{c.SKU}</td>
                            <td className="p-2">{c.Set}</td>
                            <td className="p-2 font-mono">#{c['Card Number']}</td>
                            <td className="p-2 font-bold text-white">{c.Player}</td>
                            <td className="p-2">{c.Subset}</td>
                            <td className="p-2 font-mono">PSA {c.Est_PSA} / BGS {c.Est_BGS}</td>
                            <td className="p-2 font-mono">{fmtCurrency(c.Raw_Price)}</td>
                            <td className="p-2 font-mono text-sky-300">{fmtCurrency(c.Best_Grader === 'BGS' ? (c.Est_Graded_BGS || c.BGS_9_5_Price) : (c.Est_Graded_PSA || c.PSA_10_Price))}</td>
                            <td className="p-2 font-mono text-emerald-400 font-bold">{fmtCurrency(c.Max_Net_Gain, true)}</td>
                            <td className="p-2 text-amber-300 font-semibold">{c.Recommended_Action}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* 10. GRADING CANDIDATE INSPECTOR */}
            {activePage === 'grading_inspector' && (
              <div className={inspectorMode === 'deep_dive' ? 'flex-1 min-h-0 h-full flex flex-col overflow-hidden' : 'space-y-4'}>
                {gradingCandidates.length === 0 ? (
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-6 text-center text-xs text-slate-400`}>No grading candidates match the current filter.</div>
                ) : (() => {
                  const safeIdx = Math.max(0, Math.min(inspectorIdx, gradingCandidates.length - 1));
                  const card = gradingCandidates[safeIdx];
                  const sFold = encodeURIComponent(sanitizeFolderName(card.Set));
                  if (inspectorMode === 'deep_dive') {
                    return (
                      <GradingDeepDiveStudio
                        key={`grad-gdd-${card.SKU}`}
                        card={card}
                        targetType="inventory"
                        cardIndex={safeIdx}
                        totalCards={gradingCandidates.length}
                        onPrev={() => setInspectorIdx((i) => Math.max(0, i - 1))}
                        onNext={() => setInspectorIdx((i) => Math.min(gradingCandidates.length - 1, i + 1))}
                        onBack={() => setActivePage('grading_engine')}
                        backLabel="Grading Hub"
                        onSwitchIndividual={() => setInspectorMode('individual')}
                        cardOptions={gradingCandidates.map((gc, gi) => ({
                          index: gi,
                          label: `${gi + 1}/${gradingCandidates.length} • SKU ${gc.SKU} — #${gc['Card Number']} ${gc.Player}`,
                        }))}
                        onSelectCardIndex={(idx) => setInspectorIdx(idx)}
                        onCardUpdated={(res) => {
                          if (Array.isArray(res?.rows)) {
                            setInventory(res.rows);
                          } else if (res?.card) {
                            setInventory((prev) => prev.map((row) => (row.SKU === res.card.SKU ? { ...row, ...res.card } : row)));
                          }
                        }}
                        skin={skin}
                        pushNotification={pushNotification}
                      />
                    );
                  }
                  return (
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-5 space-y-4`}>
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <button type="button" onClick={() => setActivePage('grading_engine')} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold">⬅ Grading Hub</button>
                          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-0.5 text-xs">
                            <button type="button" className={`px-2.5 py-1 rounded-lg font-bold ${skin.accentActive}`}>🪟 Individual</button>
                            <button type="button" onClick={() => setInspectorMode('deep_dive')} className="px-2.5 py-1 rounded-lg font-bold text-slate-400 hover:text-white">🔬 Deep-Dive</button>
                          </div>
                          <div>
                            <div className="text-[11px] font-mono text-sky-400 uppercase">🔬 Grading Candidate Inspector — Card {safeIdx + 1} of {gradingCandidates.length}</div>
                            <h2 className="text-lg font-bold text-white">SKU {card.SKU} — {card.Set} #{card['Card Number']} {card.Player} ({card.Subset})</h2>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => setInspectorIdx((i) => Math.max(0, i - 1))} disabled={safeIdx === 0} className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-xs font-bold">◀ Previous Card</button>
                          <button onClick={() => setInspectorIdx((i) => Math.min(gradingCandidates.length - 1, i + 1))} disabled={safeIdx >= gradingCandidates.length - 1} className={`px-4 py-2 rounded-xl text-xs font-bold disabled:opacity-30 ${skin.accentBtn}`}>Next Card ▶</button>
                        </div>
                      </div>
                      <SideBySideCardComparison
                        scanFrontUrl={card.Front_File ? `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Front_File)}` : ''}
                        scanBackUrl={card.Back_File ? `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Back_File)}` : ''}
                        cornersUrl={card.Corners_File ? `${API_ORIGIN}/static/cards/${sFold}/${encodeURIComponent(card.Corners_File)}` : ''}
                        setName={card.Set} subsetName={card.Subset} cardNumber={card['Card Number']}
                        initialTmplFrontRel={card.Matched_Template_Front} initialTmplBackRel={card.Matched_Template_Back}
                        heightClass="h-72"
                      />
                      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3"><div className="text-[10px] text-slate-400">Est. PSA / BGS</div><div className="text-base font-bold text-white font-mono">PSA {card.Est_PSA} / BGS {card.Est_BGS}</div></div>
                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3"><div className="text-[10px] text-slate-400">Centering (L/R | T/B)</div><div className="text-base font-bold text-sky-300 font-mono">{card.Centering_LR || '—'} | {card.Centering_TB || '—'}</div></div>
                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3"><div className="text-[10px] text-slate-400">Raw Value</div><div className="text-base font-bold text-white font-mono">{fmtCurrency(card.Raw_Price)}</div></div>
                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3"><div className="text-[10px] text-slate-400">Est. Slab (PSA / BGS)</div><div className="text-sm font-bold text-sky-400 font-mono">{fmtCurrency(card.Est_Graded_PSA || card.PSA_10_Price)} / {fmtCurrency(card.Est_Graded_BGS || card.BGS_9_5_Price)}</div></div>
                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3"><div className="text-[10px] text-slate-400">Net EV Gain</div><div className="text-base font-bold text-emerald-400 font-mono">{fmtCurrency(card.Max_Net_Gain, true)}</div></div>
                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3"><div className="text-[10px] text-slate-400">Best Grader</div><div className="text-base font-bold text-amber-300">{card.Best_Grader}</div></div>
                      </div>
                      <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-1 text-xs">
                        <div><span className="font-bold text-slate-400">Recommendation:</span> <span className="text-emerald-300 font-bold">{card.Recommended_Action}</span></div>
                        <div><span className="font-bold text-slate-400">10x Loupe Notes:</span> <span className="text-slate-200">{renderGradingNotesWithBadges(card.Grading_Notes)}</span></div>
                        <div><span className="font-bold text-slate-400">Subgrades:</span> Centering {card.Sub_Centering} • Corners {card.Sub_Corners} • Edges {card.Sub_Edges} • Surface {card.Sub_Surface}</div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* 11. MULTI-CARD, LOT & SET SUGGESTIONS */}
            {activePage === 'lot_suggestions' && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 shrink-0`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-sm font-bold text-white">📚 Multi-Card, Lot &amp; Set Suggestions ({lotsData.lots.length} Bundles)</h2>
                      <p className="text-xs text-slate-400">Retains your best-graded copy for PC and packages surplus duplicates into Complete Sets, Team Sets &amp; Rainbow Lots.</p>
                    </div>
                    <button onClick={() => fetch(`${NODE_API_BASE}/sales/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'auto_allocate', defaultRetainQty: 1 }) }).then((r) => r.json()).then((res) => { if (res.success) { refreshAllHubData(); pushNotification('Auto-Allocation Complete', `Retained ${res.stats?.pc_tagged || 0} PC copies, marked ${res.stats?.for_sale_tagged || 0} surplus For Sale.`, 'Sales', 'success'); } })} className={`px-3 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}>
                      ⚡ Auto-Allocate PC (Best Grade) vs. For Sale
                    </button>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                    <select value={lotCatF} onChange={(e) => setLotCatF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs"><option>All Categories</option>{Array.from(new Set(lotsData.lots.map((l) => l.Lot_Category).filter(Boolean))).map((c) => <option key={c}>{c}</option>)}</select>
                    <select value={lotSportF} onChange={(e) => setLotSportF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs"><option>All Sports</option><option>Baseball</option><option>Football</option><option>Basketball</option><option>Hockey</option><option>Soccer</option><option>Racing</option></select>
                    <select value={lotSetF} onChange={(e) => setLotSetF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs"><option>All Sets</option>{Array.from(new Set(lotsData.lots.map((l) => l.Set).filter(Boolean))).map((s) => <option key={s}>{s}</option>)}</select>
                    <input value={lotTeamF} onChange={(e) => setLotTeamF(e.target.value)} placeholder="Filter Team..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                    <input value={lotPlayerF} onChange={(e) => setLotPlayerF(e.target.value)} placeholder="Filter Player..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                    <button onClick={() => { setLotCatF('All Categories'); setLotSportF('All Sports'); setLotSetF('All Sets'); setLotTeamF(''); setLotPlayerF(''); }} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">🧹 Clear Filters</button>
                  </div>
                </div>
                <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-2xl bg-slate-900/60">
                  <table className="w-full text-left text-xs whitespace-nowrap">
                    <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                      <tr><th className="p-2">Stage</th><th className="p-2">Lot ID</th><th className="p-2">Category</th><th className="p-2">Sport</th><th className="p-2">Lot Title</th><th className="p-2">Cards</th><th className="p-2">Indiv. Sum</th><th className="p-2">Rec. Lot Price</th><th className="p-2">Strategy</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {lotsData.lots.filter((l) => {
                        if (lotCatF !== 'All Categories' && l.Lot_Category !== lotCatF) return false;
                        if (lotSportF !== 'All Sports' && inferSportFromSet(l.Set) !== lotSportF) return false;
                        if (lotSetF !== 'All Sets' && l.Set !== lotSetF) return false;
                        if (lotTeamF.trim() && !`${l.Lot_Title} ${l.Rationale}`.toLowerCase().includes(lotTeamF.toLowerCase())) return false;
                        if (lotPlayerF.trim() && !`${l.Lot_Title} ${l.Rationale}`.toLowerCase().includes(lotPlayerF.toLowerCase())) return false;
                        return true;
                      }).map((l) => (
                        <tr key={l.Lot_ID} className="hover:bg-slate-800/40">
                          <td className="p-2">
                            <button
                              onClick={() => fetch(`${NODE_API_BASE}/sales/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'generate_lot_listing', lot: l }) }).then((r) => r.json()).then((res) => { if (res.success) { refreshAllHubData(); pushNotification('Lot Listing Staged', `Saved ${res.draftId} to Listing Writer drafts.`, 'Sales', 'success'); } })}
                              className="px-2 py-0.5 rounded-lg bg-emerald-950/80 hover:bg-emerald-800 text-emerald-200 border border-emerald-700 text-[10px] font-bold"
                            >
                              ✍️ Stage
                            </button>
                          </td>
                          <td className="p-2 font-mono text-sky-400">{l.Lot_ID}</td>
                          <td className="p-2">{l.Lot_Category}</td>
                          <td className="p-2 text-slate-400">{inferSportFromSet(l.Set)}</td>
                          <td className="p-2 font-bold text-white">{l.Lot_Title}</td>
                          <td className="p-2 font-mono">{l.Total_Cards}</td>
                          <td className="p-2 font-mono">{fmtCurrency(l.Sum_Individual_Raw_USD)}</td>
                          <td className="p-2 font-mono text-emerald-400 font-bold">{fmtCurrency(l.Recommended_Lot_Price_USD)}</td>
                          <td className="p-2 text-slate-300">{l.Pricing_Strategy}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 12. LISTING WRITER (SET BLURB EDITOR, GRANULAR CONTENT CHECKBOXES & SCOPED BATCH WRITER) */}
            {activePage === 'listing_writer' && (() => {
              const sourceBatchesList = Array.from(new Set(inventory.map((c) => c.Source_Batch).filter(Boolean))).sort();
              const existingDraftSkuSet = new Set(listingDrafts.map((d) => String(d.SKU_or_Lot_ID || '').trim()));
              const batchWriterMatchCount = inventory.filter((c) => {
                if (String(c.Status || '').toLowerCase() === 'sold') return false;
                const isPc = String(c.Hold_Tag || '').toLowerCase().includes('personal collection');
                if (['for_sale', 'unlisted', 'missing_drafts'].includes(batchWriterOpts.scope) && isPc) return false;
                if (batchWriterOpts.scope === 'unlisted' && String(c.Status || '').toLowerCase() !== 'in stock') return false;
                if (batchWriterOpts.scope === 'missing_drafts' && existingDraftSkuSet.has(String(c.SKU || '').trim())) return false;
                if (batchWriterOpts.scope === 'set' && batchWriterOpts.setName !== 'All Sets' && c.Set !== batchWriterOpts.setName) return false;
                if (batchWriterOpts.scope === 'batch' && batchWriterOpts.sourceBatch !== 'All Batches' && c.Source_Batch !== batchWriterOpts.sourceBatch) return false;
                return true;
              }).length;
              const enabledSectionsCount = Object.values(listingContentOpts).filter(Boolean).length;
              const toggleContentOpt = (k) => setListingContentOpts((prev) => ({ ...prev, [k]: !prev[k] }));
              const contentToggleDefs = [
                ['include_opening', 'Opening Overview'],
                ['include_set_blurb', 'Card Set Blurb'],
                ['include_player_bio', 'Player Bio'],
                ['include_player_stats', 'Career/Season Stats'],
                ['include_player_accolades', 'Accolades'],
                ['include_pregrade_notes', 'Scanner Pre-Grade'],
                ['include_grading_disclaimer', 'Grading Disclaimer'],
                ['include_shipping_policy', 'Shipping Policy'],
                ['include_as_is_disclaimer', '48h As-Is Disclaimer'],
                ['include_sku_ref', 'Inventory SKU Ref'],
              ];

              return (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
                  <div className={`lg:col-span-7 ${skin.cardBg} border ${skin.border} rounded-2xl p-4 flex flex-col gap-3 min-h-0 overflow-y-auto`}>
                    <div className="flex items-center justify-between shrink-0">
                      <h2 className="text-sm font-bold text-white">✍️ {editingDraftId ? `Editing Saved Draft (${editingDraftId})` : 'Listing, Set Blurb & Player Bio Writer Studio'}</h2>
                      {editingDraftId && <button onClick={() => { setEditingDraftId(''); setWriterCopy({ SEO_Title_80Char: '', Description_Body: '', Recommended_Price: '' }); }} className="px-2.5 py-1 rounded-lg bg-slate-800 text-xs text-slate-300">➕ New Listing</button>}
                    </div>

                    {!editingDraftId ? (
                      <div className="flex flex-wrap gap-2 shrink-0">
                        <select value={writerSku} onChange={(e) => setWriterSku(e.target.value)} className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs">
                          {inventory.filter((c) => c.Status !== 'Sold').slice(0, 400).map((c) => (
                            <option key={c.SKU} value={c.SKU}>SKU {c.SKU} — {c.Set} #{c['Card Number']} {c.Player} [{c.Subset}]</option>
                          ))}
                        </select>
                        <button
                          onClick={() => fetch(`${NODE_API_BASE}/sales/action`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              action: 'generate_listing',
                              sku: writerSku,
                              includeBio: true,
                              includePregrade: !!listingContentOpts.include_pregrade_notes,
                              contentOptions: listingContentOpts,
                              customSetBlurb: setBlurbText,
                              saveDraft: false,
                            }),
                          }).then((r) => r.json()).then((res) => res.success && setWriterCopy(res))}
                          className={`px-3 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}
                        >
                          ✨ Generate Copy
                        </button>
                        <button
                          onClick={() => fetch(`${NODE_API_BASE}/sales/action`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              action: 'generate_listing',
                              sku: writerSku,
                              includeBio: true,
                              includePregrade: !!listingContentOpts.include_pregrade_notes,
                              contentOptions: listingContentOpts,
                              customSetBlurb: setBlurbText,
                              customTitle: writerCopy.SEO_Title_80Char,
                              customPrice: writerCopy.Recommended_Price,
                              customDescription: writerCopy.Description_Body,
                              saveDraft: true,
                            }),
                          }).then((r) => r.json()).then((res) => { if (res.success) { setWriterCopy(res); refreshAllHubData(); pushNotification('Listing Draft Saved', `Saved draft for SKU ${writerSku}.`, 'Sales', 'success'); } })}
                          className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs"
                        >
                          💾 Save Draft
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2 bg-amber-950/40 border border-amber-700/50 rounded-xl px-3 py-2 text-xs shrink-0">
                        <span className="text-amber-200 font-semibold">Editing completed draft <code>{editingDraftId}</code></span>
                        <button onClick={() => fetch(`${NODE_API_BASE}/sales/drafts/update`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ Draft_ID: editingDraftId, ...writerCopy }) }).then((r) => r.json()).then((res) => { if (res.success) { setListingDrafts(res.drafts || []); pushNotification('Draft Updated', `Updated ${editingDraftId} in Listing_Drafts.csv.`, 'Sales', 'success'); } })} className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs">💾 Save Edits</button>
                      </div>
                    )}

                    {/* CONTENT INCLUDE / EXCLUDE TOGGLES */}
                    <div className="p-2.5 bg-slate-950/85 border border-slate-800 rounded-xl space-y-1.5 shrink-0">
                      <div className="flex items-center justify-between text-[10.5px]">
                        <span className="font-bold text-sky-300">🎛️ Listing Content Sections (Applied to Single &amp; Batch Runs)</span>
                        <div className="flex gap-2">
                          <button onClick={() => setListingContentOpts({ ...DEFAULT_LISTING_CONTENT_OPTS })} className="text-sky-400 hover:underline">All On</button>
                          <button onClick={() => setListingContentOpts({ ...DEFAULT_LISTING_CONTENT_OPTS, include_player_bio: false, include_player_stats: false, include_player_accolades: false, include_pregrade_notes: false })} className="text-slate-400 hover:text-white">Minimal</button>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {contentToggleDefs.map(([k, lbl]) => (
                          <label key={k} className={`flex items-center gap-1 px-2 py-1 rounded-lg border text-[10.5px] cursor-pointer transition ${listingContentOpts[k] ? 'bg-sky-950/70 border-sky-600/60 text-sky-200 font-semibold' : 'bg-slate-900 border-slate-800 text-slate-500'}`}>
                            <input type="checkbox" checked={!!listingContentOpts[k]} onChange={() => toggleContentOpt(k)} className="w-3 h-3" />
                            <span>{lbl}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    {/* CARD SET BLURB EDITOR */}
                    {listingContentOpts.include_set_blurb && setBlurbSet && (
                      <div className="p-2.5 bg-slate-950/85 border border-slate-800 rounded-xl space-y-1.5 shrink-0">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-[10.5px]">
                          <span className="font-bold text-amber-300">📚 Card Set Blurb — {setBlurbSet}</span>
                          <div className="flex gap-1.5">
                            {setBlurbDirty && (
                              <button
                                onClick={() => fetch(`${NODE_API_BASE}/sales/set-blurb`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ set: setBlurbSet, blurb: setBlurbText }) }).then((r) => r.json()).then((res) => { if (res?.success) { setSetBlurbDirty(false); pushNotification('Set Blurb Saved', `Saved custom collector blurb for ${setBlurbSet}.`, 'Sales', 'success'); } })}
                                className="px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold"
                              >
                                💾 Save Blurb
                              </button>
                            )}
                            <button
                              onClick={() => fetch(`${NODE_API_BASE}/sales/set-blurb?set=${encodeURIComponent(setBlurbSet)}&forceRefresh=true&resetToDefault=true`).then((r) => r.json()).then((res) => { if (res) { setSetBlurbText(res.blurb || ''); setSetBlurbDirty(false); } })}
                              className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                            >
                              🔄 Default
                            </button>
                          </div>
                        </div>
                        <textarea
                          rows={2}
                          value={setBlurbText}
                          onChange={(e) => { setSetBlurbText(e.target.value); setSetBlurbDirty(true); }}
                          placeholder="Collector overview blurb for this card set..."
                          className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-[11px] text-slate-200 leading-snug"
                        />
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-2 shrink-0">
                      <input value={writerCopy.SEO_Title_80Char} onChange={(e) => setWriterCopy({ ...writerCopy, SEO_Title_80Char: e.target.value })} placeholder="SEO Listing Title (<= 80 chars)" className="md:col-span-3 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-sky-300" />
                      <input value={writerCopy.Recommended_Price} onChange={(e) => setWriterCopy({ ...writerCopy, Recommended_Price: e.target.value })} placeholder="Price ($)" className="bg-slate-950 border border-emerald-700/60 rounded-xl px-3 py-2 text-xs font-mono text-emerald-300" />
                    </div>
                    <textarea value={writerCopy.Description_Body} onChange={(e) => setWriterCopy({ ...writerCopy, Description_Body: e.target.value })} placeholder="Click 'Generate Copy' or select a completed draft on the right to edit..." className="flex-1 min-h-[210px] w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs text-slate-200 leading-relaxed" />
                  </div>

                  <div className={`lg:col-span-5 ${skin.cardBg} border ${skin.border} rounded-2xl p-4 flex flex-col gap-3 min-h-0`}>
                    <div className="flex items-center justify-between shrink-0">
                      <h3 className="text-sm font-bold text-white">📄 Completed Listings ({listingDrafts.length})</h3>
                      <button
                        onClick={() => setShowBatchWriterPanel((v) => !v)}
                        className={`px-2.5 py-1 rounded-lg border text-xs font-bold ${showBatchWriterPanel ? skin.accentActive : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-sky-300'}`}
                      >
                        🚀 Batch Writer {showBatchWriterPanel ? '⌄' : '›'}
                      </button>
                    </div>

                    {showBatchWriterPanel && (
                      <div className="p-3 bg-slate-950/90 border border-sky-500/35 rounded-xl space-y-2.5 shrink-0 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-bold text-sky-300">⚡ Scoped Batch Listing Writer</span>
                          <span className="font-mono text-[10.5px] text-emerald-300">
                            {batchWriterMatchCount.toLocaleString()} matching card(s) • {enabledSectionsCount}/10 sections ON
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="block text-[10px] text-slate-400 mb-0.5">Target Scope</label>
                            <select value={batchWriterOpts.scope} onChange={(e) => setBatchWriterOpts((p) => ({ ...p, scope: e.target.value }))} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                              <option value="for_sale">All For-Sale / Offer Cards (Excl. PC)</option>
                              <option value="unlisted">Unlisted Sellable Cards Only</option>
                              <option value="missing_drafts">Sellable Cards Missing a Draft</option>
                              <option value="set">Specific Set Only</option>
                              <option value="batch">Specific Source Batch Only</option>
                              <option value="all_in_stock">All In-Stock Cards (Incl. PC)</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-[10px] text-slate-400 mb-0.5">Platform Target</label>
                            <select value={batchWriterOpts.platform} onChange={(e) => setBatchWriterOpts((p) => ({ ...p, platform: e.target.value }))} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                              <option>eBay &amp; CollX</option><option>eBay</option><option>CollX</option><option>COMC / Whatnot</option>
                            </select>
                          </div>
                          {batchWriterOpts.scope === 'set' && (
                            <div className="col-span-2">
                              <label className="block text-[10px] text-slate-400 mb-0.5">Choose Set</label>
                              <select value={batchWriterOpts.setName} onChange={(e) => setBatchWriterOpts((p) => ({ ...p, setName: e.target.value }))} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                                <option>All Sets</option>
                                {ownedSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                              </select>
                            </div>
                          )}
                          {batchWriterOpts.scope === 'batch' && (
                            <div className="col-span-2">
                              <label className="block text-[10px] text-slate-400 mb-0.5">Choose Source Batch</label>
                              <select value={batchWriterOpts.sourceBatch} onChange={(e) => setBatchWriterOpts((p) => ({ ...p, sourceBatch: e.target.value }))} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                                <option>All Batches</option>
                                {sourceBatchesList.map((b) => <option key={b}>{b}</option>)}
                              </select>
                            </div>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                            <input type="checkbox" checked={!!batchWriterOpts.forceRefreshBio} onChange={(e) => setBatchWriterOpts((p) => ({ ...p, forceRefreshBio: e.target.checked }))} />
                            Force Fresh Web Bio/Stats
                          </label>
                          <button
                            disabled={batchWriterMatchCount === 0}
                            onClick={() => {
                              triggerJob(
                                'sales_studio',
                                `Batch Listing Writer (${batchWriterOpts.scope}${batchWriterOpts.scope === 'set' ? `: ${batchWriterOpts.setName}` : ''} — ${batchWriterMatchCount} cards)`,
                                'batch_generate_listings',
                                {
                                  scope: batchWriterOpts.scope,
                                  set_name: batchWriterOpts.setName,
                                  source_batch: batchWriterOpts.sourceBatch,
                                  platform: batchWriterOpts.platform,
                                  force_refresh_bio: !!batchWriterOpts.forceRefreshBio,
                                  content_options: listingContentOpts,
                                  custom_set_blurb: (batchWriterOpts.scope === 'set' && batchWriterOpts.setName === setBlurbSet && setBlurbDirty) ? setBlurbText : '',
                                  estimated_total: Math.max(1, batchWriterMatchCount),
                                }
                              );
                              setShowBatchWriterPanel(false);
                            }}
                            className={`px-3 py-1.5 rounded-xl font-bold text-xs disabled:opacity-40 ${skin.accentBtn}`}
                          >
                            🚀 Run Batch Writer ({batchWriterMatchCount.toLocaleString()} Cards)
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="flex-1 min-h-0 overflow-y-auto space-y-2">
                      {listingDrafts.map((d) => (
                        <div key={d.Draft_ID} onClick={() => { setEditingDraftId(d.Draft_ID); setWriterCopy({ SEO_Title_80Char: d.SEO_Title_80Char || '', Description_Body: d.Description_Body || '', Recommended_Price: d.Recommended_Price || '' }); }} className={`p-3 rounded-xl border cursor-pointer transition text-xs ${editingDraftId === d.Draft_ID ? skin.accentActive : 'bg-slate-950 border-slate-800 hover:border-slate-700'}`}>
                          <div className="flex justify-between items-start gap-2">
                            <span className="font-bold text-white">{d.SEO_Title_80Char}</span>
                            <span className="font-mono text-emerald-400 font-bold shrink-0">{fmtCurrency(d.Recommended_Price)}</span>
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono mt-1">{d.Draft_ID} • SKU {d.SKU_or_Lot_ID} • {d.Created_At}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 13. SALES STRATEGY HUB */}
            {activePage === 'sales_strategy' && (
              <div className="space-y-4">
                <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-sm font-bold text-white">💡 Expense-Based Sales Strategy Recommendations</h2>
                      <div className="text-[11px] font-mono text-slate-400 mt-0.5">
                        Logged Expenses: {fmtCurrency(financialSummary.totalExpenses)} • Unit COGS: {fmtCurrency(strategyRecs.summary?.overall_unit_cogs ?? financialSummary.unitCostBasis)}/card
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleRecalculateSalesStrategy}
                      disabled={recalculatingStrategy}
                      className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold text-xs shadow-sm transition-colors"
                    >
                      {recalculatingStrategy ? '⏳ Recalculating...' : '🔄 Recalculate Sales Strategy'}
                    </button>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                    <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Verified Market Value</div>
                      <div className="text-base font-bold text-sky-400 font-mono">{fmtCurrency(strategyRecs.total_verified_market_value ?? financialSummary.totalRawVal)}</div>
                      <div className="text-[10px] text-slate-500 mt-0.5">{(strategyRecs.comped_cards_count ?? 0).toLocaleString()} comped card(s)</div>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Uncomped Cards</div>
                      <div className="text-base font-bold text-amber-300 font-mono">{(strategyRecs.uncomped_cards_count ?? 0).toLocaleString()}</div>
                      <div className="text-[10px] text-slate-500 mt-0.5">No $1.00 inflation</div>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Projected List Value</div>
                      <div className="text-base font-bold text-emerald-400 font-mono">{fmtCurrency(strategyRecs.total_projected_listing_value ?? financialSummary.totalRecVal)}</div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Asking w/ markup &amp; floors</div>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Last Recalculated</div>
                      <div className="text-xs font-bold text-white font-mono mt-0.5">{strategyRecs.last_recalculated_at || 'Not yet run'}</div>
                      <div className="text-[10px] text-sky-300 mt-0.5">
                        {strategyRecs.last_recalc_trigger === 'auto_on_commit' ? 'Auto on Commit' : (strategyRecs.last_recalc_trigger === 'manual' ? 'Manual Trigger' : 'Cached')}
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {(strategyRecs.recommendations || []).map((rec, i) => (
                      <div key={i} className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 flex flex-col justify-between gap-2 text-xs">
                        <div className="space-y-1">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${rec.priority === 'HIGH' ? 'bg-rose-950 text-rose-300 border border-rose-700' : rec.priority === 'MEDIUM' ? 'bg-amber-950 text-amber-300 border border-amber-700' : 'bg-emerald-950 text-emerald-300 border border-emerald-700'}`}>{rec.priority}</span>
                          <div className="font-bold text-white pt-1">{rec.title}</div>
                          <p className="text-[11px] text-slate-400 leading-relaxed">{rec.detail}</p>
                        </div>
                        {rec.suggested_patch && Object.keys(rec.suggested_patch).length > 0 && (
                          <button onClick={() => { const nextStrat = { ...pricingStrategy, ...rec.suggested_patch }; setPricingStrategy(nextStrat); saveExpensesAndPricing(true, nextStrat); }} className="w-full py-1.5 rounded-lg bg-sky-900/70 hover:bg-sky-700 text-sky-200 font-bold text-[11px]">✨ Apply Recommendation</button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
                <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-5 space-y-4`}>
                  <h3 className="text-sm font-bold text-white">📈 Markup, Floor Pricing &amp; Marketplace Fee Configuration</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      ['market_markup_pct', 'Market Markup (%)'],
                      ['make_offer_markup_pct', 'Make Me an Offer Markup (%)'],
                      ['rookie_serial_bonus_pct', 'Parallel / Serial Bonus (%)'],
                      ['gem_mint_pregrade_bonus_pct', 'Gem Mint (9.5+) Bonus (%)'],
                      ['global_min_price_floor', 'Global Min Price Floor ($)'],
                      ['target_min_net_profit_per_card', 'Target Min Net Profit ($)'],
                      ['marketplace_fee_pct', 'Marketplace Fee (%)'],
                      ['fixed_transaction_fee', 'Fixed Order Fee ($)'],
                    ].map(([k, lbl]) => (
                      <div key={k}>
                        <label className="block text-[11px] text-slate-400 mb-1">{lbl}</label>
                        <input type="number" step="0.25" value={pricingStrategy[k] ?? 0} onChange={(e) => setPricingStrategy({ ...pricingStrategy, [k]: parseFloat(e.target.value) || 0 })} className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs font-mono" />
                      </div>
                    ))}
                  </div>
                  <button onClick={() => saveExpensesAndPricing(true)} className={`px-4 py-2 rounded-xl font-bold text-xs ${skin.accentBtn}`}>💾 Save Strategy &amp; Recalculate All Inventory Prices</button>
                </div>
              </div>
            )}

            {/* 14. SOLD CARDS */}
            {activePage === 'sold_cards' && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className="grid grid-cols-2 md:grid-cols-6 gap-2.5 shrink-0">
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Cards Sold</div><div className="text-lg font-bold text-white">{soldCards.length.toLocaleString()}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Gross Revenue</div><div className="text-lg font-bold text-sky-400">{fmtCurrency(financialSummary.totalRevenue)}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Marketplace Fees</div><div className="text-lg font-bold text-rose-400">{fmtCurrency(financialSummary.totalFees)}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Seller-Paid Shipping</div><div className="text-lg font-bold text-amber-400">{fmtCurrency(financialSummary.sellerPaidShipTotal)}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Avg Sale Price</div><div className="text-lg font-bold text-slate-200">{fmtCurrency(financialSummary.avgSalePrice)}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[10px] text-slate-400">Net Profit (Sales)</div><div className={`text-lg font-bold ${soldCards.reduce((a, r) => a + safeNum(r.Net_Profit), 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtCurrency(soldCards.reduce((a, r) => a + safeNum(r.Net_Profit), 0), true)}</div></div>
                </div>
                <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5 shrink-0 space-y-3`}>
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold text-white">💵 Sold Cards Ledger (Inventory\Sold_Cards.csv)</h2>
                    <button onClick={() => setShowRecordSaleForm(!showRecordSaleForm)} className={`px-3.5 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}>{showRecordSaleForm ? '▲ Hide Record Sale Form' : '➕ Record New Sale'}</button>
                  </div>
                  {showRecordSaleForm && (
                    <div className="p-4 bg-slate-950/90 border border-slate-800 rounded-xl grid grid-cols-2 md:grid-cols-6 gap-2.5">
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Sale Date</label><input type="date" value={newSale.Sale_Date} onChange={(e) => setNewSale({ ...newSale, Sale_Date: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">SKU (Auto-Fills)</label><input value={newSale.SKU} onChange={(e) => { const sVal = e.target.value; const match = inventory.find((c) => c.SKU === sVal.trim()); setNewSale(match ? { ...newSale, SKU: sVal, Set: match.Set, Subset: match.Subset, Card_Number: match['Card Number'], Player: match.Player } : { ...newSale, SKU: sVal }); }} placeholder="1000001" className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Set</label><input value={newSale.Set} onChange={(e) => setNewSale({ ...newSale, Set: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Card #</label><input value={newSale.Card_Number} onChange={(e) => setNewSale({ ...newSale, Card_Number: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Player</label><input value={newSale.Player} onChange={(e) => setNewSale({ ...newSale, Player: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Platform</label><select value={newSale.Platform} onChange={(e) => setNewSale({ ...newSale, Platform: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"><option>eBay</option><option>CollX</option><option>COMC</option><option>Local / Card Show</option><option>Direct / Manual</option></select></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Sale Price ($)</label><input type="number" step="0.01" value={newSale.Sale_Price} onChange={(e) => setNewSale({ ...newSale, Sale_Price: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Shipping Collected ($)</label><input type="number" step="0.01" value={newSale.Shipping_Collected} onChange={(e) => setNewSale({ ...newSale, Shipping_Collected: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Marketplace Fees ($)</label><input type="number" step="0.01" value={newSale.Marketplace_Fees} onChange={(e) => setNewSale({ ...newSale, Marketplace_Fees: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Shipping Cost ($)</label><input type="number" step="0.01" value={newSale.Shipping_Cost} onChange={(e) => setNewSale({ ...newSale, Shipping_Cost: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div><label className="block text-[10px] text-slate-400 mb-0.5">Cost Basis ($)</label><input type="number" step="0.01" value={newSale.Cost_Basis} onChange={(e) => setNewSale({ ...newSale, Cost_Basis: e.target.value })} className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono" /></div>
                      <div className="flex flex-col justify-end">
                        <label className="flex items-center gap-1.5 text-xs text-amber-300 mb-1.5 cursor-pointer">
                          <input type="checkbox" checked={newSale.Seller_Paid_Shipping} onChange={(e) => setNewSale({ ...newSale, Seller_Paid_Shipping: e.target.checked })} />
                          Seller Paid Shipping
                        </label>
                        <button
                          onClick={() => fetch(`${NODE_API_BASE}/sold-cards`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...newSale, markInventorySold: true }) })
                            .then((r) => r.json())
                            .then((res) => {
                              if (res && res.success) {
                                const soldLabel = newSale.Player || newSale.SKU || 'Card';
                                setSoldCards(res.rows || []);
                                setShowRecordSaleForm(false);
                                setNewSale({
                                  Sale_Date: new Date().toISOString().slice(0, 10),
                                  SKU: '', Set: '', Subset: 'Base', Card_Number: '', Player: '',
                                  Platform: newSale.Platform || 'eBay', Sale_Price: '5.00', Shipping_Collected: '1.25',
                                  Marketplace_Fees: '0.96', Shipping_Cost: '0.73', Seller_Paid_Shipping: false, Cost_Basis: '0.50', Notes: '',
                                });
                                refreshAllHubData();
                                pushNotification('Sale Recorded', `Logged sale of ${soldLabel}.`, 'Sales', 'success');
                              } else {
                                pushNotification('Save Sale Failed', res?.error || 'Could not record sale.', 'Sales', 'error');
                              }
                            })
                            .catch((e) => pushNotification('Save Sale Error', e.message, 'Sales', 'error'))}
                          className="w-full py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs"
                        >
                          💾 Save Sale
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-2xl bg-slate-900/60">
                  <table className="w-full text-left text-xs whitespace-nowrap">
                    <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                      <tr><th className="p-2">Sale ID</th><th className="p-2">Date</th><th className="p-2">SKU</th><th className="p-2">Card</th><th className="p-2">Platform</th><th className="p-2">Sale Price</th><th className="p-2">Ship Coll.</th><th className="p-2">Fees</th><th className="p-2">Ship Cost</th><th className="p-2">Seller Paid?</th><th className="p-2">Net Profit</th><th className="p-2">Undo</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {soldCards.map((s) => (
                        <tr key={s.Sale_ID} className="hover:bg-slate-800/40">
                          <td className="p-2 font-mono text-sky-400">{s.Sale_ID}</td>
                          <td className="p-2 font-mono">{s.Sale_Date}</td>
                          <td className="p-2 font-mono">{s.SKU || 'Manual'}</td>
                          <td className="p-2 font-bold text-white">{s.Set} #{s.Card_Number} {s.Player} [{s.Subset}]</td>
                          <td className="p-2">{s.Platform}</td>
                          <td className="p-2 font-mono">{fmtCurrency(s.Sale_Price)}</td>
                          <td className="p-2 font-mono">{fmtCurrency(s.Shipping_Collected)}</td>
                          <td className="p-2 font-mono text-rose-400">{fmtCurrency(s.Marketplace_Fees)}</td>
                          <td className="p-2 font-mono text-amber-300">{fmtCurrency(s.Shipping_Cost)}</td>
                          <td className="p-2">{String(s.Seller_Paid_Shipping).toLowerCase() === 'true' ? '✅ Seller' : 'Buyer'}</td>
                          <td className={`p-2 font-mono font-bold ${safeNum(s.Net_Profit) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtCurrency(s.Net_Profit, true)}</td>
                          <td className="p-2">
                            <button
                              onClick={() => fetch(`${NODE_API_BASE}/sold-cards/delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ Sale_ID: s.Sale_ID, revertInventoryStatus: true }) }).then((r) => r.json()).then((res) => { if (res.success) { setSoldCards(res.rows || []); refreshAllHubData(); pushNotification('Sale Removed', `Deleted ${s.Sale_ID}${s.SKU ? ` and reverted SKU ${s.SKU} to In Stock` : ''}.`, 'Sales', 'warning'); } })}
                              title="Delete sale & revert SKU status to In Stock"
                              className="text-rose-400 hover:text-rose-200 px-1.5"
                            >
                              🗑️
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 15. COLLECTION VALUE (LABELED TREND CHART, VALUE/SET, SET & SPORT DONUTS + 4 INSIGHT TABLES) */}
            {activePage === 'collection_value' && (() => {
              const inStockCards = inventory.filter((c) => String(c.Status || '').toLowerCase() !== 'sold');
              const cardOptVal = (c) => Math.max(safeNum(c.Raw_Price, 0), safeNum(c.EV_PSA, 0), safeNum(c.EV_BGS, 0));

              // Value & Count by Set
              const setMap = {};
              const sportMap = {};
              const playerMap = {};
              const copyStackMap = {};

              inStockCards.forEach((c) => {
                const sName = c.Set || 'Unknown Set';
                const spName = inferSportFromSet(sName);
                const rawV = safeNum(c.Raw_Price, 0);
                const recV = safeNum(c.Rec_Sale_Price, rawV);
                const optV = cardOptVal(c);

                if (!setMap[sName]) setMap[sName] = { label: sName, count: 0, totalVal: 0, rawVal: 0 };
                setMap[sName].count += 1;
                setMap[sName].totalVal += optV;
                setMap[sName].rawVal += rawV;

                sportMap[spName] = (sportMap[spName] || 0) + 1;

                const plr = String(c.Player || '').trim();
                if (plr) {
                  if (!playerMap[plr]) playerMap[plr] = { player: plr, count: 0, optVal: 0, recVal: 0, sets: new Set() };
                  playerMap[plr].count += 1;
                  playerMap[plr].optVal += optV;
                  playerMap[plr].recVal += recV;
                  playerMap[plr].sets.add(sName);
                }

                const stackKey = `${sName}|${c.Subset || 'Base'}|${String(c['Card Number'] || '').replace(/^#/, '')}|${plr}`;
                if (!copyStackMap[stackKey]) {
                  copyStackMap[stackKey] = {
                    Set: sName,
                    Subset: c.Subset || 'Base',
                    CardNumber: String(c['Card Number'] || '').replace(/^#/, ''),
                    Player: plr || 'Unknown',
                    copies: 0,
                    unitVal: optV,
                    stackVal: 0,
                  };
                }
                copyStackMap[stackKey].copies += 1;
                copyStackMap[stackKey].stackVal += optV;
                if (optV > copyStackMap[stackKey].unitVal) copyStackMap[stackKey].unitVal = optV;
              });

              const setsByVal = Object.values(setMap).sort((a, b) => b.totalVal - a.totalVal);
              const maxSetVal = Math.max(1, ...setsByVal.map((s) => s.totalVal));

              const setsByCount = Object.values(setMap).sort((a, b) => b.count - a.count);
              const topSetsDonut = setsByCount.slice(0, 7).map((s) => ({ label: s.label, value: s.count }));
              if (setsByCount.length > 7) {
                topSetsDonut.push({ label: `Other (${setsByCount.length - 7} sets)`, value: setsByCount.slice(7).reduce((a, x) => a + x.count, 0) });
              }

              const sportsDonut = Object.entries(sportMap)
                .sort((a, b) => b[1] - a[1])
                .map(([label, value]) => ({ label, value }));

              const topValuableCards = [...inStockCards].sort((a, b) => cardOptVal(b) - cardOptVal(a)).slice(0, 10);
              const mostCollectedPlayers = Object.values(playerMap).sort((a, b) => b.count - a.count).slice(0, 10);
              const mostCopiesList = Object.values(copyStackMap).sort((a, b) => (b.copies - a.copies) || (b.stackVal - a.stackVal)).slice(0, 10);
              const topPlayersByValue = Object.values(playerMap).sort((a, b) => b.optVal - a.optVal).slice(0, 10);

              const histPts = (marketData.history || []).slice(-30);
              const avgCardVal = inStockCards.length > 0 ? financialSummary.totalOptimalEv / inStockCards.length : 0;

              return (
                <div className="space-y-4">
                  {/* KPI SUMMARY ROW */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5`}><div className="text-[11px] text-slate-400">In-Stock Cards</div><div className="text-xl font-bold text-white">{financialSummary.inStockCount.toLocaleString()}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5`}><div className="text-[11px] text-slate-400">Total Raw Value</div><div className="text-xl font-bold text-sky-400">{fmtCurrency(financialSummary.totalRawVal)}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5`}><div className="text-[11px] text-slate-400">Total Rec. Sale Value</div><div className="text-xl font-bold text-emerald-400">{fmtCurrency(financialSummary.totalRecVal)}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5`}><div className="text-[11px] text-slate-400">Optimal EV (Raw/Graded)</div><div className="text-xl font-bold text-amber-400">{fmtCurrency(financialSummary.totalOptimalEv)}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3.5`}><div className="text-[11px] text-slate-400">Avg. Value / Card</div><div className="text-xl font-bold text-cyan-300">{fmtCurrency(avgCardVal)}</div></div>
                  </div>

                  {/* UPGRADED DAILY COLLECTION VALUE TREND CHART (AXES, GRIDLINES, LABELS & LEGEND) */}
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-bold text-white">📈 Collection Value Trend ({histPts.length} Snapshot{histPts.length === 1 ? '' : 's'})</h3>
                      <div className="flex items-center gap-3 text-[11px] font-semibold">
                        <span className="flex items-center gap-1.5 text-emerald-300"><span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />Optimal EV</span>
                        <span className="flex items-center gap-1.5 text-amber-300"><span className="w-2.5 h-2.5 rounded-full bg-amber-400" />Rec. Sale</span>
                        <span className="flex items-center gap-1.5 text-sky-300"><span className="w-2.5 h-2.5 rounded-full bg-sky-400" />Raw Value</span>
                      </div>
                    </div>
                    {histPts.length === 0 ? (
                      <div className="text-xs text-slate-400 py-8 text-center">No daily valuation snapshots recorded yet. Run a Market Valuation Refresh to start plotting your portfolio trend.</div>
                    ) : (() => {
                      const rawMax = Math.max(10, ...histPts.map((h) => Math.max(safeNum(h.Total_Raw_Value), safeNum(h.Total_Rec_Sale_Value), safeNum(h.Total_Optimal_EV))));
                      const maxV = Math.ceil(rawMax * 1.12);
                      const W = 780, H = 215, padL = 66, padR = 20, padT = 16, padB = 30;
                      const plotW = W - padL - padR;
                      const plotH = H - padT - padB;
                      const toX = (i) => (histPts.length === 1 ? padL + plotW * 0.5 : padL + (i / (histPts.length - 1)) * plotW);
                      const toY = (v) => padT + plotH - (Math.max(0, v) / maxV) * plotH;
                      const rawLine = histPts.map((h, i) => `${toX(i)},${toY(safeNum(h.Total_Raw_Value))}`).join(' ');
                      const recLine = histPts.map((h, i) => `${toX(i)},${toY(safeNum(h.Total_Rec_Sale_Value, safeNum(h.Total_Raw_Value)))}`).join(' ');
                      const evLine = histPts.map((h, i) => `${toX(i)},${toY(safeNum(h.Total_Optimal_EV))}`).join(' ');
                      const areaPoly = histPts.length >= 2 ? `${toX(0)},${padT + plotH} ${evLine} ${toX(histPts.length - 1)},${padT + plotH}` : '';
                      const yTicks = [0, 0.25, 0.5, 0.75, 1.0].map((f) => ({ val: maxV * f, y: toY(maxV * f) }));
                      const xTickIndices = Array.from(new Set([0, Math.floor((histPts.length - 1) * 0.33), Math.floor((histPts.length - 1) * 0.66), histPts.length - 1]));

                      return (
                        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-52 bg-slate-950/90 rounded-xl border border-slate-800">
                          <defs>
                            <linearGradient id="evAreaGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="#10b981" stopOpacity="0.28" />
                              <stop offset="100%" stopColor="#10b981" stopOpacity="0.01" />
                            </linearGradient>
                          </defs>
                          {yTicks.map((t, ti) => (
                            <g key={ti}>
                              <line x1={padL} y1={t.y} x2={W - padR} y2={t.y} stroke="#1e293b" strokeDasharray="3 3" strokeWidth="1" />
                              <text x={padL - 8} y={t.y + 3.5} textAnchor="end" fill="#94a3b8" fontSize="10" fontFamily="monospace">
                                ${t.val >= 1000 ? `${(t.val / 1000).toFixed(1)}k` : Math.round(t.val)}
                              </text>
                            </g>
                          ))}
                          {xTickIndices.map((xi) => (
                            <text key={xi} x={toX(xi)} y={H - 9} textAnchor="middle" fill="#94a3b8" fontSize="10" fontFamily="monospace">
                              {String(histPts[xi]?.Date || '').slice(0, 10)}
                            </text>
                          ))}
                          {areaPoly && <polygon fill="url(#evAreaGrad)" points={areaPoly} />}
                          {histPts.length >= 2 && <polyline fill="none" stroke="#38bdf8" strokeWidth="2.2" points={rawLine} />}
                          {histPts.length >= 2 && <polyline fill="none" stroke="#f59e0b" strokeWidth="2" strokeDasharray="4 2" points={recLine} />}
                          {histPts.length >= 2 && <polyline fill="none" stroke="#10b981" strokeWidth="2.6" points={evLine} />}
                          {histPts.map((h, i) => (
                            <g key={i}>
                              <circle cx={toX(i)} cy={toY(safeNum(h.Total_Optimal_EV))} r="3.8" fill="#10b981"><title>{`${h.Date} — Optimal EV: ${fmtCurrency(h.Total_Optimal_EV)} | Rec Sale: ${fmtCurrency(h.Total_Rec_Sale_Value)} | Raw: ${fmtCurrency(h.Total_Raw_Value)}`}</title></circle>
                              <circle cx={toX(i)} cy={toY(safeNum(h.Total_Rec_Sale_Value, safeNum(h.Total_Raw_Value)))} r="2.8" fill="#f59e0b"><title>{`${h.Date} — Rec Sale: ${fmtCurrency(h.Total_Rec_Sale_Value)}`}</title></circle>
                              <circle cx={toX(i)} cy={toY(safeNum(h.Total_Raw_Value))} r="3" fill="#38bdf8"><title>{`${h.Date} — Raw Value: ${fmtCurrency(h.Total_Raw_Value)}`}</title></circle>
                            </g>
                          ))}
                        </svg>
                      );
                    })()}
                  </div>

                  {/* 3 COMPANION CHARTS: VALUE BY SET (+ AVG $/CARD), CARD COUNT BY SET DONUT, CARD COUNT BY SPORT DONUT */}
                  <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">📊 Value by Set &amp; Avg. Value / Card</h3>
                      <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
                        {setsByVal.slice(0, 10).map((s) => {
                          const avgV = s.count > 0 ? s.totalVal / s.count : 0;
                          return (
                            <div key={s.label} className="space-y-1">
                              <div className="flex items-center justify-between gap-2 text-[11px]">
                                <span className="text-slate-200 font-semibold truncate" title={s.label}>{s.label}</span>
                                <span className="font-mono shrink-0">
                                  <span className="text-emerald-400 font-bold">{fmtCurrency(s.totalVal)}</span>
                                  <span className="text-slate-400"> ({fmtCurrency(avgV)}/cd)</span>
                                </span>
                              </div>
                              <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                                <div className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400" style={{ width: `${(s.totalVal / maxSetVal) * 100}%` }} />
                              </div>
                            </div>
                          );
                        })}
                        {setsByVal.length === 0 && <div className="text-xs text-slate-500 py-6 text-center">No sets in inventory yet.</div>}
                      </div>
                    </div>

                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">🥧 Card Count by Set</h3>
                      <SvgDonutChart data={topSetsDonut} centerLabel={inStockCards.length.toLocaleString()} centerSub="Cards" />
                    </div>

                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">🏟️ Card Count by Sport</h3>
                      <SvgDonutChart data={sportsDonut} centerLabel={String(sportsDonut.length)} centerSub="Sports" />
                    </div>
                  </div>

                  {/* 4 BOTTOM INSIGHT TABLES (2x2 GRID) */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">💎 Top 10 Most Valuable Cards</h3>
                      <div className="divide-y divide-slate-800 text-xs">
                        {topValuableCards.map((c, i) => (
                          <div key={c.SKU} className="py-2 flex items-center justify-between gap-2">
                            <div className="truncate"><span className="font-mono text-slate-500 mr-2">#{i + 1}</span><span className="font-bold text-white">{c.Player}</span> <span className="text-slate-400">{c.Set} #{c['Card Number']} [{c.Subset}]</span></div>
                            <div className="font-mono text-emerald-400 font-bold shrink-0">{fmtCurrency(cardOptVal(c))}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">🏆 Top 10 Players by Total Value (All Sets)</h3>
                      <div className="divide-y divide-slate-800 text-xs">
                        {topPlayersByValue.map((p, i) => (
                          <div key={p.player} className="py-2 flex items-center justify-between gap-2">
                            <div className="truncate"><span className="font-mono text-slate-500 mr-2">#{i + 1}</span><span className="font-bold text-white">{p.player}</span> <span className="text-slate-400">({p.count} cards • {p.sets.size} set{p.sets.size === 1 ? '' : 's'})</span></div>
                            <div className="font-mono text-amber-300 font-bold shrink-0">{fmtCurrency(p.optVal)}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">⭐ Most Collected Players (By Card Count)</h3>
                      <div className="divide-y divide-slate-800 text-xs">
                        {mostCollectedPlayers.map((p, i) => (
                          <div key={p.player} className="py-2 flex items-center justify-between gap-2">
                            <div className="truncate"><span className="font-mono text-slate-500 mr-2">#{i + 1}</span><span className="font-bold text-white">{p.player}</span> <span className="text-slate-400">({p.sets.size} set{p.sets.size === 1 ? '' : 's'})</span></div>
                            <div className="font-mono text-sky-300 shrink-0">{p.count} cards • {fmtCurrency(p.recVal)}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-2.5`}>
                      <h3 className="text-sm font-bold text-white">📚 Most Copies of a Single Card</h3>
                      <div className="divide-y divide-slate-800 text-xs">
                        {mostCopiesList.map((st, i) => (
                          <div key={`${st.Set}-${st.Subset}-${st.CardNumber}-${i}`} className="py-2 flex items-center justify-between gap-2">
                            <div className="truncate"><span className="font-mono text-slate-500 mr-2">#{i + 1}</span><span className="font-bold text-white">{st.Player}</span> <span className="text-slate-400">{st.Set} #{st.CardNumber} [{st.Subset}]</span></div>
                            <div className="font-mono shrink-0"><span className="text-cyan-300 font-bold">{st.copies}x</span> <span className="text-slate-400">({fmtCurrency(st.stackVal)})</span></div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 16. SET COMPLETION */}
            {activePage === 'set_completion' && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 shrink-0`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-sm font-bold text-white flex items-center gap-2">
                      <span>🏆 5-Mode Set Completion Dashboard</span>
                      {completionLoading && <span className="px-2 py-0.5 rounded-full bg-sky-950 border border-sky-600/70 text-sky-300 text-[10.5px] font-semibold animate-pulse">⏳ Calculating completion...</span>}
                    </h2>
                    <div className="flex flex-wrap items-center gap-2">
                      <select value={completionSet} onChange={(e) => { setCompletionSet(e.target.value); setCompSubsetF('All Subsets'); }} className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs">
                        {dynamicSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                      </select>
                      <label className="flex items-center gap-1.5 text-xs text-slate-300 px-2"><input type="checkbox" checked={completionExclSN} onChange={(e) => setCompletionExclSN(e.target.checked)} /> Exclude Serial #/N</label>
                      <button onClick={() => setShowCompBreakdown(!showCompBreakdown)} className={`px-3 py-1.5 rounded-xl border text-xs font-bold ${showCompBreakdown ? skin.accentActive : 'bg-slate-800 border-slate-700 text-slate-200'}`}>📊 Subset / Player Breakdown {showCompBreakdown ? '⌄' : '›'}</button>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-2.5">
                    {(completionData.modes || []).map((m) => (
                      <button key={m.modeIdx} onClick={() => setCompletionModeIdx(m.modeIdx)} className={`text-left p-3 rounded-xl border transition ${completionModeIdx === m.modeIdx ? skin.accentActive : 'bg-slate-950 border-slate-800 hover:border-slate-700'}`}>
                        <div className="text-[11px] font-semibold text-slate-300 truncate">{m.label.split('(')[0]}</div>
                        <div className="text-xl font-bold text-white mt-0.5">{m.completion_pct.toFixed(1)}%</div>
                        <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden my-1.5"><div className="h-full bg-emerald-500" style={{ width: `${m.completion_pct}%` }} /></div>
                        <div className="text-[10px] font-mono text-sky-400">{m.owned_count.toLocaleString()} / {m.total_count.toLocaleString()} cards</div>
                      </button>
                    ))}
                  </div>
                  {showCompBreakdown && (
                    <div className="p-3 bg-slate-950/90 border border-slate-800 rounded-xl space-y-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex gap-2">
                          <button onClick={() => setCompBreakdownTab('subset')} className={`px-3 py-1 rounded-lg text-xs font-bold ${compBreakdownTab === 'subset' ? skin.accentBtn : 'bg-slate-800 text-slate-300'}`}>By Subset ({completionData.bySubset?.length || 0})</button>
                          <button onClick={() => setCompBreakdownTab('player')} className={`px-3 py-1 rounded-lg text-xs font-bold ${compBreakdownTab === 'player' ? skin.accentBtn : 'bg-slate-800 text-slate-300'}`}>By Player ({completionData.byPlayer?.length || 0})</button>
                        </div>
                        <input value={compBreakdownSearch} onChange={(e) => setCompBreakdownSearch(e.target.value)} placeholder={`Search ${compBreakdownTab}...`} className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs" />
                      </div>
                      <div className="max-h-48 overflow-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-slate-900 text-slate-400 sticky top-0"><tr><th className="p-1.5">{compBreakdownTab === 'subset' ? 'Subset' : 'Player'}</th><th className="p-1.5">Owned</th><th className="p-1.5">Missing</th><th className="p-1.5">Total</th><th className="p-1.5">Completion</th></tr></thead>
                          <tbody className="divide-y divide-slate-800">
                            {(compBreakdownTab === 'subset' ? (completionData.bySubset || []) : (completionData.byPlayer || []))
                              .filter((x) => !compBreakdownSearch.trim() || String(x.Subset || x.Player).toLowerCase().includes(compBreakdownSearch.toLowerCase()))
                              .slice(0, 100)
                              .map((x, idx) => (
                                <tr key={idx}><td className="p-1.5 font-semibold text-white">{x.Subset || x.Player}</td><td className="p-1.5 font-mono text-emerald-400">{x.Owned}</td><td className="p-1.5 font-mono text-rose-400">{x.Missing}</td><td className="p-1.5 font-mono">{x.Total}</td><td className="p-1.5 font-mono text-sky-300">{x.Pct}%</td></tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
                <div className={`flex-1 min-h-0 flex flex-col gap-2.5 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                    <div className="flex gap-2">
                      <button onClick={() => setCompTableView('missing')} className={`px-3 py-1 rounded-xl text-xs font-bold ${compTableView === 'missing' ? 'bg-rose-600 text-white' : 'bg-slate-800 text-slate-300'}`}>❌ Missing Cards ({completionData.missing?.length || 0})</button>
                      <button onClick={() => setCompTableView('owned')} className={`px-3 py-1 rounded-xl text-xs font-bold ${compTableView === 'owned' ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-300'}`}>✅ Owned Cards ({completionData.owned?.length || 0})</button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <select value={compSubsetF} onChange={(e) => setCompSubsetF(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1 text-xs"><option>All Subsets</option>{(completionData.bySubset || []).map((s) => <option key={s.Subset}>{s.Subset}</option>)}</select>
                      <input value={compSearch} onChange={(e) => setCompSearch(e.target.value)} placeholder="Search Card #, Player, Team..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1 text-xs" />
                      <button onClick={() => { setCompSubsetF('All Subsets'); setCompSearch(''); }} className="px-2.5 py-1 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-300">🧹 Clear Filters</button>
                    </div>
                  </div>
                  {(() => {
                    const compFiltered = (compTableView === 'missing' ? (completionData.missing || []) : (completionData.owned || []))
                      .filter((r) => (compSubsetF === 'All Subsets' || r.Subset === compSubsetF) && (!compSearch.trim() || `${r['Card Number']} ${r.Player} ${r.Team} ${r.Subset}`.toLowerCase().includes(compSearch.toLowerCase())));
                    const compFilteredCnt = compFiltered.length;
                    const totPages = Math.max(1, Math.ceil(compFilteredCnt / compPageSize));
                    const safeCompP = Math.min(compPage, totPages);
                    return (
                      <>
                        <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                          <table className="w-full text-left text-xs whitespace-nowrap">
                            <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10"><tr><th className="p-2">Card #</th><th className="p-2">Player</th><th className="p-2">Subset</th><th className="p-2">Team</th><th className="p-2">Print Run</th><th className="p-2">Attributes</th></tr></thead>
                            <tbody className="divide-y divide-slate-800">
                              {completionLoading && compFilteredCnt === 0 ? (
                                <tr><td colSpan={6} className="p-6 text-center text-sky-300 font-semibold animate-pulse">⏳ Loading checklist &amp; inventory completion for {completionSet}...</td></tr>
                              ) : (
                                compFiltered
                                  .slice((safeCompP - 1) * compPageSize, safeCompP * compPageSize)
                                  .map((r, i) => (
                                    <tr key={i} className="hover:bg-slate-800/40">
                                      <td className="p-2 font-mono">#{r['Card Number']}</td>
                                      <td className="p-2 font-bold text-white">{r.Player}</td>
                                      <td className="p-2">{r.Subset}</td>
                                      <td className="p-2 text-slate-300">{r.Team}</td>
                                      <td className="p-2 font-mono text-amber-300">{r['Print Run'] ? `#/${r['Print Run']}` : '—'}</td>
                                      <td className="p-2"><AttributeBadges attributesStr={r.Attributes} glossary={chkData.glossary} /></td>
                                    </tr>
                                  ))
                              )}
                            </tbody>
                          </table>
                        </div>
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 shrink-0">
                          <span>Showing {compFilteredCnt === 0 ? 0 : ((safeCompP - 1) * compPageSize + 1).toLocaleString()}–{Math.min(compFilteredCnt, safeCompP * compPageSize).toLocaleString()} of {compFilteredCnt.toLocaleString()} cards</span>
                          <div className="flex items-center gap-2">
                            <select value={compPageSize} onChange={(e) => { setCompPageSize(parseInt(e.target.value, 10) || 250); setCompPage(1); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                              <option value={100}>100 / page</option><option value={250}>250 / page</option><option value={500}>500 / page</option>
                            </select>
                            <button onClick={() => setCompPage((p) => Math.max(1, Math.min(totPages, p) - 1))} disabled={safeCompP <= 1} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">◀ Prev</button>
                            <span className="font-mono text-white">Page {safeCompP} / {totPages}</span>
                            <button onClick={() => setCompPage((p) => Math.min(totPages, Math.min(totPages, p) + 1))} disabled={safeCompP >= totPages} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 font-semibold">Next ▶</button>
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {/* 17. CARD PURCHASE PLANNER */}
            {activePage === 'card_purchase_planner' && (
              <div className="flex-1 flex flex-col gap-3 min-h-0">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Owned in Target</div><div className="text-lg font-bold text-white">{(plannerData.summary?.owned_count || 0).toLocaleString()} / {(plannerData.summary?.total_count || 0).toLocaleString()}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Missing Cards to Buy</div><div className="text-lg font-bold text-rose-400">{(plannerData.summary?.missing_count || 0).toLocaleString()}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Est. Total Cost</div><div className="text-lg font-bold text-emerald-400">{fmtCurrency(plannerData.summary?.estimated_total_cost || 0)}</div></div>
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Avg. Cost / Card</div><div className="text-lg font-bold text-sky-400">{fmtCurrency((plannerData.summary?.estimated_total_cost || 0) / Math.max(1, plannerData.summary?.missing_count || 1))}</div></div>
                </div>
                <div className={`flex-1 min-h-0 flex flex-col gap-3 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2 shrink-0">
                    <select value={plannerSet} onChange={(e) => { setPlannerSet(e.target.value); setPlannerSubset('All Subsets'); setPlannerPlayer(''); }} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">{dynamicSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}</select>
                    <select value={plannerSubset} onChange={(e) => setPlannerSubset(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs"><option>All Subsets</option>{(plannerData.subsets || []).slice(0, 300).map((sub) => <option key={sub}>{sub}</option>)}</select>
                    <input value={plannerPlayer} onChange={(e) => setPlannerPlayer(e.target.value)} placeholder="Player Rainbow..." className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                    <label className="flex items-center gap-1.5 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1 text-xs">
                      <span className="text-[10.5px] text-slate-400 shrink-0 font-semibold">Max $/Card</span>
                      <input type="number" min="0" step="1" value={plannerMaxBudget} onChange={(e) => setPlannerMaxBudget(parseFloat(e.target.value) || 0)} placeholder="0 = Any" className="w-full min-w-0 bg-transparent text-xs font-mono text-white focus:outline-none" />
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-slate-300 px-2"><input type="checkbox" checked={plannerExclSN} onChange={(e) => setPlannerExclSN(e.target.checked)} /> Excl. Limited #/N</label>
                    <button onClick={() => { setPlannerSubset('All Subsets'); setPlannerPlayer(''); setPlannerMaxBudget(0); setPlannerExclSN(false); }} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">🧹 Clear Filters</button>
                  </div>
                  <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                    <table className="w-full text-left text-xs whitespace-nowrap">
                      <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10"><tr><th className="p-2">Card #</th><th className="p-2">Player</th><th className="p-2">Subset</th><th className="p-2">Team</th><th className="p-2">Print Run</th><th className="p-2">Est. Cost</th><th className="p-2">Buy Link</th></tr></thead>
                      <tbody className="divide-y divide-slate-800">
                        {(plannerData.rows || []).map((r, i) => (
                          <tr key={i} className="hover:bg-slate-800/40">
                            <td className="p-2 font-mono">#{r['Card Number']}</td>
                            <td className="p-2 font-bold text-white">{r.Player}</td>
                            <td className="p-2">{r.Subset}</td>
                            <td className="p-2 text-slate-300">{r.Team}</td>
                            <td className="p-2 font-mono text-amber-300">{r['Print Run'] ? `#/${r['Print Run']}` : '—'}</td>
                            <td className="p-2 font-mono text-emerald-400 font-bold">{fmtCurrency(r.Est_Cost_USD)}</td>
                            <td className="p-2"><a href={r.eBay_Buy_Link} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline font-semibold">eBay Lowest+Ship ↗</a></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* 18. EXPENSES (STATIC DISPLAY ROWS WITH INLINE ROW EDIT MODE) */}
            {activePage === 'expenses' && (() => {
              const indexedExpenses = expensesLedger.map((r, origIdx) => ({ r, origIdx }));
              const filteredExpenses = indexedExpenses.filter(({ r, origIdx }) => {
                if (origIdx === editingExpenseIdx) return true;
                if (expenseCatFilter !== 'All Categories' && (r.Category || EXPENSE_CATEGORIES[0]) !== expenseCatFilter) return false;
                if (expenseSearch.trim()) {
                  const q = expenseSearch.toLowerCase();
                  if (!`${r.ID} ${r.Date} ${r.Category} ${r.Vendor} ${r.Description} ${r['Set Scope']} ${r.Cost}`.toLowerCase().includes(q)) return false;
                }
                return true;
              });

              const startAddExpense = () => {
                const maxExpNum = expensesLedger.reduce((mx, row) => {
                  const m = String(row?.ID || '').match(/(\d+)$/);
                  return m ? Math.max(mx, parseInt(m[1], 10)) : mx;
                }, 0);
                const newRow = {
                  ID: `EXP-${String(maxExpNum + 1).padStart(3, '0')}`,
                  Date: new Date().toISOString().slice(0, 10),
                  Category: EXPENSE_CATEGORIES[0],
                  Vendor: '',
                  Description: '',
                  'Set Scope': 'All Sets (Global Overhead)',
                  Cost: '0.00',
                };
                const next = [newRow, ...expensesLedger];
                setExpensesLedger(next);
                setEditingExpenseIdx(0);
                setExpenseRowDraft(newRow);
                setExpenseIsNewDraft(true);
              };

              const startEditExpense = (origIdx, rowObj) => {
                setEditingExpenseIdx(origIdx);
                setExpenseRowDraft({ ...rowObj });
                setExpenseIsNewDraft(false);
              };

              const saveActiveExpenseRow = () => {
                if (editingExpenseIdx === null || !expenseRowDraft) return;
                const cleanCost = safeNum(expenseRowDraft.Cost, 0).toFixed(2);
                const next = expensesLedger.map((item, i) => (i === editingExpenseIdx ? { ...expenseRowDraft, Cost: cleanCost } : item));
                setExpensesLedger(next);
                setEditingExpenseIdx(null);
                setExpenseRowDraft(null);
                setExpenseIsNewDraft(false);
                saveExpensesAndPricing(false, null, next);
              };

              const cancelActiveExpenseRow = () => {
                if (expenseIsNewDraft && editingExpenseIdx !== null) {
                  setExpensesLedger((prev) => prev.filter((_, i) => i !== editingExpenseIdx));
                }
                setEditingExpenseIdx(null);
                setExpenseRowDraft(null);
                setExpenseIsNewDraft(false);
              };

              const deleteExpenseRow = (origIdx) => {
                const next = expensesLedger.filter((_, i) => i !== origIdx);
                setExpensesLedger(next);
                if (editingExpenseIdx === origIdx) {
                  setEditingExpenseIdx(null);
                  setExpenseRowDraft(null);
                  setExpenseIsNewDraft(false);
                }
                saveExpensesAndPricing(false, null, next);
              };

              return (
                <div className="flex-1 flex flex-col gap-3 min-h-0">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Total Logged Expenses</div><div className="text-xl font-bold text-white">{fmtCurrency(financialSummary.totalExpenses)}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Boxes / COGS</div><div className="text-xl font-bold text-amber-400">{fmtCurrency(financialSummary.cogsBoxes)}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Unit Cost Basis / Card</div><div className="text-xl font-bold text-sky-400">{fmtCurrency(financialSummary.unitCostBasis)}</div></div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-3`}><div className="text-[11px] text-slate-400">Projected ROI</div><div className="text-xl font-bold text-emerald-400">{financialSummary.totalExpenses > 0 ? `${(((financialSummary.totalRecVal - financialSummary.totalExpenses) / financialSummary.totalExpenses) * 100).toFixed(1)}%` : '—'}</div></div>
                  </div>
                  <div className={`flex-1 min-h-0 flex flex-col gap-3 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                    <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                      <div>
                        <h2 className="text-sm font-bold text-white">💳 Expenses Ledger (Data\Bookkeeping\Expenses.csv — {filteredExpenses.length} of {expensesLedger.length})</h2>
                        <p className="text-[11px] text-slate-400">Clean read-only rows by default. Click ✏️ Edit on any row to modify inline and auto-save.</p>
                      </div>
                      <button onClick={startAddExpense} disabled={editingExpenseIdx !== null} className={`px-3.5 py-1.5 rounded-xl font-bold text-xs disabled:opacity-40 ${skin.accentBtn}`}>➕ Add Expense</button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-2 shrink-0">
                      <select value={expenseCatFilter} onChange={(e) => setExpenseCatFilter(e.target.value)} className="bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs">
                        <option>All Categories</option>
                        {EXPENSE_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                      </select>
                      <input value={expenseSearch} onChange={(e) => setExpenseSearch(e.target.value)} placeholder="Search ID, Vendor, Description, Set Scope..." className="md:col-span-2 bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs" />
                      <button onClick={() => { setExpenseCatFilter('All Categories'); setExpenseSearch(''); }} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300">🧹 Clear Filters</button>
                    </div>
                    <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                      <table className="w-full text-left text-xs whitespace-nowrap">
                        <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10">
                          <tr><th className="p-2.5">ID</th><th className="p-2.5">Date</th><th className="p-2.5">Category</th><th className="p-2.5">Vendor</th><th className="p-2.5">Description</th><th className="p-2.5">Set Scope</th><th className="p-2.5 text-right">Cost</th><th className="p-2.5 text-right">Actions</th></tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/80">
                          {filteredExpenses.length === 0 ? (
                            <tr><td colSpan={8} className="p-6 text-center text-slate-500">No expense rows match your current filter.</td></tr>
                          ) : (
                            filteredExpenses.map(({ r, origIdx }) => {
                              const isEditing = editingExpenseIdx === origIdx && expenseRowDraft;
                              if (isEditing) {
                                return (
                                  <tr key={`ed-${origIdx}`} className="bg-amber-950/25">
                                    <td className="p-1.5"><input value={expenseRowDraft.ID || ''} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, ID: e.target.value })} className="w-20 bg-slate-950 border border-amber-600/70 rounded-lg px-1.5 py-1 font-mono" /></td>
                                    <td className="p-1.5"><input type="date" value={expenseRowDraft.Date || ''} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, Date: e.target.value })} className="w-32 bg-slate-950 border border-amber-600/70 rounded-lg px-1.5 py-1 font-mono" /></td>
                                    <td className="p-1.5"><select value={expenseRowDraft.Category || EXPENSE_CATEGORIES[0]} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, Category: e.target.value })} className="bg-slate-950 border border-amber-600/70 rounded-lg px-1.5 py-1 max-w-[210px]">{EXPENSE_CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></td>
                                    <td className="p-1.5"><input value={expenseRowDraft.Vendor || ''} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, Vendor: e.target.value })} placeholder="Vendor" className="w-28 bg-slate-950 border border-amber-600/70 rounded-lg px-1.5 py-1" /></td>
                                    <td className="p-1.5"><input value={expenseRowDraft.Description || ''} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, Description: e.target.value })} placeholder="Description" className="w-48 bg-slate-950 border border-amber-600/70 rounded-lg px-1.5 py-1" /></td>
                                    <td className="p-1.5">
                                      <input list="exp-set-scope-list" value={expenseRowDraft['Set Scope'] || ''} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, 'Set Scope': e.target.value })} className="w-44 bg-slate-950 border border-amber-600/70 rounded-lg px-1.5 py-1" />
                                      <datalist id="exp-set-scope-list">
                                        <option value="All Sets (Global Overhead)" />
                                        {dynamicSetsNewestFirst.map((s) => <option key={s} value={s} />)}
                                      </datalist>
                                    </td>
                                    <td className="p-1.5 text-right"><input type="number" step="0.01" value={expenseRowDraft.Cost || '0.00'} onChange={(e) => setExpenseRowDraft({ ...expenseRowDraft, Cost: e.target.value })} className="w-24 bg-slate-950 border border-emerald-600 rounded-lg px-1.5 py-1 font-mono text-right" /></td>
                                    <td className="p-1.5 text-right">
                                      <div className="inline-flex items-center gap-1">
                                        <button onClick={saveActiveExpenseRow} className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px]">💾 Save</button>
                                        <button onClick={cancelActiveExpenseRow} className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px]">✖</button>
                                      </div>
                                    </td>
                                  </tr>
                                );
                              }

                              return (
                                <tr key={`${r.ID || 'exp'}-${origIdx}`} className="hover:bg-slate-800/40">
                                  <td className="p-2.5 font-mono text-sky-400 font-semibold">{r.ID || '—'}</td>
                                  <td className="p-2.5 font-mono text-slate-300">{r.Date || '—'}</td>
                                  <td className="p-2.5"><span className="px-2 py-0.5 rounded-md bg-slate-950 border border-slate-800 text-slate-200 text-[11px]">{r.Category || EXPENSE_CATEGORIES[0]}</span></td>
                                  <td className="p-2.5 font-semibold text-white">{r.Vendor || '—'}</td>
                                  <td className="p-2.5 text-slate-200 max-w-[280px] truncate" title={r.Description || ''}>{r.Description || '—'}</td>
                                  <td className="p-2.5 text-slate-400">{r['Set Scope'] || 'All Sets (Global Overhead)'}</td>
                                  <td className="p-2.5 text-right font-mono font-bold text-amber-300">{fmtCurrency(r.Cost)}</td>
                                  <td className="p-2.5 text-right">
                                    <div className="inline-flex items-center gap-1.5">
                                      <button onClick={() => startEditExpense(origIdx, r)} disabled={editingExpenseIdx !== null} className="px-2 py-0.5 rounded-lg bg-slate-800 hover:bg-sky-800 text-sky-200 border border-slate-700 text-[11px] font-semibold disabled:opacity-40">✏️ Edit</button>
                                      <button onClick={() => deleteExpenseRow(origIdx)} disabled={editingExpenseIdx !== null} className="px-1.5 py-0.5 rounded-lg bg-rose-950/70 hover:bg-rose-800 text-rose-300 text-[11px] disabled:opacity-40" title="Delete Expense">🗑️</button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 19. ANALYTICS */}
            {activePage === 'analytics' && (
              <div className="space-y-4">
                <div className="flex gap-2">
                  <button onClick={() => setAnalyticsTab('inventory')} className={`px-4 py-2 rounded-xl text-xs font-bold ${analyticsTab === 'inventory' ? skin.accentBtn : 'bg-slate-800 text-slate-300'}`}>📦 Inventory Analytics</button>
                  <button onClick={() => setAnalyticsTab('sales')} className={`px-4 py-2 rounded-xl text-xs font-bold ${analyticsTab === 'sales' ? skin.accentBtn : 'bg-slate-800 text-slate-300'}`}>💵 Sales &amp; Expense Analytics</button>
                </div>
                {analyticsTab === 'inventory' ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                      <h3 className="text-sm font-bold text-white">📉 Top 10 Sets by Projected Sale Value</h3>
                      {(() => {
                        const bySet = {};
                        inventory.filter((c) => c.Status !== 'Sold').forEach((c) => { bySet[c.Set] = (bySet[c.Set] || 0) + safeNum(c.Rec_Sale_Price, safeNum(c.Raw_Price, 0)); });
                        const entries = Object.entries(bySet).sort((a, b) => b[1] - a[1]).slice(0, 10);
                        const maxV = Math.max(1, ...entries.map((e) => e[1]));
                        return entries.map(([sName, val]) => (
                          <div key={sName} className="space-y-1">
                            <div className="flex justify-between text-xs"><span className="truncate">{sName}</span><span className="font-mono text-emerald-400">{fmtCurrency(val)}</span></div>
                            <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-cyan-500 to-blue-500" style={{ width: `${(val / maxV) * 100}%` }} /></div>
                          </div>
                        ));
                      })()}
                    </div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                      <h3 className="text-sm font-bold text-white">🏷️ Inventory Distribution by Hold Tag</h3>
                      {(() => {
                        const byHold = {};
                        inventory.filter((c) => c.Status !== 'Sold').forEach((c) => { const k = c.Hold_Tag || 'For Sale'; byHold[k] = (byHold[k] || 0) + 1; });
                        const tot = Math.max(1, financialSummary.inStockCount);
                        return Object.entries(byHold).map(([tag, cnt]) => (
                          <div key={tag} className="space-y-1">
                            <div className="flex justify-between text-xs"><span>{tag}</span><span className="font-mono text-sky-300">{cnt.toLocaleString()} ({((cnt / tot) * 100).toFixed(1)}%)</span></div>
                            <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden"><div className="h-full bg-emerald-500" style={{ width: `${(cnt / tot) * 100}%` }} /></div>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                      <h3 className="text-sm font-bold text-white">💵 Sales Revenue by Platform</h3>
                      {(() => {
                        const byPlat = {};
                        soldCards.forEach((s) => { const p = s.Platform || 'Other'; byPlat[p] = (byPlat[p] || 0) + safeNum(s.Sale_Price, 0); });
                        const entries = Object.entries(byPlat).sort((a, b) => b[1] - a[1]);
                        const maxV = Math.max(1, ...entries.map((e) => e[1]));
                        return entries.length === 0 ? <div className="text-xs text-slate-500">No sales recorded yet.</div> : entries.map(([plat, val]) => (
                          <div key={plat} className="space-y-1">
                            <div className="flex justify-between text-xs"><span>{plat}</span><span className="font-mono text-emerald-400">{fmtCurrency(val)}</span></div>
                            <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden"><div className="h-full bg-emerald-500" style={{ width: `${(val / maxV) * 100}%` }} /></div>
                          </div>
                        ));
                      })()}
                    </div>
                    <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3`}>
                      <h3 className="text-sm font-bold text-white">📊 Spend Breakdown by Category</h3>
                      {(() => {
                        const byCat = {};
                        expensesLedger.forEach((r) => { const k = r.Category || 'Other'; byCat[k] = (byCat[k] || 0) + safeNum(r.Cost, 0); });
                        const entries = Object.entries(byCat).sort((a, b) => b[1] - a[1]);
                        const maxV = Math.max(1, ...entries.map((e) => e[1]));
                        return entries.map(([cat, val]) => (
                          <div key={cat} className="space-y-1">
                            <div className="flex justify-between text-xs"><span className="truncate">{cat}</span><span className="font-mono text-amber-400">{fmtCurrency(val)}</span></div>
                            <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden"><div className="h-full bg-amber-500" style={{ width: `${(val / maxV) * 100}%` }} /></div>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 20. ACCOUNTING */}
            {activePage === 'accounting' && (
              <div className={`${skin.cardBg} border ${skin.border} rounded-2xl p-5 space-y-4 max-w-3xl`}>
                <h2 className="text-sm font-bold text-white">📒 Profit &amp; Loss (P&amp;L) Financial Statement</h2>
                <div className="divide-y divide-slate-800 text-xs">
                  <div className="py-2.5 flex justify-between"><span className="text-slate-300">Gross Card Sales ({soldCards.length.toLocaleString()} Sold)</span><span className="font-mono text-white">{fmtCurrency(financialSummary.grossSales)}</span></div>
                  <div className="py-2.5 flex justify-between"><span className="text-slate-300">Shipping Collected</span><span className="font-mono text-white">{fmtCurrency(financialSummary.shipCollected)}</span></div>
                  <div className="py-2.5 flex justify-between font-bold"><span className="text-sky-300">Total Gross Revenue</span><span className="font-mono text-sky-300">{fmtCurrency(financialSummary.totalRevenue)}</span></div>
                  <div className="py-2.5 flex justify-between"><span className="text-slate-400">Less: Marketplace Fees</span><span className="font-mono text-rose-400">-{fmtCurrency(financialSummary.totalFees)}</span></div>
                  <div className="py-2.5 flex justify-between"><span className="text-slate-400">Less: Seller-Paid Shipping Costs</span><span className="font-mono text-rose-400">-{fmtCurrency(financialSummary.sellerPaidShipTotal)}</span></div>
                  <div className="py-2.5 flex justify-between"><span className="text-slate-400">Less: Logged Expenses &amp; COGS (Expenses.csv)</span><span className="font-mono text-rose-400">-{fmtCurrency(financialSummary.totalExpenses)}</span></div>
                  <div className="py-3 flex justify-between text-base font-extrabold">
                    <span className="text-white">Net Profit / (Loss)</span>
                    <span className={`font-mono ${financialSummary.netProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtCurrency(financialSummary.netProfit, true)}</span>
                  </div>
                </div>
              </div>
            )}

            {/* 21. GENERAL SETTINGS — FULL-WIDTH DYNAMIC COLLAGE LAYOUT */}
            {activePage === 'general_settings' && (() => {
              const modSpan = (key, defaultSpan) => {
                const st = settingsLayout[key] || { collapsed: false, wide: false };
                if (st.collapsed) return 'lg:col-span-4';
                return st.wide ? 'lg:col-span-12' : defaultSpan;
              };
              const ModHeader = ({ modKey, icon, title, subtitle, accentCls = 'text-white', extra }) => {
                const st = settingsLayout[modKey] || { collapsed: false, wide: false };
                return (
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-800/80">
                    <div className="min-w-0">
                      <div className={`text-xs font-extrabold tracking-wide flex items-center gap-1.5 ${accentCls}`}>
                        <span>{icon}</span>
                        <span className="truncate">{title}</span>
                      </div>
                      {subtitle && !st.collapsed && <div className="text-[10.5px] text-slate-400 mt-0.5">{subtitle}</div>}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {extra}
                      {!st.collapsed && (
                        <button
                          type="button"
                          onClick={() => toggleSettingsMod(modKey, 'wide')}
                          title={st.wide ? 'Restore compact collage width' : 'Expand module to full width'}
                          className="px-2 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-[10px] font-semibold text-slate-300"
                        >
                          {st.wide ? '⤡ Compact' : '⤢ Wide'}
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => toggleSettingsMod(modKey, 'collapsed')}
                        title={st.collapsed ? 'Expand module' : 'Collapse module'}
                        className="px-2 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-[10px] font-bold text-slate-300"
                      >
                        {st.collapsed ? '▼' : '▲'}
                      </button>
                    </div>
                  </div>
                );
              };

              return (
                <div className="space-y-4">
                  {/* TOP COLLAGE TOOLBAR + DEVELOPER MODE SWITCH */}
                  <div className={`${skin.cardBg} border ${skin.border} rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-3`}>
                    <div>
                      <h2 className="text-sm font-extrabold text-white">⚙️ General Settings &amp; Workspace Modules</h2>
                      <p className="text-[11px] text-slate-400">Dynamic collage layout — resize, expand, or collapse any settings module below.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <label className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border cursor-pointer transition text-xs font-bold ${devMode ? 'bg-fuchsia-950/85 border-fuchsia-500 text-fuchsia-200 shadow' : 'bg-slate-950 border-slate-700 text-slate-300 hover:border-fuchsia-600/60'}`}>
                        <input type="checkbox" checked={devMode} onChange={(e) => toggleDevMode(e.target.checked)} className="w-3.5 h-3.5 accent-fuchsia-500" />
                        <span>🧪 Developer Mode: {devMode ? 'ON' : 'OFF'}</span>
                      </label>
                      <button onClick={() => setAllSettingsCollapsed(false)} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] font-semibold text-slate-200">Expand All</button>
                      <button onClick={() => setAllSettingsCollapsed(true)} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] font-semibold text-slate-300">Collapse All</button>
                      <button onClick={resetSettingsCollage} className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] font-semibold text-sky-300">📐 Reset Collage</button>
                    </div>
                  </div>

                  {/* DYNAMIC 12-COLUMN COLLAGE GRID */}
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start grid-flow-dense">
                    {/* MODULE 1: CHROME-PULSE 3D SKINS */}
                    <div className={`${modSpan('skins', 'lg:col-span-7')} ${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                      <ModHeader modKey="skins" icon="🎨" title="Chrome-Pulse 3D Skins" subtitle={`Active Theme: ${skin.name}`} />
                      {!settingsLayout.skins?.collapsed && (
                        <div className={`grid gap-2.5 ${settingsLayout.skins?.wide ? 'grid-cols-1 sm:grid-cols-3 xl:grid-cols-5' : 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-3'}`}>
                          {Object.entries(CHROME_PULSE_SKINS).map(([k, sObj]) => (
                            <button
                              key={k}
                              onClick={() => changeSkin(k)}
                              className={`p-3 rounded-xl border text-left flex items-center gap-3 transition ${skinKey === k ? `${sObj.accentActive} border-2 scale-[1.01]` : 'bg-slate-950/90 border-slate-800 text-slate-300 hover:border-slate-700'}`}
                            >
                              <span className="w-6 h-6 rounded-full shrink-0 shadow ring-1 ring-white/30" style={{ background: sObj.swatch }} />
                              <div className="min-w-0">
                                <div className="text-xs font-bold truncate">{sObj.name}</div>
                                {sObj.tagline && <div className="text-[10px] text-slate-400 truncate">{sObj.tagline}</div>}
                              </div>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* MODULE 2: MARKET ALERT THRESHOLDS & NOTIFICATION DELIVERY */}
                    <div className={`${modSpan('alerts', 'lg:col-span-5')} ${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                      <ModHeader
                        modKey="alerts"
                        icon="🔔"
                        title="Market Alerts & Notification Delivery"
                        subtitle="Configure ROI alert thresholds and push/email delivery"
                        accentCls="text-sky-300"
                        extra={
                          !settingsLayout.alerts?.collapsed && (
                            <label className="flex items-center gap-1.5 text-[11px] text-slate-300 mr-1 cursor-pointer">
                              <input type="checkbox" checked={!!alertCfg.email_enabled} onChange={(e) => setAlertCfg({ ...alertCfg, email_enabled: e.target.checked })} />
                              Auto-Send
                            </label>
                          )
                        }
                      />
                      {!settingsLayout.alerts?.collapsed && (
                        <div className="space-y-3">
                          <div className={`grid gap-2.5 text-xs ${settingsLayout.alerts?.wide ? 'grid-cols-2 md:grid-cols-6' : 'grid-cols-2'}`}>
                            <div><label className="block text-[10px] text-slate-400 mb-0.5">Min Grade Net Gain ($)</label><input type="number" step="2.5" value={alertCfg.min_grade_net_gain ?? 15} onChange={(e) => setAlertCfg({ ...alertCfg, min_grade_net_gain: parseFloat(e.target.value) || 0 })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 font-mono" /></div>
                            <div><label className="block text-[10px] text-slate-400 mb-0.5">Min Grade ROI (%)</label><input type="number" step="5" value={alertCfg.min_grade_roi_pct ?? 35} onChange={(e) => setAlertCfg({ ...alertCfg, min_grade_roi_pct: parseFloat(e.target.value) || 0 })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 font-mono" /></div>
                            <div><label className="block text-[10px] text-slate-400 mb-0.5">Price Spike Alert (%)</label><input type="number" step="5" value={alertCfg.price_spike_pct ?? 25} onChange={(e) => setAlertCfg({ ...alertCfg, price_spike_pct: parseFloat(e.target.value) || 0 })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 font-mono" /></div>
                            <div><label className="block text-[10px] text-slate-400 mb-0.5">Delivery Method</label><select value={alertCfg.delivery_method || 'ntfy_topic'} onChange={(e) => setAlertCfg({ ...alertCfg, delivery_method: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5"><option value="ntfy_topic">ntfy.sh (Passwordless)</option><option value="webhook">Discord / Slack Webhook</option><option value="windows_outlook">Windows Outlook</option><option value="gmail_smtp">Gmail SMTP</option></select></div>
                            <div className={settingsLayout.alerts?.wide ? 'md:col-span-1' : 'col-span-2'}><label className="block text-[10px] text-slate-400 mb-0.5">ntfy Topic / Webhook URL</label><input value={alertCfg.delivery_method === 'webhook' ? (alertCfg.webhook_url || '') : (alertCfg.ntfy_topic || '')} onChange={(e) => setAlertCfg(alertCfg.delivery_method === 'webhook' ? { ...alertCfg, webhook_url: e.target.value } : { ...alertCfg, ntfy_topic: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 font-mono" /></div>
                            <div className={settingsLayout.alerts?.wide ? 'md:col-span-1' : 'col-span-2'}><label className="block text-[10px] text-slate-400 mb-0.5">Recipient Email</label><input value={alertCfg.recipient_email || ''} onChange={(e) => setAlertCfg({ ...alertCfg, recipient_email: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5" /></div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button onClick={() => fetch(`${NODE_API_BASE}/market/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'save_alert_settings', settings: alertCfg }) }).then((r) => r.json()).then((res) => { if (res && res.success) { pushNotification('Alert Settings Saved', 'Saved Market Alert thresholds & delivery method.', 'Settings', 'success'); } else { pushNotification('Save Alert Settings Failed', res?.error || 'Could not save alert settings.', 'Settings', 'error'); } }).catch((e) => pushNotification('Save Alert Settings Error', e.message, 'Settings', 'error'))} className={`px-3 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}>💾 Save Alert Settings</button>
                            <button onClick={() => fetch(`${NODE_API_BASE}/market/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'test_alert', settings: alertCfg }) }).then((r) => r.json()).then((res) => pushNotification(res.success ? 'Test Alert Sent' : 'Test Alert Notice', res.message || 'Done', 'Settings', res.success ? 'success' : 'warning'))} className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold">🚀 Send Test Alert</button>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* MODULE 3: UNIFIED TASK SCHEDULER */}
                    <div className={`${modSpan('scheduler', 'lg:col-span-8')} ${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                      <ModHeader
                        modKey="scheduler"
                        icon="⏰"
                        title={`Unified Task Scheduler (${schedules.length} Tasks)`}
                        subtitle="Syncs recurring background jobs directly with Windows Task Scheduler"
                        accentCls="text-amber-300"
                        extra={
                          !settingsLayout.scheduler?.collapsed && (
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => {
                                  const maxSchedNum = schedules.reduce((mx, row) => {
                                    const m = String(row?.Schedule_ID || '').match(/(\d+)$/);
                                    return m ? Math.max(mx, parseInt(m[1], 10)) : mx;
                                  }, 0);
                                  const maxTaskNum = schedules.reduce((mx, row) => {
                                    const m = String(row?.Task_Name || '').match(/Tabulas_Custom_Job_(\d+)$/);
                                    return m ? Math.max(mx, parseInt(m[1], 10)) : mx;
                                  }, 0);
                                  setSchedules([...schedules, {
                                    Schedule_ID: `SCHED-${String(maxSchedNum + 1).padStart(3, '0')}`,
                                    Enabled: true,
                                    Pipeline_Mode: 'auto_checklists',
                                    Activity_Label: '🏛️ TCDB Master Checklist Builder (With TCDB_CIDs)',
                                    Frequency: 'DAILY',
                                    Time_24h: '03:00',
                                    Task_Name: `Tabulas_Custom_Job_${maxTaskNum + 1}`,
                                    OS_Status: 'Pending Sync',
                                  }]);
                                }}
                                className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] font-semibold"
                              >
                                ➕ Add
                              </button>
                              <button
                                onClick={() => fetch(`${NODE_API_BASE}/schedules`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(schedules) })
                                  .then((r) => r.json())
                                  .then((res) => {
                                    if (res && res.schedules) setSchedules(res.schedules);
                                    const msgs = Array.isArray(res?.messages) ? res.messages : [];
                                    const hasWarn = msgs.some((m) => String(m).includes('⚠️') || /fail|error/i.test(String(m)));
                                    pushNotification(
                                      hasWarn ? 'Schedules Synced with Warnings' : 'Schedules Saved',
                                      msgs.length > 0 ? msgs.join(' | ') : 'Synced schedules with Windows Task Scheduler.',
                                      'Scheduler',
                                      hasWarn ? 'warning' : 'success'
                                    );
                                  })
                                  .catch((e) => pushNotification('Schedule Sync Error', e.message, 'Scheduler', 'error'))}
                                className={`px-2.5 py-1 rounded-lg font-bold text-[11px] ${skin.accentBtn}`}
                              >
                                💾 Sync
                              </button>
                            </div>
                          )
                        }
                      />
                      {!settingsLayout.scheduler?.collapsed && (
                        <div className="overflow-auto max-h-72 border border-slate-800 rounded-xl">
                          <table className="w-full text-left text-xs whitespace-nowrap">
                            <thead className="bg-slate-950 text-slate-400 sticky top-0"><tr><th className="p-2">On</th><th className="p-2">Activity / Pipeline</th><th className="p-2">Frequency</th><th className="p-2">Time (24h)</th><th className="p-2">Status</th><th className="p-2">Actions</th></tr></thead>
                            <tbody className="divide-y divide-slate-800">
                              {schedules.length === 0 ? (
                                <tr><td colSpan={6} className="p-4 text-center text-slate-500">No scheduled jobs configured yet. Click "➕ Add" to create one.</td></tr>
                              ) : (
                                schedules.map((s, idx) => (
                                  <tr key={s.Schedule_ID || idx}>
                                    <td className="p-2"><input type="checkbox" checked={!!s.Enabled} onChange={(e) => { const n = [...schedules]; n[idx] = { ...s, Enabled: e.target.checked }; setSchedules(n); }} /></td>
                                    <td className="p-2">
                                      <select
                                        value={s.Pipeline_Mode || 'auto_scrape'}
                                        onChange={(e) => {
                                          const pm = e.target.value;
                                          const lblMap = {
                                            auto_checklists: '🏛️ TCDB Master Checklist Builder (With TCDB_CIDs)',
                                            auto_scrape: '🕷️ TCDB Set Template Image Scraper',
                                            auto_upgrade: '🔄 TCDB High-Res Image Upgrade',
                                            auto_market: '💰 Market Comps & Grading Tiers Refresh',
                                            auto_directory: '🌐 TCDB Master Set Directory Crawler',
                                            process_scans: '🔍 Incoming_Scans PDF Batch Auto-Processing',
                                          };
                                          const n = [...schedules];
                                          n[idx] = { ...s, Pipeline_Mode: pm, Activity_Label: lblMap[pm] || pm };
                                          setSchedules(n);
                                        }}
                                        className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs"
                                      >
                                        <option value="auto_checklists">🏛️ TCDB Master Checklist Builder (With TCDB_CIDs)</option>
                                        <option value="auto_scrape">🕷️ TCDB Set Template Image Scraper</option>
                                        <option value="auto_upgrade">🔄 TCDB High-Res Image Upgrade</option>
                                        <option value="auto_market">💰 Market Comps &amp; Grading Tiers Refresh</option>
                                        <option value="auto_directory">🌐 TCDB Master Set Directory Crawler</option>
                                        <option value="process_scans">🔍 Incoming_Scans PDF Batch Auto-Processing</option>
                                      </select>
                                    </td>
                                    <td className="p-2">
                                      <select value={s.Frequency || 'DAILY'} onChange={(e) => { const n = [...schedules]; n[idx] = { ...s, Frequency: e.target.value }; setSchedules(n); }} className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs">
                                        <option>DAILY</option><option>WEEKLY</option><option>HOURLY</option><option>MONTHLY</option>
                                      </select>
                                    </td>
                                    <td className="p-2"><input value={s.Time_24h || '03:00'} onChange={(e) => { const n = [...schedules]; n[idx] = { ...s, Time_24h: e.target.value }; setSchedules(n); }} className="w-20 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 font-mono text-xs" /></td>
                                    <td className="p-2 text-emerald-400">{s.OS_Status || 'Ready'}</td>
                                    <td className="p-2 flex items-center gap-1.5">
                                      <button
                                        onClick={() => {
                                          const pm = s.Pipeline_Mode || 'auto_scrape';
                                          const jobMap = {
                                            auto_checklists: ['set_scraper', 'tcdb_checklist_scrape'],
                                            auto_scrape: ['set_scraper', 'tcdb_scrape'],
                                            auto_upgrade: ['set_scraper', 'tcdb_upgrade'],
                                            auto_market: ['market_analytics', 'refresh_market_valuations'],
                                            auto_directory: ['set_browser', 'crawl_tcdb_directory'],
                                            process_scans: ['ingest_inventory', 'scan_ingest'],
                                          };
                                          const [ln, jt] = jobMap[pm] || ['set_scraper', 'tcdb_scrape'];
                                          triggerJob(ln, `Manual Run: ${s.Activity_Label || pm}`, jt);
                                        }}
                                        className="px-2 py-1 rounded-lg bg-emerald-950 hover:bg-emerald-700 text-emerald-200 border border-emerald-700 text-[11px] font-bold"
                                      >
                                        ▶️ Run
                                      </button>
                                      <button onClick={() => setSchedules(schedules.filter((_, i) => i !== idx))} className="px-2 py-1 rounded-lg bg-rose-950/70 hover:bg-rose-800 text-rose-300 text-[11px]">🗑️</button>
                                    </td>
                                  </tr>
                                ))
                              )}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>

                    {/* MODULE 4: 3-DRIVE STORAGE ARCHITECTURE & QUICK UTILITIES */}
                    <div className={`${modSpan('storage', 'lg:col-span-4')} ${skin.cardBg} border ${skin.border} rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                      <ModHeader modKey="storage" icon="💾" title="Storage Architecture & Utilities" subtitle="Active 3-drive Hub layout & quick tools" accentCls="text-emerald-300" />
                      {!settingsLayout.storage?.collapsed && (
                        <div className="space-y-3">
                          <div className="space-y-2 text-xs bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono">
                            <div><span className="text-slate-400">Hub &amp; Data Root (C:):</span><div className="text-emerald-300 truncate">{STORAGE_ROOT}</div></div>
                            <div><span className="text-slate-400">Card Media Library (D:):</span><div className="text-sky-300 truncate">{SET_LIBRARY_ROOT}</div></div>
                            <div><span className="text-slate-400">Cold Archive Vault (F:):</span><div className="text-amber-300 truncate">F:\Tabulas Archive</div></div>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <button onClick={openLogsFolder} className="py-1.5 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-sky-300">📂 Open Logs Folder</button>
                            <button onClick={() => openHiddenPage('notification_history')} className="py-1.5 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200">🔔 Notification Log</button>
                            <button onClick={() => setActivePage('about')} className="col-span-2 py-1.5 px-2.5 rounded-xl bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-700 text-xs font-bold text-emerald-200">🔄 Open Check for Updates (v{updaterInfo.current_version || APP_VERSION})</button>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* MODULE 4B: HARDWARE & GPU ACCELERATION (DIRECTML / CUDA / OPENCL + STEP-3 NEURAL FOUNDATION) */}
                    <div className={`${modSpan('hardware', 'lg:col-span-12')} ${skin.cardBg} border border-cyan-500/35 rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                      <ModHeader
                        modKey="hardware"
                        icon="⚡"
                        title="Hardware & GPU Acceleration (DirectML / CUDA / OpenCL)"
                        subtitle={
                          computeStatus?.primary_gpu?.name
                            ? `Detected GPU: ${computeStatus.primary_gpu.name}${computeStatus.primary_gpu.vram_gb ? ` (${computeStatus.primary_gpu.vram_gb} GB VRAM)` : ''} • Active OCR: ${computeStatus.active_ocr_provider || 'CPU'}`
                            : 'Probing local GPU & ONNX/OpenCL compute backends...'
                        }
                        accentCls="text-cyan-300"
                        extra={
                          !settingsLayout.hardware?.collapsed && (
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => { refreshComputeStatus(true); pushNotification('Hardware Probe Refreshed', 'Re-scanned GPU, DirectML/CUDA & OpenCL capabilities.', 'Compute', 'info'); }}
                                className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] text-sky-300 font-semibold"
                              >
                                🔍 Re-Probe
                              </button>
                              <button
                                type="button"
                                disabled={runningComputeBench}
                                onClick={() => {
                                  setRunningComputeBench(true);
                                  fetch(`${NODE_API_BASE}/compute/benchmark`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                                    .then((r) => r.json())
                                    .then((res) => {
                                      if (res?.success) {
                                        setComputeBench(res.benchmark);
                                        if (res.status) setComputeStatus(res.status);
                                        pushNotification(
                                          'Benchmark Complete',
                                          `OpenCL: ${res.benchmark?.opencl_speedup ? `${res.benchmark.opencl_speedup}x` : 'N/A'} | OCR: ${res.benchmark?.ocr_speedup ? `${res.benchmark.ocr_speedup}x` : 'CPU'} | DINOv2: ${res.benchmark?.dinov2?.speedup ? `${res.benchmark.dinov2.speedup}x (${res.benchmark.dinov2.gpu_cards_per_sec} cards/s)` : 'Not installed'}`,
                                          'Compute',
                                          'success'
                                        );
                                      }
                                    })
                                    .catch((e) => pushNotification('Benchmark Error', e.message, 'Compute', 'error'))
                                    .finally(() => setRunningComputeBench(false));
                                }}
                                className={`px-2.5 py-1 rounded-lg text-[11px] font-bold disabled:opacity-50 ${skin.accentBtn}`}
                              >
                                {runningComputeBench ? '⏳ Benchmarking...' : '⏱️ Run Benchmark'}
                              </button>
                            </div>
                          )
                        }
                      />
                      {!settingsLayout.hardware?.collapsed && (() => {
                        const cs = computeStatus || {};
                        const cSet = cs.settings || { compute_mode: 'auto', enable_ocr_gpu: true, enable_opencl_cv: true, enable_neural_embeddings: true, enable_multiregion_neural: true, neural_batch_size: 32, max_concurrent_gpu_workers: 2 };
                        const ort = cs.onnxruntime || {};
                        const ocl = cs.opencl || {};
                        const nf = cs.neural_foundation || {};
                        const updateComputeCfg = (patch) => {
                          const next = { ...cSet, ...patch };
                          fetch(`${NODE_API_BASE}/compute/settings`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(next),
                          })
                            .then((r) => r.json())
                            .then((res) => {
                              if (res?.success && res.status) {
                                setComputeStatus(res.status);
                                pushNotification('Compute Settings Saved', `Mode: ${next.compute_mode} • Active OCR: ${res.status.active_ocr_provider}`, 'Compute', 'success');
                              }
                            })
                            .catch(() => {});
                        };

                        return (
                          <div className="space-y-3 text-xs">
                            {/* HARDWARE PROBE SUMMARY CARDS */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-0.5">
                                <div className="text-[10px] text-slate-400 uppercase font-bold">Active Target GPU</div>
                                <div className="text-xs font-extrabold text-white truncate" title={cs.primary_gpu?.name || 'CPU Only'}>
                                  {cs.primary_gpu?.name || 'Detecting...'}
                                </div>
                                <div className="text-[10.5px] font-mono text-emerald-300">
                                  {cs.primary_gpu?.device_id !== undefined ? `DXGI #${cs.primary_gpu.device_id} • ` : ''}
                                  {cs.primary_gpu?.adapter_type || cs.primary_gpu?.vendor || '—'}
                                  {cs.primary_gpu?.vram_gb ? ` • ${cs.primary_gpu.vram_gb} GB` : ''}
                                </div>
                              </div>

                              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-0.5">
                                <div className="text-[10px] text-slate-400 uppercase font-bold">Win #1: RapidOCR Provider</div>
                                <div className={`text-xs font-extrabold font-mono ${cs.gpu_ocr_ready ? 'text-emerald-300' : 'text-amber-300'}`}>
                                  {cs.active_ocr_provider || 'CPUExecutionProvider'}
                                </div>
                                <div className="text-[10px] font-mono text-slate-400 truncate">
                                  Wheel: {ort.package_flavor || 'unknown'} {ort.version ? `v${ort.version}` : ''}
                                </div>
                              </div>

                              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-0.5">
                                <div className="text-[10px] text-slate-400 uppercase font-bold">Win #3: OpenCV OpenCL (600 DPI)</div>
                                <div className={`text-xs font-extrabold ${ocl.use_opencl ? 'text-emerald-300' : 'text-slate-400'}`}>
                                  {ocl.use_opencl ? '🟢 Active (cv2.UMat GPU)' : (ocl.have_opencl ? '⏸️ Available (Disabled)' : '⚪ CPU Fallback')}
                                </div>
                                <div className="text-[10px] font-mono text-slate-400 truncate" title={ocl.device_name || ''}>
                                  {ocl.device_name || 'Standard NumPy CPU'}
                                </div>
                              </div>

                              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-0.5">
                                <div className="text-[10px] text-slate-400 uppercase font-bold">VRAM Guardrail (Phase A)</div>
                                <div className="text-xs font-extrabold font-mono text-sky-300">
                                  {cs.active_gpu_worker_count || 0} / {cSet.max_concurrent_gpu_workers || 2} GPU Slots Active
                                </div>
                                <div className="text-[10px] text-slate-400">Overflow jobs auto-run on CPU</div>
                              </div>
                            </div>

                            {/* ONE-CLICK DIRECTML INSTALL BANNER WHEN AMD/WINDOWS GPU DETECTED WITHOUT DIRECTML */}
                            {cs.needs_directml_install && (
                              <div className="p-3 bg-amber-950/35 border border-amber-500/55 rounded-xl flex flex-wrap items-center justify-between gap-2.5">
                                <div className="min-w-0">
                                  <div className="text-xs font-bold text-amber-200">
                                    ⚡ GPU Detected ({cs.primary_gpu?.name}) — DirectML Runtime Not Installed Yet
                                  </div>
                                  <div className="text-[11px] text-slate-300 mt-0.5">
                                    Install <span className="font-mono text-sky-300">onnxruntime-directml</span> to unlock 3x–6x faster GPU RapidOCR (works on AMD Radeon, NVIDIA &amp; Intel GPUs on Windows with 100% automatic CPU fallback).
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => triggerJob('system', 'Install onnxruntime-directml (Windows GPU Runtime)', 'install_directml', { estimated_total: 3 })}
                                  className="px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-xs shadow shrink-0"
                                >
                                  📦 Install DirectML GPU Runtime
                                </button>
                              </div>
                            )}

                            {/* ACCELERATION CONTROLS */}
                            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center bg-slate-950/85 border border-slate-800 rounded-xl p-3">
                              <div className="md:col-span-3">
                                <label className="block text-[10px] text-slate-400 mb-1">Acceleration Mode</label>
                                <select
                                  value={cSet.compute_mode || 'auto'}
                                  onChange={(e) => updateComputeCfg({ compute_mode: e.target.value })}
                                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs"
                                >
                                  <option value="auto">Auto (GPU + CPU Fallback)</option>
                                  <option value="directml">Prefer DirectML (Windows)</option>
                                  <option value="cuda">Prefer CUDA (NVIDIA)</option>
                                  <option value="cpu">Force CPU Only</option>
                                </select>
                              </div>
                              <div className="md:col-span-4">
                                <label className="block text-[10px] text-slate-400 mb-1">Target GPU Adapter (dGPU Steered First)</label>
                                <select
                                  value={cSet.preferred_gpu_device_id ?? -1}
                                  onChange={(e) => updateComputeCfg({ preferred_gpu_device_id: parseInt(e.target.value, 10) })}
                                  className="w-full bg-slate-900 border border-cyan-700/70 rounded-lg px-2.5 py-1.5 text-xs font-mono text-cyan-200"
                                >
                                  <option value={-1}>
                                    Auto — Always Prefer dGPU ({cs.primary_gpu?.name || 'Discrete GPU'})
                                  </option>
                                  {(cs.dxgi_adapters || []).map((ad) => (
                                    <option key={ad.device_id} value={ad.device_id}>
                                      DXGI #{ad.device_id}: {ad.name} [{ad.adapter_type} • {ad.vram_gb} GB]
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div className="md:col-span-2">
                                <label className="block text-[10px] text-slate-400 mb-1">Max GPU Workers</label>
                                <select
                                  value={cSet.max_concurrent_gpu_workers || 2}
                                  onChange={(e) => updateComputeCfg({ max_concurrent_gpu_workers: parseInt(e.target.value, 10) || 2 })}
                                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono"
                                >
                                  <option value={1}>1 GPU Worker</option>
                                  <option value={2}>2 GPU Workers</option>
                                  <option value={3}>3 GPU Workers</option>
                                </select>
                              </div>
                              <div className="md:col-span-2">
                                <label className="block text-[10px] text-slate-400 mb-1">Neural Batch Size</label>
                                <select
                                  value={cSet.neural_batch_size || 32}
                                  onChange={(e) => updateComputeCfg({ neural_batch_size: parseInt(e.target.value, 10) || 32 })}
                                  className="w-full bg-slate-900 border border-indigo-700/70 rounded-lg px-2 py-1.5 text-xs font-mono text-indigo-200"
                                >
                                  <option value={16}>16 (Conservative)</option>
                                  <option value={32}>32 (RX 9070 XT)</option>
                                  <option value={64}>64 (Max Throughput)</option>
                                </select>
                              </div>
                              <div className="md:col-span-12 flex flex-wrap items-center gap-4 pt-1">
                                <label className="flex items-center gap-1.5 text-xs text-slate-200 cursor-pointer">
                                  <input type="checkbox" checked={!!cSet.enable_ocr_gpu} onChange={(e) => updateComputeCfg({ enable_ocr_gpu: e.target.checked })} />
                                  Enable RapidOCR GPU (Win #1)
                                </label>
                                <label className="flex items-center gap-1.5 text-xs text-slate-200 cursor-pointer">
                                  <input type="checkbox" checked={!!cSet.enable_opencl_cv} onChange={(e) => updateComputeCfg({ enable_opencl_cv: e.target.checked })} />
                                  OpenCL 600 DPI (Win #3)
                                </label>
                                <label className="flex items-center gap-1.5 text-xs text-indigo-200 cursor-pointer">
                                  <input type="checkbox" checked={cSet.enable_neural_embeddings !== false} onChange={(e) => updateComputeCfg({ enable_neural_embeddings: e.target.checked })} />
                                  DINOv2 Embeddings (Win #2)
                                </label>
                                <label className="flex items-center gap-1.5 text-xs text-emerald-200 cursor-pointer">
                                  <input type="checkbox" checked={cSet.enable_defect_ai !== false} onChange={(e) => updateComputeCfg({ enable_defect_ai: e.target.checked })} />
                                  Through-Sleeve Defect AI (Win #4: {nf.defect_ai_tier || 'OpenCL/CPU Hybrid'})
                                </label>
                              </div>
                            </div>

                            {/* LIVE BENCHMARK RESULTS (WINS #1, #2, #3 & #4) */}
                            {computeBench && (
                              <div className="p-3 bg-slate-950 border border-emerald-500/40 rounded-xl grid grid-cols-1 lg:grid-cols-4 gap-3 font-mono text-[11px]">
                                <div>
                                  <div className="text-emerald-300 font-bold mb-0.5">⏱️ Win #3 — 600 DPI Filters (1500×2100)</div>
                                  <div className="text-slate-300">
                                    CPU: <span className="text-white">{computeBench.opencl_cpu_ms ?? '—'} ms</span> • GPU:{' '}
                                    <span className="text-cyan-300">{computeBench.opencl_gpu_ms ?? 'N/A'} ms</span>
                                    {computeBench.opencl_speedup ? <span className="ml-1.5 text-emerald-400 font-bold">({computeBench.opencl_speedup}x)</span> : null}
                                  </div>
                                </div>
                                <div>
                                  <div className="text-sky-300 font-bold mb-0.5">⏱️ Win #1 — RapidOCR Card Back</div>
                                  <div className="text-slate-300">
                                    CPU: <span className="text-white">{computeBench.ocr_cpu_ms ?? '—'} ms</span> • GPU:{' '}
                                    <span className="text-cyan-300">{computeBench.ocr_gpu_ms ?? 'N/A'} ms</span>
                                    {computeBench.ocr_speedup ? <span className="ml-1.5 text-emerald-400 font-bold">({computeBench.ocr_speedup}x)</span> : null}
                                  </div>
                                </div>
                                <div>
                                  <div className="text-indigo-300 font-bold mb-0.5">🧬 Win #2 — DINOv2-small (Batch-{computeBench.dinov2?.batch_size || cSet.neural_batch_size || 32})</div>
                                  {computeBench.dinov2?.installed ? (
                                    <div className="text-slate-300">
                                      CPU: <span className="text-white">{computeBench.dinov2.cpu_cards_per_sec ?? '—'}/s</span> • GPU:{' '}
                                      <span className="text-cyan-300">{computeBench.dinov2.gpu_cards_per_sec ?? 'N/A'}/s</span>
                                      {computeBench.dinov2.speedup ? <span className="ml-1.5 text-emerald-400 font-bold">({computeBench.dinov2.speedup}x)</span> : null}
                                    </div>
                                  ) : (
                                    <div className="text-slate-500">Download DINOv2-small below to benchmark</div>
                                  )}
                                </div>
                                <div>
                                  <div className="text-teal-300 font-bold mb-0.5">🔬 Win #4 — Through-Sleeve Defect AI</div>
                                  {computeBench.defect_ai?.ready ? (
                                    <div className="text-slate-300">
                                      CPU Filter: <span className="text-white">{computeBench.defect_ai.cpu_filter_ms ?? '—'} ms</span> • Inspect:{' '}
                                      <span className="text-cyan-300">{computeBench.defect_ai.inspection_ms ?? '—'} ms</span>
                                    </div>
                                  ) : (
                                    <div className="text-slate-500">{computeBench.defect_ai?.note || 'OpenCL/CPU Hybrid Ready'}</div>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* STEP 3: DINOV2-SMALL DEEP VISUAL EMBEDDINGS DOWNLOADER & BATCHED GPU INDEXER */}
                            <div className="p-3 bg-slate-950/90 border border-indigo-500/40 rounded-xl flex flex-wrap items-center justify-between gap-2.5 text-[11px]">
                              <div className="min-w-0 space-y-0.5">
                                <div className="font-bold text-indigo-300 flex flex-wrap items-center gap-2">
                                  <span>🧬 Win #2 — DINOv2-small Deep Visual Embeddings (DirectML GPU)</span>
                                  {nf.dinov2_installed ? (
                                    <span className="px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-600 text-emerald-300 text-[10px] font-bold">✅ Model Installed</span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded-full bg-amber-950 border border-amber-600 text-amber-200 text-[10px] font-bold">Not Downloaded Yet</span>
                                  )}
                                </div>
                                <div className="text-slate-300">
                                  Indexed Card Embeddings: <span className="font-mono text-white font-bold">{(nf.cached_embeddings_count || 0).toLocaleString()}</span>
                                  {nf.multiregion_embeddings_count > 0 ? (
                                    <span className="text-cyan-300 ml-2 font-mono text-[10px]">
                                      • {nf.multiregion_embeddings_count.toLocaleString()} Multi-Region (v25)
                                    </span>
                                  ) : null}
                                  {nf.cache_updated_at ? <span className="text-slate-500 ml-2">(updated {nf.cache_updated_at})</span> : null}
                                  <span className="text-slate-500 ml-2 font-mono text-[10px]">{nf.models_dir || 'Cache\\Library\\Models'}</span>
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center gap-2 shrink-0">
                                {!nf.dinov2_installed ? (
                                  <button
                                    type="button"
                                    onClick={() => triggerJob('system', 'Download DINOv2-small ONNX (~88 MB)', 'download_dinov2_model', { force_redownload: false, estimated_total: 100 })}
                                    className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-extrabold text-xs shadow"
                                  >
                                    📥 Download DINOv2-small (~88 MB)
                                  </button>
                                ) : (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() => triggerJob('system', `Build / Update DINOv2 Neural Index (GPU Batch-${cSet.neural_batch_size || 32})`, 'build_neural_index', { batch_size: cSet.neural_batch_size || 32, force_rebuild: false, estimated_total: 1000 })}
                                      className={`px-3.5 py-1.5 rounded-xl font-extrabold text-xs shadow ${skin.accentBtn}`}
                                    >
                                      🧬 Build / Update Neural Index
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => triggerJob('system', `Rebuild Full DINOv2 Neural Index (GPU Batch-${cSet.neural_batch_size || 32})`, 'build_neural_index', { batch_size: cSet.neural_batch_size || 32, force_rebuild: true, estimated_total: 1000 })}
                                      title="Re-embed all Reference_Library and _My_Collection card images from scratch"
                                      className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 font-semibold text-xs"
                                    >
                                      ♻️ Rebuild All
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })()}
                    </div>

                    {/* MODULE 5 (HIDDEN UNTIL DEVELOPER MODE = ON): DEVELOPER & DEBUGGING TOOLS */}
                    {devMode && (
                      <div className={`${modSpan('devtools', 'lg:col-span-12')} ${skin.cardBg} border border-fuchsia-500/45 rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                        <ModHeader
                          modKey="devtools"
                          icon="🧪"
                          title="Developer & Debugging Tools"
                          subtitle="System diagnostics, Python AST audit, cache purge & maintenance triggers"
                          accentCls="text-fuchsia-300"
                        />
                        {!settingsLayout.devtools?.collapsed && (
                          <div className="space-y-3">
                            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                              <button onClick={() => fetch(`${NODE_API_BASE}/devtools/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'ast_audit' }) }).then((r) => r.json()).then((res) => { if (res.success) { setDevAuditResults(res.results || []); pushNotification('AST Audit Complete', `Checked ${(res.results || []).length} Python modules.`, 'DevTools', 'info'); } })} className="py-2 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-bold text-sky-300">🔍 Python AST Audit</button>
                              <button onClick={() => fetch(`${NODE_API_BASE}/devtools/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'clear_cache' }) }).then((r) => r.json()).then((res) => pushNotification('Caches Cleared', res.message || 'Done', 'DevTools', 'warning'))} className="py-2 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-bold text-amber-300">🧹 Purge .pkl Caches</button>
                              <button onClick={() => fetch(`${NODE_API_BASE}/devtools/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'cleanup_drivers' }) }).then((r) => r.json()).then((res) => pushNotification('Driver Cleanup', res.message || 'Done', 'DevTools', 'info'))} className="py-2 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-bold text-rose-300">🛑 Kill Orphan Drivers</button>
                              <button onClick={() => fetch(`${NODE_API_BASE}/devtools/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'check_cardsight' }) }).then((r) => r.json()).then((res) => pushNotification('CardSightAI Check', res.message || 'Checked', 'DevTools', 'info'))} className="py-2 px-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-bold text-emerald-300">🤖 Check CardSightAI</button>
                              <button onClick={() => triggerJob('system', 'System Maintenance & Housekeeping', 'system_maintenance', { estimated_total: 3 })} className="py-2 px-2.5 rounded-xl bg-emerald-950/80 hover:bg-emerald-800 border border-emerald-700 text-xs font-bold text-emerald-200">🛠️ System Maintenance</button>
                              <button onClick={() => pushNotification('Test Dev Notification', 'Verified adaptive fast auto-dismiss toast (max 3 stacked) + Notifications_History.csv archive.', 'DevTools', 'info')} className="py-2 px-2.5 rounded-xl bg-fuchsia-950 hover:bg-fuchsia-900 border border-fuchsia-700 text-xs font-bold text-fuchsia-200">🔔 Emit Test Toast</button>
                            </div>
                            {/* DEDICATED CARD ROTATION FIXER (NO RE-IDENTIFICATION — ROTATE + 8-CORNERS + RE-GRADE ONLY) */}
                            <div className="p-3 bg-slate-950/90 border border-cyan-500/35 rounded-xl flex flex-wrap items-center justify-between gap-2.5">
                              <div className="min-w-0">
                                <div className="text-xs font-bold text-cyan-300">↻ Card Rotation Fixer (Rotate + 8-Corner Sheet + Re-Grade Only)</div>
                                <div className="text-[10.5px] text-slate-400">
                                  Checks Front &amp; Back orientation without changing card identity. Impacted cards get rotated in-place with a new 8-corner sheet &amp; fresh pre-grade.
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center gap-2">
                                <select
                                  value={rotFixScope}
                                  onChange={(e) => setRotFixScope(e.target.value)}
                                  className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs"
                                >
                                  <option value="all">All Cards (Inventory + Batches)</option>
                                  <option value="inventory">Master Inventory Only (_My_Collection)</option>
                                  <option value="batches">Uncommitted Batches Only</option>
                                </select>
                                <select
                                  value={rotFixSet}
                                  onChange={(e) => setRotFixSet(e.target.value)}
                                  className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs max-w-[210px]"
                                >
                                  <option>All Sets</option>
                                  {dynamicSetsNewestFirst.map((s) => <option key={s}>{s}</option>)}
                                </select>
                                <button
                                  type="button"
                                  onClick={() => triggerJob(
                                    'system',
                                    `Card Rotation Fixer (${rotFixScope === 'all' ? 'All' : rotFixScope}${rotFixSet !== 'All Sets' ? `: ${rotFixSet}` : ''})`,
                                    'fix_card_rotations',
                                    {
                                      scope: rotFixScope,
                                      set_filter: rotFixSet === 'All Sets' ? '' : rotFixSet,
                                      dry_run: false,
                                      estimated_total: Math.max(1, inventory.length),
                                    }
                                  )}
                                  className={`px-3.5 py-1.5 rounded-xl font-bold text-xs ${skin.accentBtn}`}
                                >
                                  ↻ Run Rotation Fixer
                                </button>
                              </div>
                            </div>
                            {devAuditResults.length > 0 && (
                              <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs font-mono space-y-1">
                                {devAuditResults.map((r, i) => (
                                  <div key={i} className="flex justify-between">
                                    <span className="text-slate-300">{r.file}</span>
                                    <span className={r.ok ? 'text-emerald-400' : 'text-rose-400 font-bold'}>{r.ok ? `✅ ${r.message}` : `❌ ${r.message}`}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* MODULE 6 (HIDDEN UNTIL DEVELOPER MODE = ON): ADAPTIVE RATE & CARD-BASED ETA TELEMETRY */}
                    {devMode && (
                      <div className={`${modSpan('telemetry', 'lg:col-span-12')} ${skin.cardBg} border border-cyan-500/35 rounded-2xl p-4 space-y-3 transition-all duration-200`}>
                        <ModHeader
                          modKey="telemetry"
                          icon="🧠"
                          title="Adaptive Rate & Card-Based ETA Learner Telemetry"
                          subtitle={`Saved Wasted 404 Probes: ${(rateLearnerStats.totalSaved404Probes || 0).toLocaleString()} • State: ${rateLearnerStats.stateFile || 'adaptive_rate_learner.json'}`}
                          accentCls="text-cyan-300"
                          extra={
                            !settingsLayout.telemetry?.collapsed && (
                              <div className="flex items-center gap-1.5">
                                <button onClick={() => fetch(`${NODE_API_BASE}/rate-learner`).then((r) => r.json()).then((rl) => rl && setRateLearnerStats(rl)).catch(() => {})} className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] text-sky-300 font-semibold">🔄 Refresh</button>
                                <button onClick={() => fetch(`${NODE_API_BASE}/devtools/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'reset_rate_learner' }) }).then((r) => r.json()).then((res) => { if (res.rateLearner) setRateLearnerStats(res.rateLearner); pushNotification('Rate Learner Reset', res.message || 'Reset complete.', 'DevTools', 'warning'); })} className="px-2.5 py-1 rounded-lg bg-rose-950/80 hover:bg-rose-800 border border-rose-700 text-rose-200 text-[11px] font-bold">♻️ Reset</button>
                              </div>
                            )
                          }
                        />
                        {!settingsLayout.telemetry?.collapsed && (
                          <div className="space-y-3">
                            <div className="overflow-x-auto bg-slate-950 border border-slate-800 rounded-xl p-2">
                              <table className="w-full text-left text-[11px] font-mono whitespace-nowrap">
                                <thead className="text-slate-400 border-b border-slate-800">
                                  <tr><th className="p-1.5">Endpoint</th><th className="p-1.5">Learned RPM</th><th className="p-1.5">Delay (s)</th><th className="p-1.5">429 Cliff</th><th className="p-1.5">Clean Streak</th><th className="p-1.5">Requests</th><th className="p-1.5">429s</th><th className="p-1.5">Latency</th></tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800/70">
                                  {(rateLearnerStats.endpoints || []).map((ep) => (
                                    <tr key={ep.endpoint}>
                                      <td className="p-1.5 text-sky-300 font-bold">{ep.endpoint}</td>
                                      <td className="p-1.5 text-emerald-300 font-bold">{Number(ep.safe_rpm || 0).toFixed(1)}/min</td>
                                      <td className="p-1.5 text-amber-300">{Number(ep.current_delay_s || 0).toFixed(2)}s</td>
                                      <td className="p-1.5 text-slate-400">{ep.last_429_rpm ? `~${Number(ep.last_429_rpm).toFixed(0)}/min` : '—'}</td>
                                      <td className="p-1.5 text-emerald-400">{ep.clean_streak}</td>
                                      <td className="p-1.5 text-slate-200">{ep.total_requests}</td>
                                      <td className="p-1.5 text-rose-400">{ep.total_429s}</td>
                                      <td className="p-1.5 text-slate-400">{ep.ema_latency_ms ? `${ep.ema_latency_ms}ms` : '—'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            {Array.isArray(rateLearnerStats.setStats) && rateLearnerStats.setStats.length > 0 && (
                              <div className="bg-slate-950 border border-slate-800 rounded-xl p-2.5 space-y-1.5">
                                <div className="text-[11px] font-bold text-emerald-300">📊 Cached Set Card-Counts &amp; Run History ({rateLearnerStats.setStats.length} Sets in ETA Cache)</div>
                                <div className="max-h-52 overflow-auto">
                                  <table className="w-full text-left text-[10.5px] font-mono whitespace-nowrap">
                                    <thead className="text-slate-400 border-b border-slate-800 sticky top-0 bg-slate-950">
                                      <tr><th className="p-1">Set</th><th className="p-1">Total Cards</th><th className="p-1">Base</th><th className="p-1">Subsets</th><th className="p-1">Imgs DL (F/B)</th><th className="p-1">Last Run Speed</th></tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-800/60">
                                      {rateLearnerStats.setStats.slice(0, 60).map((ss) => {
                                        const lrEntries = Object.entries(ss.last_runs || {});
                                        const lastRunStr = lrEntries.length > 0
                                          ? lrEntries.map(([mk, rv]) => `${mk}: ${rv.cards_per_sec >= 1 ? `${rv.cards_per_sec}/s` : `${(rv.cards_per_sec * 60).toFixed(1)}/m`} (${fmtEta(rv.duration_sec)})`).join(' | ')
                                          : '—';
                                        return (
                                          <tr key={ss.set_key}>
                                            <td className="p-1 text-white font-sans font-semibold">{ss.set_name}</td>
                                            <td className="p-1 text-sky-300 font-bold">{Number(ss.total_cards || 0).toLocaleString()}</td>
                                            <td className="p-1 text-slate-300">{Number(ss.base_cards || 0).toLocaleString()}</td>
                                            <td className="p-1 text-slate-400">{ss.total_subsets || 0}</td>
                                            <td className="p-1 text-emerald-300">{Number(ss.fronts_downloaded || 0).toLocaleString()} / {Number(ss.backs_downloaded || 0).toLocaleString()}</td>
                                            <td className="p-1 text-amber-300">{lastRunStr}</td>
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* 23. CHECK FOR UPDATES */}
            {activePage === 'about' && (
              <div className={`flex-1 flex flex-col min-h-0 gap-4 ${skin.cardBg} border ${skin.border} rounded-2xl p-5`}>
                <div className="flex flex-wrap items-center justify-between gap-3 shrink-0">
                  <div>
                    <h2 className="text-base font-bold text-white">🔄 Check for Updates — Tabulas Card Hub v{updaterInfo.current_version || APP_VERSION}</h2>
                    <p className="text-xs text-slate-400">Incremental Atomic Code Updater ({STORAGE_ROOT}\Updates\) • {updaterInfo.message}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => setShowRollbackSnapshots(!showRollbackSnapshots)}
                      className={`px-3 py-2 rounded-xl border font-bold text-xs transition ${showRollbackSnapshots ? 'bg-amber-950/90 border-amber-500 text-amber-200' : 'bg-slate-800 hover:bg-slate-700 border-slate-600 text-amber-300'}`}
                    >
                      ⏪ Rollback Snapshots ({(updaterInfo.snapshots || []).length}) {showRollbackSnapshots ? '▲' : '▼'}
                    </button>
                    <button onClick={handleCheckForUpdates} className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sky-300 font-bold text-xs">🔍 Check for Updates</button>
                    <button onClick={handleApplyPendingUpdates} disabled={!updaterInfo.pending_count} className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-bold text-xs shadow">🚀 Apply Pending Updates ({updaterInfo.pending_count || 0}) &amp; Reload App</button>
                  </div>
                </div>

                {showRollbackSnapshots && (
                  <div className="bg-slate-950 border border-amber-500/40 rounded-xl p-3.5 space-y-2 max-h-60 overflow-y-auto shrink-0">
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-bold text-amber-400 uppercase">⏪ Rollback Snapshots (Restores Code &amp; Archives Newer Packages to .rolledback.txt)</div>
                      <button onClick={() => setShowRollbackSnapshots(false)} className="text-xs text-slate-400 hover:text-white">✖ Hide</button>
                    </div>
                    {(updaterInfo.snapshots || []).map((snap) => (
                      <div key={snap.version} className="flex items-center justify-between border-b border-slate-800 pb-1.5 text-xs">
                        <div>
                          <span className="font-mono font-bold text-white">v{snap.version}</span>{' '}
                          {snap.is_current && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-700">ACTIVE</span>}
                          <div className="text-[10px] text-slate-400">{snap.title} ({snap.created_at})</div>
                        </div>
                        {!snap.is_current && (
                          <button onClick={() => handleRollbackVersion(snap.version)} className="px-2.5 py-1 rounded-lg bg-amber-950 hover:bg-amber-800 text-amber-200 border border-amber-700 text-[11px] font-semibold">⏪ Rollback</button>
                        )}
                      </div>
                    ))}
                    {(updaterInfo.archived_snapshots_count > 0 || archivedRollbackSnaps.length > 0) && (
                      <div className="pt-1.5">
                        <button
                          onClick={() => {
                            if (showArchivedRollbacks) {
                              setShowArchivedRollbacks(false);
                              return;
                            }
                            fetch(`${NODE_API_BASE}/updater?includeArchived=true`)
                              .then((r) => r.json())
                              .then((d) => {
                                if (d && Array.isArray(d.archived_snapshots)) {
                                  setArchivedRollbackSnaps(d.archived_snapshots);
                                  setShowArchivedRollbacks(true);
                                }
                              })
                              .catch(() => {});
                          }}
                          className="text-xs text-sky-400 hover:text-sky-300 hover:underline font-semibold"
                        >
                          {showArchivedRollbacks
                            ? '▲ Hide older archived snapshots from F:\\Tabulas Archive'
                            : `📦 Show ${updaterInfo.archived_snapshots_count || archivedRollbackSnaps.length} more rollback option(s) from F:\\Tabulas Archive…`}
                        </button>
                        {showArchivedRollbacks && archivedRollbackSnaps.length > 0 && (
                          <div className="mt-2 pl-2 border-l-2 border-slate-700 space-y-1.5">
                            {archivedRollbackSnaps.map((snap) => (
                              <div key={`arc-${snap.version}`} className="flex items-center justify-between border-b border-slate-800/70 pb-1.5 text-xs">
                                <div>
                                  <span className="font-mono font-bold text-slate-200">v{snap.version}</span>{' '}
                                  <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">F: Archive</span>
                                  <div className="text-[10px] text-slate-400">{snap.title} ({snap.created_at})</div>
                                </div>
                                <button onClick={() => handleRollbackVersion(snap.version)} className="px-2.5 py-1 rounded-lg bg-amber-950 hover:bg-amber-800 text-amber-200 border border-amber-700 text-[11px] font-semibold">
                                  ⏪ Restore
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {moduleList.length > 0 && (
                  <div className="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2 shrink-0">
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-bold text-emerald-400 uppercase">🧩 Installed Module Registry ({moduleList.length} Modules)</div>
                      {moduleList.some((m) => m['New Version']) && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-950/90 border border-amber-500/70 text-amber-200">
                          🆕 {moduleList.filter((m) => m['New Version']).length} Module Update(s) Available
                        </span>
                      )}
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-[11px] whitespace-nowrap">
                        <thead className="text-slate-400 border-b border-slate-800">
                          <tr>
                            <th className="p-1.5">Module</th>
                            <th className="p-1.5">Role</th>
                            <th className="p-1.5">Current Version</th>
                            <th className="p-1.5">New Version</th>
                            <th className="p-1.5">Last Modified</th>
                            <th className="p-1.5">Size</th>
                            <th className="p-1.5">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/70">
                          {moduleList.map((m, i) => {
                            const newVer = String(m['New Version'] || '').trim();
                            const hasUpd = Boolean(newVer) || String(m.Status || '').includes('Update Available');
                            const isMissing = String(m.Status || '').includes('Missing');
                            return (
                              <tr key={i} className={hasUpd ? 'bg-amber-950/20' : ''}>
                                <td className="p-1.5 font-mono text-sky-300 font-semibold">{m.Module}</td>
                                <td className="p-1.5 text-slate-300">{m['Component Role']}</td>
                                <td className="p-1.5 font-mono text-emerald-300">{m['Disk Version'] ? `v${String(m['Disk Version']).replace(/^v/i, '')}` : '—'}</td>
                                <td className="p-1.5 font-mono">
                                  {newVer ? (
                                    <span className="px-1.5 py-0.5 rounded-md bg-amber-950/90 border border-amber-500/70 text-amber-200 font-bold">
                                      v{newVer.replace(/^v/i, '')}
                                    </span>
                                  ) : (
                                    <span className="text-slate-600">—</span>
                                  )}
                                </td>
                                <td className="p-1.5 font-mono text-slate-400">{m['Disk Last Modified']}</td>
                                <td className="p-1.5 font-mono text-slate-400">{m.Size}</td>
                                <td className="p-1.5">
                                  {hasUpd ? (
                                    <span className="px-2 py-0.5 rounded-full bg-amber-950/90 border border-amber-500/70 text-amber-200 text-[10px] font-bold">
                                      🆕 Update Available
                                    </span>
                                  ) : isMissing ? (
                                    <span className="px-2 py-0.5 rounded-full bg-rose-950/90 border border-rose-600/70 text-rose-200 text-[10px] font-bold">
                                      ❌ Missing
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-700/60 text-emerald-300 text-[10px] font-semibold">
                                      🟢 Current
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="flex-1 min-h-0 flex flex-col bg-slate-950 border border-slate-800 rounded-xl p-3.5 gap-2">
                  <div className="flex items-center justify-between shrink-0">
                    <div className="text-xs font-bold text-sky-400 uppercase">Changelogs</div>
                    <span className="text-[10.5px] font-mono text-slate-500">{(updaterInfo.packages || []).length} release(s) • newest first</span>
                  </div>
                  <div className="flex-1 min-h-0 overflow-y-auto space-y-2.5 pr-1">
                    {[...(updaterInfo.packages || [])].reverse().map((pkg) => (
                      <div key={pkg.package_file} className="border-b border-slate-800 pb-2.5 text-xs">
                        <div className="flex flex-wrap justify-between gap-2 font-semibold text-white">
                          <span>v{pkg.version} — {renderFormattedChangelog(pkg.title)} {pkg.is_rolled_back ? '(ROLLED BACK)' : ''}</span>
                          <span className="font-mono text-[10px] text-slate-400">{pkg.timestamp}</span>
                        </div>
                        <ul className="list-disc list-inside text-[11px] text-slate-300 mt-1 space-y-0.5 leading-relaxed">
                          {(pkg.changelog || []).map((c, i) => <li key={i}>{renderFormattedChangelog(c)}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 25. FULL NOTIFICATION HISTORY */}
            {activePage === 'notification_history' && (
              <div className={`flex-1 flex flex-col gap-3 min-h-0 ${skin.cardBg} border ${skin.border} rounded-2xl p-4`}>
                <div className="flex items-center justify-between shrink-0">
                  <div>
                    <h2 className="text-sm font-bold text-white">🔔 Full Notification History ({notifications.length} Visible)</h2>
                    <p className="text-xs text-slate-400">Clearing hides items in the UI while permanently preserving them in Inventory\Notifications_History.csv.</p>
                  </div>
                  {notifications.length > 0 && (
                    <button onClick={() => clearNotification('', true)} className="px-3 py-1.5 rounded-xl bg-amber-950 hover:bg-amber-800 text-amber-200 border border-amber-700 text-xs font-semibold">🧹 Clear All Visible</button>
                  )}
                </div>
                <div className="flex-1 min-h-0 overflow-auto border border-slate-800 rounded-xl">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 sticky top-0"><tr><th className="p-2">Timestamp</th><th className="p-2">Category</th><th className="p-2">Title</th><th className="p-2">Message</th><th className="p-2">Action</th></tr></thead>
                    <tbody className="divide-y divide-slate-800">
                      {notifications.map((n) => (
                        <tr key={n.Notification_ID} className="hover:bg-slate-800/40">
                          <td className="p-2 font-mono text-slate-400">{n.Timestamp}</td>
                          <td className="p-2">{n.Category}</td>
                          <td className="p-2 font-bold text-white">{n.Title}</td>
                          <td className="p-2 text-slate-300">{n.Message}</td>
                          <td className="p-2"><button onClick={() => clearNotification(n.Notification_ID, false)} className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px]">Clear</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            </TabulasErrorBoundary>
          </main>

          {/* RIGHT-HAND STAGED SET CART SIDEBAR */}
          {showCartSidebar && (
            <aside className={`w-80 ${skin.railBg} border-l ${skin.border} p-4 flex flex-col gap-3 shrink-0 shadow-2xl ${cartPinned ? 'relative' : 'absolute right-0 top-0 bottom-0 z-30'}`}>
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="text-xs font-bold text-emerald-300">🛒 Staged Set Cart ({setCart.length})</span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setCartPinned(!cartPinned)} className={`text-[10px] px-2 py-0.5 rounded border ${cartPinned ? skin.accentActive : 'bg-slate-800 border-slate-700'}`}>{cartPinned ? '📌' : '📍'}</button>
                  <button onClick={() => setShowCartSidebar(false)} className="text-[10px] px-2 py-0.5 rounded bg-slate-800 hover:bg-rose-700">✖</button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto space-y-2">
                {setCart.length === 0 ? (
                  <div className="text-xs text-slate-500 text-center py-6">Your Staged Set Cart is empty.</div>
                ) : (
                  setCart.map((c, idx) => (
                    <div key={idx} className="p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs space-y-1">
                      <div className="flex justify-between items-start gap-1">
                        <span className="font-bold text-white truncate">{c.Folder_Name}</span>
                        <button
                          onClick={() => {
                            const nextCart = setCart.filter((_, i) => i !== idx);
                            setSetCart(nextCart);
                            fetch(`${NODE_API_BASE}/config/set-cart`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(nextCart) }).catch(() => {});
                          }}
                          className="text-rose-400 hover:text-rose-200 text-[10px]"
                        >
                          ✖
                        </button>
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">{c.Sport} • {c.Year}</div>
                    </div>
                  ))
                )}
              </div>
              {setCart.length > 0 && (
                <div className="space-y-1.5">
                  <button
                    onClick={() => fetch(`${NODE_API_BASE}/config/set-cart`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'commit', cart: setCart }) })
                      .then((r) => r.json())
                      .then((res) => {
                        if (res && res.success) {
                          setSetCart([]);
                          setShowCartSidebar(false);
                          setTrackedSetsDirty(false);
                          refreshAllHubData();
                          pushNotification('Set Cart Committed', `Added ${res.committedCount ?? setCart.length} staged set(s) to tracked_sets.json.`, 'Set Browser', 'success');
                        } else {
                          pushNotification('Commit Cart Failed', res?.error || 'Could not commit set cart.', 'Set Browser', 'error');
                        }
                      })
                      .catch((e) => pushNotification('Commit Cart Error', e.message, 'Set Browser', 'error'))}
                    className="w-full py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs"
                  >
                    ✅ Commit {setCart.length} Set(s) to Tracked Queue
                  </button>
                  <button
                    onClick={() => {
                      setSetCart([]);
                      fetch(`${NODE_API_BASE}/config/set-cart`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([]) }).catch(() => {});
                      pushNotification('Set Cart Cleared', 'Emptied tcdb_set_cart.json.', 'Set Browser', 'info');
                    }}
                    className="w-full py-1.5 rounded-xl bg-rose-950/70 hover:bg-rose-800 text-rose-200 border border-rose-800 text-xs font-semibold"
                  >
                    🗑️ Clear Cart
                  </button>
                </div>
              )}
            </aside>
          )}

          {/* RIGHT-HAND LIVE MULTI-LANE MONITOR SIDEBAR (AUTO-HIDES ON MONITOR PAGE) */}
          {showMonitor && activePage !== 'live_monitor' && (
            <aside className={`w-96 ${skin.railBg} border-l ${skin.border} p-3.5 flex flex-col shrink-0 overflow-hidden shadow-2xl ${monitorPinned ? 'relative' : 'absolute right-0 top-0 bottom-0 z-30'}`}>
              {renderMonitorBody(false)}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
