// 今日早報：讀 data/latest.json 畫出各區塊。純前端，不需要建置工具。
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cls = (v) => (v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat");
  const arrow = (v) => (v == null ? "" : v > 0 ? "▲" : v < 0 ? "▼" : "");
  const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
  const num = (v) => (v == null ? "—" : v.toLocaleString("zh-TW", { maximumFractionDigits: 2 }));

  // 走勢圖：依整段漲跌決定紅綠（圖表用 --up-mark/--down-mark），底下填一層由上往下變淡的顏色
  let gid = 0;
  function sparkline(values, { w = 300, h = 60, fill = true } = {}) {
    if (!values || values.length < 2) return "";
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 2 - ((v - lo) / span) * (h - 4)]);
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join("");
    const color = `var(--${values.at(-1) >= values[0] ? "up" : "down"}-mark)`;
    const id = `sg${++gid}`;
    const area = fill ? `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".22"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs><path d="${d}L${w} ${h}L0 ${h}Z" fill="url(#${id})"/>` : "";
    const sw = h <= 24 ? 1.5 : 2;
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${area}<path d="${d}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>`;
  }

  // 大走勢圖的互動層：滑過（或手指拖過）顯示日期與點位，終點畫一個點
  function hoverChart(el, values, dates, fmt) {
    if (!values || values.length < 2) return;
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const up = values.at(-1) >= values[0];
    el.insertAdjacentHTML("beforeend", `<span class="end-dot" style="left:100%;top:${((2 + (hi - values.at(-1)) / span * (el.clientHeight - 4)) / el.clientHeight * 100).toFixed(1)}%;background:var(--${up ? "up" : "down"}-mark)"></span><span class="hover-line" hidden></span><span class="hover-dot" hidden></span><div class="hover-tip" hidden></div>`);
    const line = el.querySelector(".hover-line"), dot = el.querySelector(".hover-dot"), tip = el.querySelector(".hover-tip");
    const show = (ev) => {
      const r = el.getBoundingClientRect();
      const x = Math.max(0, Math.min(r.width, ev.clientX - r.left));
      const i = Math.round((x / r.width) * (values.length - 1));
      const px = (i / (values.length - 1)) * r.width;
      const py = 2 + ((hi - values[i]) / span) * (r.height - 4);
      line.style.left = `${px}px`; dot.style.left = `${px}px`; dot.style.top = `${py}px`;
      const chg = ((values[i] / values[0]) - 1) * 100;
      tip.innerHTML = `<div class="muted">${esc(dates?.[i] || "")}</div><b>${fmt(values[i])}</b> <span class="${cls(chg)}">${pct(chg)}</span>`;
      tip.style.left = x > r.width / 2 ? "" : `${px + 10}px`;
      tip.style.right = x > r.width / 2 ? `${r.width - px + 10}px` : "";
      line.hidden = dot.hidden = tip.hidden = false;
    };
    const hide = () => { line.hidden = dot.hidden = tip.hidden = true; };
    el.addEventListener("pointermove", show);
    el.addEventListener("pointerdown", show);
    el.addEventListener("pointerleave", hide);
    el.title = "";
  }

  // 資料日落後（例如週二早上還是上週五的數字）就在卡片上明講，不讓舊數字被當成今天的
  const md = (d) => (d ? `${+d.slice(5, 7)}/${+d.slice(8, 10)}` : "");
  const staleTag = (q) => (q && q.stale ? `<span class="stale-tag" title="資料來源還沒更新到最新交易日">停在 ${md(q.as_of)}</span>` : "");
  const setSum = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };

  function renderTaiex(t) {
    if (t.error) { $("taiex-last").textContent = "暫無資料"; return; }
    $("taiex-date").innerHTML = `資料日 ${esc(t.as_of)} ${staleTag(t)}`;
    $("taiex-last").textContent = num(t.last);
    $("taiex-chg").innerHTML = `<span class="${cls(t.change_pct)}">${arrow(t.change_pct)} ${pct(t.change_pct)}</span>`;
    $("taiex-periods").innerHTML = [[`${md(t.as_of)} 當日`, t.change_pct], ["近五天", t.chg_5d], ["近一個月", t.chg_1m], ["近一年", t.chg_1y]]
      .map(([k, v]) => `<div><span class="muted">${k}</span><b class="${cls(v)}">${pct(v)}</b></div>`).join("");
    $("taiex-chart").innerHTML = sparkline(t.spark, { w: 600, h: 150 });
    hoverChart($("taiex-chart"), t.spark, t.spark_dates, num);
    const pos = Math.max(0, Math.min(1, t.range_pos));
    $("range-dot").style.left = `${pos * 100}%`;
    $("range-lo").textContent = `一年最低 ${num(t.low_52w)}`;
    $("range-hi").textContent = `一年最高 ${num(t.high_52w)}`;
    const zone = pos < 0.33 ? "偏低" : pos > 0.67 ? "偏高" : "中間";
    $("range-text").textContent = `位在一年區間的 ${Math.round(pos * 100)}% 位置（${zone}）`;
  }

  function renderGlobal(list) {
    setSum("global-sum", list.filter((q) => !q.error).slice(0, 4)
      .map((q) => `${esc(q.name.replace(/^美國 |^日本 |^韓國 /, ""))} <span class="${cls(q.change_pct)}">${pct(q.change_pct)}</span>`).join("・"));
    $("global").innerHTML = list.map((q) => q.error
      ? `<div class="mini"><div class="row"><span class="name">${esc(q.name)}</span><span class="muted">無資料</span></div></div>`
      : `<div class="mini" title="${esc(q.name)} ${num(q.last)}（資料日 ${esc(q.as_of)}）">
          <div class="name">${esc(q.name)} ${staleTag(q)}</div>
          <div class="row"><span>${num(q.last)}</span><span class="${cls(q.change_pct)}">${arrow(q.change_pct)}${pct(q.change_pct)}</span></div>
          ${sparkline(q.spark, { w: 120, h: 36 })}
          <div class="row muted"><span>近五天 <span class="${cls(q.chg_5d)}">${pct(q.chg_5d)}</span></span><span>一年 <span class="${cls(q.chg_1y)}">${pct(q.chg_1y)}</span></span></div>
        </div>`).join("");
  }

  function renderAI(list, bench) {
    if (bench && !bench.error) $("ai-bench").innerHTML = `${esc(bench.name)} 今天 <span class="${cls(bench.change_pct)}">${pct(bench.change_pct)}</span>`;
    const ok = list.filter((q) => !q.error);
    setSum("ai-sum", `${ok.filter((q) => q.change_pct > 0).length} 漲 ${ok.filter((q) => q.change_pct < 0).length} 跌` +
      [...ok].sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct)).slice(0, 2)
        .map((q) => `・${esc(q.name)} <span class="${cls(q.change_pct)}">${pct(q.change_pct)}</span>`).join(""));
    $("ai").innerHTML = list.map((q) => q.error
      ? `<div class="stock"><span class="name">${esc(q.name)}</span><span class="muted">無資料</span></div>`
      : `<div class="stock"><div><div class="name">${esc(q.name)} ${staleTag(q)}</div><div class="sub">${esc(q.symbol)} ${num(q.last)}</div><div class="sub">近五天 <span class="${cls(q.chg_5d)}">${pct(q.chg_5d)}</span></div></div>
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
      const big = q.kind === "yield" ? Math.abs(q.change) >= 0.1 : Math.abs(q.change_pct) >= (q.symbol === "^VIX" ? 10 : 2);
      return `<div class="gauge${big ? " big-move" : ""}" title="資料日 ${esc(q.as_of)}">
        <div class="name">${esc(q.name)} ${staleTag(q)}</div>
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

  // 產業鏈訊號：總覽熱力圖 → 值得注意清單 → 各鏈卡片（可展開）
  const LIGHT = { "轉強": "up", "轉弱": "down", "持平": "flat", "資料不足": "na" };
  const TREND = { up: ["▲ 轉強", "up"], flat: ["＝ 持平", "flat"], down: ["▼ 轉弱", "down"] };
  const pp = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
  const SHORT = { "費城半導體": "費半", "台股加權指數": "大盤", "那斯達克": "那指" };
  const short = (n) => SHORT[n] || n || "大盤";
  const code = (sym) => String(sym || "").toUpperCase().replace(/\.(TW|TWO)$/, "");

  // 代表股近一個月等權走勢：每檔先換成「第一天 = 100」再平均
  function basket(stocks) {
    const ss = stocks.map((s) => s.spark).filter((a) => a && a.length > 2);
    if (!ss.length) return null;
    const n = Math.min(...ss.map((a) => a.length));
    return Array.from({ length: n }, (_, i) => ss.reduce((t, a) => t + (a[a.length - n + i] / a[a.length - n]) * 100, 0) / ss.length);
  }

  // 我的持股（「我的資產」用私密連結打開過才有）
  let myHold = null;
  function holdSet() {
    const r = window.HOLDINGS_REPORT;
    if (!r || !r.positions) return null;
    return new Set(r.positions.filter((p) => !p.error).map((p) => code(p.symbol)));
  }
  const heldIn = (c) => (myHold ? (c.stocks || []).filter((s) => myHold.has(code(s.symbol))) : []);

  function chainDetail(c) {
    const up = (c.upstream || []).map((u) => {
      const [word, k] = TREND[u.trend] || ["待更新", "na"];
      const name = u.url ? `<a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.name)}</a>` : esc(u.name);
      return `<li><span class="trend ${k}">${word}</span><div>${name}${u.auto ? ` <span class="auto">自動</span>` : ""}<div class="muted">${esc(u.value)}${u.as_of ? `（${esc(u.as_of)}）` : ""}</div></div></li>`;
    }).join("") || `<li class="muted">還沒有上游訊號</li>`;
    const r = c.revenue || {}, p = c.price || {};
    const mine = new Set(heldIn(c).map((s) => s.symbol));
    const rows = (c.stocks || []).map((s) => s.error
      ? `<tr><td>${esc(s.name)}<div class="muted">${esc(s.symbol)}</div></td><td colspan="4" class="muted">無資料</td></tr>`
      : `<tr${mine.has(s.symbol) ? ` class="mine"` : ""}><td>${esc(s.name)}${mine.has(s.symbol) ? ` <span class="auto">持有</span>` : ""}<div class="muted">${esc(s.symbol)}</div></td>
          <td class="spark-cell">${sparkline(s.spark, { w: 64, h: 20, fill: false })}</td>
          <td class="${cls(s.chg_1m)}">${pct(s.chg_1m)}</td>
          <td><div class="pos"><span style="left:${Math.round((s.range_pos ?? 0.5) * 100)}%"></span></div></td>
          <td class="${cls(s.rev_yoy)}">${s.rev_yoy == null ? "—" : pp(s.rev_yoy)}</td></tr>`).join("");
    const basis = c.basis ? `<span class="basis${c.basis.have < c.basis.total ? " thin" : ""}">燈號依據 ${c.basis.have}/${c.basis.total} 項資料${c.basis.have < c.basis.total ? "，其餘待更新" : ""}</span>` : "";
    return `<div class="why">${(c.why || []).map(esc).join("；")} ${basis}</div>
      <div class="detail-grid">
        <div><h3>① 上游訊號</h3><ul class="upstream">${up}</ul></div>
        <div><h3>② 台股月營收${r.month ? `（${esc(r.month)}）` : ""}</h3>${r.count
          ? `<div class="kv"><span class="muted">年增率中位數</span><b class="${cls(r.avg_yoy)}">${pp(r.avg_yoy)}</b></div>
             <div class="kv"><span class="muted">比今年累計</span><b class="${cls(r.avg_accel)}">${r.avg_accel == null ? "—" : `${r.avg_accel > 0 ? "加速" : "放緩"} ${Math.abs(r.avg_accel).toFixed(1)} 個百分點`}</b></div>
             <div class="kv"><span class="muted">年增為正</span><b>${r.positive} / ${r.count} 家</b></div>`
          : `<div class="muted">這條鏈沒有台股月營收資料。</div>`}
          <h3>③ 股價已反映多少</h3>
          <div class="kv"><span class="muted">代表股近一個月</span><b class="${cls(p.avg_1m)}">${pct(p.avg_1m)}</b></div>
          <div class="kv"><span class="muted">${esc(p.bench_name || p.bench)}</span><b class="${cls(p.bench_1m)}">${pct(p.bench_1m)}</b></div>
          <p class="price-note">${esc(p.note)}</p></div>
      </div>
      <table class="chain-table"><thead><tr><th>代表股</th><th>近一月走勢</th><th>近一月</th><th>一年區間</th><th>營收年增</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function renderBacktest(bt) {
    if (!bt) { $("bt-table").innerHTML = `<div class="muted">下次更新後開始記錄。</div>`; return; }
    $("bt-since").textContent = `從 ${bt.since} 起，已記錄 ${bt.days_logged} 個交易日`;
    const hs = Object.entries(bt.horizons || {});
    const any = hs.some(([, h]) => ["轉強", "持平", "轉弱"].some((l) => (h[l] || {}).n));
    if (!any) {
      const need = Math.max(0, 6 - bt.days_logged);
      const prog = Math.min(100, (bt.days_logged / 6) * 100);
      $("bt-table").innerHTML = `<div class="bt-wait"><div class="bar"><span style="width:${prog}%"></span></div>
        <div class="muted">資料累積中：再 ${need} 個交易日可以看到「1 週後」的結果，約 1 個月後看到「1 個月後」，3 個月後看到「3 個月後」。</div></div>`;
    } else {
      const cell = (x) => !x || !x.n ? `<td class="muted">—</td>`
        : `<td><b class="${cls(x.avg_excess)}">${pp(x.avg_excess)}</b><div class="muted">${x.hit == null ? "" : `命中 ${x.hit}%｜`}${x.n} 次${x.n < 20 ? "｜樣本少，僅供參考" : ""}</div></td>`;
      $("bt-table").innerHTML = `<table class="chain-table bt"><thead><tr><th>燈號亮起後</th>${hs.map(([k]) => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>
        ${["轉強", "持平", "轉弱"].map((l) => `<tr><td><span class="light ${LIGHT[l]}">${l}</span></td>${hs.map(([, h]) => cell(h[l])).join("")}</tr>`).join("")}</tbody></table>`;
    }
    const ch = bt.changes || [];
    $("bt-changes").innerHTML = ch.map((c) => `<li><div>${esc(c.date.slice(5))} <b>${esc(c.name)}</b> ${esc(c.from)} → <span class="${LIGHT[c.to] || "flat"}">${esc(c.to)}</span>
      ${c.excess_since == null ? "" : `<span class="muted">之後</span> <b class="${cls(c.excess_since)}">${pp(c.excess_since)}</b>`}</div></li>`).join("")
      || `<li class="muted">還沒有燈號變化，變化時會列在這裡。</li>`;
  }

  function openChain(id) {
    const el = document.querySelector(`details.chain[data-id="${CSS.escape(id)}"]`);
    if (!el) { chainFilter = "全部"; renderChains(lastSig); return openChain(id); }
    el.open = true;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function watchList(sig) {
    const cs = sig.chains.filter((c) => c.price && c.price.gap != null);
    const item = (c, extra) => `<li><button class="link" data-open="${esc(c.id)}"><b>${esc(c.name)}</b></button>
      <span class="muted">比${esc(short(c.price.bench_name))}</span> <b class="${cls(c.price.gap)}">${pp(c.price.gap)}</b>${extra ? `<div class="muted">${extra}</div>` : ""}</li>`;
    const rev = (c) => (c.revenue || {}).count ? `營收年增 ${pp(c.revenue.avg_yoy)}` : "";
    const lag = cs.filter((c) => c.light === "轉強" && c.price.gap < 0).sort((a, b) => a.price.gap - b.price.gap).slice(0, 5);
    const hot = cs.filter((c) => c.price.gap >= 10).sort((a, b) => b.price.gap - a.price.gap).slice(0, 5);
    const risk = cs.filter((c) => c.light === "轉弱" && c.price.gap > 0).sort((a, b) => b.price.gap - a.price.gap).slice(0, 5);
    const col = (icon, title, tip, list, empty) => `<div class="watch-col"><h3>${icon} ${title}</h3><p class="muted">${tip}</p>
      <ul>${list.length ? list.map((c) => item(c, rev(c))).join("") : `<li class="muted">${empty}</li>`}</ul></div>`;
    let mine = "";
    if (myHold) {
      const hit = sig.chains.map((c) => [c, heldIn(c)]).filter(([, h]) => h.length);
      mine = `<div class="watch-col mine-col"><h3>💼 我的持股在哪些鏈</h3><p class="muted">從「我的資產」對照代表股</p><ul>${hit.length
        ? hit.map(([c, h]) => `<li><button class="link" data-open="${esc(c.id)}"><b>${esc(c.name)}</b></button> <span class="light ${LIGHT[c.light]}">${esc(c.light)}</span><div class="muted">${h.map((s) => esc(s.name)).join("、")}</div></li>`).join("")
        : `<li class="muted">持股都不在這 30 條鏈的代表股裡</li>`}</ul></div>`;
    }
    return col("🔍", "訊號轉強、股價落後", "基本面變好但股價還沒跟上，值得研究原因", lag, "目前沒有")
      + col("🔥", "股價已經先跑", "近一個月比對照指數多漲 10% 以上，好消息可能已反映", hot, "目前沒有")
      + col("⚠️", "轉弱但股價還沒跌", "基本面轉弱、股價卻跑贏大盤，留意風險", risk, "目前沒有") + mine;
  }

  let chainFilter = "全部", lastSig = null;
  function renderChains(sig) {
    if (sig) lastSig = sig;
    sig = lastSig;
    if (!sig || !sig.chains) { $("chains").innerHTML = `<section class="card placeholder">下次更新後就會出現。</section>`; return; }
    myHold = holdSet();
    const counts = {};
    sig.chains.forEach((c) => { counts[c.light] = (counts[c.light] || 0) + 1; });
    const revMonth = sig.chains.map((c) => (c.revenue || {}).month).filter(Boolean).sort().at(-1);
    const asOf = sig.chains.flatMap((c) => c.stocks || []).map((s) => s.as_of).filter(Boolean).sort().at(-1);

    // ① 總覽
    $("chain-stats").innerHTML = ["轉強", "持平", "轉弱"].map((l) => `<button class="stat l-${LIGHT[l]}" data-f="${l}"><b>${counts[l] || 0}</b><span>${l}</span></button>`).join("")
      + `<div class="stat-meta muted">股價資料 ${esc(asOf || "—")}<br>月營收 ${esc(revMonth || "—")}</div>`;
    $("chain-heat").innerHTML = sig.chains.map((c) => {
      const p = c.price || {}, held = heldIn(c).length;
      return `<button class="heat l-${LIGHT[c.light] || "na"}" data-open="${esc(c.id)}" title="${esc(c.name)}：${esc(c.light)}">
        <span class="hn">${esc(c.name)}${held ? " 💼" : ""}</span><span class="hv ${cls(p.avg_1m)}">${pct(p.avg_1m)}</span></button>`;
    }).join("");
    $("chain-watch").innerHTML = watchList(sig);

    // ② 篩選＋各鏈卡片
    const filters = ["全部", "轉強", "持平", "轉弱", "資料不足"].filter((f) => f === "全部" || counts[f]);
    $("chain-filter").innerHTML = filters.map((f) => `<button class="chip${f === chainFilter ? " selected" : ""}" data-f="${f}">${f} <b>${f === "全部" ? sig.chains.length : counts[f]}</b></button>`).join("");
    const list = sig.chains.filter((c) => chainFilter === "全部" || c.light === chainFilter);
    const groups = [...new Set(list.map((c) => c.group || "其他"))];
    $("chains").innerHTML = groups.map((g) => `<h2 class="group-head">${esc(g)}</h2><div class="chain-list">${list.filter((c) => (c.group || "其他") === g).map((c) => {
      const r = c.revenue || {}, p = c.price || {}, b = basket(c.stocks || []);
      const ups = (c.upstream || []).reduce((t, u) => { t[u.trend || "na"] = (t[u.trend || "na"] || 0) + 1; return t; }, {});
      const upTxt = [["up", "▲"], ["down", "▼"], ["flat", "＝"], ["na", "待更新 "]].filter(([k]) => ups[k]).map(([k, s]) => `<span class="${k === "na" ? "muted" : k}">${s}${ups[k]}</span>`).join(" ");
      return `<details class="card chain l-${LIGHT[c.light] || "na"}" data-id="${esc(c.id)}">
        <summary>
          <div class="chain-sum"><b>${esc(c.name)}${heldIn(c).length ? ` <span class="auto">持有</span>` : ""}</b><span class="light ${LIGHT[c.light] || "na"}">${esc(c.light)}</span></div>
          <p class="chain-desc muted">${esc(c.desc)}</p>
          <div class="chain-body">
            <div class="chain-spark">${b ? sparkline(b, { w: 160, h: 44 }) : ""}<span class="muted">代表股近一月</span></div>
            <div class="chain-kpis">
              <div><span class="muted">近一月</span><b class="${cls(p.avg_1m)}">${pct(p.avg_1m)}</b></div>
              <div><span class="muted">比${esc(short(p.bench_name))}</span><b class="${cls(p.gap)}">${p.gap == null ? "—" : pp(p.gap)}</b></div>
              <div><span class="muted">營收年增</span><b class="${cls(r.avg_yoy)}">${r.count ? pp(r.avg_yoy) : "—"}</b></div>
              <div><span class="muted">上游</span><b class="ups">${upTxt || "—"}</b></div>
            </div>
          </div>
        </summary>
        ${chainDetail(c)}</details>`;
    }).join("")}</div>`).join("") || `<section class="card placeholder">沒有符合的產業鏈。</section>`;

    // ③ 本月營收變化
    const ev = sig.revenue_events || [];
    const months = [...new Set(ev.map((e) => e.ym))].sort();
    $("rev-month").textContent = months.length ? `${months.at(-1)}｜共 ${ev.length} 則` : "";
    const order = { turn_up: 0, new_high: 1, turn_down: 2, accel: 3, decel: 4 };
    const sorted = [...ev].sort((a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9));
    const li = (e) => `<li><div>${esc(e.text)}</div></li>`;
    $("rev-events").innerHTML = sorted.slice(0, 8).map(li).join("")
      + (sorted.length > 8 ? `<li><details><summary class="muted">再顯示 ${sorted.length - 8} 則</summary><ul class="newslist">${sorted.slice(8).map(li).join("")}</ul></details></li>` : "")
      || `<li class="muted">這個月追蹤的公司營收沒有明顯變化（由負轉正、明顯加速／放緩、創新高）。</li>`;

    document.querySelectorAll("#tab-chains [data-f]").forEach((b) => b.addEventListener("click", () => {
      chainFilter = b.dataset.f; renderChains();
      if (b.classList.contains("stat")) $("chain-filter").scrollIntoView({ behavior: "smooth", block: "start" });
    }));
    document.querySelectorAll("#tab-chains [data-open]").forEach((b) => b.addEventListener("click", () => openChain(b.dataset.open)));
  }
  window.addEventListener("holdings:report", () => renderChains());

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

  // 卡片可以收合（點標題），記住每張卡片的狀態；手機預設先收起全球股市與美國 AI 股
  // 手機預設收起；ALWAYS_FOLD 不論桌機手機都先收起（很長、平常不必看）
  const FOLD_DEFAULT = { "global-card": true, "ai-card": true, "gauge-card": true };
  const ALWAYS_FOLD = { "pt-trades-card": true, "pt-history-card": true };
  const narrow = () => window.matchMedia("(max-width: 759px)").matches;
  let folds = {};
  try { folds = JSON.parse(localStorage.getItem("folds") || "{}"); } catch (e) { /* 無痕模式 */ }
  document.querySelectorAll(".card[data-fold]").forEach((card) => {
    const key = card.dataset.fold;
    const head = card.querySelector(".card-head");
    const apply = (on) => { card.classList.toggle("folded", on); head.setAttribute("aria-expanded", String(!on)); };
    apply(key in folds ? folds[key] : !!ALWAYS_FOLD[key] || (narrow() && !!FOLD_DEFAULT[key]));
    head.setAttribute("role", "button");
    head.tabIndex = 0;
    const toggle = () => {
      const on = !card.classList.contains("folded");
      apply(on);
      folds[key] = on;
      try { localStorage.setItem("folds", JSON.stringify(folds)); } catch (e) { /* 無痕模式 */ }
    };
    head.addEventListener("click", toggle);
    head.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
  });

  // 分頁切換，記住上次看的頁籤
  function showTab(name) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".tabpane").forEach((p) => { p.hidden = p.id !== `tab-${name}`; });
    document.body.dataset.tab = name;
    try { localStorage.setItem("tab", name); } catch (e) { /* 無痕模式 */ }
  }
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  try { const saved = localStorage.getItem("tab"); if (saved && $(`tab-${saved}`)) showTab(saved); } catch (e) { /* 無痕模式 */ }

  fetch(`data/latest.json?t=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(render)
    .catch(() => { $("headline").textContent = "早報資料讀取失敗，請稍後再試。"; });
})();
