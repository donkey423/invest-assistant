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
      <p class="muted">市值、損益都換算成台幣；占比是占全部資產。${MODE === "cloud" ? "新增或修改持股後，數字會在下次自動計算時更新。" : "修改持股請編輯 private/holdings.csv 後重新執行 python -m holdings。"}</p>
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

  function reportHtml(r, account) {
    if (!r) return "";
    const warn = (r.warnings || []).map((w) => `<div class="a-warn">${esc(w)}</div>`).join("");
    const where = MODE === "cloud" ? "持股存在你的 Supabase 資料庫，只有登入的你看得到。" : "持股資料只存在你自己的電腦。";
    return `${warn}<div class="grid">${summaryCard(r)}${alertsCard(r.analysis)}${tableCard(r, account)}${allocCard(r)}${riskCard(r)}${scenarioCard(r)}</div>
      <p class="muted a-foot">${where}AI 健檢只拿到占比、報酬率、產業與投資理由，不含帳戶與金額。僅供參考，不構成投資建議。${r.analysis?.model ? `｜模型 ${esc(r.analysis.model)}` : ""}</p>`;
  }

  function bindAccount(r, rerender) {
    const sel = document.getElementById("a-account");
    if (sel) sel.addEventListener("change", () => rerender(sel.value));
  }

  function render(r, account = "全部") {
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

  // ---------------- 雲端模式：Supabase 登入，手機可新增持股 ----------------
  // 直接呼叫 Supabase 的 REST API，不必載入額外套件。前端只用公開金鑰（publishable／anon），
  // 資料的保護靠資料庫的 Row Level Security：沒登入或別人登入都讀不到你的持股。
  const SKEY = "invest-assistant-session";
  let cfg, session;

  const loadSession = () => { try { return JSON.parse(localStorage.getItem(SKEY)); } catch (e) { return null; } };
  const saveSession = (s) => { session = s; try { s ? localStorage.setItem(SKEY, JSON.stringify(s)) : localStorage.removeItem(SKEY); } catch (e) { /* 無痕模式 */ } };
  const toSession = (t) => ({ access_token: t.access_token, refresh_token: t.refresh_token,
    expires_at: t.expires_at ? Number(t.expires_at) : Math.floor(Date.now() / 1000) + Number(t.expires_in || 3600),
    email: t.user?.email || session?.email || "" });

  async function api(path, { method = "GET", body, auth = true, prefer } = {}) {
    if (auth && session && session.expires_at - 60 < Date.now() / 1000) await refresh();
    const headers = { apikey: cfg.key, "Content-Type": "application/json" };
    if (auth && session) headers.Authorization = `Bearer ${session.access_token}`;
    if (prefer) headers.Prefer = prefer;
    const res = await fetch(cfg.url.replace(/\/$/, "") + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) {
      if (res.status === 401 && auth) { saveSession(null); showLogin("登入已過期，請重新登入"); }
      throw new Error(data?.msg || data?.message || data?.error_description || `HTTP ${res.status}`);
    }
    return data;
  }

  async function refresh() {
    const t = await fetch(cfg.url.replace(/\/$/, "") + "/auth/v1/token?grant_type=refresh_token", {
      method: "POST", headers: { apikey: cfg.key, "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: session.refresh_token }) });
    if (!t.ok) { saveSession(null); showLogin("登入已過期，請重新登入"); throw new Error("refresh failed"); }
    saveSession(toSession(await t.json()));
  }

  const AUTH_MSG = {
    "Invalid login credentials": "Email 或密碼不對",
    "Email not confirmed": "還沒確認信箱：請到信箱點確認信裡的連結，再回來登入",
    "User already registered": "這個 Email 已經註冊過了，直接按「登入」",
    "Signups not allowed for this instance": "目前不開放註冊",
  };
  const authErr = (err) => AUTH_MSG[err.message] || err.message;

  // 用 Email＋密碼登入：手機瀏覽器可以記住密碼，也不必設定登入連結要回到哪個網址
  function showLogin(msg = "") {
    root.innerHTML = `<section class="card a-login">
      <h2>登入看我的資產</h2>
      <p class="muted">持股只有你登入後看得到。</p>
      <form id="a-login-form" class="a-form">
        <label>Email<input type="email" name="email" required autocomplete="email" inputmode="email"></label>
        <label>密碼<input type="password" name="password" required minlength="8" autocomplete="current-password"></label>
        <button class="a-btn primary" type="submit" data-mode="login">登入</button>
        <button class="a-btn" type="submit" data-mode="signup">第一次使用：用這組 Email 和密碼建立帳號</button>
      </form>
      <p class="a-msg" id="a-login-msg">${esc(msg)}</p>
    </section>`;
    const msgEl = document.getElementById("a-login-msg");
    const form = document.getElementById("a-login-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const mode = e.submitter?.dataset.mode || "login";
      const email = form.email.value.trim(), password = form.password.value;
      if (password.length < 8) { msgEl.textContent = "密碼至少 8 個字"; return; }
      msgEl.textContent = mode === "signup" ? "建立帳號中…" : "登入中…";
      try {
        if (mode === "signup") {
          const t = await api("/auth/v1/signup", { method: "POST", auth: false, body: { email, password } });
          if (t?.access_token) { saveSession(toSession(t)); return cloudHome(); }
          msgEl.textContent = "帳號建好了。請到信箱點確認信裡的連結（點完如果出現打不開的頁面，關掉就好），然後回來按「登入」。";
          form.querySelector('[data-mode="signup"]').hidden = true;
          return;
        }
        const t = await api("/auth/v1/token?grant_type=password", { method: "POST", auth: false, body: { email, password } });
        saveSession(toSession(t));
        cloudHome();
      } catch (err) { msgEl.textContent = authErr(err); }
    });
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
      <div class="card-head"><h2>管理持股</h2><span class="muted">${esc(session.email)}　<button class="a-link" data-logout>登出</button></span></div>
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
    if (!session) return showLogin();
    if (!session.email) {
      try { const u = await api("/auth/v1/user"); saveSession({ ...session, email: u.email }); } catch (e) { return; }
    }
    let holdings, report;
    try {
      [holdings, report] = await Promise.all([
        api("/rest/v1/holdings?select=*&order=symbol.asc,id.asc"),
        api("/rest/v1/holdings_reports?select=report").then((r) => r?.[0]?.report || null),
      ]);
    } catch (err) {
      if (session) root.innerHTML = `<section class="card a-warn">讀取失敗：${esc(err.message)}</section>`;
      return;
    }
    root.innerHTML = `<div class="grid">${manageCard(holdings, report, open)}</div>${report ? reportHtml(report, account)
      : '<section class="card placeholder">新增持股後，第一次自動計算完成就會在這裡看到損益與分析。</section>'}`;
    bindAccount(report, (a) => cloudHome(open, a));
    const card = root.querySelector(".a-manage");
    card.querySelector("[data-logout]").addEventListener("click", async () => {
      try { await api("/auth/v1/logout", { method: "POST" }); } catch (e) { /* 已失效也沒關係 */ }
      saveSession(null); showLogin();
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
      try { await api(`/rest/v1/holdings?id=eq.${form.dataset.id}`, { method: "DELETE" }); cloudHome(null, account); }
      catch (err) { msg.textContent = `刪除失敗：${err.message}`; }
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const row = {};
      FIELDS.forEach(([k, , type]) => {
        let v = form.elements[k].value.trim();
        if (k === "symbol") v = v.toUpperCase();
        if (k === "fx_cost" && isTW(row.symbol)) v = "";
        row[k] = type === "number" || type === "date" ? (v === "" ? null : type === "number" ? Number(v) : v) : v;
      });
      msg.textContent = "儲存中…";
      try {
        if (form.dataset.id) await api(`/rest/v1/holdings?id=eq.${form.dataset.id}`, { method: "PATCH", body: row, prefer: "return=minimal" });
        else await api("/rest/v1/holdings", { method: "POST", body: row, prefer: "return=minimal" });
        cloudHome(null, account);
      } catch (err) { msg.textContent = `儲存失敗：${err.message}`; }
    });
    form.elements[open === "new" ? "symbol" : "shares"].focus();
  }

  function cloudMode() {
    MODE = "cloud";
    // 從信裡的登入連結回來時，網址後面會帶著登入資訊
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get("access_token")) {
      saveSession(toSession(Object.fromEntries(h)));
      history.replaceState(null, "", location.pathname + location.search);
      document.querySelector('.tab[data-tab="assets"]')?.click();
    } else {
      session = loadSession();
      if (h.get("error_description")) return showLogin(`登入失敗：${h.get("error_description")}`);
    }
    session ? cloudHome() : showLogin();
  }

  // supabase-config.js 有填網址與公開金鑰就用雲端模式，否則讀自己電腦上的檔案
  const s = document.createElement("script");
  s.src = "supabase-config.js";
  s.onload = () => { cfg = window.SUPABASE_CONFIG; cfg && cfg.url && cfg.key ? cloudMode() : localMode(); };
  s.onerror = localMode;
  document.head.appendChild(s);
})();
