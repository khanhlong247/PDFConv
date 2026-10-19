"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const STATE = { queued: "Đang chờ", running: "Đang xử lý", succeeded: "Hoàn tất", failed: "Lỗi" };
const views = new Map();          // job id -> {el, page}
let pollTimer = null;

function fileUrl(job, path, download = false) {
  const enc = path.split("/").map(encodeURIComponent).join("/");
  return `/api/jobs/${job.id}/files/${enc}${download ? "?download=1" : ""}`;
}

function fmtSize(n) {
  if (n > 1e6) return (n / 1e6).toFixed(1) + " MB";
  if (n > 1e3) return (n / 1e3).toFixed(0) + " KB";
  return n + " B";
}

async function loadHealth() {
  const box = $("#status");
  try {
    const h = await (await fetch("/api/health")).json();
    const chips = [
      [h.toolchain.latex, `XeLaTeX ${h.toolchain.latex ? "✓" : "✗"}`, h.toolchain.latex_engine],
      [h.toolchain.docx_pdf, `Xem trước DOCX ${h.toolchain.docx_pdf ? "✓" : "✗"}`, h.toolchain.docx_engine],
      [h.ocr.available, `OCR ${h.ocr.available ? "✓" : "✗"}`, (h.ocr.languages || []).join(", ")],
    ];
    box.replaceChildren(...chips.map(([on, text, title]) => {
      const s = document.createElement("span");
      s.className = "chip " + (on ? "on" : "off");
      s.textContent = text;
      s.title = title || "không có";
      return s;
    }));
    const v = document.createElement("span");
    v.className = "chip";
    v.textContent = "v" + h.version;
    box.append(v);
    if (!h.ocr.available) { $("#ocr").disabled = true; $("#ocr").parentElement.title = "Máy chủ chưa cài Tesseract"; }
  } catch {
    box.textContent = "Không kết nối được máy chủ";
  }
}

function setupForm() {
  const input = $("#files"), drop = $("#drop"), btn = $("#submit");
  const refresh = () => {
    const list = $("#picked");
    list.replaceChildren(...[...input.files].map(f => {
      const li = document.createElement("li");
      li.textContent = `${f.name} · ${fmtSize(f.size)}`;
      return li;
    }));
    btn.disabled = input.files.length === 0;
  };
  input.addEventListener("change", refresh);
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => { input.files = e.dataTransfer.files; refresh(); });
  drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });

  $("#form").addEventListener("submit", async e => {
    e.preventDefault();
    const msg = $("#form-msg");
    msg.textContent = "";
    const formats = [...document.querySelectorAll("input[name=fmt]:checked")].map(i => i.value);
    if (!formats.length) { msg.textContent = "Chọn ít nhất một định dạng đầu ra."; return; }
    const opts = {
      formats,
      latex_mode: $("input[name=latex_mode]:checked").value,
      compile_latex: $("#compile_latex").checked,
      preview_docx: $("#preview_docx").checked,
      detect_tables: $("#detect_tables").checked,
      detect_columns: $("#detect_columns").checked,
      ocr: $("#ocr").checked,
      ocr_language: $("#ocr_language").value || "vie+eng",
    };
    if ($("#password").value) opts.password = $("#password").value;
    if ($("#max_pages").value) opts.max_pages = parseInt($("#max_pages").value, 10);

    const fd = new FormData();
    [...input.files].forEach(f => fd.append("files", f));
    fd.append("options", JSON.stringify(opts));
    btn.disabled = true;
    btn.textContent = "Đang tải lên…";
    try {
      const res = await fetch("/api/jobs", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Tải lên thất bại");
      input.value = "";
      refresh();
      await loadJobs();
    } catch (err) {
      msg.textContent = err.message;
    } finally {
      btn.textContent = "Chuyển đổi";
      btn.disabled = input.files.length === 0;
    }
  });
}

async function loadJobs() {
  let jobs = [];
  try { jobs = await (await fetch("/api/jobs")).json(); } catch { return; }
  const box = $("#jobs");
  const seen = new Set();
  jobs.forEach((job, i) => {
    seen.add(job.id);
    let v = views.get(job.id);
    if (!v) {
      v = { el: $("#job-tpl").content.firstElementChild.cloneNode(true), page: 0, rendered: "" };
      views.set(job.id, v);
      $(".del", v.el).addEventListener("click", () => deleteJob(job.id));
      $(".prev", v.el).addEventListener("click", () => { v.page--; renderViewer(v); });
      $(".next", v.el).addEventListener("click", () => { v.page++; renderViewer(v); });
    }
    if (box.children[i] !== v.el) box.insertBefore(v.el, box.children[i] || null);
    renderJob(v, job);
  });
  for (const [id, v] of views) if (!seen.has(id)) { v.el.remove(); views.delete(id); }
  $("#empty").hidden = jobs.length > 0;
  $("#jobs-count").textContent = jobs.length ? `${jobs.length} file` : "";

  const active = jobs.some(j => j.state === "queued" || j.state === "running");
  clearTimeout(pollTimer);
  pollTimer = setTimeout(loadJobs, active ? 1200 : 8000);
}

async function deleteJob(id) {
  if (!confirm("Xoá kết quả chuyển đổi này?")) return;
  await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  loadJobs();
}

