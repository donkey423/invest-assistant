# 研究框架（walk-forward）

階段三的前置工作：把歷史拉長、補上績效指標、股利入帳、修掉已確認的錯誤，讓 `HYPOTHESES.md` 的假設可以被否證。
程式在 `papertrade/research/`，指標在 `papertrade/metrics.py`，測試在 `tests/test_research.py`、`tests/test_metrics.py`。

這裡只研究四塊：12-1 動能、葛拉漢價值、持股比例調整（綜合評分帳戶）、-8% 停損（歐尼爾、技術面四指標）。
不含 Claude 判斷與 AI 主題，也不會改動模擬帳戶的行為。

## 保留段規則（最重要）

- **最後 20% 的評估日是保留段，未經 Brad 本人明確同意，任何人、任何程式都不得使用。**
- 交易日曆＝`^TWII`、`0050.TW`、`2330.TW` 日期的聯集；前 260 個交易日是暖機，之後是評估日；保留段＝評估日的最後 20%。
- 界線 `holdout_start` 第一次抓資料時寫進 `research/data/manifest.json`，之後重抓**不會移動**（新資料只會讓保留段變長）。
- `research/data/insample.json.gz` 不含任何日期在界線當天或之後的資料：股價、股利、VIX、估值、法人都照日期截斷；月營收照「可用日」（次月 11 日）截斷。還原價 `adj_close` 會重新定基，讓保留段的配息不會從價格水準洩漏。寫檔前與讀檔時各檢查一次，發現洩漏就中止。
- 保留段檔 `research/data/holdout.json.gz` 預設**完全不寫**；加 `--write-holdout` 才寫，而且列在 `.gitignore`。
- 要讀保留段必須同時滿足：命令加 `--unlock-holdout`，而且環境變數 `RESEARCH_HOLDOUT_OK=brad-approved`。缺一個就拒絕。
- GitHub Actions 的請求檔沒有任何辦法解鎖：內容只要出現 `holdout` 字樣，整份請求就被拒絕。

## 怎麼用

本機沒有對外網路時抓不到真實資料，真實資料一律在 GitHub Actions 抓（見下一節）。

```bash
# 1. 抓資料（Yahoo 股價與現金股利、FinMind 月營收與估值、證交所 T86 法人），切掉保留段
python -m papertrade.research fetch                       # 寫 research/data/insample.json.gz、manifest.json
python -m papertrade.research fetch --skip-chips          # 不抓法人（快很多；綜合評分的外資分數會缺）
python -m papertrade.research fetch --chips-from 2021-01-04

# 2. 跑變體（只讀樣本內）
python -m papertrade.research run --variant baseline      # 寫 research/results/baseline.json、.md，並記進 research/trials.json

# 3. 變體對 baseline
python -m papertrade.research compare --base baseline --variant M1   # 寫 research/results/compare_baseline_vs_M1.json、.md

# 沒有網路時的試跑（合成資料，數字沒有任何意義；不能寫進 research/data）
python -m papertrade.research fetch --synthetic --out research/data-synthetic
python -m papertrade.research run --variant baseline --data research/data-synthetic --out /tmp/res --trials /tmp/trials.json
```

法人資料每個交易日一個快取檔（`research/data/chips/YYYY-MM-DD.json`，只有樣本內的日子、只留選股池代號），中斷後重跑會接著抓。

## 在 GitHub Actions 執行

`.github/workflows/research.yml`：在 `claude/**` 或 `hyp/**` 分支新增或修改 `research/requests/*.json` 後 push 就會執行；也可以手動執行。
流程是先跑測試（沒過就停）、執行請求、把輸出 commit 回同一個分支。不部署網頁、不碰 `site/`。

請求檔格式（只接受下列命令與鍵，其他一律拒絕；輸出位置固定）：

```json
{"cmd": "fetch", "args": ["--skip-chips"]}
{"cmd": "run", "variants": ["baseline"], "folds": 5}
{"cmd": "compare", "base": "baseline", "variants": ["M1"]}
{"steps": [{"cmd": "fetch"}, {"cmd": "run", "variants": ["baseline"]}], "note": "第一次建立資料集"}
```

- `fetch` 的 `args` 只能是 `--skip-chips`、`--chips-from YYYY-MM-DD`。
- 變體名稱必須已登記在 `papertrade/research/runner.py` 的 `VARIANTS`。
- 一次 push 只看最後一個 commit 新增或修改的請求檔；都沒有就用檔名排序最後一個。建議檔名用流水號，例如 `001-fetch.json`。
- 選用的 Secret `FINMIND_TOKEN`：有設的話 FinMind 的流量上限較高；沒設也能跑。

## 所有研究都套用的修正（不是假設）

| 項目 | 做法 | 對應 AUDIT |
|---|---|---|
| VIX 延後一天 | 台股 t 日只用日期早於 t 的最近一筆 VIX（`backtest.vix_before`；一般回測也一併修正） | 1.7、4.2 |
| 現金股利 | 除息日把「前一天收盤持有股數 × 每股現金股利」記進現金（`engine.credit_dividends`）；不扣稅與補充保費 | 3.7 |
| 對照 | 大盤價格指數（不含息）之外，另列 0050 含息再投入 | 3.7 |
| 期末持股 | 績效以「收盤價扣掉賣出手續費與證交稅」計值 | 3.8 |
| 景氣燈號 | 仍然寫死紅燈（係數 1.0）。沒有歷史資料，屬**未驗證參數** | 4.4 |

