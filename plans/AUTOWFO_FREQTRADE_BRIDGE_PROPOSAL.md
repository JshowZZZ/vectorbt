# AUTOWFO × Freqtrade Bridge Proposal: Paper/Live 交叉驗證疊代計畫

> Status: **Phase A 完成，Phase B（dry-run）已實作並進入觀察期** — 2026-04-13
> Date: 2026-04-12（最初起草），2026-04-13（Phase B 更新）
> Scope: 主系統 (AUTOWFO) 與第二系統 (Freqtrade) 的介接規劃與疊代模型
> Decision state: AWF-327–330 已落地；AWF-332–337 已落地並在本機 dry-run 運行；AWF-331 parity gate 延後與 dry-run 並行觀察

---

## 0. 當前進度快照（2026-04-13 更新）

### Phase A（backtest cross-check）— 已完成

| AWF | 內容 | 狀態 |
|-----|------|------|
| AWF-327 | Signal store schema 合約 | ✅ done |
| AWF-328 | `export_signal_bundle()` + `bridge-export-signal-store` CLI | ✅ done |
| AWF-329 | `AutowfoGenericSignalStrategyLongOnly/LongShort` | ✅ done |
| AWF-330 | `bridge-cross-check` + parity report | ✅ done |
| AWF-331 | Parity gate 實際驗證（route-B mapped replay） | ✅ done（gate frozen as `review`） |
| AWF-332 | Dry-run pair format decision（route B: BTC-cross -> USDT perpetual 映射） | ✅ done |
| AWF-333 | `bridge-live-signal` + `live_signal_producer.py` | ✅ done |
| AWF-334 | `AutowfoLiveSignalStrategyLongShort` live-mode strategy | ✅ done |
| AWF-335 | `config_autowfo_dryrun.json` + dry-run deployment | ✅ done |
| AWF-336 | 背景 start/stop/watch 腳本 + log management | ✅ done |
| AWF-337 | Daily dry-run reconcile artifact | ✅ done |

煙霧測試：`bridge-export-signal-store` → 8 pairs、82 enter_long/short、`AutowfoGenericSignalStrategyLongShort`；`bridge-cross-check --prepare-only` → exit 0，config 已備妥。
目前本機 managed dry-run stack 已啟動；`artifacts/live_signal_store/live_manifest.json` 已持續更新，`artifacts/paper_dryrun/daily_summary_20260413.json` 已生成首份對帳摘要（目前尚無成交）。另外，AWF-331 已完成 route-B mapped static replay 驗證：canonical lane 與 stable top 10 全部可在 Freqtrade 2026.3 上完成 backtest，彙總 artifact 為 `artifacts/freqtrade_bridge/awf331_stable_top10_summary.json`。目前 parity gate 的實際狀態為 `review`，因為雖然 trade-count delta 僅 `0 .. -3`，但 `exact_match_ratio` / `open_match_ratio` 仍為 `0.0`。
2026-04-17 補充：已定位到造成 `open_match_ratio=0.0` 的主要原因是 FT strategy shim 直接消費 AUTOWFO signal store 內已 `fshift(1)` 的 `enter_*` / `exit_*` executable columns。adapter 現已修正為 entry 讀 raw `signal_*`，exit 讀由 `exit_*` 反推的一-bar-earlier raw exit signal；AWF-331 parity artifact 需在此契約下重跑。

### 現役最佳候選策略

| 候選 | 描述 | 現代窗口 OOS | 舊錨點複現 |
|------|------|-------------|-----------|
| AWF-324 canonical | `obv_roc+keltner_pos+oi_roc \| htf_trend:1d:20, trigger=ad, trend_any` | 0.2819%/0.3075% | ❌ time-local |
| AWF-320 canonical | `funding_gate:0.0001:-0.0001` 疊加 AWF-311 hierarchical lane | 0.2736%/0.2978% | ❌ time-local |

⚠️ 兩者皆為 time-local：在舊 anchor (2025-04) 皆為負。Paper 觀察期目標之一是判斷 time-local 是否為真實市場結構，或僅為 anchor 選取偏差。

---

> Planning note:
> - 本提案解決的是「第二引擎交叉驗證 + paper/live 執行回饋」問題，不直接解決目前 Phase 60 暴露出的 temporal robustness 問題。
> - Phase B dry-run 授權的理由：time-local 問題目前無可靠修復路徑，paper trading 提供的真實回饋資料本身就是診斷 temporal robustness 的關鍵證據。
> - 啟動 dry-run 不代表放棄 robustness-first 主線；兩條線並行。

