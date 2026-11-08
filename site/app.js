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
    const f = c.futures;
    if (f) {
      const v = f.foreign_oi, side = v > 0 ? "淨多單" : v < 0 ? "淨空單" : "持平";
      const ch = f.change != null ? `<span class="muted">比前一天</span><b class="${cls(f.change)}">${f.change > 0 ? "+" : ""}${f.change.toLocaleString("zh-TW")} 口</b>` : "";
      $("futures").innerHTML = `<div><span class="muted">外資台指期未平倉（${esc(f.date)}）</span><b class="${cls(v)}">${side} ${Math.abs(v).toLocaleString("zh-TW")} 口</b></div>${ch ? `<div>${ch}</div>` : ""}`;
    }
    $("chips-notes").innerHTML = (c.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
  }

  // 未來一週行事曆：依日期分組
  const CAL_KIND = { fed: "Fed／央行", macro: "經濟數據", earnings: "財報", dividend: "除權息" };
  const WEEK = "日一二三四五六";
  function renderCalendar(c) {
    if (!c) { $("cal").innerHTML = `<div class="muted">下次更新後就會出現。</div>`; return; }
    const md = (iso) => { const [y, m, d] = iso.split("-").map(Number); return `${m}/${d}（${WEEK[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}）`; };
    $("cal-range").textContent = `${md(c.start)} – ${md(c.end)}｜台灣時間`;
    const byDay = {};
    (c.events || []).forEach((e) => (byDay[e.date] = byDay[e.date] || []).push(e));
    const today = c.start;
    const days = Object.keys(byDay).sort();
    const others = c.dividend_others ? `<p class="muted cal-more">另有 ${c.dividend_others} 檔股票或 ETF 這週除權息（只列常見的）</p>` : "";
    $("cal").innerHTML = (days.length ? days.map((d) => `<div class="cal-day${d === today ? " today" : ""}">
        <div class="cal-date">${md(d)}${d === today ? " 今天" : ""}</div>
        <ul>${byDay[d].map((e) => `<li class="k-${esc(e.kind)}"><span class="cal-time">${esc(e.time) || "—"}</span>
          <div><b>${esc(e.title)}</b> <span class="cal-tag">${CAL_KIND[e.kind] || ""}</span>${e.note ? `<div class="muted">${esc(e.note)}</div>` : ""}</div></li>`).join("")}</ul>
      </div>`).join("") : `<div class="muted">這一週沒有重要事件。</div>`) + others;
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
    const themes = s.themes || [];
    $("theme-card").hidden = !themes.length;
    $("themes").innerHTML = themes.map((t) => {
      const src = (t.sources || []).map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.source || x.title)}</a>`).join("、");
      return `<li><div class="theme-title"><span class="tag">${esc(t.chain)}</span><b>${esc(t.title)}</b></div>
        <p>${esc(t.reasoning)}</p>
        <div class="theme-row"><span class="muted">觀察</span><span>${(t.watch || []).map(esc).join("、")}</span></div>
        <div class="theme-row"><span class="muted">反方</span><span>${esc(t.counter)}</span></div>
        <div class="theme-row"><span class="muted">已反映？</span><span>${esc(t.priced_in)}</span></div>
        ${src ? `<div class="theme-row"><span class="muted">來源</span><span>${src}</span></div>` : ""}</li>`;
    }).join("");
  }

  // 產業鏈訊號：每條鏈一張卡，上游訊號 → 月營收 → 股價
  const LIGHT = { "轉強": "up", "轉弱": "down", "持平": "flat", "資料不足": "flat" };
  const TREND = { up: ["▲ 轉強", "up"], flat: ["＝ 持平", "flat"], down: ["▼ 轉弱", "down"] };
  const pp = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);

  function chainDetail(c) {
    const up = (c.upstream || []).map((u) => {
      const [word, k] = TREND[u.trend] || ["待更新", "flat"];
      const name = u.url ? `<a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.name)}</a>` : esc(u.name);
      return `<li><span class="trend ${k}">${word}</span><div>${name}${u.auto ? ` <span class="auto">自動</span>` : ""}<div class="muted">${esc(u.value)}${u.as_of ? `（${esc(u.as_of)}）` : ""}</div></div></li>`;
    }).join("") || `<li class="muted">還沒有上游訊號</li>`;
    const r = c.revenue || {}, p = c.price || {};
    const rev = r.count
      ? `<div class="kv"><span class="muted">${esc(r.month)} 台股年增（中位數）</span><b class="${cls(r.avg_yoy)}">${pp(r.avg_yoy)}</b></div>
         <div class="kv"><span class="muted">比今年累計</span><b class="${cls(r.avg_accel)}">${r.avg_accel == null ? "—" : `${r.avg_accel > 0 ? "加速" : "放緩"} ${Math.abs(r.avg_accel).toFixed(1)} 個百分點`}</b></div>
         <div class="kv"><span class="muted">年增為正</span><b>${r.positive} / ${r.count} 家</b></div>`
      : `<div class="muted">這條鏈沒有台股月營收資料。</div>`;
    const rows = (c.stocks || []).map((s) => s.error
      ? `<tr><td>${esc(s.name)}<div class="muted">${esc(s.symbol)}</div></td><td colspan="3" class="muted">無資料</td></tr>`
      : `<tr><td>${esc(s.name)}<div class="muted">${esc(s.symbol)}</div></td>
          <td class="${cls(s.chg_1m)}">${pct(s.chg_1m)}</td>
          <td>${s.range_pos == null ? "—" : `${Math.round(s.range_pos * 100)}%`}</td>
          <td class="${cls(s.rev_yoy)}">${s.rev_yoy == null ? "—" : pp(s.rev_yoy)}</td></tr>`).join("");
    return `<p class="muted">${esc(c.desc)}</p>
      <div class="why">${(c.why || []).map(esc).join("；")}</div>
      <h3>① 上游訊號</h3><ul class="upstream">${up}</ul>
      <h3>② 台股月營收</h3>${rev}
      <h3>③ 股價已反映多少</h3>
      <div class="kv"><span class="muted">代表股近一個月平均</span><b class="${cls(p.avg_1m)}">${pct(p.avg_1m)}</b></div>
      <div class="kv"><span class="muted">${esc(p.bench_name || p.bench)} 近一個月</span><b class="${cls(p.bench_1m)}">${pct(p.bench_1m)}</b></div>
      <p class="price-note">${esc(p.note)}</p>
      <table class="chain-table"><thead><tr><th>代表股</th><th>近一月</th><th>一年位置</th><th>營收年增</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function renderBacktest(bt) {
    if (!bt) { $("bt-table").innerHTML = `<div class="muted">下次更新後開始記錄。</div>`; return; }
    $("bt-since").textContent = `從 ${bt.since} 起，已記錄 ${bt.days_logged} 個交易日`;
    const hs = Object.entries(bt.horizons || {});
    const any = hs.some(([, h]) => ["轉強", "持平", "轉弱"].some((l) => (h[l] || {}).n));
    if (!any) {
      const need = Math.max(0, 6 - bt.days_logged);
      $("bt-table").innerHTML = `<div class="muted">資料累積中：再 ${need} 個交易日可以看到「1 週後」的結果，約 1 個月後看到「1 個月後」，3 個月後看到「3 個月後」。</div>`;
    } else {
      const cell = (x, light) => !x || !x.n ? `<td class="muted">—</td>`
        : `<td><b class="${cls(x.avg_excess)}">${pp(x.avg_excess)}</b><div class="muted">${x.hit == null ? "" : `命中 ${x.hit}%｜`}${x.n} 次</div></td>`;
      $("bt-table").innerHTML = `<table class="chain-table bt"><thead><tr><th>燈號亮起後</th>${hs.map(([k]) => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>
        ${["轉強", "持平", "轉弱"].map((l) => `<tr><td><span class="light ${LIGHT[l]}">${l}</span></td>${hs.map(([, h]) => cell(h[l], l)).join("")}</tr>`).join("")}</tbody></table>`;
    }
    const ch = bt.changes || [];
    $("bt-changes").innerHTML = ch.map((c) => `<li><div>${esc(c.date)} <b>${esc(c.name)}</b> ${esc(c.from)} → <span class="${LIGHT[c.to] || "flat"}">${esc(c.to)}</span>
      <span class="muted">${c.excess_since == null ? "" : `之後至今超額報酬 `}</span>${c.excess_since == null ? "" : `<b class="${cls(c.excess_since)}">${pp(c.excess_since)}</b>`}</div></li>`).join("")
      || `<li class="muted">還沒有燈號變化。</li>`;
  }

  let chainFilter = "全部";
  function renderChains(sig) {
    if (!sig || !sig.chains) { $("chains").innerHTML = `<section class="card placeholder">下次更新後就會出現。</section>`; return; }
    const counts = {};
    sig.chains.forEach((c) => { counts[c.light] = (counts[c.light] || 0) + 1; });
    const filters = ["全部", "轉強", "持平", "轉弱", "資料不足"].filter((f) => f === "全部" || counts[f]);
    $("chain-filter").innerHTML = filters.map((f) => `<button class="chip${f === chainFilter ? " selected" : ""}" data-f="${f}">${f} <b>${f === "全部" ? sig.chains.length : counts[f]}</b></button>`).join("");
    $("chain-filter").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { chainFilter = b.dataset.f; renderChains(sig); }));
    const list = sig.chains.filter((c) => chainFilter === "全部" || c.light === chainFilter);
    const groups = [...new Set(list.map((c) => c.group || "其他"))];
    $("chains").innerHTML = groups.map((g) => `<h2 class="group-head">${esc(g)}</h2><div class="chain-list">${list.filter((c) => (c.group || "其他") === g).map((c) => {
      const r = c.revenue || {}, p = c.price || {};
      return `<details class="card chain" data-id="${esc(c.id)}">
        <summary><div class="chain-sum"><b>${esc(c.name)}</b><span class="light ${LIGHT[c.light] || "flat"}">${esc(c.light)}</span></div>
          <div class="chain-nums muted"><span>營收年增 <b class="${cls(r.avg_yoy)}">${r.count ? pp(r.avg_yoy) : "—"}</b></span>
          <span>近一月 <b class="${cls(p.avg_1m)}">${pct(p.avg_1m)}</b></span>
          <span>比${esc(p.bench_name || "大盤")} <b class="${cls(p.gap)}">${p.gap == null ? "—" : pp(p.gap)}</b></span></div></summary>
        ${chainDetail(c)}</details>`;
    }).join("")}</div>`).join("") || `<section class="card placeholder">沒有符合的產業鏈。</section>`;
    const ev = sig.revenue_events || [];
    const months = [...new Set(ev.map((e) => e.ym))].sort();
    $("rev-month").textContent = months.length ? `${months.at(-1)}｜開啟 LINE 推播後會自動通知` : "";
    // 轉折與新高比較少見，排前面；超過 8 則收起來
    const order = { turn_up: 0, new_high: 1, turn_down: 2, accel: 3, decel: 4 };
    const sorted = [...ev].sort((a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9));
    const li = (e) => `<li><div>${esc(e.text)}</div></li>`;
    $("rev-events").innerHTML = sorted.slice(0, 8).map(li).join("")
      + (sorted.length > 8 ? `<li><details><summary class="muted">再顯示 ${sorted.length - 8} 則</summary><ul class="newslist">${sorted.slice(8).map(li).join("")}</ul></details></li>` : "")
      || `<li class="muted">這個月追蹤的公司營收沒有明顯變化（由負轉正、明顯加速／放緩、創新高）。</li>`;
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
    renderCalendar(b.calendar);
    renderSummary(b.summary);
    renderWorld(b.world);
    renderChains(b.signals);
    renderBacktest((b.signals || {}).backtest);
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
