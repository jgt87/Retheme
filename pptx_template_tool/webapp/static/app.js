let jobId = null, manifest = null;
const $ = (sel) => document.querySelector(sel);
// Smooth scrolling is motion: honour the OS reduced-motion setting.
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const scrollBehavior = () => (reduceMotion() ? "auto" : "smooth");
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------- shared pieces ----------
// Icons come from the one SVG set at the top of index.html.
const icon = (name) =>
  `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
// Status is never color alone: an icon, the word, then the message.
const errorHtml = (msg) => `${icon("alert")}<div><strong>Error.</strong> ${msg}</div>`;

// A busy button says what it is doing, keeps its width and ignores a second
// press. Returns the function that puts it back.
function setBusy(btn, label) {
  const html = btn.innerHTML;
  btn.style.minWidth = btn.offsetWidth + "px";
  btn.innerHTML = `<span class="spinner"></span>${label}`;
  btn.setAttribute("aria-busy", "true");
  btn.disabled = true;
  return () => {
    btn.innerHTML = html;
    btn.style.minWidth = "";
    btn.removeAttribute("aria-busy");
    btn.disabled = false;
  };
}

// ---------- tabs ----------
const TABS = ["extract", "apply", "preview"];
const tabBtn = (t) => $("#tabbtn-" + t);
const tabLocked = (t) => tabBtn(t).getAttribute("aria-disabled") === "true";
function switchTab(name) {
  $("#tab-help").hidden = true;
  $("#help-btn").classList.remove("active");
  $("#help-btn").setAttribute("aria-pressed", "false");
  TABS.forEach(t => {
    $("#tab-" + t).hidden = t !== name;
    const btn = tabBtn(t);
    btn.classList.toggle("active", t === name);
    btn.setAttribute("aria-selected", t === name ? "true" : "false");
    btn.tabIndex = t === name ? 0 : -1;   // one tab stop for the whole list
  });
}
TABS.forEach(t => tabBtn(t).addEventListener("click", () => {
  if (!tabLocked(t)) switchTab(t);
}));
// Arrow keys move along the tabs, Home and End jump to the ends. An open tab
// shows at once (its panel is already on the page); a locked one only takes
// focus, so its reason can be read.
$("nav.tabs").addEventListener("keydown", e => {
  const at = TABS.findIndex(t => tabBtn(t) === document.activeElement);
  if (at < 0) return;
  const to = { ArrowRight: (at + 1) % TABS.length,
               ArrowLeft: (at + TABS.length - 1) % TABS.length,
               Home: 0, End: TABS.length - 1 }[e.key];
  if (to === undefined) return;
  e.preventDefault();
  if (!tabLocked(TABS[to])) switchTab(TABS[to]);
  tabBtn(TABS[to]).focus();
});

// ---------- help page ----------
let helpReturn = "extract";
function showHelp() {
  helpReturn = TABS.find(t => tabBtn(t).classList.contains("active")) || helpReturn;
  TABS.forEach(t => {
    $("#tab-" + t).hidden = true;
    const btn = tabBtn(t);
    btn.classList.remove("active");
    btn.setAttribute("aria-selected", "false");
  });
  $("#tab-help").hidden = false;
  $("#help-btn").classList.add("active");
  $("#help-btn").setAttribute("aria-pressed", "true");
  window.scrollTo({ top: 0, behavior: scrollBehavior() });
}
$("#help-btn").addEventListener("click", () => {
  if ($("#tab-help").hidden) showHelp(); else switchTab(helpReturn);
});
$("#help-back").addEventListener("click", () => switchTab(helpReturn));

// Extract errors go back to the drop zone, so choosing another file is the
// recovery (no page reload, nothing else in the session is lost).
function showError(html) {
  $("#progress-card").hidden = true;
  $("#upload-card").hidden = false;
  $("#file-input").value = "";
  const box = $("#error-box");
  box.innerHTML = errorHtml(html + " Choose another file to try again.");
  box.hidden = false;
}

// FastAPI errors arrive as {"detail": "..."}; show the sentence, not the JSON.
async function errorDetail(res) {
  let detail = await res.text();
  try { detail = JSON.parse(detail).detail || detail; } catch (e) {}
  return escapeHtml(detail || `HTTP ${res.status}`);
}
function escapeHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
const TEMPLATE_TYPES = [".pptx", ".potx"];
const hasType = (file, types) => types.some(t => file.name.toLowerCase().endsWith(t));

// version pill is injected by the server; fall back when opened from disk
if ($("#version-pill").textContent.includes("{{")) {
  $("#version-pill").textContent = "dev";
}

// The page only works when served by the extraction server, not from disk:
// every action calls its /api/... endpoints.
if (location.protocol === "file:") {
  const note = document.createElement("div");
  note.innerHTML =
    `<p><strong>This page was opened directly from disk, so it has no
     server to talk to.</strong></p>
     <p>Start the extraction server and open it from there instead:</p>
     <p><code>python -m pptx_template_tool.cli serve</code>, then open
     <a href="http://127.0.0.1:8000/">http://127.0.0.1:8000/</a></p>`;
  $("#dropzone").hidden = true;
  $("#dropzone").before(note);
}