---

## 1. 背景與動機（Why now）

AUTOWFO 目前已累積一套 trusted evidence pipeline（Phase 40–46），walk-forward leaderboard、coverage、reruns、rescore 等治理機制逐步到位。然而目前所有驗證皆**在單一引擎（vectorbt）內自證**，存在兩個結構性盲點：

1. **單引擎盲點**：vectorbt 的 fill / lookahead / 時間對齊假設未被第二套實作挑戰。Backtest 漂亮但真實世界不成立的風險，AUTOWFO 目前無法內部識別。
2. **無真實執行回饋**：沒有 paper / live 通道，leaderboard 的「最優策略」從未被 spread、funding、滑價、交易所 API 邊界條件懲罰過。

使用者需求（本次會談確認）：

- 在幣安 USDM 永續合約市場使用槓桿，進行 paper → 最小 live 的實測。
- **主系統保持為策略真相源**，執行器端代碼改動必須最小化（一次性 adapter，之後不再動）。
- 第二系統實測結果必須能**回流 AUTOWFO 做分析**，形成疊代進步的飛輪。
- 若第二系統原生具備額外研究/驗證能力，視為加分項。

---

## 2. 候選評估與選型（How we got here）

本次比較了四個開源候選與若干付費選項。關鍵評估軸（依使用者約束收斂）：

1. 外部 signal 注入友善度
2. Binance USDM 永續 + 槓桿支援
3. Paper = Live 同代碼路徑
4. Live 完全免費開源
5. 執行器端改動量（核心約束）
6. Python 生態契合

| 候選 | 結果 | 關鍵原因 |
|---|---|---|
| **Freqtrade** | 🥇 選定 | 六軸全綠；`dry-run` 與 live 同代碼路徑；signal 注入可用 adapter 一次性寫完；GPL 完全免費 |
| Hummingbot | ❌ | 架構定位於 market making / arbitrage；directional signal 跟單逆著設計走 |
| OctoBot | ❌ | Tentacle 另一套 DSL；futures 支援相對薄；paper 與 live 路徑不一致 |
| Jesse | ❌ | Live 屬 Jesse Plus 付費，違反全開源約束；可保留作為 backtest 對拍工具 |

付費選項評估後結論：**不為付費而付費**。Jesse Plus 與 Freqtrade 重疊高、QuantConnect 對幣本位永續 overkill、NautilusTrader 目前為 overkill 備案。唯一值得考慮的付費補強是 **Tardis.dev**（機構級 tick/orderbook 歷史資料），但屬於資料層，不取代執行器。

Freqtrade 已知缺點已盤點（見 §6 風險清單），主要集中於「futures 槓桿/保證金/funding 這些交易所邊界細節」，這是 paper 期必須盯緊的紅線，而非架構否決理由。

---

## 3. 目標（What success looks like）

本次整合要達成的四個可驗證目標：

1. **策略真相源單一化**：AUTOWFO 擁有策略邏輯；Freqtrade 僅執行；不出現「回測公式 A、live 公式 B」的漂移。
2. **第二引擎交叉驗證**：每個 AUTOWFO leaderboard entry 能在 Freqtrade 獨立引擎上重跑，PnL / Sharpe 落差在可控閾值內方可晉級。
3. **Paper → Live 通道**：最小資金單位 Binance USDM live 部署能力，具備 margin / leverage / SL 對帳機制。
4. **疊代飛輪閉環**：paper / live 實測資料回流 AUTOWFO，校準 fill / spread / funding penalty，影響下一輪 walk-forward 搜尋空間。

---

## 4. 核心架構（Conceptual model）

### 4.1 職責切分

- **AUTOWFO**：策略真相源。持有指標計算、訊號規則、sizing、槓桿決定。
- **Freqtrade**：執行真相源。持有下單、交易所 API、margin 計算、SL/ROI 執行、paper/live 切換。
- **Bridge**：Signal Schema + Signal Store（先 Parquet，之後可升 Redis）。

### 4.2 四層晉級 Gate

