// 我的資產：讀 data/private/holdings.json（只在自己電腦上有，不會上傳到 GitHub Pages）。
(function () {
  "use strict";
  const root = document.getElementById("tab-assets");
  if (!root) return;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cls = (v) => (v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat");
  const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}%`);
  const num = (v, d = 2) => (v == null ? "—" : Number(v).toLocaleString("zh-TW", { maximumFractionDigits: d }));
  const twd = (v) => (v == null ? "—" : `${Math.round(v).toLocaleString("zh-TW")}`);
  const signed = (v) => (v == null ? "—" : `<span class="${cls(v)}">${v > 0 ? "+" : ""}${twd(v)}</span>`);
  const LABEL = { TW: "台股", US: "美股" };
  const STATUS = { "仍成立": "ok", "需留意": "warn", "無法判斷": "na", "未填理由": "na" };

  function line(values, w = 600, h = 140) {
    if (!values || values.length < 2) return "";
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const d = values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * w).toFixed(1)} ${(h - 2 - ((v - lo) / span) * (h - 4)).toFixed(1)}`).join("");
    const color = `var(--${values.at(-1) >= values[0] ? "up" : "down"})`;
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}L${w} ${h}L0 ${h}Z" fill="${color}" opacity="0.12"/><path d="${d}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function bars(groups, label = (g) => esc(g.key)) {
    return `<div class="a-bars">${groups.map((g) => `
      <div class="a-bar${g.over_limit ? " over" : ""}">
        <span class="a-bar-name" title="${esc(g.key)}">${label(g)}</span>
        <span class="a-bar-track"><span style="width:${Math.min(100, g.weight_pct || 0)}%"></span></span>
        <span class="a-bar-val">${num(g.weight_pct, 1)}%${g.over_limit ? '<em class="a-badge">超過上限</em>' : ""}</span>
      </div>`).join("")}</div>`;
  }

  function summaryCard(r) {
    const t = r.totals, a = r.analysis;
    const tiles = [
      ["總市值", `${twd(t.value_twd)} 元`, ""],
      ["今日損益", signed(t.day_pnl_twd), ""],
      ["未實現損益", signed(t.unrealized_twd), `<span class="${cls(t.unrealized_pct)}">${pct(t.unrealized_pct)}</span>`],
      ["已實現＋股息", signed(t.realized_twd + t.dividends_twd), `今年股息 ${twd(t.dividends_this_year_twd)}`],
    ];
    return `<section class="card a-wide">
      <div class="card-head"><h2>資產總覽</h2><span class="muted">台幣計價｜更新於 ${esc(r.generated_at.replace("T", " "))}</span></div>
      <div class="a-tiles">${tiles.map(([k, v, s]) => `<div><span class="muted">${k}</span><b>${v}</b><span class="muted">${s}</span></div>`).join("")}</div>
      ${t.pnl_from_fx_twd ? `<p class="muted">美股部位的損益中，匯率貢獻 ${signed(t.pnl_from_fx_twd)} 元</p>` : ""}
      ${a ? `<div class="a-ai"><b>${esc(a.headline)}</b><p>${esc(a.overview)}</p></div>` : `<p class="muted">還沒有 AI 健檢（執行時加上 ANTHROPIC_API_KEY 才會產生）。</p>`}
    </section>`;
  }

  function alertsCard(a) {
    if (!a || !(a.news_alerts || []).length) return "";
    const dir = { "偏多": "up", "偏空": "down", "中性": "flat" };
    return `<section class="card a-wide">
      <div class="card-head"><h2>今天碰到你持股的新聞</h2><span class="muted">AI 依今日早報整理，只是提醒</span></div>
      <ul class="a-alerts">${a.news_alerts.map((n) => `<li><b>${esc(n.symbol)}</b> <span class="${dir[n.direction] || "flat"}">${esc(n.direction)}</span>　${esc(n.reason)}</li>`).join("")}</ul>
    </section>`;
  }

  function tableCard(r, account) {
    const notes = {};
    (r.analysis?.positions || []).forEach((p) => { notes[p.symbol] = p; });
    const weight = {};
    r.allocation.by_symbol.forEach((g) => { weight[g.key] = g; });
    const total = r.totals.value_twd || 1;
    const accounts = [...new Set(r.positions.map((p) => p.account))];
    const rows = r.positions.filter((p) => account === "全部" || p.account === account);
    const body = rows.map((p) => {
      if (p.error) return `<tr><td><b>${esc(p.name || p.symbol)}</b><div class="muted">${esc(p.symbol)}</div></td><td colspan="8" class="muted">${esc(p.error)}</td></tr>`;
      const n = notes[p.symbol];
      const over = weight[p.symbol]?.over_limit;
      const fx = p.pnl_from_fx_twd != null ? `<div class="muted">股價 ${signed(p.pnl_from_price_twd)}／匯率 ${signed(p.pnl_from_fx_twd)}</div>` : "";
      return `<tr>
        <td><b>${esc(p.name || p.symbol)}</b><div class="muted">${esc(p.symbol)}｜${esc(p.account)}</div></td>
        <td class="n">${num(p.shares, 4)}<div class="muted">成本 ${num(p.avg_cost)}</div></td>
        <td class="n">${num(p.price)}<div class="${cls(p.day_change_pct)}">${pct(p.day_change_pct)}</div></td>
        <td class="n">${twd(p.value_twd)}</td>
        <td class="n">${signed(p.pnl_twd)}${fx}</td>
        <td class="n"><span class="${cls(p.return_twd_pct)}">${pct(p.return_twd_pct)}</span><div class="muted">${p.annualized_pct != null ? `年化 ${pct(p.annualized_pct)}` : p.holding_days != null ? `持有 ${p.holding_days} 天` : ""}</div></td>
        <td class="n${over ? " a-over" : ""}">${num((p.value_twd / total) * 100, 1)}%</td>
        <td class="a-thesis">${p.thesis ? esc(p.thesis) : '<span class="muted">（未填）</span>'}
          ${n ? `<div><span class="a-status ${STATUS[n.thesis_status] || "na"}">${esc(n.thesis_status)}</span> ${esc(n.comment)}</div>` : ""}</td>
      </tr>`;
    }).join("");
    const opts = ["全部", ...accounts].map((x) => `<option${x === account ? " selected" : ""}>${esc(x)}</option>`).join("");
    return `<section class="card a-wide">
      <div class="card-head"><h2>持股明細</h2><label class="muted">帳戶 <select id="a-account">${opts}</select></label></div>
      <div class="a-scroll"><table class="a-table">
        <thead><tr><th>名稱</th><th class="n">股數</th><th class="n">現價</th><th class="n">市值</th><th class="n">損益</th><th class="n">報酬</th><th class="n">占比</th><th>投資理由與 AI 檢查</th></tr></thead>
        <tbody>${body}</tbody></table></div>
      <p class="muted">市值、損益都換算成台幣；占比是占全部資產。修改持股請編輯 private/holdings.csv 後重新執行 python -m holdings。</p>
    </section>`;
  }

  function allocCard(r) {
    const a = r.allocation, c = a.concentration;
    return `<section class="card">
      <div class="card-head"><h2>資產配置與集中度</h2><span class="muted">單一持股上限 ${num(c.position_limit_pct, 0)}%、產業 ${num(c.sector_limit_pct, 0)}%</span></div>
      <div class="a-tiles small">
        <div><span class="muted">最大一檔</span><b>${num(c.top1_pct, 1)}%</b></div>
        <div><span class="muted">前三檔</span><b>${num(c.top3_pct, 1)}%</b></div>
        <div><span class="muted">相當於平均分散在</span><b>${num(c.effective_n, 1)} 檔</b></div>
      </div>
      ${r.analysis?.concentration ? `<p>${esc(r.analysis.concentration)}</p>` : ""}
      <h3>個股</h3>${bars(a.by_symbol, (g) => esc(g.name || g.key))}
      <h3>產業</h3>${bars(a.by_sector)}
      <div class="a-two"><div><h3>市場</h3>${bars(a.by_market, (g) => esc(LABEL[g.key] || g.key))}</div><div><h3>幣別</h3>${bars(a.by_currency)}</div></div>
    </section>`;
  }

  function riskCard(r) {
    const k = r.risk;
    if (!k || !k.series) return "";
    const rows = [["我的持股", k.return_pct, k.max_drawdown_pct], ...k.benchmarks.map((b) => [b.name, b.return_pct, b.max_drawdown_pct])];
    return `<section class="card">
      <div class="card-head"><h2>與大盤比較</h2><span class="muted">${esc(k.from)} 到 ${esc(k.to)}</span></div>
      <div class="chart">${line(k.series.value_twd)}</div>
      <table class="a-table compact"><thead><tr><th></th><th class="n">一年報酬</th><th class="n">最大回撤</th></tr></thead>
        <tbody>${rows.map(([n, ret, dd]) => `<tr><td>${esc(n)}</td><td class="n ${cls(ret)}">${pct(ret)}</td><td class="n">${pct(dd)}</td></tr>`).join("")}</tbody></table>
      <p class="muted">對台股大盤的 beta ${num(k.beta)}（1 代表和大盤同步，越大波動越大）；年化波動 ${pct(k.volatility_pct).replace("+", "")}。${esc(k.note)}。</p>
    </section>`;
  }

  function scenarioCard(r) {
    const s = r.risk?.scenarios;
    if (!s || !s.length) return "";
    return `<section class="card">
      <div class="card-head"><h2>情境試算</h2><span class="muted">程式估算，不是預測</span></div>
      <ul class="a-scen">${s.map((x) => x.error ? `<li>${esc(x.name)}<span class="muted">${esc(x.error)}</span></li>` : `
        <li><div>${esc(x.name)}<div class="muted">${(x.worst || []).length ? "影響最大：" + x.worst.map((w) => `${esc(w.symbol)}（beta ${num(w.beta)}）`).join("、") : esc(x.method)}</div></div>
          <b>${signed(x.est_change_twd)}<div class="${cls(x.est_change_pct)}">${pct(x.est_change_pct)}</div></b></li>`).join("")}</ul>
      ${(r.analysis?.watch_items || []).length ? `<h3>接下來留意</h3><ul class="a-watch">${r.analysis.watch_items.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
    </section>`;
  }

  function render(r, account = "全部") {
    const warn = (r.warnings || []).map((w) => `<div class="a-warn">${esc(w)}</div>`).join("");
    root.innerHTML = `${warn}<div class="grid">${summaryCard(r)}${alertsCard(r.analysis)}${tableCard(r, account)}${allocCard(r)}${riskCard(r)}${scenarioCard(r)}</div>
      <p class="muted a-foot">持股資料只存在你自己的電腦。AI 健檢只拿到占比、報酬率、產業與投資理由，不含帳戶與金額。僅供參考，不構成投資建議。${r.analysis?.model ? `｜模型 ${esc(r.analysis.model)}` : ""}</p>`;
    const sel = document.getElementById("a-account");
    if (sel) sel.addEventListener("change", () => render(r, sel.value));
  }

  function empty() {
    root.innerHTML = `<section class="card placeholder a-empty">
      <h2>還沒有持股資料</h2>
      <p>持股是私人資料，只在你自己的電腦上產生，不會出現在公開網站。</p>
      <ol>
        <li>把 <code>holdings/examples/holdings.example.csv</code> 複製到 <code>private/holdings.csv</code>，改成你的持股（可以用 Excel 編輯）</li>
        <li>執行 <code>python -m holdings</code></li>
        <li>在 <code>site</code> 資料夾執行 <code>python -m http.server 8000</code>，打開 http://localhost:8000</li>
      </ol></section>`;
  }

  fetch("data/private/holdings.json", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
    .then((r) => render(r))
    .catch(empty);
})();
