import { initTabs } from "/static/js/tabs.js";
import { initBatchTab } from "/static/js/batch.js";
import { initCoverageTab } from "/static/js/coverage.js";
import { initDashboardTab } from "/static/js/dashboard.js";

    const jq = window.jQuery;
    const hasDataTables = !!(jq && jq.fn && jq.fn.dataTable);
    const LABELS = {
      exchange: '交易所',
      base_symbol: '基準幣對',
      trade_symbols_key: '交易幣對集合',
      timeframe: '時間框架',
      data_days: '資料天數',
      regime_name: '策略型態',
      regime_type: '訊號類型',
      vol_mode: '波動條件',
      regime_rsi_long: 'RSI 回歸多頭門檻',
      regime_rsi_short: 'RSI 回歸空頭門檻',
      filter_name: '指標組合',
      indicator_list: '指標清單',
      indicator_count: '指標數量',
      vol_lookback: '波動回看(根)',
      vol_z: '波動 Z 分數門檻',
      mom_lookback: '動能回看(根)',
      trade_mom_lookback: '交易幣動能回看(根)',
      tp_stop: '獲利%出場',
      sl_stop: '止損',
      max_hold: '最長持有(根)',
      rsi_window: 'RSI 週期',
      rsi_long: 'RSI 多頭門檻',
      rsi_short: 'RSI 空頭門檻',
      bb_width: '布林帶寬度門檻',
      atr_ratio: 'ATR/價格門檻',
      ma_fast: 'MA 快線',
      ma_slow: 'MA 慢線',
      macd_hist_ratio: 'MACD 柱狀比率門檻',
      stoch_long: 'KD 多頭門檻',
      stoch_short: 'KD 空頭門檻',
      obv_lookback: 'OBV 回看(根)',
      volume_lookback: '量能回看(根)',
      volume_z: '量能 Z 分數門檻',
      roc_lookback: 'ROC 回看(根)',
      roc_threshold: 'ROC 門檻',
      mfi_long: 'MFI 多頭門檻',
      mfi_short: 'MFI 空頭門檻',
      cmf_lookback: 'CMF 回看(根)',
      cmf_threshold: 'CMF 門檻',
      vroc_lookback: '量能變化率 回看(根)',
      vroc_threshold: '量能變化率 門檻',
      ad_lookback: 'A/D 回看(根)',
      oos_avg_total_return_pct: '驗證平均總報酬(%)',
      oos_avg_win_rate_pct: '驗證平均勝率(%)',
      oos_avg_avg_trade_pct: '驗證平均每筆(%)',
      oos_avg_max_drawdown_pct: '驗證平均最大回撤(%)',
      oos_avg_position_coverage_pct: '驗證平均持倉覆蓋率(%)',
      oos_avg_total_trades: '驗證平均交易筆數',
      oos_min_total_trades: '驗證最小交易筆數',
      oos_avg_daily_trades: '驗證平均每日交易次數',
        oos_avg_hold_hours: '驗證平均持倉(小時)',
        avg_total_return_pct: '平均總報酬(%)',
        avg_win_rate_pct: '平均勝率(%)',
        avg_avg_trade_pct: '平均每筆(%)',
        avg_max_drawdown_pct: '平均最大回撤(%)',
        avg_position_coverage_pct: '平均持倉覆蓋率(%)',
        avg_daily_trades: '平均每日交易次數',
        avg_total_trades: '平均總交易筆數',
        min_total_trades: '最小總交易筆數',
        avg_hold_hours: '平均持倉(小時)',
        indicator_tags: '指標種類',
        indicator_params: '指標參數摘要',
        return_pct: '總報酬(%)',
        max_drawdown_pct: '最大回撤(%)',
        avg_daily_trades_display: '平均每日交易',
        avg_hold_hours_display: '平均持倉(小時)',
        win_rate_pct: '勝率(%)',
        data_start: '資料開始',
        data_end: '資料結束',
        timestamp_utc: 'UTC 時間',
        run_id: '執行編號',
        plot_symbol: '圖表幣對',
      report_file: '報告檔案'
    };

    const NUM_COLS = new Set([
      'vol_lookback','vol_z','mom_lookback','trade_mom_lookback','tp_stop','sl_stop','max_hold',
      'rsi_window','rsi_long','rsi_short','bb_width','atr_ratio','ma_fast','ma_slow',
      'macd_hist_ratio','stoch_long','stoch_short','obv_lookback','volume_lookback','volume_z',
      'roc_lookback','roc_threshold','mfi_long','mfi_short','cmf_lookback','cmf_threshold',
      'vroc_lookback','vroc_threshold','ad_lookback','indicator_count',
      'oos_avg_total_return_pct','oos_avg_win_rate_pct','oos_avg_avg_trade_pct','oos_avg_max_drawdown_pct',
      'oos_avg_position_coverage_pct','oos_avg_total_trades','oos_min_total_trades','oos_avg_daily_trades',
        'oos_avg_hold_hours',
        'avg_total_return_pct','avg_win_rate_pct','avg_avg_trade_pct','avg_max_drawdown_pct',
        'avg_position_coverage_pct','avg_daily_trades','avg_total_trades','min_total_trades','avg_hold_hours'
      ]);

      const TOP_COLS = [
        'timeframe',
        'data_days',
        'regime_name',
        'indicator_tags',
        'indicator_params',
        'return_pct',
        'max_drawdown_pct',
        'avg_daily_trades_display',
        'avg_hold_hours_display',
        'win_rate_pct'
      ];

      const COMBO_COLS = TOP_COLS;

    const LB_COLS = [
      'timestamp_utc','run_id','plot_symbol','timeframe','data_days',
      'oos_avg_total_return_pct','avg_total_return_pct','avg_daily_trades','avg_hold_hours','min_total_trades','report_file'
    ];

    function parseNumber(val) {
      if (val === null || val === undefined) return null;
      if (typeof val === 'string' && val.trim() === '') return null;
      const num = Number(val);
      if (!Number.isFinite(num)) return null;
      return num;
    }

    function formatNumber(val) {
      const num = parseNumber(val);
      if (num === null) return '';
      return num.toFixed(4).replace(/\.0+$/, '');
    }

    function decodeHtml(text) {
      if (!text) return '';
      const el = document.createElement('textarea');
      el.innerHTML = text;
      return el.value;
    }

    function escapeHtml(text) {
      if (text === null || text === undefined) return '';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    const PARAM_ORDER = [
      'vol_lookback','vol_z','mom_lookback','trade_mom_lookback',
      'rsi_window','rsi_long','rsi_short',
      'bb_width','atr_ratio','ma_fast','ma_slow','macd_hist_ratio',
      'stoch_long','stoch_short','obv_lookback','volume_lookback','volume_z',
      'roc_lookback','roc_threshold','mfi_long','mfi_short',
      'cmf_lookback','cmf_threshold','vroc_lookback','vroc_threshold','ad_lookback',
      'tp_stop','sl_stop','max_hold'
    ];

    const PARAM_SHORT = {
      vol_lookback: 'vol_lb',
      vol_z: 'vol_z',
      mom_lookback: 'mom_lb',
      trade_mom_lookback: 'trade_mom_lb',
      rsi_window: 'rsi',
      rsi_long: 'rsiL',
      rsi_short: 'rsiS',
      bb_width: 'bb',
      atr_ratio: 'atr',
      ma_fast: 'maF',
      ma_slow: 'maS',
      macd_hist_ratio: 'macd',
      stoch_long: 'stochL',
      stoch_short: 'stochS',
      obv_lookback: 'obv',
      volume_lookback: 'volu_lb',
      volume_z: 'volu_z',
      roc_lookback: 'roc_lb',
      roc_threshold: 'roc',
      mfi_long: 'mfiL',
      mfi_short: 'mfiS',
      cmf_lookback: 'cmf_lb',
      cmf_threshold: 'cmf',
      vroc_lookback: 'vroc_lb',
      vroc_threshold: 'vroc',
      ad_lookback: 'ad_lb',
      tp_stop: 'tp',
      sl_stop: 'sl',
      max_hold: 'hold'
    };

    const PARAM_EXCLUDE_PREFIXES = [
      'oos_','avg_','min_','max_','total_','position_','win_','data_',
      'timestamp','run_id','plot_','report_','trade_symbols','base_symbol','exchange','timeframe',
      'regime_','vol_mode','filter_name','indicator_list','indicator_count'
    ];

    function isParamLikeKey(key) {
      if (!key) return false;
      if (PARAM_ORDER.includes(key)) return true;
      const lower = key.toLowerCase();
      if (PARAM_EXCLUDE_PREFIXES.some(p => lower.startsWith(p))) return false;
      return /(lookback|window|threshold|ratio|_long|_short)$/.test(lower);
    }

    function collectParamPairs(row) {
      const pairs = [];
      const seen = new Set();
      PARAM_ORDER.forEach(key => {
        const val = row[key];
        if (val !== null && val !== undefined && val !== '') {
          pairs.push([key, val]);
          seen.add(key);
        }
      });
      Object.keys(row).forEach(key => {
        if (seen.has(key)) return;
        if (!isParamLikeKey(key)) return;
        const val = row[key];
        if (val === null || val === undefined || val === '') return;
        pairs.push([key, val]);
        seen.add(key);
      });
      return pairs;
    }

    function getIndicatorTags(row) {
      const raw = row.indicator_list || row.filter_name || '';
      const decoded = decodeHtml(String(raw));
      if (!decoded) return [];
      const parts = decoded.split(/[,+;|\/]+/).map(s => s.trim()).filter(Boolean);
      if (!parts.length) return [decoded.trim()];
      const unique = [];
      const seen = new Set();
      parts.forEach(p => {
        const clean = p.replace(/[()\[\]]/g, '').trim();
        if (!clean || seen.has(clean)) return;
        seen.add(clean);
        unique.push(clean);
      });
      return unique;
    }

    function buildIndicatorTagsCell(td, row) {
      const tags = getIndicatorTags(row);
      if (!tags.length) {
        td.textContent = '';
        return;
      }
      td.classList.add('text-left');
      const container = document.createElement('div');
      container.className = 'tag-list';
      const visible = tags.slice(0, 6);
      visible.forEach(tag => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = tag;
        container.appendChild(span);
      });
      const remaining = tags.length - visible.length;
      if (remaining > 0) {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = `+${remaining}`;
        container.appendChild(span);
      }
      td.appendChild(container);
    }

    function buildParamSummaryCell(td, row) {
      const pairs = collectParamPairs(row);
      if (!pairs.length) {
        td.textContent = '';
        return;
      }
      td.classList.add('text-left');
      const text = pairs.map(([key, val]) => {
        const label = PARAM_SHORT[key] || key;
        return `${label}=${formatNumber(val)}`;
      }).join(', ');
      const display = text.length > 120 ? `${text.slice(0, 117)}...` : text;
      const div = document.createElement('div');
      div.className = 'param-summary';
      div.textContent = display;
      if (display !== text) div.title = text;
      td.appendChild(div);
    }

    function getColumnDisplayValue(row, col) {
      if (col === 'indicator_tags') {
        return getIndicatorTags(row).join(' + ');
      }
      if (col === 'indicator_params') {
        const pairs = collectParamPairs(row);
        if (!pairs.length) return '';
        return pairs.map(([key, val]) => {
          const label = PARAM_SHORT[key] || key;
          return `${label}=${formatNumber(val)}`;
        }).join(', ');
      }
      if (col === 'return_pct') {
        const val = pickMetric(row, ['oos_avg_total_return_pct', 'avg_total_return_pct', 'total_return_pct']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'max_drawdown_pct') {
        const val = pickMetric(row, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct', 'max_drawdown_pct']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'avg_daily_trades_display') {
        const val = pickMetric(row, ['oos_avg_daily_trades', 'avg_daily_trades']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'avg_hold_hours_display') {
        const val = pickMetric(row, ['oos_avg_hold_hours', 'avg_hold_hours']);
        return val === null ? '' : formatNumber(val);
      }
      if (col === 'win_rate_pct') {
        const val = pickMetric(row, ['oos_avg_win_rate_pct', 'avg_win_rate_pct', 'win_rate_pct']);
        return val === null ? '' : formatNumber(val);
      }
      const raw = row[col] ?? '';
      if (NUM_COLS.has(col)) {
        return formatNumber(raw);
      }
      return decodeHtml(raw);
    }

    function pickMetric(row, keys) {
      for (const key of keys) {
        const num = parseNumber(row[key]);
        if (num !== null) return num;
      }
      return null;
    }

    function buildDetailElement(row) {
      const wrapper = document.createElement('div');
      wrapper.className = 'detail-wrap';

      const grid = document.createElement('div');
      grid.className = 'detail-grid';

      const pairs = collectParamPairs(row);
      const detailItems = [];

      if (row.indicator_list || row.filter_name) {
        detailItems.push(['指標組合', decodeHtml(row.indicator_list || row.filter_name)]);
      }

      pairs.forEach(([key, val]) => {
        const label = LABELS[key] || key;
        detailItems.push([label, formatNumber(val)]);
      });

      Object.keys(row).forEach(key => {
        if (PARAM_ORDER.includes(key)) return;
        if (key === 'indicator_list' || key === 'filter_name') return;
        if (TOP_COLS.includes(key) || COMBO_COLS.includes(key)) return;
        if (key.startsWith('oos_') || key.startsWith('avg_')) return;
        const val = row[key];
        if (val === null || val === undefined || val === '') return;
        const label = LABELS[key] || key;
        detailItems.push([label, decodeHtml(val)]);
      });

      if (!detailItems.length) {
        const empty = document.createElement('div');
        empty.textContent = '沒有額外參數';
        wrapper.appendChild(empty);
        return wrapper;
      }

      detailItems.forEach(([label, value]) => {
        const item = document.createElement('div');
        item.className = 'detail-item';
        const labelSpan = document.createElement('span');
        labelSpan.className = 'detail-label';
        labelSpan.textContent = `${label}:`;
        const valueSpan = document.createElement('span');
        valueSpan.className = 'detail-value';
        valueSpan.textContent = value;
        item.appendChild(labelSpan);
        item.appendChild(valueSpan);
        grid.appendChild(item);
      });

      wrapper.appendChild(grid);
      return wrapper;
    }

    async function refreshTests() {
      try {
        const res = await fetch('/tests/status.json', { cache: 'no-store' });
        const data = await res.json();
        const mappings = {
          testStage: data.stage ?? '',
          testElapsed: data.elapsed ?? '',
          testReturnCode: data.return_code ?? ''
        };
        for (const [id, val] of Object.entries(mappings)) {
          const el = document.getElementById(id);
          if (el) el.textContent = val;
        }
        const startedEl = document.getElementById('testStarted');
        if (startedEl) {
          const raw = data.started;
          if (raw) {
            const parsed = Date.parse(raw);
            startedEl.textContent = Number.isNaN(parsed) ? raw : new Date(parsed).toLocaleString();
          } else {
            startedEl.textContent = '';
          }
        }
        const updatedEl = document.getElementById('testUpdated');
        if (updatedEl) {
          const raw = data.updated;
          if (raw) {
            const parsed = Date.parse(raw);
            updatedEl.textContent = Number.isNaN(parsed) ? raw : new Date(parsed).toLocaleString();
          } else {
            updatedEl.textContent = '';
          }
        }
        const logRes = await fetch('/tests/log-tail.txt', { cache: 'no-store' });
        if (logRes.ok) {
          const logText = await logRes.text();
          const logEl = document.getElementById('testLog');
          if (logEl) logEl.textContent = logText;
        }
      } catch (e) {}
    }

    function buildTable(tableId, rows, columns, options = {}) {
      const table = document.getElementById(tableId);
      const thead = table.querySelector('thead');
      const tbody = table.querySelector('tbody');
      thead.innerHTML = '';
      tbody.innerHTML = '';
      const cols = columns && columns.length ? columns : (rows.length ? Object.keys(rows[0]) : []);
      const tr = document.createElement('tr');
      cols.forEach(col => {
        const th = document.createElement('th');
        th.textContent = LABELS[col] || col;
        tr.appendChild(th);
      });
      thead.appendChild(tr);

      rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.classList.add('row-expand');
        tr.dataset.row = JSON.stringify(row);
        cols.forEach(col => {
          const td = document.createElement('td');
          if (col === 'indicator_tags') {
            buildIndicatorTagsCell(td, row);
          } else if (col === 'indicator_params') {
            buildParamSummaryCell(td, row);
          } else if (col === 'return_pct') {
            const val = pickMetric(row, ['oos_avg_total_return_pct', 'avg_total_return_pct', 'total_return_pct']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
              if (val > 0) td.classList.add('pos');
              if (val < 0) td.classList.add('neg');
            }
          } else if (col === 'max_drawdown_pct') {
            const val = pickMetric(row, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct', 'max_drawdown_pct']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
              if (val > 0) td.classList.add('neg');
              if (val < 0) td.classList.add('pos');
            }
          } else if (col === 'avg_daily_trades_display') {
            const val = pickMetric(row, ['oos_avg_daily_trades', 'avg_daily_trades']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
            }
          } else if (col === 'avg_hold_hours_display') {
            const val = pickMetric(row, ['oos_avg_hold_hours', 'avg_hold_hours']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
            }
          } else if (col === 'win_rate_pct') {
            const val = pickMetric(row, ['oos_avg_win_rate_pct', 'avg_win_rate_pct', 'win_rate_pct']);
            if (val !== null) {
              td.textContent = formatNumber(val);
              td.setAttribute('data-order', String(val));
              if (val > 0) td.classList.add('pos');
            }
          } else {
            const raw = row[col] ?? '';
            if (NUM_COLS.has(col)) {
              const num = Number(raw);
              td.textContent = formatNumber(raw);
              if (!Number.isNaN(num)) {
                td.setAttribute('data-order', String(num));
                if (num > 0) td.classList.add('pos');
                if (num < 0) td.classList.add('neg');
              }
            } else {
              td.textContent = decodeHtml(raw);
            }
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });

      if (hasDataTables) {
        if (jq.fn.dataTable.isDataTable(table)) {
          jq(table).DataTable().destroy();
        }
        const defaultOrder = [];
        const returnIdx = cols.indexOf('return_pct');
        const ddIdx = cols.indexOf('max_drawdown_pct');
        if (returnIdx >= 0) defaultOrder.push([returnIdx, 'desc']);
        if (ddIdx >= 0) defaultOrder.push([ddIdx, 'asc']);
        const dt = jq(table).DataTable({
          pageLength: 25,
          order: defaultOrder,
          lengthMenu: [[25, 50, 100, 200], [25, 50, 100, 200]]
        });
        if (options.rowDetails) {
          jq(table).find('tbody').off('click', 'tr').on('click', 'tr', function () {
            if (this.classList.contains('child')) return;
            const row = dt.row(this);
            const node = row.node();
            if (!node || !node.dataset.row) return;
            let rowData = null;
            try {
              rowData = JSON.parse(node.dataset.row);
            } catch (e) {
              return;
            }
            if (row.child.isShown()) {
              row.child.hide();
              this.classList.remove('shown');
            } else {
              row.child(buildDetailElement(rowData)).show();
              this.classList.add('shown');
            }
          });
        }
      }
    }

    function bestMetric(rows, key) {
      let best = null;
      rows.forEach(row => {
        const val = parseNumber(row[key]);
        if (val !== null && (best === null || val > best)) best = val;
      });
      return best;
    }

    function hasNumericMetric(rows, key) {
      return rows.some(row => parseNumber(row[key]) !== null);
    }

    function updateKpis(payload, filteredRows) {
      const rows = payload.combo.rows || [];
      const filtered = filteredRows || rows;
      const kpiContainer = document.getElementById('kpis');
      kpiContainer.innerHTML = '';
      const total = payload.combo.total || 0;
      const bestOos = bestMetric(filtered, 'oos_avg_total_return_pct');
      const bestAvg = bestMetric(filtered, 'avg_total_return_pct');
      const bestDaily = bestMetric(filtered, 'avg_daily_trades');
      const bestHold = bestMetric(filtered, 'avg_hold_hours');
      const latestReport = payload.latest_report ? `/artifacts/${payload.latest_report}` : '';

      const cards = [
        { label: '篩選後組合', value: filtered.length },
        { label: '全部組合', value: total },
        { label: '最佳驗證總報酬(%)', value: bestOos },
        { label: '最佳平均總報酬(%)', value: bestAvg },
        { label: '最佳平均每日交易', value: bestDaily },
        { label: '最佳平均持倉(小時)', value: bestHold },
        { label: '最新報告', value: payload.latest_report || '無' },
      ];

      cards.forEach(card => {
        const div = document.createElement('div');
        div.className = 'kpi';
        const label = document.createElement('div');
        label.className = 'label';
        label.textContent = card.label;
        const value = document.createElement('div');
        value.className = 'value';
        if (typeof card.value === 'number') {
          value.textContent = formatNumber(card.value);
          if (card.value > 0) value.classList.add('pos');
          if (card.value < 0) value.classList.add('neg');
        } else if (card.label === '最新報告' && latestReport) {
          const link = document.createElement('a');
          link.href = latestReport;
          link.textContent = card.value;
          link.target = '_blank';
          value.appendChild(link);
        } else {
          value.textContent = card.value ?? '';
        }
        div.appendChild(label);
        div.appendChild(value);
        kpiContainer.appendChild(div);
      });

      const note = document.getElementById('dataNote');
      if (payload.combo.truncated) {
        note.textContent = `只載入最新 ${payload.combo.rows.length} 筆（總共 ${payload.combo.total} 筆），可調整伺服器限制。`;
      } else {
        note.textContent = `資料更新時間：${payload.generated_utc || ''}`;
      }
      if (!hasNumericMetric(filtered, 'oos_avg_total_return_pct')) {
        note.textContent += '；目前無有效 OOS 指標，已回退顯示平均值（請確認資料天數是否足夠支援 WF 視窗）。';
      }
    }

    function updateTimeframeOptions(rows, available) {
      const select = document.getElementById('filterTimeframe');
      const current = select.value || 'all';
      const values = new Set();
      (available || []).forEach(val => {
        if (val && val !== 'nan') values.add(val);
      });
      rows.forEach(r => {
        if (r.timeframe && r.timeframe !== 'nan') values.add(r.timeframe);
      });
      const sortedValues = Array.from(values).sort();
      select.innerHTML = '<option value="all">全部</option>';
      sortedValues.forEach(val => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        select.appendChild(opt);
      });
      if (sortedValues.includes(current)) {
        select.value = current;
      }
    }
    function renderSymbolOptions(options, selected) {
      const container = document.getElementById('cfgSymbolsOptions');
      const summary = document.getElementById('cfgSymbolsSummary');
      if (!container) return;
      const selectedSet = new Set((selected || []).map(s => s.toUpperCase()));
      container.innerHTML = '';
      options.forEach(symbol => {
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = symbol;
        if (selectedSet.has(symbol.toUpperCase())) {
          checkbox.checked = true;
        }
        checkbox.onchange = () => syncSymbolSelection();
        label.appendChild(checkbox);
        const span = document.createElement('span');
        span.textContent = symbol;
        label.appendChild(span);
        container.appendChild(label);
      });
      if (summary) {
        summary.textContent = selected && selected.length ? `已選 ${selected.length} 個幣對` : '選擇幣對';
      }
      syncSymbolSelection();
    }

    function syncSymbolSelection() {
      const container = document.getElementById('cfgSymbolsOptions');
      const summary = document.getElementById('cfgSymbolsSummary');
      const selected = Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(el => el.value);
      const input = document.getElementById('cfgTradeSymbols');
      input.value = selected.join(',');
      if (summary) {
        summary.textContent = selected.length ? `已選 ${selected.length} 個幣對` : '選擇幣對';
      }
    }

    async function loadTopSymbols() {
      try {
        const res = await fetch('/symbols/top?limit=10', { cache: 'no-store' });
        const data = await res.json();
        const symbols = data.symbols || [];
        renderSymbolOptions(symbols, symbols);
      } catch (err) {
        alert(`載入熱門幣對失敗: ${err}`);
      }
    }

    async function loadConfig() {
      const status = document.getElementById('configStatus');
      try {
        const res = await fetch('/config.json', { cache: 'no-store' });
        const cfg = await res.json();
        const tf = (cfg.timeframes && cfg.timeframes.length) ? cfg.timeframes[0] : { timeframe: '', days: '' };
        document.getElementById('cfgMode').value = cfg.search_mode || 'combo';
        document.getElementById('cfgTimeframe').value = tf.timeframe || '';
        document.getElementById('cfgDays').value = tf.days ?? '';
        document.getElementById('cfgWfTrainDays').value = cfg.wf_train_days ?? '';
        document.getElementById('cfgWfTestDays').value = cfg.wf_test_days ?? '';
        document.getElementById('cfgWfStepDays').value = cfg.wf_step_days ?? '';
        document.getElementById('cfgCapitalMode').value = cfg.capital_mode || 'shared';
        document.getElementById('cfgInitCash').value = cfg.init_cash_usdt ?? '';
        const orderPct = cfg.order_size_pct ?? '';
        document.getElementById('cfgOrderSize').value = (Number(orderPct) > 0 && Number(orderPct) <= 1) ? (Number(orderPct) * 100) : orderPct;
        document.getElementById('cfgMaxPositions').value = cfg.max_concurrent_positions ?? '';
        document.getElementById('cfgTradeSymbols').value = Array.isArray(cfg.trade_symbols) ? cfg.trade_symbols.join(',') : '';
          document.getElementById('cfgComboSizes').value = Array.isArray(cfg.combo_sizes) ? cfg.combo_sizes.join(',') : '';
          document.getElementById('cfgSeed').value = cfg.combo_seed ?? '';
          document.getElementById('cfgSlippage').value = cfg.slippage_bps ?? '';
          document.getElementById('cfgSpread').value = cfg.spread_bps ?? '';
          document.getElementById('cfgFunding').value = cfg.funding_rate_daily ?? '';
          document.getElementById('cfgSegStart').value = cfg.combo_segment_start ?? '';
          document.getElementById('cfgSegSize').value = cfg.combo_segment_size ?? '';
          document.getElementById('cfgTopN').value = cfg.top_n_refine ?? '';
        const symbols = Array.isArray(cfg.trade_symbols) ? cfg.trade_symbols : [];
        if (symbols.length) {
          renderSymbolOptions(symbols, symbols);
        } else {
          loadTopSymbols();
        }
        if (status) status.textContent = '已載入設定';
      } catch (err) {
        if (status) status.textContent = `載入設定失敗: ${err}`;
      }
    }

    async function saveConfig() {
      const status = document.getElementById('configStatus');
      const timeframe = document.getElementById('cfgTimeframe').value.trim();
      const days = Number(document.getElementById('cfgDays').value);
      const wfTrainRaw = document.getElementById('cfgWfTrainDays').value;
      const wfTestRaw = document.getElementById('cfgWfTestDays').value;
      const wfStepRaw = document.getElementById('cfgWfStepDays').value;
        const comboSizesRaw = document.getElementById('cfgComboSizes').value;
        const tradeSymbolsRaw = document.getElementById('cfgTradeSymbols').value;
        const payload = {
          search_mode: document.getElementById('cfgMode').value || 'combo',
          timeframes: timeframe && days ? [{ timeframe, days }] : [],
          wf_train_days: wfTrainRaw === '' ? null : Number(wfTrainRaw),
          wf_test_days: wfTestRaw === '' ? null : Number(wfTestRaw),
          wf_step_days: wfStepRaw === '' ? null : Number(wfStepRaw),
          capital_mode: document.getElementById('cfgCapitalMode').value || 'shared',
          init_cash_usdt: Number(document.getElementById('cfgInitCash').value),
          order_size_pct: Number(document.getElementById('cfgOrderSize').value),
          max_concurrent_positions: Number(document.getElementById('cfgMaxPositions').value),
          trade_symbols: tradeSymbolsRaw.split(',').map(v => v.trim()).filter(Boolean),
            combo_sizes: comboSizesRaw.split(',').map(v => v.trim()).filter(Boolean),
            combo_seed: Number(document.getElementById('cfgSeed').value),
          slippage_bps: Number(document.getElementById('cfgSlippage').value),
          spread_bps: Number(document.getElementById('cfgSpread').value),
          funding_rate_daily: Number(document.getElementById('cfgFunding').value),
          combo_segment_start: Number(document.getElementById('cfgSegStart').value),
        combo_segment_size: document.getElementById('cfgSegSize').value === '' ? null : Number(document.getElementById('cfgSegSize').value),
        top_n_refine: Number(document.getElementById('cfgTopN').value)
      };
      try {
        const res = await fetch('/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (status) status.textContent = result.message || '已儲存設定';
      } catch (err) {
        if (status) status.textContent = `儲存設定失敗: ${err}`;
      }
    }

    function getFilterValues() {
      return {
        timeframe: document.getElementById('filterTimeframe').value,
        minOosReturn: parseFloat(document.getElementById('filterOosReturn').value),
        minOosWinRate: parseFloat(document.getElementById('filterOosWinRate').value),
        minDailyTrades: parseFloat(document.getElementById('filterDailyTrades').value),
        maxDrawdown: parseFloat(document.getElementById('filterMaxDrawdown').value),
        oosPositive: document.getElementById('filterOosPositive').checked
      };
    }

    function filterRows(rows) {
      const filters = getFilterValues();
      return rows.filter(row => {
        if (filters.timeframe !== 'all' && row.timeframe !== filters.timeframe) return false;
        const oosReturn = pickMetric(row, ['oos_avg_total_return_pct', 'avg_total_return_pct']);
        const oosWin = pickMetric(row, ['oos_avg_win_rate_pct', 'avg_win_rate_pct']);
        const daily = pickMetric(row, ['oos_avg_daily_trades', 'avg_daily_trades']);
        const dd = pickMetric(row, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct']);
        if (!Number.isNaN(filters.minOosReturn) && (oosReturn === null || oosReturn < filters.minOosReturn)) return false;
        if (!Number.isNaN(filters.minOosWinRate) && (oosWin === null || oosWin < filters.minOosWinRate)) return false;
        if (!Number.isNaN(filters.minDailyTrades) && (daily === null || daily < filters.minDailyTrades)) return false;
        if (!Number.isNaN(filters.maxDrawdown) && (dd === null || dd > filters.maxDrawdown)) return false;
        if (filters.oosPositive && (oosReturn === null || oosReturn <= 0)) return false;
        return true;
      });
    }

    function pickTopN(rows, n) {
      if (!rows.length) return [];
      let sortCol = 'oos_avg_total_return_pct';
      if (!rows.some(row => parseNumber(row[sortCol]) !== null)) {
        sortCol = 'avg_total_return_pct';
      }
      return [...rows]
        .sort((a, b) => {
          const bVal = parseNumber(b[sortCol]);
          const aVal = parseNumber(a[sortCol]);
          const bNum = bVal === null ? -Infinity : bVal;
          const aNum = aVal === null ? -Infinity : aVal;
          return bNum - aNum;
        })
        .slice(0, n);
    }

    function renderScatter(canvasId, points) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fdfdfd';
      ctx.fillRect(0, 0, w, h);
      if (!points.length) {
        ctx.fillStyle = '#888';
        ctx.fillText('無資料', 10, 20);
        return;
      }
      const padding = 40;
      const xs = points.map(p => p.x);
      const ys = points.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const spanX = maxX - minX || 1;
      const spanY = maxY - minY || 1;

      ctx.strokeStyle = '#bbb';
      ctx.beginPath();
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(w - padding, h - padding);
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(padding, padding);
      ctx.stroke();

      ctx.fillStyle = '#666';
      ctx.fillText('回撤(%)', w - padding - 40, h - padding + 20);
      ctx.save();
      ctx.translate(12, padding);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText('報酬(%)', 0, 0);
      ctx.restore();

      points.forEach(p => {
        const x = padding + ((p.x - minX) / spanX) * (w - padding * 2);
        const y = h - padding - ((p.y - minY) / spanY) * (h - padding * 2);
        ctx.fillStyle = p.y >= 0 ? '#0b7a36' : '#b3122f';
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    function renderHistogram(canvasId, values) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fdfdfd';
      ctx.fillRect(0, 0, w, h);
      if (!values.length) {
        ctx.fillStyle = '#888';
        ctx.fillText('無資料', 10, 20);
        return;
      }
      const padding = 40;
      const minVal = Math.min(...values);
      const maxVal = Math.max(...values);
      const bins = 10;
      const span = maxVal - minVal || 1;
      const counts = Array.from({ length: bins }, () => 0);
      values.forEach(val => {
        const idx = Math.min(bins - 1, Math.floor(((val - minVal) / span) * bins));
        counts[idx] += 1;
      });
      const maxCount = Math.max(...counts) || 1;
      const barWidth = (w - padding * 2) / bins;

      ctx.strokeStyle = '#bbb';
      ctx.beginPath();
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(w - padding, h - padding);
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(padding, padding);
      ctx.stroke();
      ctx.fillStyle = '#666';
      ctx.fillText('報酬分佈', w - padding - 50, h - padding + 20);

      counts.forEach((count, i) => {
        const barHeight = (count / maxCount) * (h - padding * 2);
        const x = padding + i * barWidth + 2;
        const y = h - padding - barHeight;
        ctx.fillStyle = '#4c78a8';
        ctx.fillRect(x, y, barWidth - 4, barHeight);
      });
    }

    function renderFrontier(canvasId, points) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fdfdfd';
      ctx.fillRect(0, 0, w, h);
      if (!points.length) {
        ctx.fillStyle = '#888';
        ctx.fillText('無資料', 10, 20);
        return;
      }
      const padding = 40;
      const xs = points.map(p => p.x);
      const ys = points.map(p => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const spanX = maxX - minX || 1;
      const spanY = maxY - minY || 1;

      ctx.strokeStyle = '#bbb';
      ctx.beginPath();
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(w - padding, h - padding);
      ctx.moveTo(padding, h - padding);
      ctx.lineTo(padding, padding);
      ctx.stroke();

      const sorted = [...points].sort((a, b) => a.x - b.x);
      const frontier = [];
      let bestY = -Infinity;
      sorted.forEach(p => {
        if (p.y > bestY) {
          frontier.push(p);
          bestY = p.y;
        }
      });

      ctx.strokeStyle = '#1f77b4';
      ctx.lineWidth = 2;
      ctx.beginPath();
      frontier.forEach((p, idx) => {
        const x = padding + ((p.x - minX) / spanX) * (w - padding * 2);
        const y = h - padding - ((p.y - minY) / spanY) * (h - padding * 2);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      frontier.forEach(p => {
        const x = padding + ((p.x - minX) / spanX) * (w - padding * 2);
        const y = h - padding - ((p.y - minY) / spanY) * (h - padding * 2);
        ctx.fillStyle = '#1f77b4';
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    function exportCsv(filename, rows, columns) {
      if (!rows.length) {
        alert('沒有可匯出的資料。');
        return;
      }
      const cols = columns && columns.length ? columns : Object.keys(rows[0]);
      const lines = [];
      lines.push(cols.join(','));
      rows.forEach(row => {
        const line = cols.map(col => {
          const raw = getColumnDisplayValue(row, col);
          const val = String(raw).replace(/"/g, '""');
          return `"${val}"`;
        }).join(',');
        lines.push(line);
      });
      const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    async function refreshStatus() {
      try {
        const res = await fetch('/status.json', { cache: 'no-store' });
        const data = await res.json();
        for (const k of ['stage','total','done','remaining','skipped','percent','elapsed','eta','updated']) {
          if (k === 'updated') {
            const raw = data[k];
            if (raw) {
              const parsed = Date.parse(raw);
              if (!Number.isNaN(parsed)) {
                document.getElementById(k).textContent = new Date(parsed).toLocaleString();
                continue;
              }
            }
          }
          document.getElementById(k).textContent = data[k] ?? '';
        }
      } catch (e) {}
    }

    let cachedPayload = null;
    let lastFilteredRows = [];
    let lastFilteredColumns = [];
    let lastTopRows = [];
    let lastTopColumns = [];

    function applyFiltersAndRender() {
      if (!cachedPayload) return;
      const comboRows = cachedPayload.combo.rows || [];
      if (!comboRows.length) {
        const note = document.getElementById('dataNote');
        note.textContent = '目前沒有可用資料，請確認回測是否已完成或 CSV 是否存在。';
      }
      updateTimeframeOptions(comboRows, cachedPayload.timeframes || []);
      const filteredRows = filterRows(comboRows);
      const topRows = pickTopN(filteredRows, 10);
      updateKpis(cachedPayload, filteredRows);

      const topCols = (cachedPayload.top10.columns || []).filter(c => TOP_COLS.includes(c));
      const comboCols = (cachedPayload.combo.columns || []).filter(c => COMBO_COLS.includes(c));
      const lbCols = (cachedPayload.leaderboard.columns || []).filter(c => LB_COLS.includes(c));

        const topColsFinal = TOP_COLS;
        const comboColsFinal = COMBO_COLS;
      const lbColsFinal = lbCols.length ? lbCols : (cachedPayload.leaderboard.columns && cachedPayload.leaderboard.columns.length ? cachedPayload.leaderboard.columns : LB_COLS);

        buildTable('top10Table', topRows, topColsFinal, { rowDetails: true });
        buildTable('comboTable', filteredRows, comboColsFinal, { rowDetails: true });
        buildTable('leaderboardTable', cachedPayload.leaderboard.rows || [], lbColsFinal);

      lastFilteredRows = filteredRows;
      lastFilteredColumns = comboColsFinal;
      lastTopRows = topRows;
      lastTopColumns = topColsFinal;

      const points = filteredRows
        .map(r => ({
          x: pickMetric(r, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct']),
          y: pickMetric(r, ['oos_avg_total_return_pct', 'avg_total_return_pct'])
        }))
        .filter(p => p.x !== null && p.y !== null);
      renderScatter('scatterChart', points);

      const histValues = filteredRows
        .map(r => pickMetric(r, ['oos_avg_total_return_pct', 'avg_total_return_pct']))
        .filter(v => v !== null);
      renderHistogram('histChart', histValues);

      renderFrontier('frontierChart', points);

      const note = document.getElementById('filterNote');
      note.textContent = `篩選後 ${filteredRows.length} 筆 / 總共 ${cachedPayload.combo.total || comboRows.length} 筆`;

      const reportLink = document.getElementById('reportLink');
      if (cachedPayload.latest_report) reportLink.href = `/artifacts/${cachedPayload.latest_report}`;
    }

    async function refreshResults() {
      try {
        const tfSelect = document.getElementById('filterTimeframe');
        const tf = tfSelect ? tfSelect.value : 'all';
        const query = tf && tf !== 'all' ? `?timeframe=${encodeURIComponent(tf)}` : '';
        const res = await fetch(`/results.json${query}`, { cache: 'no-store' });
        cachedPayload = await res.json();
        if (cachedPayload.errors && cachedPayload.errors.length) {
          const note = document.getElementById('dataNote');
          note.textContent = cachedPayload.errors.join('；');
        }
        applyFiltersAndRender();
      } catch (e) {
        const note = document.getElementById('dataNote');
        if (note) {
          note.textContent = `讀取資料失敗：${e}`;
        }
      }
    }

    document.getElementById('startBtn').onclick = async () => {
      const res = await fetch('/start', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已觸發');
      refreshStatus();
    };
    document.getElementById('pauseBtn').onclick = async () => {
      const res = await fetch('/pause', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已暫停');
      refreshStatus();
    };
    document.getElementById('resumeBtn').onclick = async () => {
      const res = await fetch('/resume', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已繼續');
      refreshStatus();
    };
    document.getElementById('clearLogBtn').onclick = async () => {
      const res = await fetch('/clear-log', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已清空');
    };
    document.getElementById('testStartBtn').onclick = async () => {
      const res = await fetch('/tests/start', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已觸發');
      refreshTests();
    };
    document.getElementById('testStopBtn').onclick = async () => {
      const res = await fetch('/tests/stop', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已停止');
      refreshTests();
    };
    document.getElementById('testClearLogBtn').onclick = async () => {
      const res = await fetch('/tests/clear-log', { method: 'POST' });
      const data = await res.json();
      alert(data.message || '已清空');
      refreshTests();
    };
    document.getElementById('applyFilterBtn').onclick = () => refreshResults();
    document.getElementById('resetFilterBtn').onclick = () => {
      document.getElementById('filterTimeframe').value = 'all';
      document.getElementById('filterOosReturn').value = '';
      document.getElementById('filterOosWinRate').value = '';
      document.getElementById('filterDailyTrades').value = '';
      document.getElementById('filterMaxDrawdown').value = '';
      document.getElementById('filterOosPositive').checked = false;
      refreshResults();
    };
    document.getElementById('filterTimeframe').onchange = () => refreshResults();
    document.getElementById('exportFilteredBtn').onclick = () => exportCsv('filtered_combos.csv', lastFilteredRows, lastFilteredColumns);
    document.getElementById('exportTopBtn').onclick = () => exportCsv('top10.csv', lastTopRows, lastTopColumns);
    document.getElementById('saveConfigBtn').onclick = () => saveConfig();
    document.getElementById('loadTopSymbolsBtn').onclick = () => loadTopSymbols();

    initTabs();
    initBatchTab();
    initCoverageTab();
    initDashboardTab();

    loadConfig();
    refreshStatus();
    refreshResults();
    refreshTests();
    setInterval(refreshStatus, 5000);
    setInterval(refreshResults, 30000);
    setInterval(refreshTests, 5000);
  
