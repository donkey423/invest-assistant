# HYPOTHESES.md：模擬帳戶現有方法的改進假設（階段二）

- 日期：2026-11-12
- 對象：`donkey423/invest-assistant` 的 `papertrade/`，基準 commit `673d65a`。前置文件：[AUDIT.md](AUDIT.md)。
- 範圍：Brad 確認的四塊，即 12-1 動能、葛拉漢價值、持股比例調整（季線＋VIX）、-8% 停損。沒有擴大到其他方法。
- 性質：只提假設，沒有改程式碼、沒有跑任何回測。
- 執行方式：2 個子代理分工，實際使用模型皆為 **Fable 5.2（claude-fable-5-2）**。主對話驗收：核對了所有假設引用的程式碼行號與 `site/data/backtest.json` 的數字，並親自重查 3 篇關鍵文獻（Cederburg 等 2020、Du 等 2009、Zakamulin 2014），內容與報告相符。其餘文獻的查證由子代理完成，逐項標示查證程度。
- 標記：**事實**＝讀過程式碼或線上查證過；**推論**＝依文獻與機制推估，未量測；**未知**＝目前無法判定。

## 0. 先講結論

共 10 個假設（動能 3、葛拉漢 2、持股比例 3、停損 2），每塊都沒有硬湊滿 3 個。

| 編號 | 假設 | 新增可調數值 | 過擬合風險 | 類型 |
|---|---|---|---|---|
| M1 | 動能：大盤在年線下不買新股 | 0（沿用既有的 200） | 低到中 | 訊號 |
| M2 | 動能：持股比例隨自身波動縮放 | 0（視窗 126 日取自文獻） | 中 | 訊號 |
| M3 | 動能：排名改用含息報酬 | 0 | 低 | 定義修正 |
| G1 | 葛拉漢：加「累計營收不衰退」濾網 | 0（門檻 0） | 低到中 | 訊號 |
| G2 | 葛拉漢：排名改為價值與動能各半 | 0（50/50 取自文獻） | 中 | 訊號 |
| E1 | 持股比例：等比例部分減碼、回升時補回 | 0 | 低 | 機制修正 |
| E2 | 持股比例：每日看季線改為月底看年線 | 0（取自 Faber） | 中 | 訊號 |
| E3 | 持股比例：VIX 改為台股自身波動 | 0（視窗 21 日為慣例） | 中偏高 | 訊號 |
| S1 | 停損：漲跌幅改用含息價格 | 0 | 低 | 機制修正 |
| S2 | 停損：固定 -8% 改為 5 倍日標準差 | 0（倍數 5 取自文獻；視窗 60 日為本文件選擇） | 中 | 訊號 |

**首選順序（推論）**：先做 E1、S1、M3 三個零參數的修正，再做 M1、G1；M2、G2、E2、E3、S2 的文獻本身正反並陳，放在最後。

**兩件必須先知道的事**

1. **文獻對台股的先驗並不樂觀（事實）**：動能在台股偏弱（Du, Huang & Liao 2009；Chui, Titman & Wei 2010），價值效應在台灣也弱（Chen & Zhang 1998），波動管理與均線擇時的樣本外結果都被質疑（Cederburg 等 2020；Zakamulin 2014）。合理的期待是降低回撤、避開已知的失效情境，不是把報酬拉高。
2. **以目前的資料量，這些假設大多無法否證（推論）**：見第 5 節的前置條件。

## 1. 12-1 動能

**現況（事實）**
- 設定 `papertrade/config.py:19-24`，沒有任何出場鍵；選股 `papertrade/methods.py:32-38`，`ret(ctx, code, 252, skip=21)`。
- 報酬不含息（`papertrade/backtest.py:41`、`:46`）。
- 買前 5 名、掉出前 10 名才賣（`papertrade/engine.py:148-160`、`:176-191`），沒有停損，持股比例固定 1.0（`papertrade/engine.py:211`）。
- 現有回測（受 AUDIT 所列偏誤影響，只當背景）：6 個月 -6.19%、MaxDD -39.39%、15 筆；3 個月 -18.14%、MaxDD -39.19%。問題在回撤，不在換手。

### M1 市場狀態閘門：大盤在年線下不買新動能股