// ---------- drop zones ----------
// Enter and leave are counted, so the highlight does not flicker while the
// pointer crosses the zone's own children.
function wireDropzone(zone, onFile) {
  let depth = 0;
  const lit = (on) => zone.classList.toggle("hover", on);
  zone.addEventListener("dragenter", e => { e.preventDefault(); depth++; lit(true); });
  zone.addEventListener("dragover", e => e.preventDefault());
  zone.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); lit(depth > 0); });
  zone.addEventListener("drop", e => {
    e.preventDefault(); depth = 0; lit(false);
    if (e.dataTransfer.files.length) onFile(e.dataTransfer.files[0]);
  });
}
// A file dropped beside a zone must not replace the page with that file.
["dragover", "drop"].forEach(ev => window.addEventListener(ev, e => e.preventDefault()));

wireDropzone($("#dropzone"), upload);
$("#file-input").addEventListener("change", e => {
  if (e.target.files.length) upload(e.target.files[0]);
});

// ---------- content-deck dropzone (mirrors the extract dropzone) ----------
const DECK_TYPES = [".pptx", ".potx", ".ppsx"];
// The name shortens in the middle, so the extension stays readable.
function showPickedDeck(file) {
  const dot = file.name.lastIndexOf(".");
  const stem = dot > 0 ? file.name.slice(0, dot) : file.name;
  const ext = dot > 0 ? file.name.slice(dot) : "";
  const picked = $("#deck-picked");
  picked.innerHTML = `<span class="lead">Selected: </span><span class="stem">${
    escapeHtml(stem)}</span><span class="ext">${escapeHtml(ext)}</span>`;
  picked.title = file.name;
  picked.hidden = false;
}
wireDropzone($("#deck-dropzone"), file => {
  $("#apply-error").hidden = true;
  if (!hasType(file, DECK_TYPES)) {  // drag-and-drop skips the accept filter
    applyError(`<strong>${escapeHtml(file.name)}</strong> is not a PowerPoint deck.
      Use a .pptx, .potx or .ppsx file.`);
    return;
  }
  // put the dropped file into the input so the apply handler picks it up
  const dt = new DataTransfer();
  dt.items.add(file);
  $("#content-file").files = dt.files;
  showPickedDeck(file);
});
$("#content-file").addEventListener("change", e => {
  if (e.target.files.length) showPickedDeck(e.target.files[0]);
});

async function upload(file) {
  $("#error-box").hidden = true;
  if (!hasType(file, TEMPLATE_TYPES)) {  // drag-and-drop skips the accept filter
    showError(`<strong>${escapeHtml(file.name)}</strong> is not a PowerPoint template.
      Use a .pptx or .potx file.`);
    return;
  }
  showProgress("Starting…", 0);
  $("#upload-card").hidden = true;
  $("#progress-card").hidden = false;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/extract", { method: "POST", body: fd });
    if (!res.ok) {
      showError(`Upload rejected: ${await errorDetail(res)}.`);
      return;
    }
    jobId = (await res.json()).job_id;
    poll();
  } catch (err) {
    showError(`Could not reach the extraction server (<code>${err}</code>).
      Is it running? Start it with
      <code>python -m pptx_template_tool.cli serve</code> and open the
      address it prints.`);
  }
}

// The step in words plus how far along it is; never 100% before the server
// confirms the work is done.
function showProgress(step, fraction) {
  const pct = Math.min(99, Math.round((fraction || 0) * 100));
  $("#progress-step").textContent = step;
  $("#progress-pct").textContent = `${pct}%`;
  const bar = $("#progress-bar");
  bar.value = Math.min(0.99, fraction || 0);
  bar.setAttribute("aria-valuetext", `${step} ${pct}%`);
}

