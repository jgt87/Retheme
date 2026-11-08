let jobId = null, manifest = null;
const $ = (sel) => document.querySelector(sel);
// Smooth scrolling is motion: honour the OS reduced-motion setting.
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const scrollBehavior = () => (reduceMotion() ? "auto" : "smooth");
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ---------- tabs ----------
const TABS = ["extract", "apply", "preview"];
function switchTab(name) {
  $("#tab-help").classList.add("hidden");
  $("#help-btn").classList.remove("active");
  TABS.forEach(t => {
    $("#tab-" + t).classList.toggle("hidden", t !== name);
    const btn = $("#tabbtn-" + t);
    btn.classList.toggle("active", t === name);
    btn.setAttribute("aria-selected", t === name ? "true" : "false");
  });
}
TABS.forEach(t => $("#tabbtn-" + t).addEventListener("click", () => switchTab(t)));

// ---------- help page ----------
let helpReturn = "extract";
function showHelp() {
  helpReturn = TABS.find(t => $("#tabbtn-" + t).classList.contains("active")) || helpReturn;
  TABS.forEach(t => {
    $("#tab-" + t).classList.add("hidden");
    const btn = $("#tabbtn-" + t);
    btn.classList.remove("active");
    btn.setAttribute("aria-selected", "false");
  });
  $("#tab-help").classList.remove("hidden");
  $("#help-btn").classList.add("active");
  window.scrollTo({ top: 0, behavior: scrollBehavior() });
}
$("#help-btn").addEventListener("click", showHelp);
$("#help-back").addEventListener("click", () => switchTab(helpReturn));

// Extract errors go back to the drop zone, so choosing another file is the
// recovery (no page reload, nothing else in the session is lost).
function showError(html) {
  $("#progress-card").classList.add("hidden");
  $("#upload-card").classList.remove("hidden");
  $("#file-input").value = "";
  const box = $("#error-box");
  box.innerHTML = html + " Choose another file to try again.";
  box.classList.remove("hidden");
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
  $("#dropzone").innerHTML =
    `<p><strong>This page was opened directly from disk, so it has no
     server to talk to.</strong></p>
     <p>Start the extraction server and open it from there instead:</p>
     <p><code>python -m pptx_template_tool.cli serve</code> &nbsp;→&nbsp;
     <a href="http://127.0.0.1:8000/">http://127.0.0.1:8000/</a></p>`;
}

// ---------- upload ----------
const dz = $("#dropzone");
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("hover"); });
dz.addEventListener("dragleave", () => dz.classList.remove("hover"));
dz.addEventListener("drop", e => {
  e.preventDefault(); dz.classList.remove("hover");
  if (e.dataTransfer.files.length) upload(e.dataTransfer.files[0]);
});
$("#file-input").addEventListener("change", e => {
  if (e.target.files.length) upload(e.target.files[0]);
});

// ---------- content-deck dropzone (mirrors the extract dropzone) ----------
const deckDz = $("#deck-dropzone");
function showPickedDeck(file) {
  const picked = $("#deck-picked");
  picked.textContent = "Selected: " + file.name;
  picked.classList.remove("hidden");
}
deckDz.addEventListener("dragover", e => {
  e.preventDefault(); deckDz.classList.add("hover"); });
deckDz.addEventListener("dragleave", () => deckDz.classList.remove("hover"));
deckDz.addEventListener("drop", e => {
  e.preventDefault(); deckDz.classList.remove("hover");
  if (e.dataTransfer.files.length) {
    // put the dropped file into the input so the apply handler picks it up
    const dt = new DataTransfer();
    dt.items.add(e.dataTransfer.files[0]);
    $("#content-file").files = dt.files;
    showPickedDeck(e.dataTransfer.files[0]);
  }
});
$("#content-file").addEventListener("change", e => {
  if (e.target.files.length) showPickedDeck(e.target.files[0]);
});

