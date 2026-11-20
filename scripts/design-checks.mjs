// Runs both rendered checks on a built app with invented data: a small server on the test port in the
// config's "base" serves the build folder and answers /api/* from the config's "api" block, then
// check-design-rules.mjs (every view in the config) and check-control-rows.mjs (the first screen at
// the given widths) run against it, and the server stops. check-control-rows has no API stubs of its
// own; through this server it sees the same data as the design check. Never the person's running app.
//
//   node scripts/design-checks.mjs --root ../dist [--config design-check.json] [--widths 1440,720,390]
//        [--design-port 9571] [--rows-port 9572]
//
// Exit: the larger of the two checks' codes (0 pass, 1 a rule broken, 2 setup). Pick debug ports
// apart from the checks' defaults (9558, 9559) when another project may run its checks at the same
// time. From a PowerShell bridge with a React UI (`npm run check:design`), 16 Nov 2026.
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = import.meta.dirname;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.json': 'application/json', '.ico': 'image/x-icon' };

function parseArgs(argv) {
  const o = { config: 'design-check.json', root: '', widths: '1440,720,390', designPort: 9571, rowsPort: 9572 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--config') o.config = argv[++i];
    else if (a === '--root') o.root = argv[++i];
    else if (a === '--widths') o.widths = argv[++i];
    else if (a === '--design-port') o.designPort = Number(argv[++i]);
    else if (a === '--rows-port') o.rowsPort = Number(argv[++i]);
    else { console.error(`Unknown argument: ${a}`); process.exit(2); }
  }
  if (!o.root) { console.error('Give --root <the built app folder>.'); process.exit(2); }
  return o;
}

/** The test server's requests: /api/* from the config's "api", files from the build folder `root`
 *  (normalized and absolute), anything outside it refused. */
export const staticHandler = (root, cfg) => async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (path.startsWith('/api/')) {
    const body = cfg.api?.[path];
    res.writeHead(body === undefined ? 404 : 200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(body === undefined ? { error: 'not in the design config "api"' } : body));
    return;
  }
  const file = normalize(join(root, path === '/' ? 'index.html' : path));
  if (!file.startsWith(root)) { res.writeHead(403); res.end(); return; }
  const send = async (f) => { const b = await readFile(f); res.writeHead(200, { 'Content-Type': types[extname(f)] || 'application/octet-stream' }); res.end(b); };
  // A missing file falls back to index.html (the app's own routes); without one it is a 404, not a crash.
  try { await send(file); } catch { try { await send(join(root, 'index.html')); } catch { res.writeHead(404); res.end(); } }
};

const run = (args) => new Promise((done) => {
  const p = spawn(process.execPath, args, { stdio: 'inherit' });
  p.on('exit', (code) => done(code ?? 2));
  p.on('error', () => done(2));
});

function main() {
  const o = parseArgs(process.argv.slice(2));
  const configPath = resolve(o.config);
  const cfg = JSON.parse(readFileSync(configPath, 'utf8'));
  const base = new URL(cfg.base);
  const server = createServer(staticHandler(normalize(resolve(o.root)), cfg));
  server.on('error', (e) => { console.error(`design-checks: the test port ${base.port} is not free (${e.message})`); process.exit(2); });
  server.listen(Number(base.port), base.hostname, async () => {
    const design = await run([join(here, 'check-design-rules.mjs'), '--config', configPath, '--port', String(o.designPort)]);
    // "rowsIgnore" in the config: controls the row check leaves out, such as the parts of a composite
    // field (an input with its own small button) that are one control to the eye.
    const ignore = cfg.rowsIgnore ? ['--ignore', cfg.rowsIgnore] : [];
    const rows = await run([join(here, 'check-control-rows.mjs'), cfg.base + '/', '--widths', o.widths, '--port', String(o.rowsPort), ...ignore]);
    server.close();
    process.exit(Math.max(design, rows));
  });
}

// Runs only as a program: the test imports staticHandler.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
