// Jonli signal: har 5 soniyada yangi signal bormi tekshiriladi → toast + ovoz + badge
(function () {
  const badges = document.querySelectorAll("[data-alert-badge]");
  if (!badges.length) return;
  let latest = null;
  const box = document.getElementById("toasts");

  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.25].forEach((t) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
        g.gain.setValueAtTime(0.15, ctx.currentTime + t);
        o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.18);
      });
    } catch (e) {}
  }

  function esc(s) { const d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; }

  function toast(a) {
    const icon = a.color === "red" ? "bi-exclamation-octagon-fill" : "bi-exclamation-triangle-fill";
    const el = document.createElement("div");
    el.className = "toast show border-0 shadow";
    el.innerHTML = `
      <div class="toast-header zone-${a.color}">
        <i class="bi ${icon} me-2"></i><strong class="me-auto">${a.escalated ? "⏫ " : ""}${esc(a.color_label)} zona — ${esc(a.kind)}</strong>
        <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
      </div>
      <div class="toast-body">
        <a href="${a.url}" class="fw-semibold">${esc(a.name)}</a><br>
        <small class="text-muted">${esc(a.clinic)}, ${esc(a.district)}</small>
        ${a.changes ? `<div class="small mt-1">📈 ${esc(a.changes)}</div>` : ""}
        <ul class="small mb-0 mt-1 ps-3">${a.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      </div>`;
    box.appendChild(el);
    el.querySelector(".btn-close").onclick = () => el.remove();
    setTimeout(() => el.remove(), 20000);
  }

  async function poll() {
    try {
      const r = await fetch(`/alerts/feed/?since=${latest || 0}`, { headers: { "X-Requested-With": "fetch" } });
      if (!r.ok) return;
      const d = await r.json();
      badges.forEach((badge) => {
        badge.textContent = d.new_count;
        badge.classList.toggle("d-none", !d.new_count);
      });
      if (latest !== null && d.items.length) {
        d.items.forEach(toast);
        beep();
        document.body.dispatchEvent(new Event("alerts-changed"));
      }
      latest = d.latest;
    } catch (e) {}
  }
  poll();
  setInterval(poll, 5000);
})();

// ---------- Jadvallar: avtomatik qidiruv + ustun filtrlari (barcha sahifalarda) ----------
(() => {
  const L = { uz: ["Jadvaldan qidirish…", "Hammasi", "ta qator", "Tozalash"], ru: ["Поиск по таблице…", "Все", "строк", "Сброс"],
              en: ["Search table…", "All", "rows", "Clear"] }[document.documentElement.lang] || ["Jadvaldan qidirish…", "Hammasi", "ta qator", "Tozalash"];
  const norm = (t) => (t || "").toLowerCase().replace(/[ʻ‘’`´]/g, "'").replace(/\s+/g, " ").trim();
  const cellText = (td) => norm(td ? td.innerText : "");

  function enhance(table) {
    if (table.dataset.enhanced || table.closest("[data-nofilter]") || table.closest(".modal") || table.closest("#ai-sum")) return;
    const body = table.tBodies[0];
    const head = table.tHead && table.tHead.rows[0];
    if (!body || !head) return;
    const rows = [...body.rows].filter((r) => !r.querySelector(".empty") && r.cells.length > 1);
    if (rows.length < 6) return;
    table.dataset.enhanced = "1";

    // ustun filtri: 2–8 xil qiymatli ustunlar (zona, holat, rol, turi...)
    const filters = [];
    [...head.cells].forEach((th, i) => {
      const title = th.textContent.trim().replace(/\s+/g, " ");
      if (!title) return;
      const vals = new Map();
      rows.forEach((r) => { const t = r.cells[i] ? r.cells[i].innerText.trim().replace(/\s+/g, " ") : ""; if (t && t.length < 40) vals.set(norm(t), t); });
      const filled = rows.filter((r) => r.cells[i] && r.cells[i].innerText.trim()).length;
      if (vals.size >= 2 && vals.size <= 8 && filled >= rows.length * 0.6) filters.push({ i, title, vals: [...vals.entries()].sort((a, b) => a[1].localeCompare(b[1])) });
    });

    const bar = document.createElement("div");
    bar.className = "table-tools d-flex flex-wrap gap-2 align-items-center p-2 border-bottom";
    bar.innerHTML = `<div class="input-group input-group-sm" style="max-width:280px"><span class="input-group-text"><i class="bi bi-search"></i></span>
      <input type="search" class="form-control" placeholder="${L[0]}"></div>` +
      filters.slice(0, 3).map((f) => `<select class="form-select form-select-sm" style="max-width:190px" data-col="${f.i}">
        <option value="">${f.title}: ${L[1]}</option>${f.vals.map(([k, v]) => `<option value="${k.replace(/"/g, "&quot;")}">${v}</option>`).join("")}</select>`).join("") +
      `<span class="small text-muted ms-auto" data-count></span>`;
    const host = table.closest(".table-responsive") || table;
    host.parentNode.insertBefore(bar, host);

    const input = bar.querySelector("input"), sels = [...bar.querySelectorAll("select")], count = bar.querySelector("[data-count]");
    const apply = () => {
      const q = norm(input.value).split(" ").filter(Boolean);
      let shown = 0;
      rows.forEach((r) => {
        const txt = norm(r.innerText);
        const ok = q.every((w) => txt.includes(w)) && sels.every((s) => !s.value || cellText(r.cells[+s.dataset.col]) === s.value);
        r.style.display = ok ? "" : "none";
        if (ok) shown++;
      });
      count.textContent = shown === rows.length ? `${rows.length} ${L[2]}` : `${shown} / ${rows.length} ${L[2]}`;
    };
    input.addEventListener("input", apply);
    sels.forEach((s) => s.addEventListener("change", apply));
    apply();
  }

  const run = () => document.querySelectorAll("table.table").forEach(enhance);
  run();
  document.addEventListener("shown.bs.tab", run);                // yashirin tablar ochilganda
  document.body.addEventListener("htmx:afterSettle", run);       // HTMX bilan yangilangan qismlar
})();
