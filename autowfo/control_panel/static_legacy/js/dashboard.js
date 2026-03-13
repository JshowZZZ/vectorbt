const DASHBOARD_POLL_MS = 8000;

let initialized = false;
let pollTimer = null;

function _fmtNumber(value, digits = 4) {
  const num = Number(value);
  if (!Number.isFinite(num)) return value === null || value === undefined ? "" : String(value);
  return num.toFixed(digits).replace(/\.?0+$/, "");
}

function _fmtTime(raw) {
  if (!raw) return "";
  const parsed = Date.parse(raw);
  if (Number.isNaN(parsed)) return String(raw);
  return new Date(parsed).toLocaleString();
}

function _setMessage(text, isError = false) {
  const el = document.getElementById("cpDashMessage");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "#b3122f" : "#355d3a";
}

async function _requestJson(url, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const req = { ...options, headers: { ...headers, ...(options.headers || {}) } };
  const res = await fetch(url, req);
  let payload = {};
  try {
    payload = await res.json();
  } catch (_err) {
    payload = {};
  }
  if (!res.ok || payload.ok === false) {
    const msg = payload.message || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return payload;
}

function _buildDashboardUi(dashSection, historySection) {
  if (dashSection) {
    dashSection.innerHTML = `
      <div class="panel cp-dash-card">
        <h2>Cross-Run Dashboard</h2>
        <div class="row">
          <button id="cpDashRefreshBtn" type="button">Refresh</button>
          <button id="cpDashGenReportBtn" type="button">Generate Report</button>
          <a id="cpDashOpenReport" href="/dashboard/report" target="_blank" class="button secondary">Open Report</a>
          <label>Top N
            <input id="cpDashTopN" type="number" min="1" step="1" value="20">
          </label>
          <span id="cpDashMessage" class="note"></span>
        </div>
        <div id="cpDashSummary" class="kpi-grid"></div>
        <h3>Global Leaderboard</h3>
        <div class="cp-dash-wrap">
          <table id="cpDashLeaderboard" class="cp-dash-table"></table>
        </div>
        <h3>Combo Stability</h3>
        <div class="cp-dash-wrap">
          <table id="cpDashCombo" class="cp-dash-table"></table>
        </div>
      </div>
    `;
  }

  if (historySection) {
    historySection.innerHTML = `
      <div class="panel cp-dash-card">
        <h2>Run History Timeline</h2>
        <div class="cp-dash-wrap">
          <table id="cpDashHistory" class="cp-dash-table"></table>
        </div>
      </div>
    `;
  }
}

function _renderSummary(summary, generatedUtc) {
  const host = document.getElementById("cpDashSummary");
  if (!host) return;
  const cards = [
    ["Total Runs", summary.total_runs],
    ["Unique Symbols", summary.unique_symbols],
    ["Unique Timeframes", summary.unique_timeframes],
    ["Avg OOS Return %", _fmtNumber(summary.avg_oos_return_pct)],
    ["Coverage %", _fmtNumber(summary.coverage_pct, 2)],
    ["Latest Run", summary.latest_run_id || ""],
    ["Generated UTC", _fmtTime(generatedUtc)],
  ];
  host.innerHTML = "";
  cards.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "kpi";
    const labelEl = document.createElement("div");
    labelEl.className = "label";
    labelEl.textContent = label;
    const valueEl = document.createElement("div");
    valueEl.className = "value";
    valueEl.textContent = value === null || value === undefined ? "" : String(value);
    card.appendChild(labelEl);
    card.appendChild(valueEl);
    host.appendChild(card);
  });
}

function _renderTable(tableId, headers, rows) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  headers.forEach((h) => {
    const th = document.createElement("th");
    th.textContent = h;
    hr.appendChild(th);
  });
  thead.appendChild(hr);

  const tbody = document.createElement("tbody");
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = headers.length;
    td.textContent = "No data";
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell === null || cell === undefined ? "" : String(cell);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }
  table.innerHTML = "";
  table.appendChild(thead);
  table.appendChild(tbody);
}