```text
Tier 1: AUTOWFO walk-forward trusted leaderboard     (現有)
          ↓  轉譯 + 獨立引擎重跑
Tier 2: Freqtrade backtest cross-check 通過
          ↓  Hyperopt 微調執行層參數
Tier 3: Freqtrade dry-run paper 4–8 週通過
          ↓  最小資金
Tier 4: Binance USDM live
```

### 4.3 三條回饋迴路

| 頻率 | 回饋內容 | 出口 |
|---|---|---|
| 日 | margin / leverage / SL 執行對帳差異 | 修 adapter 或鎖 Freqtrade 版本 |
| 週 | paper vs backtest PnL 落差 | 更新 `slippage_model` |
| 月 | paper + live 實測分佈 | 進 AUTOWFO walk-forward 作為真實 penalty |

### 4.4 Hyperopt 的合理角色

為避免 Freqtrade Hyperopt 與 AUTOWFO walk-forward 搶同一塊搜尋空間，明確切兩層：

| 參數類別 | 由誰優化 |
|---|---|
| 策略結構 / 訊號參數（指標窗口、閾值、regime） | **AUTOWFO walk-forward** 獨佔 |
| 執行層參數（`stoploss`、ROI、trailing、entry offset、stake curve、leverage） | **Freqtrade Hyperopt** |
| 收斂驗證（可選） | Hyperopt 當第三方，對同策略跑，看最優參數是否與 AUTOWFO 結果收斂——不收斂即 robustness 警訊 |

### 4.5 本機 Repo 佈局與 Git 邊界

- 本機固定路徑：`E:/Project/freqtrade`
- 佈局原則：Freqtrade 保持為 `E:/Project/vectorbt-master` 的 sibling repo，不做 nested repo、不做 vendor copy。
- Git 邊界：AUTOWFO 與 Freqtrade 永遠分開 commit / push；若同一項 bridge 工作改到兩邊，應在規劃文件中互記兩邊 commit SHA。
- 目前已落地的本機狀態：官方 Freqtrade repo 已 clone 到 `E:/Project/freqtrade`，官方 remote 名稱採 `upstream`，本地工作基線切到 `stable`。
- 目前已落地的安裝狀態：已建立專用環境 `E:/Project/freqtrade/.venv`，並以 `freqtrade -V` 與 `freqtrade list-exchanges` 驗證 CLI 可用。
- Remote 原則：
    - 若僅需跟官方更新：本機可先用官方 repo 作為 fetch remote。
    - 若需上傳自有 bridge 修改：改為「個人 fork = `origin`、官方 repo = `upstream`」模型。
- 分支原則：保留一條乾淨的 upstream-tracking base branch，再用獨立 bridge feature branch 疊加本地修改。

---

## 5. 階段展開（Phased plan — schedulable but not started）

### Phase A — 最小 cross-check slice（唯一建議的第一個啟動範圍）

目標：只建立 Tier 1 → Tier 2 的最小交叉驗證能力，先驗證 signal parity，不把 paper/live 複雜度一次背進來。

1. **Signal Schema 定版**：`pair / timeframe / candle_ts / entry_long / entry_short / exit_long / exit_short / stake_pct / leverage / sl_price / tp_price / strategy_id / run_id / expires_at / signal_version`。
2. **AUTOWFO `signal_exporter`**：從 frozen leaderboard entry 匯出可回放的 signal store（先 Parquet）。
3. **Freqtrade `GenericSignalStrategy`**（薄殼）讀取 signal store，僅做 staleness gate、欄位映射與執行層透傳，不引入額外策略判斷。
4. **Cross-check runner**：固定同一期間、同一 pair、同一 fee/slippage 前提，執行 `freqtrade backtesting` 並輸出對拍結果。
5. **Parity verdict artifact**：產出可機讀差異報告，至少包含 PnL、trade count、max DD、entry/exit timestamp 偏差摘要。

Phase A 的完成條件：

- 能用一個 frozen AUTOWFO lane 產出 signal store。
- Freqtrade 可在不改策略語意的前提下完成重跑。
- 已定義明確 pass/fail parity gate。
- 尚未引入 live、paper、Hyperopt、reconcile、tier state machine。

### Phase B — Dry-Run 架構（已授權，2026-04-13 啟動）

> 決策：跳過 AWF-331 完整 parity gate（需要 FT OHLCV datadir）而直接進入 dry-run。AWF-331 降為與 dry-run 並行觀察項。理由：dry-run 本身就是比 backtest cross-check 更有效的真實信號，paper 結果即為 parity 證據。