- **假設**：在 momentum 設定加 `"market_filter": 200`，沿用林區法現成的機制（`papertrade/config.py:70`；`papertrade/engine.py:213-215`）。大盤收盤低於 200 日均線時不買新股，持股照排名續抱。只測 200 這一個值。
- **來源**
  - Cooper, Gutierrez & Hameed (2004), "Market States and Momentum", *Journal of Finance*。大盤先前報酬為正之後動能月均 +0.93%，為負之後 -0.37%。https://academicnewsletter.sufe.edu.cn/info/361185 （摘要與數字已線上查證；原文以 36 個月大盤報酬定義狀態，未能線上查證）
  - Du, Huang & Liao (2009), "Why is there no momentum in the Taiwan stock market?", *Journal of Economics and Business* 61(2):140-152。台股較常處於 DOWN 狀態，其後動能獲利更負。https://experts.nau.edu/en/publications/why-is-there-no-momentum-in-the-taiwan-stock-market/ （已線上查證，主對話重查）
  - Daniel & Moskowitz (2016), "Momentum crashes", *JFE* 122(2):221-247。https://econpapers.repec.org/RePEc:eee:jfinec:v:122:y:2016:i:2:p:221-247 （僅書目已線上查證）
- **預期效果（推論）**：MaxDD 改善最明顯，空頭期間可能淺 5–15 個百分點；Sharpe 小升、Calmar 升；CAGR 方向不明（V 型反彈時落後）；換手略降。
- **過擬合風險：低到中**。一個既有參數、一個變體。但文獻證據來自多空組合，本專案只做多，這條規則有一部分其實是大盤擇時；200 日均線也只是原文定義的代理。
- **資料**：現成。
- **可否證條件**：樣本外 Calmar 沒有高於原版；或 Sharpe 低於原版超過 0.1；或測試期間閘門關閉天數少於 5%（判定「無法檢驗」，不算通過）。

### M2 波動度管理：動能持股比例隨自身波動縮放

- **假設**：`papertrade/engine.py:211` 讓 momentum 使用 `e = min(1, σ基準 / σ̂)`。σ̂ 是當日前 5 名等權組合過去 126 個交易日日報酬的年化標準差；σ基準是到當日為止所有 σ̂ 的擴張視窗中位數。上限 1.0，不開槓桿。不採用原文的 12% 目標，因為那是給多空組合用的。
- **來源**
  - Barroso & Santa-Clara (2015), "Momentum has its moments", *JFE* 116(1):111-120。動能風險可預測，管理後幾乎消除崩盤、Sharpe 近乎加倍。https://econpapers.repec.org/RePEc:eee:jfinec:v:116:y:2015:i:1:p:111-120 （摘要已線上查證；六個月視窗與 Sharpe 0.53→0.97 等數字取自二手整理 https://www.cxoadvisory.com/momentum-investing/avoiding-momentum-strategy-crashes/ ）
  - Moreira & Muir (2017), "Volatility-Managed Portfolios", *Journal of Finance* 72(4):1611-1644。https://www.nber.org/papers/w22208 （已線上查證）
  - **反證**：Cederburg, O'Doherty, Wang & Yan (2020), *JFE* 138(1):95-117。可即時執行的樣本外版本，Sharpe 與確定性等值報酬通常低於未管理的原組合。https://econpapers.repec.org/RePEc:eee:jfinec:v:138:y:2020:i:1:p:95-117 （已線上查證，主對話重查）
- **預期效果（推論）**：MaxDD 改善、Calmar 升；Sharpe 小升或持平；CAGR 多半下降；換手上升。
- **過擬合風險：中**。可調數值為零，但「用擴張中位數當基準」是本文件的設計選擇，文獻沒有對應的只做多版本；台股沒有直接證據；與 M1 的效果會重疊；引擎現在降比例是整檔賣出（見 E1），5 檔時每階 20%，很粗糙。
- **資料**：現成。
- **可否證條件**：樣本外 Sharpe 沒有高於原版；或 MaxDD 改善不到 5 個百分點而 CAGR 下降；或換手增加使扣成本後 Calmar 不升。

### M3 動能訊號改用含息報酬