let pollFailures = 0;
async function poll() {
  let s;
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    s = await res.json();
    pollFailures = 0;
  } catch (err) {
    if (++pollFailures <= 5) return setTimeout(poll, 1500); // transient blip
    showError(`Lost contact with the server while extracting
      (<code>${err}</code>). If the server console shows an error, please
      report it; otherwise restart the server and try again.`);
    return;
  }
  showProgress(s.step || s.status, s.progress);
  if (s.status === "running") return setTimeout(poll, 700);
  if (s.status === "error") {
    showError(`Extraction failed: <code>${escapeHtml(s.error)}</code>.`);
    return;
  }
  manifest = await (await fetch(`/api/jobs/${jobId}/manifest`)).json();
  $("#progress-card").hidden = true;
  $("#review").hidden = false;
  renderReview();
  const sess = $("#bk-session");
  sess.disabled = false;
  sess.checked = true;
  $("#bk-session-note").textContent =
    `(${manifest.template_name || "this session"})`;
}

// ---------- review ----------
const ROLE_OPTIONS = ["primary","secondary","accent","background","text","hyperlink"];
const TYPE_OPTIONS = ["logo","background_image","decorative_shape","icon","content_placeholder_image"];
// Plain-language names; the technical value stays the option value.
const TYPE_LABELS = { logo: "Logo", background_image: "Background image",
  decorative_shape: "Decorative shape", icon: "Icon",
  content_placeholder_image: "Content placeholder image" };
const SLOT_LABELS = { dk1: "Dark 1", lt1: "Light 1", dk2: "Dark 2", lt2: "Light 2",
  accent1: "Accent 1", accent2: "Accent 2", accent3: "Accent 3", accent4: "Accent 4",
  accent5: "Accent 5", accent6: "Accent 6", hlink: "Hyperlink", folHlink: "Followed link" };
const cap = (w) => w.charAt(0).toUpperCase() + w.slice(1);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function slug(s){ return s.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"") || "layout"; }

let reviewBaseline = null;  // snapshot to detect what the user changed

