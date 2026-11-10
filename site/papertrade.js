// 模擬帳戶頁：讀 data/papertrade.json。每種預測方法各一個 100 萬的模擬帳戶，和大盤比。
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cls = (v) => (v == null ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat");
  const pct = (v, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
  const money = (v) => (v == null ? "—" : Math.round(v).toLocaleString("zh-TW"));
  const md = (d) => (d ? `${+d.slice(5, 7)}/${+d.slice(8, 10)}` : "");
  let DATA = null, SEL = null;

  function chart(methods, bench, sel) {
    const series = methods.map((m) => ({ id: m.id, name: m.name, pts: m.equity.map((e) => e.equity) }));
    const tw = (bench["^TWII"] || {}).equity || [];
    const all = [...series.flatMap((s) => s.pts), ...tw.map((e) => e.equity), DATA.start_cash];
    const n = Math.max(...series.map((s) => s.pts.length), tw.length);
    if (n < 1) return `<div class="pt-empty">第一個交易日收盤後開始畫線。</div>`;
    const W = 640, H = 220, L = 46, R = 8, T = 8, B = 22;
    const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
    const x = (i) => L + (n === 1 ? (W - L - R) / 2 : (i / (n - 1)) * (W - L - R));
    const y = (v) => T + (1 - (v - lo) / span) * (H - T - B);
    const path = (pts) => [DATA.start_cash, ...pts].map((v, i) => `${i ? "L" : "M"}${x(Math.max(0, i - 1)).toFixed(1)} ${y(v).toFixed(1)}`).join("");
    const ticks = [lo, (lo + hi) / 2, hi].map((v) => `<text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${pct((v / DATA.start_cash - 1) * 100, 1)}</text><line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`).join("");
    const dates = (tw.length ? tw : methods[0].equity).map((e) => e.date);
    const xl = dates.length ? `<text x="${x(0)}" y="${H - 6}">${md(dates[0])}</text><text x="${x(dates.length - 1)}" y="${H - 6}" text-anchor="end">${md(dates.at(-1))}</text>` : "";
    const lines = series.filter((s) => s.id !== sel).map((s) => `<path class="pt-line" d="${path(s.pts)}"><title>${esc(s.name)}</title></path>`).join("");
    const cur = series.find((s) => s.id === sel);
    return `<svg class="pt-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="各方法帳戶淨值走勢">
      <g class="pt-axis">${ticks}${xl}</g>${lines}
      ${tw.length ? `<path class="pt-bench" d="${path(tw.map((e) => e.equity))}"><title>台股加權指數</title></path>` : ""}
      ${cur ? `<path class="pt-sel" d="${path(cur.pts)}"><title>${esc(cur.name)}</title></path>` : ""}</svg>
      <div class="pt-legend"><span><i class="k sel"></i>${esc(cur ? cur.name : "")}</span><span><i class="k bench"></i>台股加權指數</span><span><i class="k other"></i>其他方法</span></div>`;
  }

  function hero(d) {
    const prog = Math.round((d.days_done / d.days_total) * 100);
    const b = d.benchmarks || {};
    const bret = (s) => { const e = (b[s] || {}).equity || []; return e.length ? (e.at(-1).equity / d.start_cash - 1) * 100 : null; };
    const r = d.regime || {}, bc = d.business_cycle || {};
    const status = d.status === "done" ? `已完成 ${md(d.start)}–${md(d.end)}，共 ${d.days_total} 個交易日`
      : d.days_done ? `第 ${d.days_done} / ${d.days_total} 個交易日（${md(d.start)} 開始）`
        : `已選好股票，下一個交易日開盤成交後開始計算（決策日 ${md(d.last_decision)}）`;
    $("pt-hero").innerHTML = `
      <div class="pt-status"><b>${esc(status)}</b><div class="bar"><span style="width:${prog}%"></span></div></div>
      <div class="pt-kpis">
        <div><span class="muted">台股加權指數</span><b class="${cls(bret("^TWII"))}">${pct(bret("^TWII"))}</b></div>
        <div><span class="muted">0050</span><b class="${cls(bret("0050.TW"))}">${pct(bret("0050.TW"))}</b></div>
        <div><span class="muted">目前第一名</span><b>${esc((d.methods.find((m) => m.rank === 1) || {}).name || "—")}</b></div>
        <div><span class="muted">景氣燈號（${esc(bc.month || "")}）</span><b>${esc(bc.light || "—")} ${bc.score ?? ""}</b></div>
        <div><span class="muted">大盤 vs 季線</span><b>${r.above_ma60 == null ? "—" : r.above_ma60 ? "季線之上" : "跌破季線"}</b></div>
      </div>
      <p class="muted">規則：${d.methods.length} 種方法各自從 ${d.universe_size} 檔產業鏈代表股裡選股，每個帳戶起始 ${money(d.start_cash)} 元、最多 ${d.top_n} 檔等權重；收盤後選股，<b>隔天開盤價成交</b>，含手續費 ${(d.costs.fee_rate * 100).toFixed(4)}%（最低 ${d.costs.fee_min} 元）與證交稅 ${(d.costs.tax_rate * 100).toFixed(1)}%。股票全部由程式依方法自動選出，不是買賣建議。</p>`;
  }

  function board(d) {
    const rows = [...d.methods].sort((a, b) => a.rank - b.rank).map((m) => {
      const h = m.picks_hit || {};
      return `<tr data-m="${m.id}" class="${m.id === SEL ? "sel" : ""}" tabindex="0">
        <td><b>${m.rank}</b> ${esc(m.name)}</td>
        <td class="${cls(m.return_pct)}">${pct(m.return_pct)}</td>
        <td class="${cls(m.excess_pct)}">${pct(m.excess_pct)}</td>
        <td>${pct(m.mdd_pct)}</td>
        <td>${m.days ? `${m.beat_days}/${m.days}` : "—"}</td>
        <td>${h.n ? `${h.hit_rate}%<span class="muted">（${h.n}）</span>` : "—"}</td>
        <td>${m.win_rate == null ? "—" : `${m.win_rate}%<span class="muted">（${m.closed}）</span>`}</td>
        <td>${money(m.equity_now)}</td></tr>`;
    }).join("");
    $("pt-board").innerHTML = `<div class="pt-scroll"><table class="chain-table pt-table"><thead><tr><th>方法</th><th>報酬</th><th>比大盤</th><th>最大回落</th><th>贏大盤天數</th><th>選股命中率</th><th>賣出勝率</th><th>帳戶淨值</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="muted">選股命中率＝每天推薦的前 ${d.top_n} 名，隔天開盤買、抱 ${d.pick_horizon} 個交易日，跑贏大盤的比例（不管帳戶有沒有真的買）；括號是樣本數。比大盤＝帳戶報酬減台股加權指數報酬。</p>`;
    document.querySelectorAll("#pt-board [data-m]").forEach((tr) => {
      const go = () => select(tr.dataset.m);
      tr.addEventListener("click", go);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    });
  }

  function detail(m) {
    const src = (m.sources || []).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join("、");
    const hold = m.holdings.length ? `<table class="chain-table pt-hold"><thead><tr><th>持股</th><th>股數</th><th>成本</th><th>現價</th><th>損益</th><th>買進日</th></tr></thead><tbody>
      ${m.holdings.map((h) => `<tr><td>${esc(h.name)} <span class="muted">${esc(h.code)}</span><div class="pt-why">${esc(h.reason)}</div></td><td>${money(h.shares)}</td><td>${h.price}</td><td>${h.last}</td><td class="${cls(h.pnl_pct)}">${pct(h.pnl_pct)}</td><td>${md(h.date)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="pt-empty">目前沒有持股${m.pending && m.pending.buys.length ? "，下一個交易日開盤買進下面的股票" : ""}。</div>`;
    const L = m.latest || { picks: [], sells: [], buys: [] };
    const buys = new Set(L.buys || []);
    const picks = L.picks.length ? `<ol class="pt-picks">${L.picks.map((p) => `<li><b>${esc(p.name)}</b> <span class="muted">${esc(p.code)}</span>${buys.has(p.code) ? ` <span class="pt-tag buy">明天買進</span>` : m.holdings.some((h) => h.code === p.code) ? ` <span class="pt-tag">續抱</span>` : ""}<div class="pt-why">${esc(p.reason)}</div></li>`).join("")}</ol>` : `<div class="pt-empty">${esc(L.note || "今天沒有選出股票。")}</div>`;
    const sells = (L.sells || []).length ? `<ul class="pt-sells">${L.sells.map((s) => `<li><span class="pt-tag sell">明天賣出</span> ${esc(s.name)} <span class="muted">${esc(s.code)}</span>：${esc(s.reason)}</li>`).join("")}</ul>` : "";
    const trades = m.recent_trades.length ? `<table class="chain-table pt-trades"><thead><tr><th>日期</th><th>買賣</th><th>股票</th><th>股數</th><th>成交價</th><th>費用</th><th>損益</th></tr></thead><tbody>
      ${m.recent_trades.map((t) => `<tr><td>${md(t.date)}</td><td class="${t.side === "買" ? "up" : "down"}">${t.side}</td><td>${esc(t.name)} <span class="muted">${esc(t.code)}</span></td><td>${money(t.shares)}</td><td>${t.price}</td><td>${money(t.fee)}</td><td class="${cls(t.pnl)}">${t.pnl == null ? "" : `${money(t.pnl)}（${pct(t.pnl_pct)}）`}</td></tr>`).join("")}</tbody></table>` : `<div class="pt-empty">還沒有成交紀錄。</div>`;
    $("pt-detail").innerHTML = `
      <div class="card-head"><h2>${esc(m.name)}</h2><span class="muted">第 ${m.rank} 名 · 現金 ${money(m.cash)} · 持股市值 ${money(m.invested)} · 手續費＋稅 ${money(m.fees)}</span></div>
      <p><b>怎麼選：</b>${esc(m.how)}</p>
      <p class="muted"><b>依據：</b>${esc(m.basis)}${src ? ` 來源：${src}` : ""}</p>
      <div class="pt-cols">
        <div><h3 class="bt-sub">${md(L.date)} 收盤後選出的股票</h3>${L.method === "combo" && L.note ? `<p class="muted">${esc(L.note)}</p>` : ""}${picks}${sells}</div>
        <div><h3 class="bt-sub">目前持股</h3>${hold}</div>
      </div>
      <h3 class="bt-sub">最近成交</h3><div class="pt-scroll">${trades}</div>`;
  }

  function history(d) {
    const name = Object.fromEntries(d.methods.map((m) => [m.id, m.name]));
    $("pt-history").innerHTML = (d.history || []).slice(0, 30).map((h) => {
      const items = h.items.filter((i) => i.buys.length || i.sells.length);
      return `<li><b>${md(h.date)} 收盤後</b> ${items.length ? items.map((i) => `<span class="pt-hi">${esc(name[i.method] || i.method)}：${i.buys.length ? `買 ${esc(i.buys.join("、"))}` : ""}${i.buys.length && i.sells.length ? "；" : ""}${i.sells.length ? `賣 ${esc(i.sells.join("、"))}` : ""}</span>`).join("") : `<span class="muted">全部續抱，沒有換股</span>`}</li>`;
    }).join("") || `<li class="muted">還沒有紀錄。</li>`;
  }

  function select(id) {
    SEL = id;
    try { localStorage.setItem("pt-sel", id); } catch (e) { /* 無痕模式 */ }
    document.querySelectorAll("#pt-board [data-m]").forEach((tr) => tr.classList.toggle("sel", tr.dataset.m === id));
    $("pt-chart").innerHTML = chart(DATA.methods, DATA.benchmarks || {}, id);
    detail(DATA.methods.find((m) => m.id === id));
  }

  function render(d) {
    DATA = d;
    let saved = null;
    try { saved = localStorage.getItem("pt-sel"); } catch (e) { /* 無痕模式 */ }
    SEL = d.methods.some((m) => m.id === saved) ? saved : (d.methods.find((m) => m.rank === 1) || d.methods[0]).id;
    hero(d);
    board(d);
    history(d);
    select(SEL);
    $("pt-updated").textContent = `更新於 ${new Date(d.generated_at).toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}`;
    $("pt-warn").innerHTML = (d.warnings || []).map((w) => `<div>${esc(w)}</div>`).join("");
  }

  fetch(`data/papertrade.json?t=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(render)
    .catch(() => { $("pt-hero").innerHTML = `<div class="pt-empty">模擬帳戶還沒開始，第一次排程執行後就會出現。</div>`; });
})();