Dry-run 的核心架構與 Phase A backtest cross-check **根本不同**：

| 面向 | Phase A（backtest） | Phase B（dry-run） |
|------|---------------------|-------------------|
| 訊號來源 | 靜態凍結歷史 bundle（180d 回測） | 每 2h 滾動計算最新 K 棒訊號 |
| 策略讀取方式 | `bot_start()` 一次性載入全部歷史訊號 | 每個 K 棒呼叫時重新讀取最新訊號檔 |
| FT 模式 | `freqtrade backtesting` | `freqtrade trade --dry-run` |
| 訊號時間對齊 | 已 fshift(1)，FT 直接對應 timestamp | AUTOWFO 寫「原始訊號」，FT 自然取下一根開盤 |
| 交易對格式 | `LTC/BTC`（BTC-cross） | `LTC/USDT:USDT` 等 USDT perpetual，並在策略層 reverse-map 回 BTC-cross 訊號 |

#### Phase B 所需的五個新元件

**B1 — 訊號對格式決策（AWF-332）**

AUTOWFO 候選皆使用 BTC-cross pairs（`LTC/BTC`, `LINK/BTC`, ...）。Binance USDM 永續期貨格式是 `LTC/USDT:USDT`，BTC-cross pairs 在 USDM 期貨中**不存在**。三個可行路徑：

| 路徑 | 描述 | 代價 |
|------|------|------|
| **a. Spot BTC-stake** | Binance Spot，stake=BTC，BTC-cross 白名單，leverage=1x 或無槓桿 | 最小改動；無 USDM futures；無槓桿 |
| **b. USDT pair 映射** | `LTC/BTC` 訊號 → `LTC/USDT:USDT` 下單（接受 basis 風險） | 中等；需在 Freqtrade strategy 做 execution/source pair 映射 |
| **c. 重新跑 AUTOWFO USDT pairs** | 換 10 个 alt/USDT pairs 重新跑 walk-forward | 工作量大；但與 USDM futures 完美對齊 |

**Phase B 決策**：採用 **路徑 b（USDT pair 映射）**。AUTOWFO 保持 BTC-cross 訊號真相源，Freqtrade 執行層把 source pair 對應到 Binance USDM `*/USDT:USDT` pairs；目前實際 dry-run 白名單已配置 8 組 source/execution pairs。

**B2 — 活訊號生產 daemon（AWF-333）**

已落地的新元件 `autowfo/live_signal_producer.py`：
- 每 2h 在 K 棒關閉後喚醒（one-shot 或 interval loop）
- 從 frozen bundle manifest 還原選定 lane，並以 rolling-window 模式重建最近訊號
- 寫入 `artifacts/live_signal_store/current_signals.parquet`（附 `current_signals.csv` 備份）
- 寫入 `artifacts/live_signal_store/live_manifest.json`（含 source bundle、last bar、rows、pairs）

不寫入「歷史」——只保留最近 N 根 K 棒（避免檔案無限增長），N = max_hold + 1 即可。

**B3 — Freqtrade LiveMode Strategy 變體（AWF-334）**

修改 `scripts/freqtrade_generic_signal_strategy.py`，加入 live-mode 邏輯：
- `bot_start()` 改為只設定 manifest path，不一次性載入全部訊號
- `populate_indicators()` 每次呼叫時重新讀取 `current_signals.parquet`
- 加入 staleness gate：若 `last_bar_ts` 相對於最新 candle timestamp 早超過 1.5 根 K 棒，回傳全空訊號
- 使用 `signal_long` / `signal_short` 欄位（非 fshift 後的 `enter_long`），讓 FT 的延遲執行自然處理時間偏移
- exit path 同步遵循 FT next-open 契約：由 AUTOWFO `exit_*` executable 欄位反推 raw exit signal，再交給 FT 消費
- 以 reverse mapping 將 execution pair（如 `LTC/USDT:USDT`）還原回 source pair（如 `LTC/BTC`）

新 class：`AutowfoLiveSignalStrategyLongOnly`、`AutowfoLiveSignalStrategyLongShort`（與 backtest replay variant 共存）

**B4 — Freqtrade Dry-Run Config（AWF-335）**

在 `E:/Project/freqtrade/user_data/` 建立：
- `config_autowfo_dryrun.json`（dry_run=true，futures + isolated + USDT stake，timeframe=2h，autowfo_signal_manifest 與 pair mapping）