function renderReview() {
  reviewBaseline = {
    colors: Object.fromEntries(manifest.colors.map(c => [c.theme_slot, c.role])),
    assets: Object.fromEntries(manifest.assets.map(a => [a.asset_id, {
      type: a.type,
      x: a.position?.x_in ?? "", y: a.position?.y_in ?? "",
      w: a.size?.width_in ?? "", h: a.size?.height_in ?? "",
    }])),
  };
  // colors
  const ctb = $("#colors-table tbody"); ctb.innerHTML = "";
  manifest.colors.forEach(c => {
    const usage = Object.entries(c.usage || {}).sort((a,b)=>b[1]-a[1])
      .map(([k,v])=>`${k}×${v}`).join(", ") || "unused";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><span class="swatch" style="background:#${c.hex}"></span>#${c.hex}</td>
      <td>${SLOT_LABELS[c.theme_slot] || c.theme_slot} <span class="muted">(${c.theme_slot})</span></td><td class="muted">${usage}</td>
      <td><select data-slot="${c.theme_slot}" aria-label="Role for ${c.theme_slot} #${c.hex}">
        ${ROLE_OPTIONS.map(r=>`<option value="${r}" ${r===c.role?"selected":""}>${cap(r)}</option>`).join("")}
      </select></td>`;
    ctb.appendChild(tr);
  });
  if (!manifest.colors.length) {
    ctb.innerHTML = `<tr><td class="empty" colspan="4">This template defines no
      theme colors, so there are no roles to correct.</td></tr>`;
  }

  // layouts
  const nav = $("#layout-nav"); nav.innerHTML = "";
  manifest.layouts.forEach((l, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = l.name;
    b.setAttribute("aria-pressed", "false");
    b.onclick = () => showLayout(i);
    nav.appendChild(b);
  });
  if (manifest.layouts.length) showLayout(0);

  // assets
  const atb = $("#assets-table tbody"); atb.innerHTML = "";
  manifest.assets.forEach(a => {
    try {
    const p = a.position || {}, s = a.size || {};
    const owners = a.owning_layout === "all" ? "all"
      : (a.owning_layouts || []).slice(0,2).join(", ") +
        ((a.owning_layouts||[]).length > 2 ? ` (+${a.owning_layouts.length-2})` : "");
    // background masks (useBgFill shapes) have no file of their own
    const thumb = a.file_path
      ? `<img class="asset-thumb" src="/api/jobs/${jobId}/files/${a.file_path}" alt=""
         onerror="this.style.display='none'">`
      : '<span class="muted bg-mask">bg&nbsp;mask</span>';
    const tr = document.createElement("tr");
    tr.dataset.assetId = a.asset_id;
    tr.innerHTML = `<td>${thumb}</td>
      <td><code>${a.asset_id}</code><br><span class="muted">${a.source_format}</span></td>
      <td><select class="a-type" aria-label="Asset type for ${a.asset_id}">${TYPE_OPTIONS.map(t=>`<option value="${t}" ${t===a.type?"selected":""}>${TYPE_LABELS[t]}</option>`).join("")}</select></td>
      <td class="muted">${owners}<br>${a.role_notes || ""}</td>
      <td class="num"><input class="pos" type="number" step="0.01" data-f="position.x_in" aria-label="${a.asset_id} x (inches)" value="${p.x_in ?? ""}"></td>
      <td class="num"><input class="pos" type="number" step="0.01" data-f="position.y_in" aria-label="${a.asset_id} y (inches)" value="${p.y_in ?? ""}"></td>
      <td class="num"><input class="pos" type="number" step="0.01" data-f="size.width_in" aria-label="${a.asset_id} width (inches)" value="${s.width_in ?? ""}"></td>
      <td class="num"><input class="pos" type="number" step="0.01" data-f="size.height_in" aria-label="${a.asset_id} height (inches)" value="${s.height_in ?? ""}"></td>
      <td class="flag-cell">${a.needs_review ? `<span class="flag">${icon("alert")}Verify</span>` : ""}</td>`;
    atb.appendChild(tr);
    } catch (err) {
      console.error("could not render asset row", a.asset_id, err);
    }
  });
  if (!manifest.assets.length) {
    atb.innerHTML = `<tr><td class="empty" colspan="9">This template has no logos,
      background images or decorative shapes to extract.</td></tr>`;
  }
  const flagged = manifest.assets.filter(a=>a.needs_review).length;
  const rc = $("#review-count");
  rc.innerHTML = flagged
    ? `${icon("alert")}${plural(flagged, "item needs", "items need")} review` : "";
  rc.hidden = !flagged;
  updateSaveButton();
}

// Jump to the first flagged asset row and focus its type selector.
$("#review-count").addEventListener("click", () => {
  const id = (manifest.assets.find(a => a.needs_review) || {}).asset_id;
  const row = id && document.querySelector(`#assets-table tr[data-asset-id="${CSS.escape(id)}"]`);
  if (!row) return;
  row.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
  row.querySelector(".a-type").focus({ preventScroll: true });
  row.classList.add("flash");
  setTimeout(() => row.classList.remove("flash"), 1600);
});

function showLayout(i) {
  const l = manifest.layouts[i];
  [...$("#layout-nav").children].forEach((b,j) => {
    b.classList.toggle("active", j===i);
    b.setAttribute("aria-pressed", j===i ? "true" : "false");
  });
  const img = document.createElement("img");
  img.src = `/api/jobs/${jobId}/files/previews/layout-${slug(l.name)}.png`;
  img.alt = `Preview of the ${l.name} layout`;
  $("#layout-preview").replaceChildren(img);
  const bg = l.background || {};
  const bgTxt = bg.type === "solid" ? `solid #${bg.hex}`
    : bg.type === "gradient" ? `gradient (${(bg.stops||[]).map(s=>"#"+s.hex).join(" to ")})`
    : bg.type === "image" ? `image (${bg.asset_id})` : bg.type;
  const purpose = l.purpose && l.purpose !== l.name ? `: ${l.purpose}` : "";
  let html = `<p><strong>${l.name}</strong>${purpose}<br>
    <span class="muted">Background: ${bgTxt} · static assets: ${(l.static_assets||[]).length}</span></p>
    <table><caption class="sr-only">Placeholders of the ${l.name} layout</caption>
    <thead><tr><th scope="col">Placeholder</th><th scope="col">Position (in)</th>
    <th scope="col">Size (in)</th><th scope="col">Font</th></tr></thead><tbody>`;
  if (!(l.placeholders || []).length) {
    html += `<tr><td class="empty" colspan="4">This layout has no placeholders.</td></tr>`;
  }
  (l.placeholders || []).forEach(ph => {
    const p = ph.position || {}, s = ph.size || {};
    const f = (ph.format_levels || {})["1"] || {};
    html += `<tr><td>${ph.type}</td>
      <td>${p.x_in ?? "?"}, ${p.y_in ?? "?"}</td>
      <td>${s.width_in ?? "?"} × ${s.height_in ?? "?"}</td>
      <td>${f.font || "(inherited)"} ${f.size_pt ? f.size_pt + "pt" : ""}
          ${f.color ? `<span class="swatch" style="background:#${f.color}"></span>` : ""}</td></tr>`;
  });
  $("#layout-detail").innerHTML = html + "</tbody></table>";
}

// ---------- save / download ----------
// Only what the user actually changed: untouched rows must keep their
// review flags and inferred confidence.
function collectCorrections() {
  const corrections = { colors: [], assets: [] };
  document.querySelectorAll("#colors-table select").forEach(sel => {
    if (sel.value !== reviewBaseline.colors[sel.dataset.slot]) {
      corrections.colors.push({ theme_slot: sel.dataset.slot, role: sel.value });
    }
  });
  document.querySelectorAll("#assets-table tbody tr").forEach(tr => {
    const base = reviewBaseline.assets[tr.dataset.assetId] || {};
    const corr = { asset_id: tr.dataset.assetId, position: {}, size: {} };
    let changed = false;
    const type = tr.querySelector(".a-type").value;
    if (type !== base.type) { corr.type = type; changed = true; }
    const baseKey = { "position.x_in": "x", "position.y_in": "y",
                      "size.width_in": "w", "size.height_in": "h" };
    tr.querySelectorAll("input.pos").forEach(inp => {
      if (inp.value === "") return;
      const val = parseFloat(inp.value);
      const orig = base[baseKey[inp.dataset.f]];
      if (orig === "" || Math.abs(val - orig) > 1e-9) {
        const [obj, key] = inp.dataset.f.split(".");
        corr[obj][key] = val;
        changed = true;
      }
    });
    if (changed) {
      corr.needs_review = false;  // the user engaged with this row
      corrections.assets.push(corr);
    }
  });
  return corrections;
}

// Save stays disabled until something differs from what was extracted.
function updateSaveButton() {
  const c = collectCorrections();
  const n = c.colors.length + c.assets.length;
  const btn = $("#save-btn");
  btn.disabled = n === 0;
  btn.textContent = n ? `Save ${plural(n, "correction", "corrections")}` : "Save corrections";
}
["change", "input"].forEach(ev => {
  $("#colors-table").addEventListener(ev, updateSaveButton);
  $("#assets-table").addEventListener(ev, updateSaveButton);
});

$("#save-btn").addEventListener("click", async () => {
  const corrections = collectCorrections();
  if (!corrections.colors.length && !corrections.assets.length) return;
  $("#save-status").textContent = "";
  const done = setBusy($("#save-btn"), "Saving…");
  let res;
  try {
    res = await fetch(`/api/jobs/${jobId}/manifest`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corrections) });
  } catch (err) {
    done();
    $("#save-status").textContent =
      "Save failed: could not reach the server. Your edits are kept; try again.";
    updateSaveButton();
    return;
  }
  done();
  $("#save-status").textContent = res.ok
    ? "Saved. template.json and template.md updated."
    : `Save failed: ${await errorDetail(res)}`;
  if (res.ok) {
    manifest = await (await fetch(`/api/jobs/${jobId}/manifest`)).json();
    renderReview();
  } else {
    updateSaveButton();  // keep the edits; let the user retry
  }
});

