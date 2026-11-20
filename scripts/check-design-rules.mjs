// Rendered checks for design rules that reading the CSS cannot hold (rules/ui.md, rules/design.md;
// docs/19 §8). Each was a written rule that a shipped interface broke without anyone noticing.
//
// Per view, from the config:
//   primary       one primary button per view (rules/ui.md "One primary button per view")
//   page-scroll   a view that fills the window never makes the page scroll (docs/17 §9)
//   first-screen  in a narrow window the view's main control starts on the first screen (docs/17 §9)
//   touch         on a touch screen every control reaches 44px, by its box or its ::after (docs/17 §2)
//   label         a label drawn over data marks covers none of them (docs/17 §10)
// The rendered-DOM layout lint (docs/19 §8), on every view at the desktop and the touch size.
// Never intentional, so they fail:
//   tiny-text        text under 10px; under 11px at phone width
//   touching-text    text closer than 4px to the edge of the box or card it sits in
//   spill            text sticking out of its box
//   sideways-scroll  the page scrolls sideways
//   input-zoom       a field under 16px on a touch screen (the page zooms on focus)
//   field-edge       a text field whose edge (or fill) is under 3:1 against what is behind it, at
//                    rest: it does not read as a place to type (rules/ui.md, WCAG 1.4.11)
//   motion-hides     text that is visible normally and hidden under reduced motion
// For a person to judge (listed, never failing unless --strict):
//   tight-inset      text 4 to 8px from its box's edge (the rule's minimum is 8, 12 preferred)
//   card-in-card, border-and-shadow, near-tangent (edges 1 to 7px apart), heading-space (less room
//   above a heading than below), control-text (button text off 12-14px, code under 13px),
//   line-height (small wrapped text under 1.3), emoji, straight-quote (' or " in UI copy, not in
//   code or a text field), dark-panel (a panel darker than the page)
// A finding that is right as it is gets a waiver in the config with a reason; more than five
// waivers is itself a failure, and hiding the element to clear a finding is a bug (docs/19 §8).
//
// Origin: a PowerShell tool's web UI, 2026-11-14. A whole-interface review, eight releases in, found
// two primary buttons in an edit form, a map that scrolled the page by 37px, the main input a full
// screen down in a half-width window, 28px controls on touch and topic names lying on their own dots.
// Every one of those rules was already in rules/; none had a check.
//
//   node scripts/check-design-rules.mjs --config design-check.json [--strict] [--port 9559] [--browser <path>]
//   node scripts/check-design-rules.mjs --self-test     proves each rule fails on a broken page
//
// design-check.json (every key but "views" has a default):
//   { "base": "http://127.0.0.1:5193",
//     "api": { "/api/status": { "ok": true } },      answered in the browser, so no server is needed;
//                                                     invented data only
//     "primary": ".btn--primary",
//     "controls": "button, a.btn, select, input, [role=tab]",
//     "exempt": ".link-btn",                          text links inside a sentence (WCAG 2.5.8)
//     "lintIgnore": ".map svg",                       parts the lint does not read (a canvas, a chart)
//     "waivers": [{ "rule": "tight-inset", "match": "kbd", "reason": "key caps are 4px by design" }],
//     "desktop": [[1440, 900], [1024, 768]], "narrow": [[720, 900], [390, 844]], "touch": [390, 844],
//     "views": [
//       { "name": "home", "path": "/", "ready": ".composer", "main": ".composer" },
//       { "name": "map", "path": "/#/graph", "ready": ".dot", "fill": true, "labels": ".area-name", "marks": "circle.dot" },
//       { "name": "edit form", "path": "/#/graph", "ready": ".dot", "steps": [{ "click": "Edit" }, { "wait": 400 }] } ] }
// A view's "steps" reach a state: { "click": "<button text>" }, { "clickSelector": "<css>" }, { "wait": ms }.
// "touch": false or "lint": false on a view skips that part. 720px is half of a 1440px screen: the
// width of a window snapped beside another, which the phone width does not cover.
// Run it against the dev server or the built app on a test port, never the person's live instance.
// Exit 0 = every rule holds (findings to judge are listed); 1 = a rule is broken (view, rule, what
// was measured); 2 = setup, or nothing was checked (an empty run is not a pass). No dependencies
// (Node 22+). Writes nothing but a temp browser profile.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULTS = {
  base: '',
  api: null,
  primary: '.btn--primary',
  controls: 'button, select, input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]):not([type=file]), a[class*="btn"], a[class*="button"], [role="button"], [role="tab"]',
  exempt: '',
  lintIgnore: '',
  waivers: [],
  desktop: [[1440, 900], [1024, 768]],
  narrow: [[720, 900], [390, 844]],
  touch: [390, 844],
  touchTarget: 44,
  firstScreen: 0.6,
  wait: 500,
  views: [],
};
const MAX_WAIVERS = 5;
const BROWSERS = [
  process.env.CHROME_PATH,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/microsoft-edge',
].filter(Boolean);