async function upload(file) {
  $("#error-box").classList.add("hidden");
  if (!hasType(file, TEMPLATE_TYPES)) {  // drag-and-drop skips the accept filter
    showError(`<strong>${escapeHtml(file.name)}</strong> is not a PowerPoint template.
      Use a .pptx or .potx file.`);
    return;
  }
  $("#progress-step").textContent = "Starting…";
  $("#progress-bar").value = 0;
  $("#upload-card").classList.add("hidden");
  $("#progress-card").classList.remove("hidden");
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
  $("#progress-step").textContent = s.step || s.status;
  $("#progress-bar").value = s.progress || 0;
  if (s.status === "running") return setTimeout(poll, 700);
  if (s.status === "error") {
    showError(`Extraction failed: <code>${escapeHtml(s.error)}</code>.`);
    return;
  }
  manifest = await (await fetch(`/api/jobs/${jobId}/manifest`)).json();
  $("#progress-card").classList.add("hidden");
  $("#review").classList.remove("hidden");
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

  // layouts
  const nav = $("#layout-nav"); nav.innerHTML = "";
  manifest.layouts.forEach((l, i) => {
    const b = document.createElement("button");
    b.textContent = l.name; b.className = "secondary";
    b.onclick = () => showLayout(i);
    nav.appendChild(b);
  });
  showLayout(0);

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
      <td><input class="pos" type="number" step="0.01" data-f="position.x_in" aria-label="${a.asset_id} x (inches)" value="${p.x_in ?? ""}"></td>
      <td><input class="pos" type="number" step="0.01" data-f="position.y_in" aria-label="${a.asset_id} y (inches)" value="${p.y_in ?? ""}"></td>
      <td><input class="pos" type="number" step="0.01" data-f="size.width_in" aria-label="${a.asset_id} width (inches)" value="${s.width_in ?? ""}"></td>
      <td><input class="pos" type="number" step="0.01" data-f="size.height_in" aria-label="${a.asset_id} height (inches)" value="${s.height_in ?? ""}"></td>
      <td class="flag-cell">${a.needs_review ? '<span class="flag">⚠ verify</span>' : ""}</td>`;
    atb.appendChild(tr);
    } catch (err) {
      console.error("could not render asset row", a.asset_id, err);
    }
  });
  const flagged = manifest.assets.filter(a=>a.needs_review).length;
  const rc = $("#review-count");
  rc.textContent = flagged ? `⚠ ${plural(flagged, "item needs", "items need")} review` : "";
  rc.classList.toggle("hidden", !flagged);
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
  [...$("#layout-nav").children].forEach((b,j)=>b.classList.toggle("active", j===i));
  const img = document.createElement("img");
  img.src = `/api/jobs/${jobId}/files/previews/layout-${slug(l.name)}.png`;
  img.alt = `Preview of the ${l.name} layout`;
  $("#layout-preview").replaceChildren(img);
  const bg = l.background || {};
  const bgTxt = bg.type === "solid" ? `solid #${bg.hex}`
    : bg.type === "gradient" ? `gradient (${(bg.stops||[]).map(s=>"#"+s.hex).join(" → ")})`
    : bg.type === "image" ? `image (${bg.asset_id})` : bg.type;
  const purpose = l.purpose && l.purpose !== l.name ? `: ${l.purpose}` : "";
  let html = `<p><strong>${l.name}</strong>${purpose}<br>
    <span class="muted">background: ${bgTxt} · static assets: ${(l.static_assets||[]).length}</span></p>
    <table><thead><tr><th>placeholder</th><th>pos (in)</th><th>size (in)</th><th>font</th></tr></thead><tbody>`;
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
  $("#save-btn").disabled = true;
  $("#save-status").textContent = "Saving…";
  const res = await fetch(`/api/jobs/${jobId}/manifest`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corrections) });
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
  box.innerHTML = msg;
  box.classList.remove("hidden");
}

