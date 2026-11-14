# HANDOFF
- 目標與驗收條件：優化既有模擬方法中的四塊（動能、葛拉漢、持股比例、停損），每個改動要事先登記、可否證、在樣本內 walk-forward 與一次性保留段驗證。四個階段都已完成，結論見 `research/docs/REPORT.md`。
- 目前進度與下一步：2026-11-14 Brad 同意，第 1～3 點已完成（#21、#36、#44 合併；`graham_mom` 帳戶已加進 `papertrade/config.py` 與 `methods.graham_mom`；九個 PR 已關閉）。剩下：
  - 模擬帳戶只跑 30 個交易日（`TRADING_DAYS`），要做 12 個月前瞻對照，需另外讓 graham 與 graham_mom 在模擬結束後繼續跑，或定期用回測比較（待 Brad 決定）。
  - 2027-11 依撤回條件判定是否保留 graham_mom。
- 原始清單（歷史紀錄）：
  1. 決定是否合併 PR #21（研究框架與修正，不改變現有帳戶行為）。
  2. 決定是否為 G2 另開並行模擬帳戶「葛拉漢＋動能」：在 `papertrade/config.py` 的 `METHODS` 加一個帳戶，帶 `variant={"graham_value_momentum": True}`（目前旗標只在研究框架傳入，正式帳戶要另外接線並加測試）；撤回條件寫在 REPORT.md。
  3. 關閉 #32～#35、#37～#41、#43（保留為紀錄）。#36、#44 視第 2 點決定。
  4. 若要再驗證：建立事前選股池（每年初依當時市值／成交值）後重跑 G2。
- 環境與指令：
  - 測試：`python -m pytest tests/test_research.py tests/test_metrics.py tests/test_backtest_papertrade.py tests/test_papertrade.py tests/test_hyp_*.py -q`
  - 雲端容器連不到 Yahoo／FinMind／證交所；真實資料只能在 GitHub Actions 跑：`research/requests/*.json` push 到 `claude/**` 或 `hyp/**` 分支（見 `research/README.md`）。
- 已做的設計決策與原因：
  - 保留段界線固定 2025-04-28，寫在 `research/data/manifest.json`，重抓不移動。
  - 保留段已用掉（`research/holdout/USED.json`）。之後任何新假設都不能再拿這段當樣本外，只能用前瞻（實際往後跑）的資料。
  - Deflated Sharpe 在這裡鑑別力低（絕對夏普被事後選股池灌水），採用依據看成對夏普差與事先登記的條件。
- 不要碰的地方 / 注意事項：不碰 ib_insync 或任何真實交易；`claude`、`claude2` 帳戶不在研究範圍；研究用子代理一律 Fable、最多 2 個並行；每個階段結束要等 Brad 同意。
- 需要人工授權或決定的事項：上面 1～3。