function parseArgs(argv) {
  const o = { config: '', port: 9559, browser: '', selfTest: false, strict: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--config') o.config = argv[++i];
    else if (a === '--port') o.port = Number(argv[++i]);
    else if (a === '--browser') o.browser = argv[++i];
    else if (a === '--self-test') o.selfTest = true;
    else if (a === '--strict') o.strict = true;
    else { console.error(`Unknown argument: ${a}`); process.exit(2); }
  }
  return o;
}

// ---------- scans that run in the page; each returns a JSON value ----------
const visible = `const seen = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); if (!(r.width > 0 && r.height > 0) || s.visibility === 'hidden') return false; const open = document.querySelector('dialog[open]'); return open ? open.contains(e) : !e.closest('dialog'); };`;
const primaryScan = (sel) => `(() => { ${visible} return JSON.stringify([...document.querySelectorAll(${JSON.stringify(sel)})].filter(seen).map((e) => (e.textContent.trim() || e.getAttribute('aria-label') || e.tagName).slice(0, 30))); })()`;
const scrollScan = `JSON.stringify([document.documentElement.scrollHeight, innerHeight])`;
const topScan = (sel) => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); return JSON.stringify(e ? Math.round(e.getBoundingClientRect().top + scrollY) : null); })()`;
// The reach of a control: its own box, or the invisible ::after that grows it (docs/10 §4).
const touchScan = (sel, exempt, min) => `(() => { ${visible}
  const reach = (e) => { const h = e.getBoundingClientRect().height; const a = getComputedStyle(e, '::after'); return a.content !== 'none' && a.position === 'absolute' ? Math.max(h, parseFloat(a.height) || 0) : h; };
  const exempt = ${JSON.stringify(exempt)};
  return JSON.stringify([...document.querySelectorAll(${JSON.stringify(sel)})].filter((e) => seen(e) && !e.closest('svg') && !(exempt && e.matches(exempt)) && reach(e) < ${min} - 0.5)
    .map((e) => (e.textContent.trim() || e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.tagName).replace(/\\s+/g, ' ').slice(0, 24) + '=' + Math.round(reach(e)) + 'px')); })()`;
const labelScan = (labels, marks) => `(() => { ${visible}
  const hit = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const boxes = [...document.querySelectorAll(${JSON.stringify(marks)})].map((m) => m.getBoundingClientRect()).filter((r) => r.width > 0);
  return JSON.stringify([...document.querySelectorAll(${JSON.stringify(labels)})].filter((l) => seen(l) && getComputedStyle(l).opacity !== '0')
    .map((l) => ({ name: l.textContent.trim().slice(0, 30), n: boxes.filter((b) => hit(l.getBoundingClientRect(), b)).length })).filter((x) => x.n > 0).map((x) => x.name + ' covers ' + x.n)); })()`;
// How much text a person can see: compared between a normal load and one with reduced motion.
const textScan = `(() => { let n = 0; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t = w.nextNode(); t; t = w.nextNode()) { const e = t.parentElement; if (e && t.nodeValue.trim() && !e.closest('script, style, noscript') && e.checkVisibility({ opacityProperty: true, visibilityProperty: true })) n += t.nodeValue.trim().length; }
  return JSON.stringify(n); })()`;
// Dark scheme: a bordered or rounded panel whose fill is darker than the page behind it.
const darkScan = (ignore) => `(() => { ${visible}
  const lum = (c) => { const m = c.match(/[\\d.]+/g); if (!m) return null; let [r, g, b, a] = m.map(Number); if (c.startsWith('color(')) { r *= 255; g *= 255; b *= 255; } if (a === 0 || c === 'transparent') return null; return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };
  const page = lum(getComputedStyle(document.body).backgroundColor) ?? lum(getComputedStyle(document.documentElement).backgroundColor);
  if (page === null) return JSON.stringify([]);
  const ignore = ${JSON.stringify(ignore)};
  const out = [];
  for (const e of document.querySelectorAll('body *')) {
    if (out.length >= 6 || !seen(e) || e.closest('svg') || (ignore && e.closest(ignore))) continue;
    const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    if (r.width < 120 || r.height < 48 || !(parseFloat(s.borderTopWidth) > 0 || parseFloat(s.borderTopLeftRadius) >= 6)) continue;
    const l = lum(s.backgroundColor);
    if (l !== null && l < page - 0.004) out.push(e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\\s+/)[0] : ''));
  }
  return JSON.stringify(out); })()`;

// The layout lint. Returns { fail: [...], judge: [...] }, each entry "[rule] element what".
const lintScan = (phone, coarse, ignore) => `(() => { ${visible}
  const ignore = ${JSON.stringify(ignore)};
  const out = { fail: [], judge: [] };
  const counts = {};
  const tag = (e) => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\\s+/)[0] : '');
  const say = (tier, rule, e, what) => { if (ignore && e.closest(ignore)) return; counts[rule] = (counts[rule] || 0) + 1; if (counts[rule] <= 6) out[tier].push('[' + rule + '] ' + tag(e) + ' ' + what); };
  const px = (v) => parseFloat(v) || 0;
  // Transparent: alpha 0 only (rgba(..., 0) or "/ 0"); opaque black rgb(0, 0, 0) is a colour.
  const clear = (c) => !c || c === 'transparent' || /^rgba\\(.*,\\s*0(\\.0+)?\\)$|\\/\\s*0(\\.0+)?\\)$/.test(c);
  const CONTROL = 'button, [role=button], [role=tab], [role=menuitem], input, select, textarea, kbd';
  // The box a text sits in: the nearest ancestor with an edge or a fill of its own.
  const boxOf = (e) => { for (let p = e; p && p !== document.body; p = p.parentElement) { const s = getComputedStyle(p); if (s.display === 'inline') continue; if ((px(s.borderLeftWidth) > 0 && !clear(s.borderLeftColor)) || !clear(s.backgroundColor)) return p; } return null; };
  const sized = new Set(); const boxed = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const e = n.parentElement;
    if (!n.nodeValue.trim() || !e || !seen(e) || e.closest('svg, script, style, noscript')) continue;
    const er = e.getBoundingClientRect();
    if (er.width <= 2 || er.height <= 2) continue; // text for screen readers only
    const range = document.createRange(); range.selectNodeContents(n);
    const b = range.getBoundingClientRect();
    if (b.width < 1 || b.height < 1) continue;
    const s = getComputedStyle(e); const fs = px(s.fontSize);
    if (!sized.has(e)) {
      sized.add(e);
      if (fs < 10) say('fail', 'tiny-text', e, fs + 'px: "' + n.nodeValue.trim().slice(0, 24) + '"');
      else if (${phone} && fs < 11) say('fail', 'tiny-text', e, fs + 'px at phone width: "' + n.nodeValue.trim().slice(0, 24) + '"');
      if (fs < 13 && b.height > fs * 2.2 && s.lineHeight !== 'normal' && px(s.lineHeight) / fs < 1.3) say('judge', 'line-height', e, (px(s.lineHeight) / fs).toFixed(2) + ' on ' + fs + 'px wrapped text');
      if (/\\p{Emoji_Presentation}/u.test(n.nodeValue)) say('judge', 'emoji', e, '"' + n.nodeValue.trim().slice(0, 24) + '"');
      // UI copy uses curly quotes; code and what the user types keep straight ones (docs/01 §3).
      if (/['"]/.test(n.nodeValue) && !e.closest('code, pre, kbd, samp, textarea')) say('judge', 'straight-quote', e, '"' + n.nodeValue.trim().slice(0, 32) + '"');
    }
    if (e.closest(CONTROL)) continue;
    const box = boxOf(e);
    if (!box || boxed.has(box)) continue;
    const bs = getComputedStyle(box); const br = box.getBoundingClientRect();
    // Clipped when the box or anything between it and the text clips (a label with an ellipsis).
    let clips = bs.overflowX !== 'visible';
    for (let p = e; p && p !== box && !clips; p = p.parentElement) clips = getComputedStyle(p).overflowX !== 'visible';
    const left = b.left - br.left - px(bs.borderLeftWidth); const right = br.right - px(bs.borderRightWidth) - b.right;
    const inset = Math.min(left, right);
    if (inset < -1) { if (!clips) { boxed.add(box); say('fail', 'spill', box, 'text sticks out by ' + Math.round(-inset) + 'px: "' + n.nodeValue.trim().slice(0, 24) + '"'); } }
    else if (inset < 4) { boxed.add(box); say('fail', 'touching-text', box, Math.round(inset * 10) / 10 + 'px from its edge: "' + n.nodeValue.trim().slice(0, 24) + '"'); }
    else if (inset < 8) { boxed.add(box); say('judge', 'tight-inset', box, Math.round(inset * 10) / 10 + 'px from its edge: "' + n.nodeValue.trim().slice(0, 24) + '"'); }
  }
  if (document.documentElement.scrollWidth > innerWidth + 1) {
    const wide = [...document.querySelectorAll('body *')].find((e) => seen(e) && e.getBoundingClientRect().right > innerWidth + 1 && !e.closest('svg'));
    say('fail', 'sideways-scroll', wide || document.body, 'the page is ' + document.documentElement.scrollWidth + 'px wide in a ' + innerWidth + 'px window');
  }
  for (const e of document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]):not([type=file]), select, textarea')) {
    if (${coarse} && seen(e) && px(getComputedStyle(e).fontSize) < 16) say('fail', 'input-zoom', e, px(getComputedStyle(e).fontSize) + 'px on a touch screen');
  }
  // field-edge: measured at rest (a focused field shows its focus look; an autofocused box passed on
  // it). Colours are painted on a 1px canvas, so color-mix(), color(srgb ...) and system colours come
  // out as rgb, and translucent layers behind the field are composited in order.
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
  const cv = document.createElement('canvas'); cv.width = cv.height = 1; const cx = cv.getContext('2d', { willReadFrequently: true });
  const paint = (layers) => { cx.globalCompositeOperation = 'copy'; cx.fillStyle = '#fff'; cx.fillRect(0, 0, 1, 1); cx.globalCompositeOperation = 'source-over'; for (const c of layers) { cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1); } const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2]]; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // The edge and fill of a box against the backgrounds behind it.
  const strength = (box) => {
    const s = getComputedStyle(box); const under = [];
    for (let p = box.parentElement; p; p = p.parentElement) { const c = getComputedStyle(p).backgroundColor; if (!clear(c)) under.unshift(c); }
    const base = paint(under);
    // The strongest side: an underlined field has only a bottom edge, and a field joined to a tool row
    // below it has its edge on the top and sides (a PowerShell bridge's message box, 16 Nov 2026).
    const side = (n) => (px(s['border' + n + 'Width']) >= 1 && !clear(s['border' + n + 'Color']) ? contrast(paint([...under, s['border' + n + 'Color']]), base) : 0);
    return { edge: Math.max(side('Top'), side('Right'), side('Bottom'), side('Left')), fill: clear(s.backgroundColor) ? 0 : contrast(paint([...under, s.backgroundColor]), base) };
  };
  // A bare field inside a group (an input with an affix, a tag input) shows the group's box: the
  // nearest of its three closest ancestors that draws an edge (the kit gallery's input groups, 17 Nov 2026).
  const wrapperOf = (e) => { let p = e.parentElement; for (let n = 0; p && n < 3; n++, p = p.parentElement) { const s = getComputedStyle(p); if (['Top', 'Right', 'Bottom', 'Left'].some((k) => px(s['border' + k + 'Width']) >= 1 && !clear(s['border' + k + 'Color']))) return p; } return null; };
  for (const e of document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]):not([type=file]):not([type=color]), select, textarea')) {
    if (!seen(e)) continue;
    let { edge, fill } = strength(e), by = '';
    const wrap = !edge && !fill ? wrapperOf(e) : null;
    if (wrap) { ({ edge, fill } = strength(wrap)); by = ' (drawn by ' + tag(wrap) + ')'; }
    if (Math.max(edge, fill) < 3) say('fail', 'field-edge', e, 'edge ' + edge.toFixed(2) + ':1, fill ' + fill.toFixed(2) + ':1 against what is behind it (3:1 needed)' + by);
  }
  for (const e of document.querySelectorAll('button, [role=button], [role=menuitem]')) {
    const f = px(getComputedStyle(e).fontSize);
    // 12px is the small control size; a button in a table head follows the head's 11 to 12px.
    if (seen(e) && e.textContent.trim() && !e.closest('svg, th') && (f < 12 || f > 14) && !${coarse}) say('judge', 'control-text', e, f + 'px (13 to 14, 12 for small controls): "' + e.textContent.trim().slice(0, 20) + '"');
  }
  for (const e of document.querySelectorAll('code, pre')) if (seen(e) && px(getComputedStyle(e).fontSize) < 13) say('judge', 'control-text', e, px(getComputedStyle(e).fontSize) + 'px code (13 or more)');
  // Cards: a box with an edge all round and rounded corners, big enough to hold content.
  const floating = (e) => e.closest('dialog, [role=menu], [role=tooltip], [role=listbox]') === e || ['fixed', 'absolute'].includes(getComputedStyle(e).position);
  const cards = [...document.querySelectorAll('body *')].filter((e) => { if (!seen(e) || e.matches('button, a, input, select, textarea, dialog') || e.closest('svg')) return false; const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    return r.width >= 120 && r.height >= 48 && px(s.borderTopLeftRadius) >= 6 && ['Top', 'Right', 'Bottom', 'Left'].every((k) => px(s['border' + k + 'Width']) > 0 && !clear(s['border' + k + 'Color'])); });
  for (const c of cards) {
    const outer = cards.find((o) => o !== c && o.contains(c));
    if (outer) say('judge', 'card-in-card', c, 'inside ' + tag(outer));
    const sh = getComputedStyle(c).boxShadow;
    if (sh !== 'none' && !floating(c) && sh.split(/,(?![^(]*\\))/).some((x) => !/inset/.test(x))) say('judge', 'border-and-shadow', c, 'has both');
  }
  for (const p of document.querySelectorAll('body, body *')) {
    if (p.closest('svg') || p.children.length < 2 || p.children.length > 40) continue;
    const kids = [...p.children].filter((k) => seen(k) && getComputedStyle(k).position !== 'absolute' && getComputedStyle(k).display !== 'inline').map((k) => ({ k, r: k.getBoundingClientRect() }));
    for (let i = 1; i < kids.length; i++) {
      const a = kids[i - 1], b = kids[i];
      if (b.r.top < a.r.bottom - 1) continue; // side by side, not stacked
      const d = Math.abs(a.r.left - b.r.left);
      if (d > 0.75 && d < 8) { say('judge', 'near-tangent', b.k, 'starts ' + Math.round(d * 10) / 10 + 'px off ' + tag(a.k) + ' above it'); break; }
    }
  }
  for (const h of document.querySelectorAll('h1, h2, h3, h4')) {
    const prev = h.previousElementSibling, next = h.nextElementSibling;
    if (!seen(h) || !prev || !next || !seen(prev) || !seen(next)) continue;
    const r = h.getBoundingClientRect(); const above = r.top - prev.getBoundingClientRect().bottom; const below = next.getBoundingClientRect().top - r.bottom;
    if (above >= 0 && below > 0 && above + 0.5 < below) say('judge', 'heading-space', h, Math.round(above) + 'px above, ' + Math.round(below) + 'px below');
  }
  for (const [rule, n] of Object.entries(counts)) if (n > 6) { const tier = out.fail.some((x) => x.startsWith('[' + rule + ']')) ? 'fail' : 'judge'; out[tier].push('[' + rule + '] and ' + (n - 6) + ' more'); }
  return JSON.stringify(out); })()`;

// Closes the browser through its debug connection. The process spawn() starts is only the launcher:
// Edge starts the real browser and the launcher exits, so proc.kill() reached nothing and every run
// left the browser and its helpers running (12 processes after one self-test on Windows, 15 Nov 2026).
async function closeBrowser(ws, wait) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const closed = new Promise((r) => ws.addEventListener('close', r));
  try { ws.send(JSON.stringify({ id: 1e9, method: 'Browser.close' })); } catch { return; }
  await Promise.race([closed, wait(3000)]);
}

// Deletes the temp profile, retrying for up to 5 s while the closing browser releases its files;
// after 1 s it stops any process still running with this profile (Windows). One try left a profile
// of up to 17 MB behind on most runs (19 Nov 2026: 304 folders, 1.5 GB in TEMP). Says so when it stays.
async function removeProfile(profile, wait) {
  for (let k = 0; k < 20; k++) {
    if (k === 4 && process.platform === 'win32') {
      const p = profile.replace(/'/g, "''");
      spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
        `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('${p}') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`], { stdio: 'ignore' });
    }
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* still in use */ }
    if (!existsSync(profile)) return;
    await wait(250);
  }
  console.error(`Could not delete the temp browser profile ${profile}; delete it by hand.`);
}

/** The browser to run: --browser, else the first one installed. Exits 2 (setup) when there is none. */
function findBrowser(o) {
  const exe = o.browser || BROWSERS.find((p) => existsSync(p));
  if (!exe) { console.error('No Edge or Chrome found: pass --browser <path> or set CHROME_PATH.'); process.exit(2); }
  if (!existsSync(exe)) { console.error(`No browser at ${exe}: pass --browser <path> or set CHROME_PATH.`); process.exit(2); }
  return exe;
}

/** Waits up to 15 s for the browser's debug port, then opens its socket. */
async function connect(port, wait) {
  let info;
  for (let i = 0; i < 60 && !info; i++) { try { info = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch { await wait(250); } }
  if (!info) throw new Error(`the browser did not open its debug port ${port}`);
  const ws = new WebSocket(info.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  return ws;
}

/** The app's API, answered here from the config: no server, no real data. */
function fulfil(send, api, m) {
  const body = api[new URL(m.params.request.url).pathname];
  send('Fetch.fulfillRequest', { requestId: m.params.requestId, responseCode: body === undefined ? 404 : 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
    body: Buffer.from(JSON.stringify(body === undefined ? { error: 'not in design-check.json "api"' } : body)).toString('base64') }, m.sessionId).catch(() => {});
}

/** A DevTools client on the socket: send(method, params, sessionId) resolves with the result. */
function devtools(ws, api) {
  let id = 0;
  const pending = new Map();
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => { const i = ++id; pending.set(i, { resolve, reject }); ws.send(JSON.stringify({ id: i, method, params, sessionId })); });
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    const p = m.id && pending.get(m.id);
    if (p) { pending.delete(m.id); if (m.error) p.reject(new Error(m.error.message)); else p.resolve(m.result); return; }
    if (m.method === 'Fetch.requestPaused') fulfil(send, api, m);
  });
  return send;
}

/** Opens one tab and returns S (a DevTools call in it) and js (an expression's value in it). */
async function openTab(send, api) {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable');
  if (api) await S('Fetch.enable', { patterns: Object.keys(api).map((p) => ({ urlPattern: `*${p}*` })) });
  const js = async (expression) => {
    const r = await S('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(`a scan failed in the page: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
    return r.result.value;
  };
  return { S, js };
}