$("#download-btn").addEventListener("click", () => {
  window.location = `/api/jobs/${jobId}/download`;
});
$("#goto-apply-btn").addEventListener("click", () => switchTab("apply"));

// ---------- apply brandkit ----------
let applyId = null;

function applyError(msg) {
  const box = $("#apply-error");
  box.innerHTML = errorHtml(msg);
  box.hidden = false;
  box.scrollIntoView({ behavior: scrollBehavior(), block: "nearest" });
}

$("#apply-btn").addEventListener("click", async () => {
  $("#apply-error").hidden = true;
  const deck = $("#content-file").files[0];
  if (!deck) { applyError("Choose a content deck (.pptx) first."); return; }
  const mode = (document.querySelector('input[name="bk"]:checked') || {}).value;
  if (!mode) { applyError("Choose where the brandkit comes from."); return; }

  const fd = new FormData();
  fd.append("content_file", deck);
  if (mode === "session") {
    if (!jobId) { applyError("No brandkit extracted in this session yet."); return; }
    fd.append("job_id", jobId);
  } else if (mode === "zip") {
    const zip = $("#package-zip").files[0];
    if (!zip) { applyError("Choose a template-package zip."); return; }
    fd.append("package_zip", zip);
  } else {
    const path = $("#package-path").value.trim();
    if (!path) { applyError("Enter the template-package folder path."); return; }
    fd.append("package_path", path);
  }

  $("#apply-status").textContent = "Retheming…";
  const done = setBusy($("#apply-btn"), "Retheming…");
  try {
    const res = await fetch("/api/apply", { method: "POST", body: fd });
    if (!res.ok) {
      applyError(`Apply failed: ${await errorDetail(res)}`);
      return;
    }
    const out = await res.json();
    applyId = out.apply_id;
    if (out.decisions && out.decisions.length) {
      renderDecisions(out.decisions, out.slides || 0);
      return;
    }
    finishApply(out);
  } catch (err) {
    applyError(`Could not reach the server (<code>${err}</code>).`);
  } finally {
    $("#apply-status").textContent = "";
    done();
  }
});