function renderJob(v, job) {
  const el = v.el;
  v.job = job;
  const badge = $(".badge", el);
  badge.className = "badge " + job.state;
  badge.textContent = STATE[job.state] || job.state;
  $(".name", el).textContent = job.filename;

  const running = job.state === "queued" || job.state === "running";
  const prog = $(".progress", el);
  prog.hidden = !running;
  $(".bar", el).style.width = (job.progress || 2) + "%";
  $(".msg", el).textContent = `${job.progress || 0}% · ${job.message}`;

  const err = $(".error", el);
  err.hidden = job.state !== "failed";
  err.textContent = job.error || "";

  const ok = job.state === "succeeded" && job.report;
  $(".result", el).hidden = !ok;
  const zip = (job.artifacts || []).find(a => a.kind === "zip");
  const zipBtn = $(".zip", el);
  zipBtn.hidden = !zip;
  if (zip) zipBtn.href = fileUrl(job, zip.path, true);
  if (!ok) return;

  const key = job.updated_at;
  if (v.rendered === key) return;
  v.rendered = key;
  renderResult(v);
}

function avg(xs) { return xs && xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; }

function renderResult(v) {
  const { el, job } = v;
  const r = job.report;
  const stats = [
    ["Trang", `${r.processed_pages}/${r.total_pages}`],
    ["Thời gian", `${(r.timings.total || 0).toFixed(1)} s`],
  ];
  const fl = avg(r.fidelity.latex), fd = avg(r.fidelity.docx);
  if (fl !== null) stats.push(["Độ giống LaTeX", (fl * 100).toFixed(1) + "%"]);
  if (fd !== null) stats.push(["Độ giống DOCX", (fd * 100).toFixed(1) + "%"]);
  const tables = r.pages.reduce((a, p) => a + p.tables, 0);
  const images = r.pages.reduce((a, p) => a + p.images, 0);
  stats.push(["Bảng", tables], ["Ảnh", images]);
  if (r.pages.some(p => p.columns > 1)) stats.push(["Nhiều cột", "có"]);
  if (r.pages.some(p => p.scanned)) stats.push(["Trang scan", r.pages.filter(p => p.scanned).length]);
  $(".stats", el).replaceChildren(...stats.map(([k, val]) => {
    const d = document.createElement("div");
    d.className = "stat";
    d.append(k + ": ");
    const b = document.createElement("b");
    b.textContent = val;
    d.append(b);
    return d;
  }));

  const files = $(".files", el);
  files.replaceChildren(...job.artifacts.filter(a => a.kind !== "zip").map(a => {
    const link = document.createElement("a");
    link.className = "btn";
    link.href = fileUrl(job, a.path, !a.path.endsWith(".pdf"));
    if (a.path.endsWith(".pdf")) link.target = "_blank";
    link.textContent = `${a.label} · ${fmtSize(a.size)}`;
    return link;
  }));

  const warns = [...r.warnings, ...r.pages.flatMap(p => p.warnings.map(w => `Trang ${p.index + 1}: ${w}`))];
  const wb = $(".warn-box", el);
  wb.hidden = warns.length === 0;
  $("summary", wb).textContent = `${warns.length} cảnh báo`;
  $("ul", wb).replaceChildren(...warns.map(w => { const li = document.createElement("li"); li.textContent = w; return li; }));

  const lb = $(".log-box", el);
  const log = [r.latex_log && "=== LaTeX ===\n" + r.latex_log, r.docx_log && "=== DOCX ===\n" + r.docx_log].filter(Boolean).join("\n\n");
  lb.hidden = !log;
  $("pre", lb).textContent = log;

  v.page = 0;
  renderViewer(v);
}

function renderViewer(v) {
  const { el, job } = v;
  const pv = job.report.previews || [];
  const viewer = $(".viewer", el);
  viewer.hidden = pv.length === 0;
  if (!pv.length) return;
  v.page = Math.max(0, Math.min(v.page, pv.length - 1));
  const p = pv[v.page];
  $(".page-label", el).textContent = `Trang ${p.page} / ${pv.length}`;
  $(".prev", el).disabled = v.page === 0;
  $(".next", el).disabled = v.page === pv.length - 1;
  const cols = [["original", "Bản gốc", null], ["latex", "LaTeX", "latex"], ["docx", "DOCX", "docx"]];
  $(".panes", el).replaceChildren(...cols.filter(([k]) => k === "original" || job.artifacts.some(a => a.kind.startsWith(k)))
    .map(([key, title, fkey]) => {
      const pane = document.createElement("div");
      pane.className = "pane";
      const h = document.createElement("h4");
      h.textContent = title;
      const score = fkey && job.report.fidelity[fkey] ? job.report.fidelity[fkey][v.page] : undefined;
      if (score !== undefined) {
        const s = document.createElement("span");
        s.className = "score";
        s.textContent = (score * 100).toFixed(1) + "%";
        s.title = "Độ giống thị giác so với bản gốc";
        h.append(s);
      }
      pane.append(h);
      if (p[key]) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = `${title} – trang ${p.page}`;
        img.src = fileUrl(job, p[key]);
        pane.append(img);
      } else {
        const n = document.createElement("div");
        n.className = "none";
        n.textContent = key === "original" ? "Không có ảnh" : "Chưa biên dịch / không có công cụ xem trước";
        pane.append(n);
      }
      return pane;
    }));
}

loadHealth();
setupForm();
loadJobs();