- **假設**：排名用的報酬改以還原股利的價格計算（`papertrade/backtest.py:46` 多留 `Adj Close`，`papertrade/methods.py:35` 的排名改讀它）。成交與計值仍用原始價。沒有新參數。
- **來源**：Jegadeesh & Titman (1993), *Journal of Finance* 48(1):65-91。https://econpapers.repec.org/RePEc:bla:jfinan:v:48:y:1993:i:1:p:65-91 （僅書目已線上查證；原文使用含息報酬這一點未能線上查證）
- **預期效果（推論）**：很小，可能在雜訊內。這是定義修正，不是績效來源。
- **過擬合風險：低**。
- **資料**：Yahoo 的 Adj Close 可抓，但它對台股股利與配股的還原是否正確：**未知**，需先抽查幾檔。
- **可否證條件**：與原版的持股重疊率高於 90% 且績效差在雜訊內，記為「無差異」並維持現狀；抽查發現 Adj Close 有錯則直接放棄。

**考慮過但不提**：把形成期改成 12-7（Novy-Marx 2012）。Goyal & Wahal (2015, *JFQA*) 在美國以外 37 國找不到這個現象，不值得占一個測試名額。

## 2. 葛拉漢價值

**現況（事實）**
- 設定 `papertrade/config.py:62-65`；選股 `papertrade/methods.py:206-215`：`pe ≤ 15`、`pb ≤ 1.5`、`pe×pb ≤ 22.5`，分數 `-pe*pb`。
- 沒有停損，持股比例固定 1.0。不再符合門檻的股票會從排名消失，隔天賣出。
- 現有回測（只當背景）：6 個月 +10.25%、MaxDD -9.76%、11 筆；3 個月 +11.25%。樣本太小，看不出真假。
- **未知**：每天實際有幾檔通過門檻。若常少於 10 檔，`KEEP_RANK` 形同虛設。

### G1 營收不衰退濾網：排除價值陷阱

- **假設**：`papertrade/methods.py:211` 的條件加一項，今年累計營收年增率 `ytd_yoy ≥ 0`，缺資料視為不通過。門檻 0 是自然分界，不調整。
- **來源**
  - Piotroski (2000), *Journal of Accounting Research* 38:1-41。在高淨值市價比股票中用財報強度篩選，年報酬至少提高 7.5%。https://econpapers.repec.org/RePEc:bla:joares:v:38:y:2000:i::p:1-41 （書目已線上查證；數字取自二手整理 https://www.cxoadvisory.com/fundamental-valuation/piotroskis-efficient-value-investing ，該文也指出報酬未扣成本、集中在小型低流動股）
  - Piotroski & So (2012), *Review of Financial Studies* 25(9):2841-2875。https://ideas.repec.org/a/oup/rfinst/v25y2012i9p2841-2875.html （已線上查證）
  - 台股證據：Chen & Yu (2022), *Review of Quantitative Finance and Accounting* 58:245-295。台灣月營收的意外能預測未來盈餘意外。https://link.springer.com/10.1007/s11156-021-00994-1 （已線上查證）
- **預期效果（推論）**：MaxDD 略改善、Sharpe 小升、Calmar 升；CAGR 方向不明；換手略升。
- **過擬合風險：低到中**。一個門檻、一個變體。但營收年增只是財報強度的粗略代理，不是 F-Score；通過的股票若太少，績效差異可能其實來自持現金。
- **資料**：現成（`papertrade/backtest.py:83-96` 已依公布日對齊）。
- **可否證條件**：樣本外 Sharpe 與 Calmar 都沒有高於原版；或平均持股少於 3 檔（判定規則太嚴、無法評估）。

### G2 價值加動能：通過門檻後，排名改為價值與 12-1 動能各半

- **假設**：門檻不變。`papertrade/methods.py:213` 的分數改為 `0.5 × 百分位(-pe*pb) + 0.5 × 百分位(12-1 報酬)`，用現成的 `_pct_rank` 與 `ret(..., 252, skip=21)`。算不出動能的股票排除。50/50 取自文獻的等權組合，不調整。
- **來源**：Asness, Moskowitz & Pedersen (2013), "Value and Momentum Everywhere", *Journal of Finance*。價值與動能負相關，合併後 Sharpe 較高。https://www.aqr.com/library/journal-articles/value-and-momentum-everywhere （摘要已線上查證；卷期頁碼未能線上查證）
- **預期效果（推論）**：Sharpe 小升、MaxDD 略改善；換手上升；CAGR 不明。
- **過擬合風險：中**。台股動能本身偏弱，動能那一半可能沒有資訊；候選池可能只有十來檔，百分位很吵；事後挑的選股池對動能排名有利（AUDIT 2.1）。
- **資料**：現成。
- **可否證條件**：樣本外 Sharpe 沒有高於原版；或換手增加後扣成本的 Calmar 下降。
- G1、G2 各自單獨測，兩者都通過才測合併版。