async function withBrowser(o, cfg, fn) {
  const exe = findBrowser(o);
  const profile = mkdtempSync(join(tmpdir(), 'design-rules-'));
  const proc = spawn(exe, ['--headless=new', `--remote-debugging-port=${o.port}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  let ws = null;
  try {
    ws = await connect(o.port, wait);
    const tab = await openTab(devtools(ws, cfg.api), cfg.api);
    return await fn({ ...tab, wait });
  } finally {
    await closeBrowser(ws, wait);
    proc.kill();
    await wait(300);
    await removeProfile(profile, wait);
  }
}

/** Opens a view in the state its steps describe. Throws when its ready element never shows: an
 *  empty page must never count as a pass. `media`: { dark, reduced } for that load. */
async function open(page, cfg, view, [w, h], touch = false, media = {}) {
  await emulate(page, [w, h], touch, media);
  await page.S('Page.navigate', { url: 'about:blank' });
  await page.S('Page.navigate', { url: view.url || cfg.base + (view.path || '/') });
  if (view.ready) await waitForReady(page, cfg, view, w);
  await page.wait(cfg.wait);
  for (const s of view.steps || []) await runStep(page, view, s);
}

/** The window size, touch, and the colour scheme and motion preference of the next load. */
async function emulate(page, [w, h], touch, media) {
  await page.S('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: touch });
  await page.S('Emulation.setTouchEmulationEnabled', { enabled: touch });
  await page.S('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: media.dark ? 'dark' : 'light' }, { name: 'prefers-reduced-motion', value: media.reduced ? 'reduce' : 'no-preference' }] });
}

/** Waits up to 10 s for the view's ready element; throws when it never shows. */
async function waitForReady(page, cfg, view, w) {
  for (let k = 0; k < 100; k++) {
    if (await page.js(`!!document.querySelector(${JSON.stringify(view.ready)})`).catch(() => false)) return;
    await page.wait(100);
  }
  throw new Error(`view "${view.name}": "${view.ready}" never appeared at ${w}px (is the app running on ${cfg.base}?)`);
}

const clickByText = (text) => `(() => { const b = [...document.querySelectorAll('button, a, [role=button], [role=tab]')].find((e) => e.textContent.trim() === ${JSON.stringify(text)} && e.getBoundingClientRect().width > 0); if (b) b.click(); return !!b; })()`;
const clickBySelector = (sel) => `(() => { const b = document.querySelector(${JSON.stringify(sel)}); if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true })); return !!b; })()`;

/** One step towards the view's state: a wait, or a click that must find its target. */
async function runStep(page, view, s) {
  if (s.wait) { await page.wait(s.wait); return; }
  const found = await page.js(s.click ? clickByText(s.click) : clickBySelector(s.clickSelector));
  if (!found) throw new Error(`view "${view.name}": step ${JSON.stringify(s)} found nothing to click`);
  await page.wait(300);
}

/** The layout lint of one view: desktop and touch, then the dark and the reduced-motion load. */
const LINT_FAILS = ['tiny-text', 'touching-text', 'spill', 'sideways-scroll', 'input-zoom', 'field-edge'];

/** Lint findings ("[rule] text") grouped by rule, without the rule prefix. */
export function byRule(found) {
  const rules = new Map();
  for (const f of found) { const rule = f.match(/^\[([\w-]+)\]/)[1]; rules.set(rule, [...(rules.get(rule) || []), f.replace(/^\[[\w-]+\] /, '')]); }
  return rules;
}

/** The layout lint at one size; a finding to judge is listed once per view. */
async function lintAt(c, view, size, touch, seenJudge) {
  await open(c.page, c.cfg, view, size, touch);
  const found = await c.list(lintScan(size[0] < 600, touch, c.cfg.lintIgnore));
  const where = touch ? ` (touch, ${size[0]}px)` : '';
  const rules = byRule(found.fail);
  for (const rule of LINT_FAILS) c.expect(!rules.has(rule), view, rule, (rules.get(rule) || []).join('; ') + where);
  for (const j of found.judge) if (!seenJudge.has(j)) { seenJudge.add(j); c.judge.push(`${view.name}  ${j}${where}`); }
}

/** The layout lint of one view: desktop and touch, then the dark and the reduced-motion load. */
async function lint(c, view) {
  const seenJudge = new Set();
  await lintAt(c, view, c.cfg.desktop[0], false, seenJudge);
  await lintAt(c, view, c.cfg.touch, true, seenJudge);
  await open(c.page, c.cfg, view, c.cfg.desktop[0]);
  const normal = await c.list(textScan);
  await open(c.page, c.cfg, view, c.cfg.desktop[0], false, { reduced: true });
  const reduced = await c.list(textScan);
  c.expect(reduced >= normal * 0.95, view, 'motion-hides', `${normal} characters of text normally, ${reduced} under reduced motion`);
  await open(c.page, c.cfg, view, c.cfg.desktop[0], false, { dark: true });
  for (const p of await c.list(darkScan(c.cfg.lintIgnore))) c.judge.push(`${view.name}  [dark-panel] ${p} is darker than the page`);
}

/** primary, and label when the view names labels and marks: both at the first desktop size. */
async function checkDesktop(c, view) {
  await open(c.page, c.cfg, view, c.cfg.desktop[0]);
  const prim = await c.list(primaryScan(c.cfg.primary));
  c.expect(prim.length <= 1, view, 'primary', `${prim.length} primary buttons: ${prim.join(', ')}`);
  if (!view.labels || !view.marks) return;
  const under = await c.list(labelScan(view.labels, view.marks));
  c.expect(under.length === 0, view, 'label', `labels over marks: ${under.join('; ')}`);
}

/** page-scroll, for a view that fills the window: at each desktop size. */
async function checkFill(c, view) {
  for (const size of c.cfg.desktop) {
    await open(c.page, c.cfg, view, size);
    const [doc, inner] = await c.list(scrollScan);
    c.expect(doc <= inner, view, 'page-scroll', `the page is ${doc}px high in a ${size[0]}x${inner} window`);
  }
}

/** first-screen, for a view with a main control: at each narrow size. */
async function checkFirstScreen(c, view) {
  for (const size of c.cfg.narrow) {
    await open(c.page, c.cfg, view, size, size[0] < 600);
    const top = await c.list(topScan(view.main));
    const text = top === null ? `"${view.main}" is not on the page at ${size[0]}px` : `"${view.main}" starts at ${top}px of a ${size[1]}px window at ${size[0]}px wide`;
    c.expect(top !== null && top < size[1] * c.cfg.firstScreen, view, 'first-screen', text);
  }
}

/** touch: every control reaches the target size on a touch screen. */
async function checkTouch(c, view) {
  await open(c.page, c.cfg, view, c.cfg.touch, true);
  const small = await c.list(touchScan(c.cfg.controls, c.cfg.exempt, c.cfg.touchTarget));
  c.expect(small.length === 0, view, 'touch', `under ${c.cfg.touchTarget}px on touch: ${small.join(', ')}`);
}

/** Each check in the order it runs, and whether a view asks for it. */
const VIEW_CHECKS = [
  [checkDesktop, () => true],
  [checkFill, (view) => view.fill],
  [checkFirstScreen, (view) => view.main],
  [checkTouch, (view) => view.touch !== false],
  [lint, (view) => view.lint !== false],
];

async function run(page, cfg) {
  const problems = [];
  const judge = [];
  let checks = 0;
  const expect = (ok, view, rule, text) => { checks++; if (!ok) problems.push(`${view.name}  [${rule}]  ${text}`); };
  const list = async (expr) => JSON.parse(await page.js(expr));
  const c = { page, cfg, list, expect, judge };
  for (const view of cfg.views) {
    for (const [check, wanted] of VIEW_CHECKS) if (wanted(view)) await check(c, view);
  }
  return { problems, judge, checks };
}

/** Takes waived findings out of both lists. A waiver names a rule, a piece of the finding's text and
 *  a reason; one that matches nothing, has no reason, or is the sixth is a problem itself. */
const wellFormed = (w) => Boolean(w.rule && w.match && w.reason && w.reason.trim().length >= 10);

export function applyWaivers(cfg, result) {
  const used = [];
  const errors = [];
  if (cfg.waivers.length > MAX_WAIVERS) errors.push(`${cfg.waivers.length} waivers: more than ${MAX_WAIVERS} is a failure (fix the findings instead)`);
  for (const w of cfg.waivers) {
    if (!wellFormed(w)) { errors.push(`waiver ${JSON.stringify(w)} needs "rule", "match" and a "reason" of a sentence`); continue; }
    const hit = (f) => f.includes(`[${w.rule}]`) && f.includes(w.match);
    const n = result.problems.filter(hit).length + result.judge.filter(hit).length;
    if (!n) { errors.push(`waiver for [${w.rule}] "${w.match}" matches no finding: remove it`); continue; }
    result.problems = result.problems.filter((f) => !hit(f));
    result.judge = result.judge.filter((f) => !hit(f));
    used.push(`[${w.rule}] ${w.match}: ${w.reason} (${n})`);
  }
  // A view's rule with every finding waived leaves an empty problem line behind: drop those.
  result.problems = result.problems.filter((f) => !/\]\s+( \(touch, \d+px\))?$/.test(f)).concat(errors);
  return used;
}

// ---------- self-test: one page that breaks every rule, one that keeps them ----------
const selfPage = (ok) => 'data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><style>
  body { margin: 0; font: 13px/1.45 sans-serif; }
  .btn { box-sizing: border-box; height: 32px; padding: 0 12px; border: 1px solid #888; font-size: 13px; }
  .rail { height: ${ok ? 80 : 900}px; }
  .stage { position: relative; height: ${ok ? '120px' : '100vh'}; }
  .dot { position: absolute; left: 100px; top: ${ok ? 80 : 20}px; width: 10px; height: 10px; border-radius: 50%; background: #333; }
  .name { position: absolute; left: 80px; top: 16px; }
  .card { border: 1px solid #888; border-radius: 8px; padding: ${ok ? 12 : 2}px; width: 300px; min-height: 60px; ${ok ? '' : 'box-shadow: 0 2px 4px #0004;'} }
  .fine { font-size: ${ok ? 12 : 9}px; }
  .long { width: 90px; border: 1px solid #888; padding: 8px; ${ok ? 'overflow-wrap: anywhere;' : 'white-space: nowrap;'} }
  .wide { width: ${ok ? 'auto' : '1700px'}; }
  .off { margin-left: ${ok ? 0 : 3}px; }
  h2 { font-size: 16px; margin: ${ok ? '24px 0 8px' : '2px 0 24px'}; }
  .reveal { ${ok ? '' : 'opacity: 0; animation: show 0.05s forwards;'} }
  .note { box-sizing: border-box; width: 300px; font: inherit; padding: 8px; ${ok ? 'border: 1px solid #767676;' : 'border: 0; background: transparent;'} }
  @keyframes show { to { opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .reveal { animation: none; } }
  @media (pointer: coarse) { .btn, .note { ${ok ? 'min-height: 44px; font-size: 16px;' : ''} } }
</style>
<div class="rail">side bar</div>
<div class="main"><input class="box btn" placeholder="main control"><button class="btn btn--primary">Send</button>${ok ? '<button class="btn">Save</button>' : '<button class="btn btn--primary">Save</button>'}</div>
<div class="stage"><span class="dot"></span><b class="name">Topic</b></div>
<div class="wide"><p>Intro text of the section.</p><h2>A heading</h2><p class="off">Text under the heading${ok ? '' : ' \u{1F680}'}.</p><p>${ok ? 'It doesn’t open “here”' : 'It doesn\'t open "here"'}; <code>"code" keeps its quotes</code></p></div>
<div class="card"><span class="fine">Fine print in a card</span>${ok ? '' : '<div class="card">a card in a card</div>'}</div>
<div class="long">Averyveryverylongwordwithoutspaces</div>
<textarea class="note" aria-label="A note" autofocus></textarea>
<p class="reveal">${'This paragraph is revealed by an animation and must stay readable without it. '.repeat(6)}</p>`);