let previewSeq = 0, previewTimer = null;

function currentChoices() {
  const choices = {};
  document.querySelectorAll("#choices-list .decision").forEach(div => {
    const sel = div.querySelector("select.d-choice");
    if (sel) { choices[div.dataset.id] = sel.value; return; }
    const checked = div.querySelector("input.d-choice:checked");
    if (checked) choices[div.dataset.id] = checked.value;
  });
  // per-slide protection (reserved keys the retheme engine understands)
  const pb = $("#protect-block");
  if (pb) {
    const slides = [...pb.querySelectorAll(".p-slide:checked")].map(c => c.value);
    if (slides.length) {
      choices["__protect__"] = slides.join(",");
      choices["__protect_mode__"] = pb.querySelector(".p-mode:checked").value;
      choices["__protect_apply__"] =
        [...pb.querySelectorAll(".p-adj:checked")].map(c => c.value).join(",");
    }
  }
  return choices;
}

// each change re-rethemes the deck server-side with the CURRENT selections
// (defaults included), so every decision's effect shows in the preview
function schedulePreviewRefresh() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshDraftPreview, 350);
}

async function refreshDraftPreview() {
  const seq = ++previewSeq;
  $("#preview-status").textContent = "Updating preview…";
  try {
    const res = await fetch(`/api/apply/${applyId}/preview-draft`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choices: currentChoices() }) });
    if (!res.ok) {
      let detail = await res.text();
      try { detail = JSON.parse(detail).detail || detail; } catch (err) {}
      throw new Error(detail || `HTTP ${res.status}`);
    }
    const html = await res.text();
    if (seq !== previewSeq) return;  // superseded by a newer selection
    $("#choices-frame").srcdoc = html;
    $("#preview-status").textContent = "";
  } catch (e) {
    if (seq !== previewSeq) return;
    $("#preview-status").textContent = "Live preview unavailable.";
    const msg = String(e && e.message || e)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;");
    $("#choices-frame").srcdoc =
      `<body style="font:13px system-ui;color:${cssVar("--stage-ink")};
        background:${cssVar("--stage-bg")};padding:16px">Live preview could not be rendered: ${msg}<br><br>
        Your choices below still apply when you confirm.</body>`;
  }
}

// Size the preview to the space the choices occupy: at least one slide tall,
// growing with the choices column, but never taller than the whole deck.
function fitPreviewHeight() {
  const frame = $("#choices-frame");
  let doc;
  try { doc = frame.contentDocument; } catch (e) { return; }
  if (!doc || !doc.body) return;
  const slides = doc.querySelectorAll(".slide");
  if (!slides.length) return;  // error/blank preview keeps the CSS min-height
  requestAnimationFrame(() => {
    // the preview scales its slides to the iframe width, so scrollHeight is
    // the true on-screen height of the whole (uniform) deck
    const total = doc.body.scrollHeight;
    if (!total) return;
    const oneSlide = total / slides.length;
    const listH = $("#choices-list").getBoundingClientRect().height;
    const h = Math.round(Math.max(oneSlide, Math.min(listH, total)));
    frame.style.height = h + "px";
  });
}
$("#choices-frame").addEventListener("load", fitPreviewHeight);
window.addEventListener("resize", () => {
  if (!$("#choices-card").hidden) fitPreviewHeight();
});

