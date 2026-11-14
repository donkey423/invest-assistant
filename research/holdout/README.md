# 保留段一次性確認

- 保留段＝評估日的最後 20%（2025-04-28 起），階段一到三完全沒有使用。
- 只有階段三唯一通過的候選 **G2**（葛拉漢價值內再用 12-1 動能排序）拿來確認，候選在看保留段之前就定案，不能看完再挑。
- `request.json` push 到 `claude/**` 分支會觸發 `.github/workflows/holdout.yml`；跑完寫 `USED.json`，之後再觸發一律拒絕。
- 結果在 `research/results/holdout/`（`baseline.holdout.*`、`G2.holdout.*`、`compare_baseline_vs_G2.*`）。
- 事前登記的否證條件（HYPOTHESES.md）：保留段夏普沒有高於原版，或換手增加後扣成本的 Calmar 下降 → 否決。
