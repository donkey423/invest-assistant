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
  let MODE = "local"; // local：讀自己電腦上的檔案；cloud：Supabase 登入
  const STATUS = { "仍成立": "ok", "需留意": "warn", "無法判斷": "na", "未填理由": "na" };

  function line(values, w = 600, h = 140) {
    if (!values || values.length < 2) return "";
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const d = values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * w).toFixed(1)} ${(h - 2 - ((v - lo) / span) * (h - 4)).toFixed(1)}`).join("");
    const color = `var(--${values.at(-1) >= values[0] ? "up" : "down"}-mark)`;
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}L${w} ${h}L0 ${h}Z" fill="${color}" opacity="0.12"/><path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function bars(groups, label = (g) => esc(g.key)) {
    return `<div class="a-bars">${groups.map((g) => `
      <div class="a-bar${g.over_limit ? " over" : ""}">
        <span class="a-bar-name" title="${esc(g.key)}">${label(g)}</span>
        <span class="a-bar-track"><span style="width:${Math.min(100, g.weight_pct || 0)}%"></span></span>
        <span class="a-bar-val">${num(g.weight_pct, 1)}%${g.over_limit ? '<em class="a-badge">超過上限</em>' : ""}</span>
      </div>`).join("")}</div>`;
  }

  // ---------- 版面：一眼看懂 → 要注意什麼 → 每一檔 → 配置與風險 ----------
  const CAT = ["var(--cat1)", "var(--cat2)", "var(--cat3)", "var(--cat4)", "var(--cat5)", "var(--cat6)", "var(--cat7)"];
  const pctOf = (a, b) => (b ? (a / b) * 100 : null);
  const money = (v) => (v == null ? "—" : `<span class="${cls(v)}">${v > 0 ? "+" : v < 0 ? "−" : ""}${twd(Math.abs(v))}</span>`);
  const pctTag = (v) => `<span class="a-pct ${cls(v)}">${v == null ? "—" : `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(2)}%`}</span>`;

  // 依市值排序的配置色：同一檔在比例條、明細列用同一個顏色
  function colorMap(r) {
    const m = {};
    [...r.allocation.by_symbol].sort((a, b) => (b.weight_pct || 0) - (a.weight_pct || 0))
      .forEach((g, i) => { m[g.key] = i < CAT.length - 1 ? CAT[i] : CAT[CAT.length - 1]; });
    return m;
  }

  function stackBar(r, colors) {
    const groups = [...r.allocation.by_symbol].sort((a, b) => (b.weight_pct || 0) - (a.weight_pct || 0));
    const seg = groups.map((g) => `<span style="flex:${g.weight_pct || 0};background:${colors[g.key]}" title="${esc(g.name || g.key)} ${num(g.weight_pct, 1)}%"></span>`).join("");
    const legend = groups.map((g) => `<li><i style="background:${colors[g.key]}"></i>${esc(g.name || g.key)}<b>${num(g.weight_pct, 1)}%</b></li>`).join("");
    return `<div class="a-stack" role="img" aria-label="各檔占比">${seg}</div><ul class="a-legend">${legend}</ul>`;
  }

  function heroCard(r, colors) {
    const t = r.totals, k = r.risk;
    const prev = (t.value_twd || 0) - (t.day_pnl_twd || 0);
    const total = t.total_pnl_twd ?? (t.unrealized_twd + (t.realized_twd || 0) + (t.dividends_twd || 0));
    const stats = [
      ["今日", money(t.day_pnl_twd), pctTag(pctOf(t.day_pnl_twd, prev))],
      ["總損益", money(total), pctTag(pctOf(total, t.cost_twd))],
      ["帳上未實現", money(t.unrealized_twd), pctTag(t.unrealized_pct)],
    ];
    const bench = k?.benchmarks?.[0];
    const trend = k?.series ? `<div class="a-trend">
        <div class="a-trend-head"><span class="muted">近一年</span>${pctTag(k.return_pct)}${bench ? `<span class="muted">${esc(bench.name)} ${pct(bench.return_pct)}</span>` : ""}</div>
        <div class="chart">${line(k.series.value_twd, 600, 120)}</div></div>` : "";
    const extra = [
      `投入成本 ${twd(t.cost_twd)} 元`,
      t.realized_twd ? `已實現 ${money(t.realized_twd)}` : "",
      t.dividends_twd ? `股息 ${twd(t.dividends_twd)}（今年 ${twd(t.dividends_this_year_twd)}）` : "",
      t.pnl_from_fx_twd ? `匯率影響 ${money(t.pnl_from_fx_twd)}` : "",
    ].filter(Boolean).join("<span class=\"a-dot\">·</span>");
    return `<section class="card a-wide a-hero">
      <div class="a-hero-main">
        <div>
          <span class="muted">我的總資產（台幣）· ${t.positions} 檔 · ${esc(r.generated_at.slice(5, 16).replace("T", " ").replace("-", "/"))} 更新</span>
          <div class="a-total">${twd(t.value_twd)}<small>元</small></div>
          <div class="a-stats">${stats.map(([k2, v, p]) => `<div><span class="muted">${k2}</span><b>${v}</b>${p}</div>`).join("")}</div>
        </div>${trend}
      </div>
      ${stackBar(r, colors)}
      <p class="muted a-extra">${extra}</p>
      ${r.analysis ? `<p class="a-ai"><b>${esc(r.analysis.headline)}</b> ${esc(r.analysis.overview)}</p>` : ""}
    </section>`;
  }

  // 要注意：只列真正需要處理的（超過上限、轉弱、碰到新聞），其餘收起來
  const HLIGHT = { "轉強": "up", "轉弱": "down", "持平": "flat", "資料不足": "flat" };
  function attentionCard(r) {
    const h = r.health, a = r.analysis;
    const items = (h?.items || []);
    const must = items.filter((i) => i.level === "warn" || i.level === "bad");
    const rest = items.filter((i) => !(i.level === "warn" || i.level === "bad"));
    const dir = { "偏多": "up", "偏空": "down", "中性": "flat" };
    const news = (a?.news_alerts || []).map((n) => `<li class="a-n"><b>${esc(n.symbol)}</b> <span class="${dir[n.direction] || "flat"}">${esc(n.direction)}</span> ${esc(n.reason)}</li>`).join("");
    const watch = (a?.watch_items || []).map((w) => `<li class="a-n">${esc(w)}</li>`).join("");
    const list = must.map((i) => `<li class="a-${esc(i.level)}">${esc(i.text)}</li>`).join("") + news + watch;
    const rows = (h?.chain_exposure || []).map((e) => `<tr><td><b>${esc(e.name)}</b> <span class="muted">${e.holdings.map((x) => esc(x.name)).join("、")}</span></td>
        <td><span class="light ${HLIGHT[e.light] || "flat"}">${esc(e.light || "—")}</span></td><td class="n">${num(e.weight_pct, 1)}%</td></tr>`).join("");
    const more = rest.length || rows ? `<details class="a-more"><summary>產業鏈燈號與其他觀察</summary>
        ${h ? `<p class="muted">在轉強產業鏈 ${num(h.strong_pct, 1)}%・轉弱 ${num(h.weak_pct, 1)}%・對不到產業鏈 ${num(h.unmapped_pct, 1)}%${h.signals_at ? `（燈號 ${esc(h.signals_at.slice(5, 16).replace("T", " "))}）` : ""}</p>` : ""}
        ${rest.length ? `<ul class="a-list-plain">${rest.map((i) => `<li>${esc(i.text)}</li>`).join("")}</ul>` : ""}
        ${rows ? `<table class="a-table compact"><thead><tr><th>產業鏈（我的持股）</th><th>燈號</th><th class="n">占資產</th></tr></thead><tbody>${rows}</tbody></table>
        <p class="muted">一檔可能屬於多條鏈，占比加總可能超過 100%。燈號來自「產業鏈訊號」分頁。</p>` : ""}
      </details>` : "";
    if (!list && !more) return "";
    return `<section class="card a-wide a-attn">
      <div class="card-head"><h2>要注意</h2><span class="muted">${list ? `${must.length + (a?.news_alerts || []).length + (a?.watch_items || []).length} 件` : "目前沒有需要處理的事"}</span></div>
      ${list ? `<ul class="a-attn-list">${list}</ul>` : ""}${more}
    </section>`;
  }

  function holdingsCard(r, account, colors) {
    const notes = {};
    (r.analysis?.positions || []).forEach((p) => { notes[p.symbol] = p; });
    const total = r.totals.value_twd || 1;
    const accounts = [...new Set(r.positions.map((p) => p.account))];
    const rows = r.positions.filter((p) => account === "全部" || p.account === account)
      .sort((a, b) => (b.value_twd || 0) - (a.value_twd || 0));
    const over = {};
    r.allocation.by_symbol.forEach((g) => { over[g.key] = g.over_limit; });
    const body = rows.map((p) => {
      if (p.error) return `<li class="a-pos"><div class="a-pos-name"><b>${esc(p.name || p.symbol)}</b><span class="muted">${esc(p.symbol)}</span></div><div class="muted a-pos-err">${esc(p.error)}</div></li>`;
      const w = (p.value_twd / total) * 100, n = notes[p.symbol];
      const fx = p.pnl_from_fx_twd != null ? `股價 ${money(p.pnl_from_price_twd)}／匯率 ${money(p.pnl_from_fx_twd)}` : "";
      const sub = [`${num(p.shares, 4)} 股`, `成本 ${num(p.avg_cost)}`, `現價 ${num(p.price)}`, p.account,
        p.holding_days != null ? `持有 ${p.holding_days} 天` : ""].filter(Boolean).join("・");
      const thesis = p.thesis || n ? `<div class="a-pos-why">${p.thesis ? esc(p.thesis) : '<span class="muted">未填投資理由</span>'}${n ? ` <span class="a-status ${STATUS[n.thesis_status] || "na"}">${esc(n.thesis_status)}</span> <span class="muted">${esc(n.comment)}</span>` : ""}</div>` : "";
      return `<li class="a-pos">
        <div class="a-pos-name"><i style="background:${colors[p.symbol] || CAT[6]}"></i><b>${esc(p.name || p.symbol)}</b><span class="muted">${esc(p.symbol)}</span></div>
        <div class="a-pos-val"><b>${twd(p.value_twd)}</b><span class="muted a-wv${over[p.symbol] ? " a-over" : ""}">占 ${num(w, 1)}%${over[p.symbol] ? " 超過上限" : ""}</span></div>
        <div class="a-pos-day"><span class="muted a-w${over[p.symbol] ? " a-over" : ""}">占 ${num(w, 1)}%・</span><span class="muted">今日</span>${pctTag(p.day_change_pct)}</div>
        <div class="a-pos-pnl"><b>${money(p.pnl_twd)}</b>${pctTag(p.return_twd_pct)}</div>
        <div class="a-pos-sub muted">${esc(sub)}${fx ? `・${fx}` : ""}</div>
        ${thesis}
      </li>`;
    }).join("");
    const chips = accounts.length > 1 ? `<div class="chips a-acct">${["全部", ...accounts].map((x) => `<button class="chip${x === account ? " selected" : ""}" data-acct="${esc(x)}">${esc(x)}</button>`).join("")}</div>` : "";
    return `<section class="card a-wide">
      <div class="card-head"><h2>每一檔持股</h2><span class="muted">依市值排序，金額都換算成台幣</span></div>
      ${chips}<div class="a-pos a-pos-head muted"><div>名稱</div><div>市值・占比</div><div>今日漲跌</div><div>損益・報酬率</div></div><ul class="a-pos-list">${body}</ul>
      ${MODE === "cloud" ? "" : '<p class="muted">修改持股請編輯 private/holdings.csv 後重新執行 python -m holdings。</p>'}
    </section>`;
  }

  function allocCard(r) {
    const a = r.allocation, c = a.concentration;
    return `<section class="card">
      <div class="card-head"><h2>配置與集中度</h2><span class="muted">上限：單檔 ${num(c.position_limit_pct, 0)}%、產業 ${num(c.sector_limit_pct, 0)}%</span></div>
      <div class="a-tiles small">
        <div><span class="muted">最大一檔</span><b>${num(c.top1_pct, 1)}%</b></div>
        <div><span class="muted">前三檔</span><b>${num(c.top3_pct, 1)}%</b></div>
        <div><span class="muted">等於分散在</span><b>${num(c.effective_n, 1)} 檔</b></div>
      </div>
      ${r.analysis?.concentration ? `<p>${esc(r.analysis.concentration)}</p>` : ""}
      <h3>產業</h3>${bars(a.by_sector)}
      <div class="a-two"><div><h3>市場</h3>${bars(a.by_market, (g) => esc(LABEL[g.key] || g.key))}</div><div><h3>幣別</h3>${bars(a.by_currency)}</div></div>
    </section>`;
  }

  function riskCard(r) {
    const k = r.risk;
    if (!k || !k.series) return "";
    const rows = [["我的持股", k.return_pct, k.max_drawdown_pct], ...k.benchmarks.map((b) => [b.name, b.return_pct, b.max_drawdown_pct])];
    return `<section class="card">
      <div class="card-head"><h2>和大盤比</h2><span class="muted">${esc(k.from)} 到 ${esc(k.to)}</span></div>
      <table class="a-table compact"><thead><tr><th></th><th class="n">一年報酬</th><th class="n">最大回撤</th></tr></thead>
        <tbody>${rows.map(([n, ret, dd]) => `<tr><td>${esc(n)}</td><td class="n ${cls(ret)}">${pct(ret)}</td><td class="n">${pct(dd)}</td></tr>`).join("")}</tbody></table>
      <p class="muted">beta ${num(k.beta)}（1＝和台股大盤同步，越大波動越大）・年化波動 ${pct(k.volatility_pct).replace("+", "")}。${esc(k.note)}。</p>
    </section>`;
  }

  function scenarioCard(r) {
    const s = r.risk?.scenarios;
    if (!s || !s.length) return "";
    return `<section class="card">
      <div class="card-head"><h2>如果大跌，我會少多少</h2><span class="muted">程式估算，不是預測</span></div>
      <ul class="a-scen">${s.map((x) => x.error ? `<li>${esc(x.name)}<span class="muted">${esc(x.error)}</span></li>` : `
        <li><div>${esc(x.name)}<div class="muted">${(x.worst || []).length ? "影響最大：" + x.worst.map((w) => esc(w.symbol)).join("、") : esc(x.method)}</div></div>
          <b>${money(x.est_change_twd)}<div class="${cls(x.est_change_pct)}">${pct(x.est_change_pct)}</div></b></li>`).join("")}</ul>
    </section>`;
  }

  function reportHtml(r, account) {
    if (!r) return "";
    const colors = colorMap(r);
    const warn = (r.warnings || []).map((w) => `<div class="a-warn">${esc(w)}</div>`).join("");
    const where = MODE === "cloud" ? "持股存在你的 Supabase 資料庫，只有用私密連結打開過的裝置看得到。" : "持股資料只存在你自己的電腦。";
    return `${warn}<div class="grid a-grid">${heroCard(r, colors)}${attentionCard(r)}${holdingsCard(r, account, colors)}${allocCard(r)}${riskCard(r)}${scenarioCard(r)}</div>
      <p class="muted a-foot">${where}AI 健檢只拿到占比、報酬率、產業與投資理由，不含帳戶與金額。僅供參考，不構成投資建議。${r.analysis?.model ? `｜模型 ${esc(r.analysis.model)}` : ""}</p>`;
  }

  function bindAccount(r, rerender) {
    root.querySelectorAll("[data-acct]").forEach((b) => b.addEventListener("click", () => rerender(b.dataset.acct)));
  }

  // 早報頁最上面放一條「我的資產」摘要，點了直接跳到資產頁（只在這台已記住私密連結的裝置上出現）
  function briefStrip(r) {
    const host = document.getElementById("tab-brief");
    if (!host || !r) return;
    let el = document.getElementById("my-strip");
    if (!el) {
      el = document.createElement("button");
      el.id = "my-strip"; el.className = "my-strip"; el.type = "button";
      el.addEventListener("click", () => { document.querySelector('.tab[data-tab="assets"]')?.click(); window.scrollTo(0, 0); });
      host.prepend(el);
    }
    const t = r.totals, prev = (t.value_twd || 0) - (t.day_pnl_twd || 0);
    const total = t.total_pnl_twd ?? t.unrealized_twd;
    el.innerHTML = `<span class="muted">我的資產</span><b>${twd(t.value_twd)}</b>
      <span><span class="muted">今日</span> ${money(t.day_pnl_twd)} ${pctTag(pctOf(t.day_pnl_twd, prev))}</span>
      <span><span class="muted">總損益</span> ${money(total)} ${pctTag(pctOf(total, t.cost_twd))}</span><span class="my-go">看明細 ›</span>`;
  }

  function render(r, account = "全部") {
    // 讓「產業鏈訊號」分頁標出持股所在的產業鏈（只在這台瀏覽器裡，不會送出去）
    if (window.HOLDINGS_REPORT !== r) { window.HOLDINGS_REPORT = r; window.dispatchEvent(new Event("holdings:report")); }
    briefStrip(r);
    root.innerHTML = reportHtml(r, account);
    bindAccount(r, (a) => render(r, a));
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

  function localMode() {
    fetch("data/private/holdings.json", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((r) => render(r))
      .catch(empty);
  }

  // ---------------- 雲端模式：私密連結（不用帳號密碼） ----------------
  // 你的私密連結長這樣：https://…/invest-assistant/#k=一長串密碼
  // 「#」後面的部分瀏覽器不會送到任何伺服器；打開一次後存在這台裝置，之後直接開網站就好。
  // 資料庫只透過 vault_* 函式回應，金鑰不對就什麼都拿不到；資料表本身對外完全不開放。
  const KKEY = "invest-assistant-key";
  let cfg, vkey;
  const loadKey = () => { try { return localStorage.getItem(KKEY); } catch (e) { return null; } };
  const saveKey = (k) => { vkey = k; try { k ? localStorage.setItem(KKEY, k) : localStorage.removeItem(KKEY); } catch (e) { /* 無痕模式 */ } };

  async function rpc(fn, args) {
    const res = await fetch(`${cfg.url.replace(/\/$/, "")}/rest/v1/rpc/${fn}`, {
      method: "POST", headers: { apikey: cfg.key, "Content-Type": "application/json" },
      body: JSON.stringify({ k: vkey, ...args }) });
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) {
      const msg = data?.message || `HTTP ${res.status}`;
      if (msg === "invalid key") { saveKey(null); showNoKey("這條私密連結已經失效，請用新的連結打開。"); }
      throw new Error(msg);
    }
    return data;
  }

  function showNoKey(msg = "") {
    root.innerHTML = `<section class="card a-login">
      <h2>我的資產</h2>
      <p>這一頁只給你自己看。請用你的<b>私密連結</b>打開一次，這台裝置就會記住，之後直接開網站即可。</p>
      ${msg ? `<p class="a-msg">${esc(msg)}</p>` : ""}
    </section>`;
  }

  const FIELDS = [
    ["symbol", "代號", "text", "2330、0050、NVDA；上櫃寫 6488.TWO", true],
    ["name", "名稱", "text", "台積電", false],
    ["shares", "股數", "number", "1000", true],
    ["avg_cost", "每股成本", "number", "台股填台幣、美股填美元", true],
    ["buy_date", "買入日期", "date", "", false],
    ["account", "帳戶", "text", "永豐、複委託", false],
    ["sector", "產業", "text", "半導體、ETF、金融", false],
    ["fx_cost", "買入匯率", "number", "美股才填，例如 32.5", false],
    ["thesis", "投資理由", "textarea", "為什麼買？Claude 健檢時會檢查理由是否還成立", false],
  ];
  const isTW = (sym) => /^\d{4,6}[A-Z]?(\.TWO?)?$/i.test(sym || "");

  function holdingForm(h = {}, lists = {}) {
    const field = ([k, label, type, ph, req]) => {
      const v = h[k] ?? "";
      const attrs = `name="${k}" ${req ? "required" : ""} placeholder="${esc(ph)}"`;
      const input = type === "textarea" ? `<textarea ${attrs} rows="2" maxlength="500">${esc(v)}</textarea>`
        : `<input type="${type}" ${attrs} value="${esc(v)}" ${type === "number" ? 'step="any" min="0" inputmode="decimal"' : ""}
            ${k === "symbol" ? 'autocapitalize="characters" autocomplete="off"' : ""} ${lists[k] ? `list="a-list-${k}"` : ""}>`;
      return `<label class="a-f-${k}">${label}${req ? " *" : ""}${input}</label>`;
    };
    const dl = Object.entries(lists).map(([k, vals]) => `<datalist id="a-list-${k}">${vals.map((v) => `<option value="${esc(v)}">`).join("")}</datalist>`).join("");
    return `<form class="a-form a-holding-form" data-id="${h.id ?? ""}">${FIELDS.map(field).join("")}${dl}
      <div class="a-actions"><button class="a-btn primary" type="submit">${h.id ? "儲存" : "新增"}</button>
      <button class="a-btn" type="button" data-cancel>取消</button>
      ${h.id ? '<button class="a-btn danger" type="button" data-delete>刪除這筆</button>' : ""}</div>
      <p class="a-msg"></p></form>`;
  }

  function manageCard(holdings, report, open) {
    const valued = new Set((report?.positions || []).filter((p) => !p.error).map((p) => `${p.symbol}|${p.account}`));
    const items = holdings.map((h) => {
      const key = `${String(h.symbol).toUpperCase()}|${h.account || "未指定"}`;
      return open === h.id ? `<li class="a-editing">${holdingForm(h, listsOf(holdings))}</li>`
        : `<li><button class="a-row" data-edit="${h.id}">
            <span><b>${esc(h.name || h.symbol)}</b> <span class="muted">${esc(h.symbol)}${h.account ? "｜" + esc(h.account) : ""}</span></span>
            <span class="n">${num(h.shares, 4)} 股 @ ${num(h.avg_cost)}${valued.has(key) ? "" : '<em class="a-badge">待計算</em>'}</span></button></li>`;
    }).join("");
    return `<section class="card a-wide a-manage">
      <div class="card-head"><h2>新增或修改持股</h2><span class="muted">這台裝置已記住你的私密連結　<button class="a-link" data-logout>忘記這台裝置</button></span></div>
      ${open === "new" ? holdingForm({}, listsOf(holdings)) : `<button class="a-btn primary a-add" data-new>＋ 新增持股</button>`}
      ${holdings.length ? `<ul class="a-list">${items}</ul>` : '<p class="muted">還沒有持股，按上面的按鈕新增第一筆。</p>'}
      <p class="muted">點一筆可以修改或刪除。損益與分析在每天自動計算時更新（台股收盤後與美股收盤後）。</p>
    </section>`;
  }

  function listsOf(holdings) {
    const uniq = (k) => [...new Set(holdings.map((h) => h[k]).filter(Boolean))];
    return { account: uniq("account"), sector: uniq("sector") };
  }

  async function cloudHome(open = null, account = "全部") {
    if (!vkey) return showNoKey();
    let data;
    try { data = await rpc("vault_data", {}); }
    catch (err) { if (vkey) root.innerHTML = `<section class="card a-warn">讀取失敗：${esc(err.message)}</section>`; return; }
    const holdings = data.holdings || [], report = data.report || null;
    if (report) { window.HOLDINGS_REPORT = report; window.dispatchEvent(new Event("holdings:report")); briefStrip(report); }
    // 有報告時先看數字，管理持股放在最下面；還沒有報告（或正在編輯）才放上面
    const manage = `<div class="grid">${manageCard(holdings, report, open)}</div>`;
    root.innerHTML = report && open == null ? `${reportHtml(report, account)}${manage}`
      : `${manage}${report ? reportHtml(report, account) : '<section class="card placeholder">新增持股後，下一次自動計算完成就會在這裡看到損益與分析。</section>'}`;
    bindAccount(report, (a) => cloudHome(open, a));
    const card = root.querySelector(".a-manage");
    card.querySelector("[data-logout]").addEventListener("click", () => {
      if (!confirm("這台裝置將不再記住私密連結，之後要再用連結打開才能看。確定？")) return;
      saveKey(null); showNoKey("已忘記這台裝置。");
    });
    card.querySelector("[data-new]")?.addEventListener("click", () => cloudHome("new", account));
    card.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => cloudHome(Number(b.dataset.edit), account)));
    const form = card.querySelector(".a-holding-form");
    if (!form) return;
    const fx = form.querySelector(".a-f-fx_cost"), sym = form.elements.symbol;
    const toggleFx = () => { fx.hidden = !sym.value || isTW(sym.value.trim()); };
    sym.addEventListener("input", toggleFx); toggleFx();
    form.querySelector("[data-cancel]").addEventListener("click", () => cloudHome(null, account));
    const msg = form.querySelector(".a-msg");
    form.querySelector("[data-delete]")?.addEventListener("click", async () => {
      if (!confirm(`確定刪除 ${sym.value}？`)) return;
      try { await rpc("vault_remove_holding", { hid: Number(form.dataset.id) }); cloudHome(null, account); }
      catch (err) { msg.textContent = `刪除失敗：${err.message}`; }
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const row = {};
      FIELDS.forEach(([k, , type]) => {
        let v = form.elements[k].value.trim();
        if (k === "symbol") v = v.toUpperCase();
        if (k === "fx_cost" && isTW(row.symbol)) v = "";
        row[k] = type === "number" ? (v === "" ? null : Number(v)) : v;
      });
      if (form.dataset.id) row.id = Number(form.dataset.id);
      msg.textContent = "儲存中…";
      try { await rpc("vault_save_holding", { h: row }); cloudHome(null, account); }
      catch (err) { msg.textContent = `儲存失敗：${err.message}`; }
    });
    form.elements[open === "new" ? "symbol" : "shares"].focus();
  }

  function cloudMode() {
    MODE = "cloud";
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get("k")) {
      saveKey(h.get("k"));
      history.replaceState(null, "", location.pathname + location.search);  // 網址列不留金鑰
      document.querySelector('.tab[data-tab="assets"]')?.click();
    } else {
      vkey = loadKey();
    }
    vkey ? cloudHome() : showNoKey();
  }
  // 網站已經開著時再點私密連結，只會改變「#」後面，不會重新載入
  window.addEventListener("hashchange", () => { if (MODE === "cloud" && location.hash.includes("k=")) cloudMode(); });

  // supabase-config.js 有填網址與公開金鑰就用雲端模式，否則讀自己電腦上的檔案
  const s = document.createElement("script");
  s.src = "supabase-config.js";
  s.onload = () => { cfg = window.SUPABASE_CONFIG; cfg && cfg.url && cfg.key ? cloudMode() : localMode(); };
  s.onerror = localMode;
  document.head.appendChild(s);
})();