**G3 不提**：買入／續抱門檻緩衝需要新增沒有先驗值的參數，而現有換手並不高；殖利率條件在股利入帳之前測不乾淨。

## 3. 持股比例調整（季線＋VIX）

**現況（事實）**
- `papertrade/methods.py:191-203` 的 `exposure()`：景氣燈號對應係數、大盤低於 60 日線減 0.3、VIX ≥ 25 減 0.2、夾在 0.3–1.0。
- 只套用在 combo 與 claude（`papertrade/engine.py:211`）。
- `papertrade/engine.py:166-174`：已投資金額超過目標 1.1 倍才減碼，從排名最後的持股**整檔賣出**。`papertrade/engine.py:183-184`：既有持股不會加碼，所以比例回升時不補回。
- 回測的景氣燈號寫死紅燈、VIX 有一天前視（AUDIT 1.7、4.4）。

**與「Claude 判斷」的交集（重要）**：E1、E2、E3 改的是共用程式，會連帶改變 claude 帳戶的行為。實作時必須加開關只作用於 combo，或先與改寫 Claude 判斷的討論串協調。

### E1 降低持股比例改為等比例部分減碼，回升時對稱補回

- **假設**：超過目標 1.1 倍時，對所有留下的持股等比例賣出到目標值；低於目標 0.9 倍時等比例補回。觸發帶沿用現有的 ±10%，不新增數值。需要讓 `_fill`（`papertrade/engine.py:51-66`）支援部分賣出。
- **來源**：Novy-Marx & Velikov (2016), "A Taxonomy of Anomalies and Their Trading Costs", *Review of Financial Studies* 29(1):104-147。扣成本後，買進／續抱門檻分開是最有效的簡單降成本手法。https://www.nber.org/papers/w20721 （摘要已線上查證）。**限制**：該文研究的是美股因子組合；「等比例減碼優於整檔賣出」沒有直接的學術檢定，屬機制推論。
- **預期效果（推論）**：比例由 1.0 降到 0.7 時，現行成交約淨值的 50%（賣 2 檔、再買 1 檔新股），改後約 30%；維持 5 檔而不是 3–4 檔，集中度風險較低。Sharpe、Calmar 小幅正向，可能低於量測雜訊。
- **過擬合風險：低**。零新參數，是機制修正不是訊號。
- **資料**：現成。
- **可否證條件**：樣本外 combo 的換手率或費用占比沒有下降即否決；walk-forward 多數折的 Sharpe 差 ≤ 0 且 MaxDD 沒改善即否決。

### E2 趨勢濾網由「每日看 60 日線」改為「月底看 200 日線」

- **假設**：`papertrade/methods.py:196-198` 的訊號改為「上個月最後一個交易日的加權指數收盤是否低於當日 200 日均線」。減碼幅度 0.3 不動。只測這一個變體。
- **來源**
  - Faber (2007), "A Quantitative Approach to Tactical Asset Allocation", *Journal of Wealth Management*。價格高於 10 個月均線才持有、每月檢查。https://quantpedia.com/strategies/asset-class-trend-following （二手摘要已線上查證）
  - **反證**：Zakamulin (2014), *Journal of Asset Management* 15(4):261-278。含成本的樣本外檢定顯示這類擇時績效被高度誇大。https://ideas.repec.org/a/pal/assmgt/v15y2014i4d10.1057_jam.2014.25.html （已線上查證，主對話重查）
  - 亞洲：Bessembinder & Chan (1995), *Pacific-Basin Finance Journal* 3(2-3):257-284。https://ideas.repec.org/a/eee/pacfin/v3y1995i2-3p257-284.html （僅書目已線上查證，對台灣的具體結論未能查證，不作為依據）
- **預期效果（推論）**：訊號翻轉次數與換手明顯減少；V 型急跌時反應較慢，MaxDD 可能比現行更深；Sharpe、Calmar 方向不確定。
- **過擬合風險：中**。均線長度與檢查頻率的選擇空間很大，這裡以文獻值預先固定一組。
- **資料**：現成。
- **可否證條件**：在 `^TWII` 長歷史上，新規則扣成本後 Calmar 沒有比較高或翻轉次數沒有比較少即否決；組合層級保留段 Sharpe 差 ≤ 0 且 MaxDD 更深即否決；樣本內沒有任何跌破年線事件則標記「無法檢定」，不得採用。

