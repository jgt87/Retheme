// Rendered check: every row of controls has one height (rules/ui.md "One height per bar and per
// control kind, checked by a test over rendered heights at desktop and phone width"; docs/17 §2).
// Opens each page in headless Edge or Chrome over the DevTools protocol, at each width, and groups
// the visible controls into rows: same parent element and same centre line (6px bands). A row whose
// controls render at different heights fails. Origin: a PowerShell tool's web UI, 2026-11-13: an
// <a class="btn"> rendered 34px next to 32px <button>s (no box-sizing), and an edit form put 28px
// small buttons beside 32px fields; screenshots judged by eye had missed both.
//
//   node scripts/check-control-rows.mjs <url> [<url> ...] [--widths 1440,390] [--port 9558]
//        [--wait 1500] [--selector "<css>"] [--ignore "<css>"] [--browser <path>]
//   node scripts/check-control-rows.mjs --self-test     proves the scan catches a mixed row
//
// Run it against the dev server or the built app on a test port, never the person's live instance.
// Pages that need clicks to reach a state (a dialog, an edit form): copy this file and add the steps
// in `visit()` (open, click, then scan), as the origin project did for its graph, list and dialogs.
// Exit 0 = every row has one height; 1 = a row mixes heights (named with its heights); 2 = setup.
// No dependencies (Node 22+: global WebSocket and fetch). Writes nothing but a temp browser profile.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULT_SELECTOR = 'button, select, input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=hidden]), a[class*="btn"], a[class*="button"], [role="button"], .field';
const BROWSERS = [
  process.env.CHROME_PATH,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/microsoft-edge',
].filter(Boolean);

export function parseArgs(argv) {
  const o = { urls: [], widths: [1440, 390], port: 9558, wait: 1500, selector: DEFAULT_SELECTOR, ignore: '', browser: '', selfTest: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === '--widths') o.widths = next().split(',').map(Number).filter(Boolean);
    else if (a === '--port') o.port = Number(next());
    else if (a === '--wait') o.wait = Number(next());
    else if (a === '--selector') o.selector = next();
    else if (a === '--ignore') o.ignore = next();
    else if (a === '--browser') o.browser = next();
    else if (a === '--self-test') o.selfTest = true;
    else o.urls.push(a);
  }
  return o;
}

// Runs in the page: rows of visible controls with more than one height.
const scanSource = (selector, ignore) => `(() => {
  const ignore = ${JSON.stringify(ignore)};
  const els = [...document.querySelectorAll(${JSON.stringify(selector)})].filter((e) => {
    if (ignore && e.matches(ignore)) return false;
    if (e.closest('svg')) return false;
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'contents';
  });
  const rows = new Map();
  for (const e of els) {
    const r = e.getBoundingClientRect();
    const p = e.parentElement;
    if (!p) continue;
    if (!p.__rowId) p.__rowId = (p.className && typeof p.className === 'string' ? p.className.trim().split(/\\s+/)[0] : p.tagName.toLowerCase()) + '#' + (rows.size + 1);
    const key = p.__rowId + '|' + Math.round((r.top + r.height / 2) / 6);
    if (!rows.has(key)) rows.set(key, []);
    const name = (e.getAttribute('aria-label') || e.textContent.trim() || e.getAttribute('placeholder') || e.tagName).replace(/\\s+/g, ' ').slice(0, 20);
    rows.get(key).push({ name, h: Math.round(r.height * 10) / 10 });
  }
  const bad = [];
  for (const [key, list] of rows) {
    if (list.length < 2 || new Set(list.map((x) => x.h)).size < 2) continue;
    bad.push(key.split('|')[0].replace(/#\\d+$/, '') + ': ' + list.map((x) => x.name + '=' + x.h + 'px').join(', '));
  }
  return JSON.stringify(bad);
})()`;

const SELF_TEST_PAGE = 'data:text/html,' + encodeURIComponent(`<!doctype html><style>
  .btn { display: inline-flex; height: 32px; padding: 0 12px; border: 1px solid #888; align-items: center; font: 13px sans-serif; }
  .ok .btn { box-sizing: border-box; }
</style>
<div class="bad"><button class="btn">Button</button><a class="btn" href="#">Link button</a></div>
<div class="ok"><button class="btn">Button</button><a class="btn" href="#">Link button</a></div>`);

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

async function withBrowser(o, fn) {
  const exe = o.browser || BROWSERS.find((p) => existsSync(p));
  if (!exe) { console.error('No Edge or Chrome found: pass --browser <path> or set CHROME_PATH.'); process.exit(2); }
  if (!existsSync(exe)) { console.error(`No browser at ${exe}: pass --browser <path> or set CHROME_PATH.`); process.exit(2); }
  const profile = mkdtempSync(join(tmpdir(), 'control-rows-'));
  const proc = spawn(exe, ['--headless=new', `--remote-debugging-port=${o.port}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  let ws = null;
  try {
    let info;
    for (let i = 0; i < 60 && !info; i++) { try { info = await (await fetch(`http://127.0.0.1:${o.port}/json/version`)).json(); } catch { await wait(250); } }
    if (!info) throw new Error(`the browser did not open its debug port ${o.port}`);
    ws = new WebSocket(info.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
    let id = 0;
    const pending = new Map();
    ws.addEventListener('message', (e) => {
      const m = JSON.parse(e.data);
      if (!m.id || !pending.has(m.id)) return;
      const p = pending.get(m.id); pending.delete(m.id);
      if (m.error) p.reject(new Error(m.error.message)); else p.resolve(m.result);
    });
    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => { const i = ++id; pending.set(i, { resolve, reject }); ws.send(JSON.stringify({ id: i, method, params, sessionId })); });
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
    const page = { send: (m, p) => send(m, p, sessionId), wait };
    return await fn(page);
  } finally {
    await closeBrowser(ws, wait);
    proc.kill();
    await wait(300);
    await removeProfile(profile, wait);
  }
}

async function visit(page, url, width, o) {
  await page.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 600 });
  await page.send('Page.enable');
  await page.send('Page.navigate', { url });
  await page.wait(o.wait);
  const r = await page.send('Runtime.evaluate', { expression: scanSource(o.selector, o.ignore), returnByValue: true });
  if (r.exceptionDetails) throw new Error(`the scan failed on ${url}: ${r.exceptionDetails.text}`);
  return JSON.parse(r.result.value);
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  if (o.selfTest) {
    const bad = await withBrowser(o, (page) => visit(page, SELF_TEST_PAGE, 1440, { ...o, wait: 300 }));
    const caught = bad.length === 1 && bad[0].startsWith('bad:');
    console.log(caught ? `OK: the scan caught the mixed row and passed the fixed one (${bad[0]}).` : `FAIL: expected one bad row "bad", got ${JSON.stringify(bad)}.`);
    process.exit(caught ? 0 : 1);
  }
  if (!o.urls.length) { console.error('Give at least one page URL (or --self-test).'); process.exit(2); }
  const failures = await withBrowser(o, async (page) => {
    const out = [];
    for (const url of o.urls) for (const w of o.widths) for (const row of await visit(page, url, w, o)) out.push(`${url} @${w}px  ${row}`);
    return out;
  });
  if (failures.length) { console.log('Rows with more than one control height:\n' + failures.join('\n')); process.exit(1); }
  console.log(`OK: every row of controls has one height (${o.urls.length} page(s); ${o.widths.join(' and ')} px).`);
  process.exit(0); // the browser's debug socket would keep the process alive after a pass
}

// Runs only as a program: the test imports parseArgs.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => { console.error(`check-control-rows: ${e.message}`); process.exit(2); });
}