完整 config 需包含：
```json
{
    "dry_run": true,
    "trading_mode": "futures",
    "margin_mode": "isolated",
    "stake_currency": "USDT",
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.95,
    "timeframe": "2h",
    "exchange": { "name": "binance", ... },
    "pairlists": [{ "method": "StaticPairList" }],
    "strategy_path": "E:/Project/vectorbt-master/scripts/",
    "autowfo_signal_manifest": ".../live_signal_store/live_manifest.json",
    "autowfo_pair_mapping": { "LTC/BTC": "LTC/USDT:USDT" },
    "max_open_trades": 8
}
```

實作上不再需要把 strategy 複製到 `user_data/strategies/`；目前直接由 `strategy_path` 指向本 repo 的 `scripts/`。為符合 Binance market order 驗證，config 另已修正為 `price_side="other"` 並改用 orderbook pricing。

**B5 — 背景執行與日常對帳（AWF-336 + AWF-337）**

- 啟動腳本：`scripts/start_live_signal_producer.ps1`、`scripts/start_ft_dryrun.ps1`
- 停止 / 觀察腳本：`scripts/stop_live_signal_producer.ps1`、`scripts/stop_ft_dryrun.ps1`、`scripts/watch_ft_dryrun.ps1`
- Runtime metadata：`artifacts/paper_dryrun/runtime/`；logs：`artifacts/paper_dryrun/logs/`
- 每日對帳：`autowfo/paper_dryrun_reconcile.py` + `bridge-dryrun-reconcile` 讀取 FT trade DB（SQLite `tradesv3.dryrun.sqlite`），輸出每日 paper 摘要 → `artifacts/paper_dryrun/daily_summary_YYYYMMDD.json`
- 每週 retro 觸發 AUTOWFO 端的 slippage_model 候選更新

### Phase C — Paper 觀察期（4–8 週）

1. Dry-run 啟動後最小觀察期 **4 週**。
2. 週度 retro：paper PnL vs AUTOWFO 預估 → 計算 execution drift。
3. 若 paper 穩定（max DD < 15%、任意週虧損 < 5%），才開啟 Phase D live 討論。

### Phase D — 小 live + 飛輪

1. 僅在 paper 穩定後，才開放最小 notional live。
2. `tier` 晉級/降級狀態機延後到此階段前後再實作，避免治理層先於證據層落地。
3. 月度 recalibration 再把 paper/live 實測資料正式回灌 AUTOWFO penalty。

---

## 6. 已知風險與紅線（Freqtrade 實況盤點）

自 GitHub issue 與社群回饋彙整，與本架構相關的 Freqtrade 風險：

| # | 風險 | 對本架構的影響 | 緩解 |
|---|---|---|---|
| 1 | Futures 槓桿/保證金計算曾有 bug（2025.11.2 才修 `set-leverage` follow-up；短倉餘額顯示錯誤） | Freqtrade 自算 margin，AUTOWFO 無法覆蓋 | 版本鎖定、paper 期三方對帳、避免 isolated/cross 混用 |
| 2 | Binance funding rate 不再固定 8h，歷史資料有 gap | 影響 funding cost 納入訊號 | Funding 成本由 **AUTOWFO 端**自抓自算，不信 Freqtrade funding 資料 |
| 3 | Binance stoploss 行為歷史上反覆修 bug | 若 adapter 傳 `sl_price` 交給 Freqtrade 執行 SL，行為不保證 | 訊號端同時帶 SL 與 emergency exit；或 AUTOWFO 端算 exit signal 不依賴 Freqtrade SL |
| 4 | 安裝環境相依地獄（Mac ARM64 須 Docker） | 部署摩擦 | 直接走官方 Docker image，禁止 native pip install |
| 5 | `custom_exit` vs `populate_exit_trend` 優先級 / 內部 state machine 可能覆寫外部 signal | Adapter 若設計不當，Freqtrade 會用自有邏輯蓋掉 AUTOWFO 訊號 | Adapter 設計階段必須寫 golden test 驗證 |
| 6 | `stake_amount` / `max_open_trades` 是全局設定 | 多策略並行時無法 per-strategy 資金池 | Adapter 層或 AUTOWFO 端自行處理資金分配 |
| 7 | 每月 release、API 偶有破壞性變更 | 升級風險 | 鎖版本 + CI 回測驗證 + 升級前 sandbox |