$("#apply-btn").addEventListener("click", async () => {
  $("#apply-error").classList.add("hidden");
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

  $("#apply-status").textContent = "Applying…";
  $("#apply-btn").disabled = true;
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
    $("#apply-btn").disabled = false;
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
        background:${cssVar("--stage-bg")};padding:18px">Live preview could not be rendered: ${msg}<br><br>
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
  if (!$("#choices-card").classList.contains("hidden")) fitPreviewHeight();
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
  if (!$("#tab-preview").classList.contains("hidden")) fitResultFrame();
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
  const box = document.createElement("div");
  box.className = "protect-card";
  box.id = "protect-block";
  const slides = Array.from({ length: n }, (_, k) => k + 1).map(s =>
    `<label class="opt"><input type="checkbox" class="p-slide" value="${s}"> ${s}</label>`
  ).join("");
  const adj = [["color", "Colors"], ["font", "Fonts"], ["title", "Title sizes"],
               ["heading", "Headings"], ["resize", "Resize"]].map(([v, l]) =>
    `<label class="opt"><input type="checkbox" class="p-adj" value="${v}" checked> ${l}</label>`
  ).join("");
  box.innerHTML = `<strong>Protect slides</strong>
    <p class="muted">Tick any slides that should ignore
      the choices above. <b>Full retain</b> keeps them looking exactly as in your
      deck; <b>Partial</b> still applies only the adjustments you leave ticked.</p>
    <div class="slide-grid">${slides}</div>
    <div class="pmode">
      <label class="opt"><input type="radio" name="pmode" class="p-mode"
        value="full" checked> Full retain (original look)</label>
      <label class="opt"><input type="radio" name="pmode" class="p-mode"
        value="partial"> Partial: still apply</label>
    </div>
    <div class="padj hidden">${adj}</div>`;
  $("#choices-list").appendChild(box);
  const padj = box.querySelector(".padj");
  box.querySelectorAll(".p-mode").forEach(el => el.addEventListener("change", () => {
    padj.classList.toggle("hidden",
      box.querySelector(".p-mode:checked").value !== "partial");
    schedulePreviewRefresh();
  }));
  box.querySelectorAll(".p-slide, .p-adj").forEach(el =>
    el.addEventListener("change", schedulePreviewRefresh));
}

function renderDecisions(decisions, slideCount) {
  const list = $("#choices-list");
  list.innerHTML = "";
  decisions.forEach((d, i) => {
    const div = document.createElement("div");
    div.className = "decision";
    div.dataset.id = d.id;
    const swatches = (d.swatches || []).map(h =>
      `<span style="background:#${h}" title="#${h}"></span>`).join("");
    let controls;
    if (d.kind === "layout") {
      controls = `<select class="d-choice">` + d.options.map(o =>
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
    div.innerHTML = `<strong>${heading}</strong>
      ${swatches ? `<div class="swatches">${swatches}</div>` : ""}
      <p class="muted">${d.detail || ""}</p>
      ${controls}`;
    list.appendChild(div);
  });
  list.querySelectorAll(".d-choice").forEach(el =>
    el.addEventListener("change", schedulePreviewRefresh));
  renderProtect(slideCount);  // per-slide "leave as-is" controls
  $("#choices-card").classList.remove("hidden");
  $("#choices-card").scrollIntoView({ behavior: scrollBehavior() });
  refreshDraftPreview();  // first render uses the pre-selected defaults
}

$("#confirm-btn").addEventListener("click", async () => {
  const choices = currentChoices();
  $("#confirm-status").textContent = "Applying…";
  $("#confirm-btn").disabled = true;
  try {
    const res = await fetch(`/api/apply/${applyId}/confirm`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choices }) });
    if (!res.ok) {
      applyError(`Apply failed: ${await errorDetail(res)}`);
      return;
    }
    $("#choices-card").classList.add("hidden");
    finishApply(await res.json());
  } catch (err) {
    applyError(`Could not reach the server (<code>${err}</code>).`);
  } finally {
    $("#confirm-status").textContent = "";
    $("#confirm-btn").disabled = false;
  }
});

function finishApply(out) {
    $("#tabbtn-preview").disabled = false;
    $("#tabbtn-preview").title = "";
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
      critical.map(w => `<div class="error-box">${w}</div>`).join("") +
      (rest.length ? rest.map(w => "&bull; " + w).join("<br>") : "");
    const details = $("#notes-details");
    if (warnings.length) {
      $("#notes-count").textContent = `(${warnings.length})`;
      details.classList.remove("hidden");
      details.open = critical.length > 0;  // auto-expand critical warnings
    } else {
      details.classList.add("hidden");
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
  $("#deck-picked").classList.add("hidden");
  $("#apply-error").classList.add("hidden");
  $("#choices-card").classList.add("hidden");
  switchTab("apply");
  $("#content-file").focus();
});