### E3 以台股自身的已實現波動取代「VIX ≥ 25 減 0.2」

- **假設**：刪除 VIX 項（`papertrade/methods.py:199-201`），改為 `level *= min(1, σ_ref / σ_21)`。σ_21 是 `^TWII` 近 21 個交易日日報酬的標準差；σ_ref 是同一序列到當日為止的擴張視窗中位數，暖機 252 日。上限 1、下限沿用 0.3。**對照組預先登記為「直接刪除 VIX 項」**。附帶好處是 VIX 的時區前視從根本消失。
- **來源**
  - Moreira & Muir (2017)，同 M2（已線上查證）
  - Harvey 等 (2018), "The Impact of Volatility Targeting", *Journal of Portfolio Management*。對股票有效，美股 Sharpe 0.40 升到約 0.48–0.51。https://alphaarchitect.com/volatility-targeting-improves-risk-adjusted-returns/ （二手摘要已線上查證）
  - **反證一**：Cederburg 等 (2020)，同 M2
  - **反證二**：Liu, Tang & Zhou (2019), *Journal of Portfolio Management* 46(1):38-51。常見做法含前視偏誤，修正後只在金融危機期間贏大盤。https://profiles.wustl.edu/en/publications/volatility-managed-portfolio-does-it-really-work/ （已線上查證）。本假設用擴張視窗中位數正是為了避開這個偏誤。
  - 台灣或亞洲的專門證據：**未知**（沒找到可查證的文獻）。
- **預期效果（推論）**：平均持股比例會低於現行；MaxDD 與波動下降；CAGR 估計每年拖累 1–3 個百分點；Sharpe 持平到小升，也可能下降；沒有 E1 時整檔賣出會放大換手。
- **過擬合風險：中偏高**。文獻樣本外結果分歧；與 E1 有交互作用。
- **資料**：現成，但 σ_ref 需要至少 1 年暖機。
- **可否證條件**：指數層級樣本外 Sharpe 不高於買進持有且 Calmar 沒升即否決；保留段 Calmar 不高於對照組即否決；對照組表現不輸時應採對照組（參數更少）。

## 4. -8% 停損

**現況（事實）**
- `papertrade/engine.py:130-140`：`chg = 當日收盤 / 進場成交價 − 1`，固定參考價、不含股利，隔日開盤出場。
- 使用停損的方法：claude（`papertrade/config.py:18`，不在本次範圍）、oneil（`:76`，-8%、最多 20 日）、tech4（`:81`，-8%、+10% 停利、最多 20 日）。
- 動能與葛拉漢沒有停損。

### S1 停損的漲跌幅改用含息價格

- **假設**：`chg` 改為「(收盤 + 進場後累計每股現金股利) / 進場價 − 1」。-8% 門檻不動。影響 oneil、tech4；claude 共用同一段程式，需加開關或協調。
- **來源**：Chen, Chow & Shiu (2013), "Ex-dividend prices and investor trades: Evidence from Taiwan", *Pacific-Basin Finance Journal* 24:39-65。https://scholars.ncu.edu.tw/zh/publications/ex-dividend-prices-and-investor-trades-evidence-from-taiwan/ （摘要已線上查證）。該文支持除息日股價確實因配息下跌，但沒有檢定停損規則；「除息誤觸停損傷害績效」是邏輯推論。
- **預期效果（推論）**：幅度小，因為只影響持有期間跨除息日的部位，而這兩法選的多是低殖利率強勢股。主要價值是正確性。
- **過擬合風險：低**。零新參數。
- **資料**：**不完全現成**。需要個股除息日與每股現金股利；yfinance 可取但目前沒保留；Yahoo 對台股配股是否還原：未知。
- **可否證條件**：樣本內由除息造成的停損少於 3 筆，結論是「無實質影響」，只以正確性理由保留，不得宣稱績效改善；被改判不停損的部位之後平均報酬為負即否決。

### S2 固定 -8% 停損改為依個股波動縮放（5 倍日標準差）