**對本架構不是風險的 Freqtrade 常見吐槽**（記錄免得重複討論）：

- Hyperopt 過擬合 → 僅用於執行層參數，搜尋空間小，且非策略發現。
- 公開策略庫普遍不賺 → 本架構不使用社群策略，AUTOWFO 自研。
- Python 學習曲線 → 已是 Python shop。

---

## 7. 一個典型「週」的操作情境

| 日 | 動作 | 角色 |
|---|---|---|
| 一 | AUTOWFO walk-forward 跑完 → 5 候選進 Tier 1 | 使用者 review |
| 二 | Agent 觸發 Freqtrade cross-check backtest（5 個） | Agent |
| 三 | 3 通過；2 個 PnL 落差超閾值，Agent 產歸因報告 | 使用者 review 歸因 |
| 四 | 3 通過的跑 Hyperopt（僅執行層參數） | Agent |
| 五 | 選 2 個進 paper dry-run；同時既有 paper 策略週度 retro | 使用者決定上/下架 |
| 持續 | Paper 每日 `reconcile` + 每週 `slippage_model` 更新 | Agent 自動 |
| 月末 | AUTOWFO recalibration；paper 優等生 → 小 live | 使用者決定撥款 |

---

## 8. AWF 編號規劃（更新至 2026-04-13）

| 編號 | 範圍 | 狀態 |
|------|------|------|
| AWF-327 | Signal Schema contract | ✅ done |
| AWF-328 | `signal_exporter` + Parquet signal store | ✅ done |
| AWF-329 | Freqtrade `GenericSignalStrategy` replay adapter（backtest） | ✅ done |
| AWF-330 | Freqtrade backtest cross-check runner + parity report | ✅ done |
| AWF-331 | Parity gate freeze + first frozen-lane validation | ✅ done（route-B mapped replay 已驗證；gate 狀態目前為 `review`） |
| AWF-332 | 交易對格式決策 + 確認 dry-run pair 白名單（route B: BTC-cross -> USDT perpetual） | ✅ done |
| AWF-333 | 活訊號生產 daemon（`live_signal_producer.py`）+ 每 2h 滾動計算 | ✅ done |
| AWF-334 | `AutowfoLiveSignalStrategyLongShort`（live-mode variant 含 staleness gate） | ✅ done |
| AWF-335 | Freqtrade dry-run config（`config_autowfo_dryrun.json`）+ strategy 部署 | ✅ done |
| AWF-336 | 背景執行腳本（start/stop/watch）+ 日誌管理 | ✅ done |
| AWF-337 | 每日對帳工具（FT trade DB → `paper_dryrun` artifact） | ✅ done |

---

## 9. 下一步決策點（2026-04-13 更新）

Phase B 已進入觀察期。現階段優先序如下：

1. **持續觀察 dry-run stack**：保持 `live_signal_producer` 與 `freqtrade trade --dry-run` 長時間運行，等待第一批真實 paper trades 寫入 `tradesv3.dryrun.sqlite`。

2. **每日對帳**：執行 `bridge-dryrun-reconcile`，追蹤 entry/exit signal match rate、execution drift、pair coverage 與每日盈虧。

3. **週度 retro**：對照 AUTOWFO 預估與 paper 結果，判斷 time-local 現象是否延續，並同步追蹤 AWF-331 凍結後暴露出的 timestamp-level parity drift。

4. **操作安全**：若 dry-run 使用的 Binance read-only key 曾在不安全通道曝光，應先輪替後再延長觀察期。

**已定案的部署前提**：
- Dry-run pair format：route B，BTC-cross 訊號映射到 USDT perpetual execution pairs
- 初始 dry-run config：futures + isolated + USDT + `AutowfoLiveSignalStrategyLongShort`
- 背景運行方式：PowerShell start/stop/watch scripts + `artifacts/paper_dryrun/` runtime/logs



## 10. 非目標（What this plan explicitly is NOT）

- 不是把 AUTOWFO 重寫或改架構。
- 不是用 Freqtrade 取代 vectorbt 作為回測引擎。
- 不是採用 Freqtrade 的公開策略庫。
- 不是追求 tick 級 / HFT 執行——本架構以 bar-based walk-forward 為前提。
- 不是 live auto-trade 全自動化——live 撥款仍需使用者決定。