function _renderLeaderboard(rows) {
  const tableRows = (rows || []).map((row) => [
    row.run_id || "",
    _fmtTime(row.timestamp_utc),
    row.search_mode || "",
    row.best_timeframe || "",
    _fmtNumber(row.oos_avg_total_return_pct),
    _fmtNumber(row.avg_total_return_pct),
    (row.trade_symbols || []).join(","),
  ]);
  _renderTable(
    "cpDashLeaderboard",
    ["run_id", "timestamp", "search_mode", "best_tf", "oos_return_pct", "avg_return_pct", "symbols"],
    tableRows
  );
}

function _renderComboStability(rows) {
  const tableRows = (rows || []).map((row) => [
    row.combo_key || "",
    row.appearances || 0,
    _fmtNumber(row.avg_oos_return_pct),
    _fmtNumber(row.best_oos_return_pct),
    _fmtNumber(row.avg_oos_drawdown_pct),
    (row.run_ids || []).join(","),
  ]);
  _renderTable(
    "cpDashCombo",
    ["combo_key", "appearances", "avg_oos_return_pct", "best_oos_return_pct", "avg_oos_drawdown_pct", "run_ids"],
    tableRows
  );
}

function _renderHistory(rows) {
  const tableRows = (rows || []).map((row) => [
    row.run_id || "",
    _fmtTime(row.timestamp_utc),
    row.search_mode || "",
    (row.timeframes || []).join(","),
    (row.trade_symbols || []).join(","),
    _fmtNumber(row.oos_avg_total_return_pct),
    row.report_file || "",
  ]);
  _renderTable(
    "cpDashHistory",
    ["run_id", "timestamp", "search_mode", "timeframes", "symbols", "oos_return_pct", "report_file"],
    tableRows
  );
}

async function _refreshDashboard() {
  const topNEl = document.getElementById("cpDashTopN");
  const topN = Math.max(1, Number(topNEl?.value || 20));
  try {
    const payload = await _requestJson(`/dashboard/cross_run.json?top_n=${encodeURIComponent(String(topN))}`, {
      cache: "no-store",
    });
    _renderSummary(payload.summary || {}, payload.generated_utc);
    _renderLeaderboard(payload.global_leaderboard || []);
    _renderComboStability(payload.combo_stability || []);
    _renderHistory(payload.run_history || []);
  } catch (err) {
    _setMessage(`Dashboard refresh failed: ${err}`, true);
  }
}

function _bindEvents() {
  const refreshBtn = document.getElementById("cpDashRefreshBtn");
  if (refreshBtn) {
    refreshBtn.onclick = async () => {
      await _refreshDashboard();
    };
  }

  const topNEl = document.getElementById("cpDashTopN");
  if (topNEl) {
    topNEl.onchange = async () => {
      await _refreshDashboard();
    };
  }

  const genBtn = document.getElementById("cpDashGenReportBtn");
  if (genBtn) {
    genBtn.onclick = async () => {
      const topN = Math.max(1, Number(document.getElementById("cpDashTopN")?.value || 20));
      try {
        await _requestJson("/dashboard/report/generate", {
          method: "POST",
          body: JSON.stringify({ top_n: topN }),
        });
        _setMessage("Cross-run report generated.");
      } catch (err) {
        _setMessage(`Generate report failed: ${err}`, true);
      }
    };
  }
}

export function initDashboardTab() {
  if (initialized) return;
  const dashSection = document.querySelector('.cp-tab-panel[data-tab="dashboard"]');
  const historySection = document.querySelector('.cp-tab-panel[data-tab="history"]');
  if (!dashSection || !historySection) return;

  _buildDashboardUi(dashSection, historySection);
  _bindEvents();
  _refreshDashboard();
  pollTimer = window.setInterval(() => {
    _refreshDashboard();
  }, DASHBOARD_POLL_MS);
  initialized = true;
  void pollTimer;
}