const SELF_FAILS = ['primary', 'label', 'page-scroll', 'first-screen', 'touch', ...LINT_FAILS, 'motion-hides'];
const SELF_JUDGED = ['card-in-card', 'border-and-shadow', 'near-tangent', 'heading-space', 'emoji', 'straight-quote'];
/** The rules the broken page should have hit and did not. */
const notCaught = (rules, found) => rules.filter((r) => !found.some((p) => p.startsWith('broken') && p.includes(`[${r}]`)));

async function selfTest(o) {
  const view = (ok) => ({ name: ok ? 'kept' : 'broken', url: selfPage(ok), ready: '.main', main: '.main', fill: true, labels: '.name', marks: '.dot' });
  const cfg = { ...DEFAULTS, wait: 250, views: [view(false), view(true)] };
  const { problems, judge } = await withBrowser(o, cfg, (page) => run(page, cfg));
  const missed = [...notCaught(SELF_FAILS, problems), ...notCaught(SELF_JUDGED, judge)];
  const wrong = [...problems, ...judge].filter((p) => p.startsWith('kept'));
  const good = !missed.length && !wrong.length;
  console.log(good ? `OK: the broken page failed all ${SELF_FAILS.length} rules (${SELF_FAILS.join(', ')}), was listed for all ${SELF_JUDGED.length} judged ones (${SELF_JUDGED.join(', ')}), and the kept page was clean.` : `FAIL: not caught on the broken page: ${missed.join(', ') || 'none'}; wrongly flagged on the kept page: ${wrong.join(' | ') || 'none'}.`);
  process.exit(good ? 0 : 1);
}

