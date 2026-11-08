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

  // 市場溫度計：台股籌碼（證交所）＋ VIX、美債、美元、台幣、費半、黃金、原油、比特幣
  const GAUGE_FMT = {
    yield: (q) => `${q.last.toFixed(2)}%`,
    twd: (q) => q.last.toFixed(2),
    btc: (q) => Math.round(q.last).toLocaleString("zh-TW"),
  };
  const yi = (v) => `${v > 0 ? "+" : ""}${v.toLocaleString("zh-TW", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} 億`;

  function renderGauges(list) {
    if (!list || !list.length) { $("gauges").innerHTML = `<div class="muted">下次更新後就會出現。</div>`; return; }
    $("gauges").innerHTML = list.map((q) => {
      if (q.error) return `<div class="gauge"><div class="name">${esc(q.name)}</div><div class="muted">無資料</div></div>`;
      const val = (GAUGE_FMT[q.kind] || ((x) => num(x.last)))(q);
      const chg = q.kind === "yield"
        ? `<span class="${cls(q.change)}">${arrow(q.change)}${Math.abs(Math.round(q.change * 100))} 基點</span>`
        : `<span class="${cls(q.change_pct)}">${arrow(q.change_pct)}${pct(q.change_pct)}</span>`;
      return `<div class="gauge" title="資料日 ${esc(q.as_of)}">
        <div class="name">${esc(q.name)}</div>
        <div class="row"><b>${val}</b>${chg}</div>
        ${sparkline(q.spark.slice(-22), { w: 120, h: 28, fill: false })}
        <div class="note">${esc(q.note)}</div></div>`;
    }).join("");
  }

  function renderChips(c) {
    if (!c || (!c.institutional && !c.margin)) {
      $("inst").innerHTML = `<div class="muted">證交所資料下次更新後就會出現。</div>`;
      return;
    }
    const i = c.institutional;
    if (i) {
      $("inst-date").textContent = `資料日 ${i.date}｜單位：億元`;
      const rows = [["外資", i.foreign], ["投信", i.trust], ["自營商", i.dealer]];
      const max = Math.max(1, ...rows.map((r) => Math.abs(r[1])));
      $("inst").innerHTML = rows.map(([k, v]) => {
        const w = (Math.abs(v) / max) * 50;
        const bar = `<span class="bar ${cls(v)}" style="${v >= 0 ? "left:50%" : `left:${50 - w}%`};width:${w}%"></span>`;
        return `<div class="inst-row"><span>${k}</span><div class="track">${bar}</div><b class="${cls(v)}">${yi(v)}</b></div>`;
      }).join("") + `<div class="inst-row total"><span>合計</span><div></div><b class="${cls(i.total)}">${yi(i.total)}</b></div>`;
    }
    const h = (c.history || []).slice(-10);
    if (h.length >= 2) {
      const max = Math.max(1, ...h.map((d) => Math.abs(d.foreign)));
      $("inst-hist").innerHTML = `<div class="muted">外資近 ${h.length} 個交易日</div><div class="hist-bars">${h.map((d) =>
        `<span class="hb ${cls(d.foreign)}" style="height:${Math.max(4, (Math.abs(d.foreign) / max) * 100)}%" title="${esc(d.date)} ${yi(d.foreign)}"></span>`).join("")}</div>`;
    }
    const m = c.margin;
    if (m) {
      const ratio = m.short_ratio != null ? `<div><span class="muted">券資比</span><b>${m.short_ratio.toFixed(2)}%</b></div>` : "";
      $("margin").innerHTML = `<div><span class="muted">融資餘額</span><b>${num(Math.round(m.margin_balance))} 億</b></div>
        <div><span class="muted">比前一天</span><b class="${cls(m.margin_change)}">${yi(m.margin_change)}</b></div>${ratio}`;
    }
    $("chips-notes").innerHTML = (c.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
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


  // 今天的世界：地圖泡泡大小 = 新聞則數，橘色外框 = 標題有衝突、關稅等字眼
  const MAP_VIEW = { x: 50, y: 0, w: 300, h: 122 };  // 經度 -130~170、去掉最南端，手機上字比較大
  const ago = (iso) => {
    if (!iso) return "";
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    return m < 60 ? `${Math.max(1, m)} 分鐘前` : m < 1440 ? `${Math.round(m / 60)} 小時前` : `${Math.round(m / 1440)} 天前`;
  };
  const newsItem = (n, tag) => `<li>${tag ? `<span class="tag">${esc(tag)}</span>` : ""}<div><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>
      <div class="muted">${esc(n.source)}${n.published ? ` · ${ago(n.published)}` : ""}</div></div></li>`;

  function renderWorld(w) {
    if (!w) { $("world-headline").textContent = "這一份早報還沒有國際資料，下次更新後就會出現。"; return; }
    $("world-headline").textContent = w.headline;
    $("world-count").textContent = `依 ${w.news_count} 則新聞標題統計${w.by_ai ? "｜一句話由 Claude 撰寫" : ""}`;
    $("ai-headline").textContent = w.ai_headline;
    $("ai-news").innerHTML = (w.ai_news || []).map((n) => newsItem(n, n.category)).join("") || `<li class="muted">今天沒有 AI 相關新聞</li>`;

    const map = window.WORLD_MAP, regs = (w.regions || []).filter((r) => r.count > 0);
    const max = Math.max(1, ...regs.map((r) => r.count));
    const xy = (lon, lat) => [lon + 180, map.top - lat];
    const bubbles = regs.map((r) => {
      const [px, py] = xy(r.lon, r.lat), [bx, by] = xy(r.label_lon, r.label_lat);
      const rad = 4 + 6 * Math.sqrt(r.count / max);
      const leader = px !== bx || py !== by ? `<line x1="${px}" y1="${py}" x2="${bx}" y2="${by}" class="leader"/><circle cx="${px}" cy="${py}" r="1.3" class="pin"/>` : "";
      return `<g class="bubble${r.risk.length ? " risk" : ""}" data-region="${r.id}" tabindex="0" role="button" aria-label="${esc(r.name)} ${r.count} 則">
        ${leader}<circle cx="${bx}" cy="${by}" r="${rad.toFixed(1)}"/>
        <text x="${bx}" y="${(by + rad + 8).toFixed(1)}">${esc(r.name)} ${r.count}</text></g>`;
    }).join("");
    $("world-map").innerHTML = `<svg viewBox="${MAP_VIEW.x} ${MAP_VIEW.y} ${MAP_VIEW.w} ${MAP_VIEW.h}" role="img" aria-label="各地區新聞熱度地圖">
      <path d="${map.land}" class="land"/>${bubbles}</svg>`;

    const sorted = [...regs].sort((a, b) => b.count - a.count);
    $("region-chips").innerHTML = sorted.map((r) => `<button class="chip${r.risk.length ? " risk" : ""}" data-region="${r.id}" role="tab">${esc(r.name)} <b>${r.count}</b></button>`).join("");
    const select = (id) => {
      const r = regs.find((x) => x.id === id);
      if (!r) return;
      document.querySelectorAll("[data-region]").forEach((el) => el.classList.toggle("selected", el.dataset.region === id));
      const warn = r.risk.length ? `<li class="riskline">留意：標題提到「${r.risk.map(esc).join("、")}」</li>` : "";
      $("region-news").innerHTML = warn + r.news.map((n) => newsItem(n)).join("");
    };
    document.querySelectorAll("#tab-world [data-region]").forEach((el) => {
      el.addEventListener("click", () => select(el.dataset.region));
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(el.dataset.region); } });
    });
    const first = sorted.find((r) => r.risk.length) || sorted[0];
    if (first) select(first.id);
    else $("region-news").innerHTML = `<li class="muted">今天沒有抓到國際新聞</li>`;
  }

  function render(b) {
    const t = new Date(b.generated_at);
    $("updated").textContent = `更新於 ${t.toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}`;
    $("warnings").innerHTML = (b.warnings || []).map((w) => `<div>${esc(w)}</div>`).join("");
    renderTaiex(b.market.taiex);
    renderGlobal(b.market.global);
    renderAI(b.market.ai_stocks, b.market.ai_benchmark);
    renderGauges(b.market.gauges);
    renderChips(b.market.chips);
    renderSummary(b.summary);
    renderWorld(b.world);
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
