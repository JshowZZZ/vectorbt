const COVERAGE_POLL_MS = 5000;

let initialized = false;
let pollTimer = null;

function _setMessage(text, isError = false) {
  const el = document.getElementById("cpCoverageMessage");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "#b3122f" : "#355d3a";
}

function _setModeEnabled() {
  const workflowEl = document.getElementById("cpCoverageWorkflow");
  const modeEl = document.getElementById("cpCoverageMode");
  if (!workflowEl || !modeEl) return;
  const isRun = workflowEl.value === "run";
  modeEl.disabled = !isRun;
  if (!isRun) {
    modeEl.value = "";
  } else if (!modeEl.value) {
    modeEl.value = "combo";
  }
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

function _buildUi(section) {
  const card = document.createElement("div");
  card.className = "panel cp-coverage-card";
  card.id = "cpCoverageCard";
  card.innerHTML = `
    <h2>Coverage Matrix</h2>
    <div class="note">Click a cell to enqueue that timeframe/symbol pair into batch queue.</div>
    <div class="filter-group cp-coverage-form">
      <label>Workflow
        <select id="cpCoverageWorkflow">
          <option value="baseline">baseline</option>
          <option value="run">run</option>
        </select>
      </label>
      <label>Mode
        <select id="cpCoverageMode" disabled>
          <option value="">(none)</option>
          <option value="combo">combo</option>
          <option value="refine">refine</option>
        </select>
      </label>
      <label>Workers
        <input id="cpCoverageWorkers" type="number" min="1" step="1" placeholder="optional">
      </label>
      <div class="row">
        <button id="cpCoverageRefreshBtn" type="button">Refresh</button>
        <button id="cpCoverageStartBatchBtn" type="button">Start Batch</button>
      </div>
    </div>
    <div id="cpCoverageSummary" class="note"></div>
    <div class="cp-coverage-legend">
      <span class="cp-cov-pill cp-cov-tested">tested</span>
      <span class="cp-cov-pill cp-cov-queued">queued</span>
      <span class="cp-cov-pill cp-cov-untested">untested</span>
    </div>
    <div class="cp-coverage-wrap">
      <table id="cpCoverageTable" class="cp-coverage-table"></table>
    </div>
    <span id="cpCoverageMessage" class="note"></span>
  `;
  section.innerHTML = "";
  section.appendChild(card);
}

function _renderSummary(payload) {
  const summaryEl = document.getElementById("cpCoverageSummary");
  if (!summaryEl) return;
  const summary = payload?.summary || {};
  const total = summary.total || 0;
  const tested = summary.tested || 0;
  const queued = summary.queued || 0;
  const untested = summary.untested || 0;
  const pct = summary.coverage_pct || 0;
  summaryEl.textContent = `total=${total} tested=${tested} queued=${queued} untested=${untested} coverage=${pct}%`;
}

function _statusToClass(status) {
  if (status === "tested") return "cp-cov-tested";
  if (status === "queued") return "cp-cov-queued";
  return "cp-cov-untested";
}

function _renderTable(payload) {
  const table = document.getElementById("cpCoverageTable");
  if (!table) return;
  const timeframes = Array.isArray(payload?.timeframes) ? payload.timeframes : [];
  const symbols = Array.isArray(payload?.symbols) ? payload.symbols : [];
  const cells = Array.isArray(payload?.cells) ? payload.cells : [];
  const cellMap = new Map();
  cells.forEach((cell) => {
    const tf = String(cell.timeframe || "");
    const sym = String(cell.symbol || "");
    if (!tf || !sym) return;
    cellMap.set(`${tf}||${sym}`, String(cell.status || "untested"));
  });

  table.innerHTML = "";
  if (!timeframes.length || !symbols.length) {
    const tbody = document.createElement("tbody");
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.className = "text-left";
    td.textContent = "No coverage data available.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    table.appendChild(tbody);
    return;
  }

  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  const firstTh = document.createElement("th");
  firstTh.textContent = "symbol \\ timeframe";
  firstTh.className = "text-left";
  hr.appendChild(firstTh);
  timeframes.forEach((tf) => {
    const th = document.createElement("th");
    th.textContent = tf;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  symbols.forEach((symbol) => {
    const tr = document.createElement("tr");

    const symbolTd = document.createElement("td");
    symbolTd.className = "text-left";
    symbolTd.textContent = symbol;
    tr.appendChild(symbolTd);

    timeframes.forEach((tf) => {
      const td = document.createElement("td");
      const status = cellMap.get(`${tf}||${symbol}`) || "untested";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `cp-cov-cell ${_statusToClass(status)}`;
      btn.dataset.timeframe = tf;
      btn.dataset.symbol = symbol;
      btn.dataset.status = status;
      btn.textContent = status;
      td.appendChild(btn);
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
}

function _currentEnqueueOptions() {
  const workflow = (document.getElementById("cpCoverageWorkflow")?.value || "baseline").trim();
  const mode = (document.getElementById("cpCoverageMode")?.value || "").trim();
  const workersRaw = (document.getElementById("cpCoverageWorkers")?.value || "").trim();
  const payload = { workflow };
  if (workflow === "run" && mode) payload.mode = mode;
  if (workersRaw) payload.workers = Number(workersRaw);
  return payload;
}

async function _refreshMatrix() {
  try {
    const payload = await _requestJson("/coverage/matrix.json", { cache: "no-store" });
    _renderSummary(payload);
    _renderTable(payload);
  } catch (err) {
    _setMessage(`Coverage refresh failed: ${err}`, true);
  }
}

function _bindEvents() {
  const workflowEl = document.getElementById("cpCoverageWorkflow");
  if (workflowEl) {
    workflowEl.onchange = () => _setModeEnabled();
  }

  const refreshBtn = document.getElementById("cpCoverageRefreshBtn");
  if (refreshBtn) {
    refreshBtn.onclick = async () => {
      await _refreshMatrix();
    };
  }

  const startBatchBtn = document.getElementById("cpCoverageStartBatchBtn");
  if (startBatchBtn) {
    startBatchBtn.onclick = async () => {
      try {
        await _requestJson("/batch/start", { method: "POST" });
        _setMessage("Batch started.");
      } catch (err) {
        _setMessage(`Batch start failed: ${err}`, true);
      }
    };
  }

  const table = document.getElementById("cpCoverageTable");
  if (table) {
    table.onclick = async (event) => {
      const target = event.target;
      if (!target || !(target instanceof HTMLElement)) return;
      if (!target.classList.contains("cp-cov-cell")) return;

      const timeframe = String(target.dataset.timeframe || "").trim();
      const symbol = String(target.dataset.symbol || "").trim();
      const status = String(target.dataset.status || "").trim();
      if (!timeframe || !symbol) return;

      if (status === "queued") {
        _setMessage(`Already queued: ${timeframe} / ${symbol}`, false);
        return;
      }

      let shouldQueue = true;
      if (status === "tested") {
        shouldQueue = window.confirm(`Pair is already tested. Queue another run for ${timeframe} / ${symbol}?`);
      }
      if (!shouldQueue) return;

      try {
        const base = _currentEnqueueOptions();
        await _requestJson("/coverage/enqueue", {
          method: "POST",
          body: JSON.stringify({
            timeframe,
            symbol,
            ...base,
          }),
        });
        _setMessage(`Queued ${timeframe} / ${symbol}`);
        await _refreshMatrix();
      } catch (err) {
        _setMessage(`Enqueue failed: ${err}`, true);
      }
    };
  }
}

export function initCoverageTab() {
  if (initialized) return;
  const section = document.querySelector('.cp-tab-panel[data-tab="coverage"]');
  if (!section) return;
  _buildUi(section);
  _bindEvents();
  _setModeEnabled();
  _refreshMatrix();
  pollTimer = window.setInterval(() => {
    _refreshMatrix();
  }, COVERAGE_POLL_MS);
  initialized = true;
  void pollTimer;
}