// Preview page: show 1.25 slides tall, so the next slide peeks in and it
// reads as a scrollable deck rather than a single fixed frame.
const PREVIEW_SLIDES_TALL = 1.25;
function fitResultFrame() {
  const frame = $("#preview-frame");
  let doc;
  try { doc = frame.contentDocument; } catch (e) { return; }
  if (!doc || !doc.body) return;
  const slides = doc.querySelectorAll(".slide");
  if (!slides.length) return;
  requestAnimationFrame(() => {
    const total = doc.body.scrollHeight;   // scaled height of the whole deck
    if (!total) return;
    const oneSlide = total / slides.length;
    frame.style.height = Math.round(oneSlide * PREVIEW_SLIDES_TALL) + "px";
  });
}
$("#preview-frame").addEventListener("load", fitResultFrame);
window.addEventListener("resize", () => {
  if (!$("#tab-preview").hidden) fitResultFrame();
});

// If an option names a color (e.g. "Recolor to brand primary #RRGGBB"), show
// a swatch of it so the user sees the color they're choosing to apply.
function optLabel(label) {
  const m = String(label).match(/#([0-9A-Fa-f]{6})(?![0-9A-Fa-f])/);
  return label + (m
    ? ` <span class="opt-swatch" style="background:#${m[1]}" title="#${m[1]}"></span>`
    : "");
}

// Keep only chars safe inside a CSS font-family value (mirrors the server).
function cssFontName(name) { return String(name).replace(/[^\w \-]/g, "").trim(); }

// Render any mentioned font name in that font, so the user sees the typeface
// (only when it's installed on their machine; falls back gracefully otherwise).
function previewFontNames(label, fonts) {
  let out = label;
  [...new Set(fonts.filter(Boolean))].forEach(f => {
    const safe = cssFontName(f);
    if (!safe) return;
    const esc = f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    out = out.replace(new RegExp(esc, "g"),
      `<span style="font-family:'${safe}',sans-serif">${f}</span>`);
  });
  return out;
}

function renderProtect(n) {
  if (!n) return;
  const box = document.createElement("fieldset");
  box.className = "protect-card";
  box.id = "protect-block";
  const slides = Array.from({ length: n }, (_, k) => k + 1).map(s =>
    `<label class="opt"><input type="checkbox" class="p-slide" value="${s}"
       aria-label="Protect slide ${s}"> ${s}</label>`
  ).join("");
  const adj = [["color", "Colors"], ["font", "Fonts"], ["title", "Title sizes"],
               ["heading", "Headings"], ["resize", "Resize"]].map(([v, l]) =>
    `<label class="opt"><input type="checkbox" class="p-adj" value="${v}" checked> ${l}</label>`
  ).join("");
  box.innerHTML = `<legend>Protect slides</legend>
    <p class="muted">Tick any slides that should ignore
      the choices above. <b>Full retain</b> keeps them looking exactly as in your
      deck; <b>Partial</b> still applies only the adjustments you leave ticked.</p>
    <div class="slide-grid" role="group" aria-label="Slides to protect">${slides}</div>
    <div class="pmode" role="radiogroup" aria-label="How protected slides are handled">
      <label class="opt"><input type="radio" name="pmode" class="p-mode"
        value="full" checked> Full retain (original look)</label>
      <label class="opt"><input type="radio" name="pmode" class="p-mode"
        value="partial"> Partial: still apply</label>
    </div>
    <div class="padj" role="group" aria-label="Adjustments still applied" hidden>${adj}</div>`;
  $("#choices-list").appendChild(box);
  const padj = box.querySelector(".padj");
  box.querySelectorAll(".p-mode").forEach(el => el.addEventListener("change", () => {
    padj.hidden = box.querySelector(".p-mode:checked").value !== "partial";
    schedulePreviewRefresh();
  }));
  box.querySelectorAll(".p-slide, .p-adj").forEach(el =>
    el.addEventListener("change", schedulePreviewRefresh));
}

// One primary button per view: while the choices are open, confirming them is
// the forward step, so "Retheme deck" steps back to a secondary button.
function showChoices(on) {
  $("#choices-card").hidden = !on;
  $("#apply-btn").classList.toggle("primary", !on);
}

function renderDecisions(decisions, slideCount) {
  const list = $("#choices-list");
  list.innerHTML = "";
  decisions.forEach((d, i) => {
    // a fieldset, so the question is read out with each of its options
    const div = document.createElement("fieldset");
    div.className = "decision";
    div.dataset.id = d.id;
    const swatches = (d.swatches || []).map(h =>
      `<span style="background:#${h}" title="#${h}"></span>`).join("");
    let controls;
    if (d.kind === "layout") {
      controls = `<select class="d-choice" aria-labelledby="dq${i}">` + d.options.map(o =>
        `<option value="${o.value}" ${o.value === d.default ? "selected" : ""}>
         ${o.label}</option>`).join("") + `</select>`;
    } else {
      controls = d.options.map(o => {
        let lab = optLabel(o.label);
        if (d.kind === "font") lab = previewFontNames(lab, [d.source, d.target]);
        return `<label class="opt"><input type="radio" name="d${i}" class="d-choice"
         value="${o.value}" ${o.value === d.default ? "checked" : ""}>
         ${lab}</label>`;
      }).join("");
    }
    const heading = d.kind === "font"
      ? previewFontNames(d.label, [d.source, d.target]) : d.label;
    div.innerHTML = `<legend id="dq${i}">${heading}</legend>
      ${swatches ? `<div class="swatches">${swatches}</div>` : ""}
      <p class="muted">${d.detail || ""}</p>
      ${controls}`;
    list.appendChild(div);
  });
  list.querySelectorAll(".d-choice").forEach(el =>
    el.addEventListener("change", schedulePreviewRefresh));
  renderProtect(slideCount);  // per-slide "leave as-is" controls
  showChoices(true);
  $("#choices-card").scrollIntoView({ behavior: scrollBehavior() });
  refreshDraftPreview();  // first render uses the pre-selected defaults
}

$("#confirm-btn").addEventListener("click", async () => {
  const choices = currentChoices();
  $("#apply-error").hidden = true;
  $("#confirm-status").textContent = "Applying…";
  const done = setBusy($("#confirm-btn"), "Applying…");
  try {
    const res = await fetch(`/api/apply/${applyId}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choices }) });
    if (!res.ok) {
      applyError(`Apply failed: ${await errorDetail(res)}`);
      return;
    }
    showChoices(false);
    finishApply(await res.json());
  } catch (err) {
    applyError(`Could not reach the server (<code>${err}</code>).`);
  } finally {
    $("#confirm-status").textContent = "";
    done();
  }
});

function finishApply(out) {
    // unlock the Preview tab: there is now a deck to show
    ["aria-disabled", "aria-describedby", "title"].forEach(a =>
      $("#tabbtn-preview").removeAttribute(a));
    const warnings = out.warnings || [];
    const isCritical = w => w.startsWith("BRANDKIT OUTDATED")
                         || w.startsWith("APPROXIMATE OUTPUT");
    const critical = warnings.filter(isCritical);
    const rest = warnings.filter(w => !isCritical(w));
    // Always end with a receipt, so a clean run says so instead of saying nothing.
    $("#result-info").textContent = `${plural(out.slides, "slide", "slides")} rethemed. ` +
      (critical.length ? "Read the warning in Logs before using this deck."
       : rest.length ? `${plural(rest.length, "note", "notes")} in Logs.`
       : "No warnings: all content was retained.");
    $("#apply-warnings").innerHTML =
      critical.map(w => `<div class="error-box">${icon("alert")}<div>${w}</div></div>`).join("") +
      (rest.length ? `<ul>${rest.map(w => `<li>${w}</li>`).join("")}</ul>` : "");
    const details = $("#notes-details");
    if (warnings.length) {
      $("#notes-count").textContent = `(${warnings.length})`;
      details.hidden = false;
      details.open = critical.length > 0;  // auto-expand critical warnings
    } else {
      details.hidden = true;
    }
    $("#preview-frame").src = `/api/apply/${applyId}/preview`;
    switchTab("preview");
}

// picking a zip / typing a path selects the matching source automatically
$("#package-zip").addEventListener("change", () => {
  document.querySelector('input[name="bk"][value="zip"]').checked = true;
});
$("#package-path").addEventListener("input", () => {
  document.querySelector('input[name="bk"][value="path"]').checked = true;
});

$("#pptx-btn").addEventListener("click", () => {
  if (applyId) window.location = `/api/apply/${applyId}/pptx`;
});
$("#html-btn").addEventListener("click", () => {
  if (applyId) window.location = `/api/apply/${applyId}/html`;
});
// Next deck, same brandkit: clear only the deck, keep the brandkit choice.
$("#again-btn").addEventListener("click", () => {
  $("#content-file").value = "";
  $("#deck-picked").hidden = true;
  $("#apply-error").hidden = true;
  showChoices(false);
  switchTab("apply");
  $("#content-file").focus();
});