/** The config with its defaults; exits 2 (setup) when there is none or it lists no views. */
function loadConfig(o) {
  if (!o.config) { console.error('Give --config <design-check.json> (or --self-test).'); process.exit(2); }
  const cfg = { ...DEFAULTS, ...JSON.parse(readFileSync(o.config, 'utf8')) };
  if (!cfg.views.length) { console.error('The config lists no views: nothing would be checked.'); process.exit(2); }
  return cfg;
}

/** "home; edit form (after "Edit")": a rule is held only for the states visited (docs/19 §8). */
export function visitedLine(views) {
  const clicks = (v) => (v.steps || []).filter((s) => s.click || s.clickSelector).map((s) => `"${s.click || s.clickSelector}"`);
  return views.map((v) => v.name + (clicks(v).length ? ` (after ${clicks(v).join(', ')})` : '')).join('; ');
}

const indented = (lines) => lines.map((l) => '  ' + l).join('\n');

async function main() {
  const o = parseArgs(process.argv.slice(2));
  if (o.selfTest) return selfTest(o);
  const cfg = loadConfig(o);
  const result = await withBrowser(o, cfg, (page) => run(page, cfg));
  const waived = applyWaivers(cfg, result);
  if (waived.length) console.log('Waived, with the reason given:\n' + indented(waived));
  if (result.judge.length) console.log(`For a person to judge (${result.judge.length}; not failures${o.strict ? ', but --strict' : ''}):\n` + indented(result.judge));
  console.log(`Views visited: ${visitedLine(cfg.views)}. Anything else is not checked.`);
  if (result.problems.length || (o.strict && result.judge.length)) { console.log('Design rules broken:\n' + result.problems.join('\n')); process.exit(1); }
  console.log(`OK: ${result.checks} rendered design checks over ${cfg.views.length} view(s), none broken.`);
  process.exit(0); // the browser's debug socket would keep the process alive after a pass
}

// Runs only as a program: the tests import the pure parts (waivers, the report lines) without a browser.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => { console.error(`check-design-rules: ${e.message}`); process.exit(2); });
}
