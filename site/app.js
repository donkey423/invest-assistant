// 今日早報：讀 data/latest.json 畫出各區塊。純前端，不需要建置工具。
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cls = (v) => (v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat");
  const arrow = (v) => (v == null ? "" : v > 0 ? "▲" : v < 0 ? "▼" : "");
  const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
  const num = (v) => (v == null ? "—" : v.toLocaleString("zh-TW", { maximumFractionDigits: 2 }));

  // 走勢圖：依整段漲跌決定紅綠，底下填一層淡色
  function sparkline(values, { w = 300, h = 60, fill = true } = {}) {
    if (!values || values.length < 2) return "";
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 2 - ((v - lo) / span) * (h - 4)]);
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join("");
    const color = `var(--${values.at(-1) >= values[0] ? "up" : "down"})`;
    const area = fill ? `<path d="${d}L${w} ${h}L0 ${h}Z" fill="${color}" opacity="0.12"/>` : "";
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${area}<path d="${d}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function renderTaiex(t) {
    if (t.error) { $("taiex-last").textContent = "暫無資料"; return; }
    $("taiex-date").textContent = `資料日 ${t.as_of}`;
    $("taiex-last").textContent = num(t.last);
    $("taiex-chg").innerHTML = `<span class="${cls(t.change_pct)}">${arrow(t.change_pct)} ${pct(t.change_pct)}</span>`;
    $("taiex-periods").innerHTML = [["今天", t.change_pct], ["近五天", t.chg_5d], ["近一個月", t.chg_1m], ["近一年", t.chg_1y]]
      .map(([k, v]) => `<div><span class="muted">${k}</span><b class="${cls(v)}">${pct(v)}</b></div>`).join("");
    $("taiex-chart").innerHTML = sparkline(t.spark, { w: 600, h: 150 });
    const pos = Math.max(0, Math.min(1, t.range_pos));
    $("range-dot").style.left = `${pos * 100}%`;
    $("range-lo").textContent = `一年最低 ${num(t.low_52w)}`;
    $("range-hi").textContent = `一年最高 ${num(t.high_52w)}`;
    const zone = pos < 0.33 ? "偏低" : pos > 0.67 ? "偏高" : "中間";
    $("range-text").textContent = `位在一年區間的 ${Math.round(pos * 100)}% 位置（${zone}）`;
  }

  function renderGlobal(list) {
    $("global").innerHTML = list.map((q) => q.error
      ? `<div class="mini"><div class="row"><span class="name">${esc(q.name)}</span><span class="muted">無資料</span></div></div>`
      : `<div class="mini" title="${esc(q.name)} ${num(q.last)}（資料日 ${esc(q.as_of)}）">
          <div class="name">${esc(q.name)}</div>
          <div class="row"><span>${num(q.last)}</span><span class="${cls(q.change_pct)}">${arrow(q.change_pct)}${pct(q.change_pct)}</span></div>
          ${sparkline(q.spark, { w: 120, h: 36 })}
          <div class="row muted"><span>近五天 <span class="${cls(q.chg_5d)}">${pct(q.chg_5d)}</span></span><span>一年 <span class="${cls(q.chg_1y)}">${pct(q.chg_1y)}</span></span></div>
        </div>`).join("");
  }

  function renderAI(list, bench) {
    if (bench && !bench.error) $("ai-bench").innerHTML = `${esc(bench.name)} 今天 <span class="${cls(bench.change_pct)}">${pct(bench.change_pct)}</span>`;
    $("ai").innerHTML = list.map((q) => q.error
      ? `<div class="stock"><span class="name">${esc(q.name)}</span><span class="muted">無資料</span></div>`
      : `<div class="stock"><div><div class="name">${esc(q.name)}</div><div class="sub">${esc(q.symbol)} ${num(q.last)}</div><div class="sub">近五天 <span class="${cls(q.chg_5d)}">${pct(q.chg_5d)}</span></div></div>
          <div class="pct ${cls(q.change_pct)}">${arrow(q.change_pct)}${pct(q.change_pct)}</div></div>`).join("");
  }

  function renderSummary(s) {
    if (!s) { $("headline").textContent = "AI 摘要尚未產生"; return; }
    $("headline").textContent = s.headline;
    $("comment").textContent = s.market_comment;
    $("points").innerHTML = (s.points || []).map((p) => {
      const src = (p.sources || [])[0];
      const title = src ? `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title);
      const more = (p.sources || []).length > 1 ? `<span class="muted">（${p.sources.length} 則來源）</span>` : "";
      return `<li><span class="tag">${esc(p.tag)}</span><div>${title}${more}</div><div class="sum">${esc(p.summary)}</div></li>`;
    }).join("");
    if (s.model) $("model").textContent = `｜摘要模型 ${s.model}`;
  }

  function render(b) {
    const t = new Date(b.generated_at);
    $("updated").textContent = `更新於 ${t.toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}`;
    $("warnings").innerHTML = (b.warnings || []).map((w) => `<div>${esc(w)}</div>`).join("");
    renderTaiex(b.market.taiex);
    renderGlobal(b.market.global);
    renderAI(b.market.ai_stocks, b.market.ai_benchmark);
    renderSummary(b.summary);
  }

  // 分頁切換，記住上次看的頁籤
  function showTab(name) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".tabpane").forEach((p) => { p.hidden = p.id !== `tab-${name}`; });
    try { localStorage.setItem("tab", name); } catch (e) { /* 無痕模式 */ }
  }
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  try { const saved = localStorage.getItem("tab"); if (saved && $(`tab-${saved}`)) showTab(saved); } catch (e) { /* 無痕模式 */ }

  fetch(`data/latest.json?t=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(render)
    .catch(() => { $("headline").textContent = "早報資料讀取失敗，請稍後再試。"; });
})();