## Walk-forward 的定義

所有假設的數值都是事先固定的，不在資料上調參。所以這裡的 walk-forward 是：
各方法各自的 100 萬帳戶從樣本內第一天連續跑到最後一天（訊號能用的歷史逐日變長），
評估期切成 5 個相連、不重疊、等長的折，每一折與全期各算一次績效。

每個方法、每一折與全期的輸出：`papertrade.metrics.summarize` 的指標（總報酬、年化報酬、波動、夏普、最大回撤、Calmar、年換手、交易筆數、費用、勝率），
加上平均持股檔數、平均持股比例、停損出場次數、入帳股利；另外列出各折大盤低於季線、低於年線、VIX ≥ 25 的天數（假設的否證條件會用到）。

診斷欄位（只記錄，不影響淨值與交易；各假設的否證條件會用到）：
- `picks`：每個評估日開盤成交的那次決策（前一個交易日收盤）當下，該方法的前 5 名代號。比較報告的「前 5 名名單重疊率」由它算出（看訊號，不是實際持股）。
- `avg_candidates`：每天排名內的檔數（通過該方法門檻的檔數）的平均。
- `target`／`target_exposure`：引擎下單用的目標持股比例（不是實際市值占比）的平均、中位數、最低、低於 100% 的天數、為 0（大盤閘門關閉、完全不買新股）的天數，以及逐日序列。

## 試驗次數規則（Deflated Sharpe）

- 每次 `run` 都會追加一筆到 `research/trials.json`（變體名稱、旗標內容的 hash、程式版本、時間、資料集識別碼、各方法全期與各折的每日夏普），不管結果好壞，不得刪除。
- `N` ＝紀錄中**不同旗標內容**的個數（baseline 也算一筆），而且至少是 `HYPOTHESES.md` 事先登記的 **12**。同一組旗標重跑不多算；改了旗標內容就是新的一次試驗。
- 各試驗夏普的變異數取自紀錄中同一份資料集、同一個方法、每個 hash 最新的一筆。紀錄不足 2 筆時算不出來，Deflated Sharpe 會退回「對 0 的 PSR」，比較報告會註明。
- 注意：每個假設在自己的分支跑，各分支的 `trials.json` 互不相通，所以 12 這個下限很重要；多數試驗不影響某個方法時，該方法的變異數會偏小（門檻偏鬆），判讀時要保守。
- 事後加任何變體都要在這裡留下紀錄，並重算。

## 怎麼加一個假設（給假設分支）

1. 在 `papertrade/research/runner.py` 的 `VARIANTS` 加一筆，名稱用 `HYPOTHESES.md` 的編號。
2. 只是改設定的假設（例如 M1）不用寫程式：`"M1": {"methods": {"momentum": {"market_filter": 200}}}`。`methods` 底下的鍵會蓋在 `C.METHODS` 的複本上，跑完還原；只能指定研究範圍內的五個方法。
3. 要改邏輯的假設：自訂旗標（`methods`、`lookback` 以外的任何鍵）。整個旗標 dict 在選股方法裡是 `ctx["variant"]`，在 `engine.plan_orders` 裡是 `state["variant"]`。模擬帳戶與一般回測沒有這兩個鍵，所以新邏輯一律寫成 `(ctx.get("variant") or {}).get("旗標")` 才啟動，預設行為不變。
4. 需要比 320 根 K 棒更長歷史的假設（擴張視窗）：旗標加 `"lookback": None`（給全部歷史，較慢），或用 `ctx["memo"]`（同一次執行跨日共用的 dict）逐日累積。
5. 還原價在 `ctx["px"][代號]["adj_close"]`、每股現金股利在 `["div"]`、持股進場以來領到的股利在 `pos["div"]`（元）。還原價只能用比值，不能用水準。
6. 加測試，push 一個 `{"cmd": "run", ...}` 與 `{"cmd": "compare", ...}` 的請求檔。

## 已知限制（沿用 AUDIT.md）

- **選股池是事後挑的**（2026-11 才選出的產業鏈代表股套回 2018 年起的歷史）：所有絕對報酬與夏普都偏好看，**只有「變體對 baseline」的差有意義**；動能類的變體受影響最大。池內也沒有已下市的股票。
- 沒有漲跌停、成交量、滑價的成交模型；下的是零股，卻用 09:00 開盤價成交。
- 上櫃股沒有法人資料（T86 只有上市）。
- Yahoo 的收盤價會回溯調整股票分割：保留段內若發生分割，樣本內的價格水準會跟著改（比值不受影響）；法人買賣超股數沒有跟著調整。資料集另存了 `split` 欄位備查。
- Yahoo 的 `adj_close` 對台股股利與配股的還原是否正確還沒抽查（假設 M3 之前要先查）。
- 月營收一律視為次月 11 日可用，沒有處理假日順延；FinMind 是否為當時公布值未知。
- 產業鏈燈號在歷史上只能用「月營收是否加速」重建；門檻是 2026-11 調過的樣本內參數。
- 現金股利入帳不扣所得稅與二代健保補充保費；股票股利依 Yahoo 的價格調整處理。
- 每日淨值四捨五入到元。