- **假設**：停損門檻改為 `−5 × σ_60`，σ_60 是該股進場日前 60 個交易日日報酬的標準差，進場時固定。倍數 5 取自 Lei & Li 測試的 5／10／20 倍中最緊的一檔；60 日視窗是本文件的選擇。只測這一個變體，影響 oneil、tech4。
- **來源**
  - Lei & Li (2009), "The value of stop loss strategies", *Financial Services Review* 18(1):23-51。停損不提高報酬水準，移動式停損可降低風險。https://openjournals.libs.uga.edu/fsr/article/view/4933 （期刊頁已線上查證；細節取自二手摘要）
  - Kaminski & Lo (2014), "When do stop-loss rules stop losses?", *Journal of Financial Markets* 18:234-254。https://econpapers.repec.org/RePEc:eee:finmar:v:18:y:2014:i:c:p:234-254 （摘要已線上查證）
  - **反證**：Lo & Remorov（2015 工作論文）。緊的停損主要因交易成本而顯著輸給買進持有。https://www.cxoadvisory.com/equity-premium/stop-losses-on-stock-positions-in-depth （二手摘要已線上查證）
  - Han, Zhou & Zhu（SSRN 工作論文）, "Taming Momentum Crashes"。15% 停損使動能最差單月由 -49.8% 改善到約 -17%，但未扣成本，扣掉後效益可能全數消失。https://alphaarchitect.com/taming-the-momentum-roller-coaster-fact-or-fiction/ （已線上查證）
  - 台股專門的停損實證：**未知**。
- **預期效果（推論）**：無漂移隨機漫步下，20 日內純因雜訊觸及停損的機率如下。

  | 停損設定 | 日波動 1.5% | 日波動 2.5% |
  |---|---|---|
  | 固定 -8% | 約 23% | 約 47% |
  | 5 倍日標準差 | 約 26% | 約 26% |

  高波動股的停損次數與換手會下降；但單筆最大虧損變大，MaxDD 可能**變深**；Sharpe、Calmar 方向不確定。
- **過擬合風險：中**。兩個數值預先固定；只影響兩個方法，樣本內停損事件少。
- **資料**：現成。
- **可否證條件**：樣本外停損筆數沒有減少即否決；被 -8% 停損但新規則不停損的部位，之後平均報酬 ≤ 0 即否決；保留段 Calmar 下降即否決。

**S3 不提**：tech4 的 +10% 停利沒有可查證的直接文獻；調整 `KEEP_RANK`、`max_hold` 屬純參數調整，就是過擬合。

## 5. 進入階段三前必須先做的事（推論，需 Brad 同意）

這些不是假設，是讓假設「可以被否證」的前置工作。

1. **加長歷史**。動能要 253 根 K 棒才有第一個訊號，現在只抓 2 年（`papertrade/backtest.py:41`），扣掉暖機只剩約一年可測，再保留 20% 樣本外就只有兩個多月。M1、E2 還需要樣本內有跌破年線的期間。價量與 FinMind 都要拉到至少 5 年以上。
2. **補指標層**。`papertrade/summary.py:92-104` 要先有日報酬的 Sharpe、CAGR、Calmar、換手率、平均持股檔數，以及 Deflated Sharpe。
3. **股利入帳**。葛拉漢偏高殖利率股，不含息會系統性低估它（AUDIT 3.7），G1、G2、S1 與原版的比較會失真。
4. **修掉 AUDIT 已確認的錯誤**：VIX 位移一天（AUDIT 1.7）是修錯，不算假設。
5. **事先登記試驗次數**。本文件 10 個假設，加上 G1＋G2 合併版與 E3 的對照組，共 **12 次試驗**。Deflated Sharpe 以 12 計，事後不再加變體；若加了就要重算。
6. **選股池偏誤仍在（AUDIT 2.1）**。所有結果只能看「改版相對原版」的差，不能看絕對數字。動能類的改動（M1–M3、G2）受這個偏誤影響最大。

## 6. 未知事項彙整

- 回測期間大盤是否跌破年線、VIX 是否碰過 25。
- Yahoo `^TWII` 與個股可回溯的年數；Adj Close 對台股股利與配股的還原是否正確。
- 葛拉漢每天通過門檻的檔數。
- 「VIX 水位高預示後續報酬差」沒有找到已查證的支持文獻，現行 VIX ≥ 25 規則的依據不明。
- 景氣燈號係數（`papertrade/methods.py:194`）在回測中寫死紅燈，完全沒被測到，列為「未驗證參數」，本次不提假設。
- 所有預期效果的幅度都是推論，不是量測值。
