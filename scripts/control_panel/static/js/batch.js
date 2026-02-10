const POLL_INTERVAL_MS = 4000;

let initialized = false;
let pollTimer = null;

function _fmtTime(raw) {
  if (!raw) return "";
  const parsed = Date.parse(raw);
  if (Number.isNaN(parsed)) return String(raw);
  return new Date(parsed).toLocaleString();
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

function _setMessage(text, isError = false) {
  const el = document.getElementById("cpBatchMessage");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "#b3122f" : "#355d3a";
}

function _setWorkflowModeEnabled() {
  const workflowEl = document.getElementById("cpBatchWorkflow");
  const modeEl = document.getElementById("cpBatchMode");
  if (!workflowEl || !modeEl) return;
  const isRun = workflowEl.value === "run";
  modeEl.disabled = !isRun;
  if (!isRun) {
    modeEl.value = "";
  } else if (!modeEl.value) {
    modeEl.value = "combo";
  }
}

function _buildSummary(summary, running, lastExitCode) {
  const queued = summary?.queued || 0;
  const submitted = summary?.submitted || 0;
  const active = (summary?.running || 0) + submitted;
  const done = summary?.done || 0;
  const failed = summary?.failed || 0;
  const skipped = summary?.skipped_seen_key || 0;
  const cancelled = summary?.cancelled || 0;
  const total = summary?.total || 0;
  const runText = running ? "running" : "idle";
  const exitText = lastExitCode ? ` last_exit=${lastExitCode}` : "";
  return `status=${runText}${exitText} | total=${total} queued=${queued} active=${active} done=${done} failed=${failed} skipped=${skipped} cancelled=${cancelled}`;
}

function _renderRows(jobs) {
  const tbody = document.getElementById("cpBatchBody");
  if (!tbody) return;
  tbody.innerHTML = "";
  const rows = Array.isArray(jobs) ? jobs : [];

  rows.forEach((job) => {
    const tr = document.createElement("tr");

    const idTd = document.createElement("td");
    idTd.textContent = String(job.id ?? "");
    tr.appendChild(idTd);

    const nameTd = document.createElement("td");
    nameTd.textContent = String(job.name || "");
    tr.appendChild(nameTd);

    const wfTd = document.createElement("td");
    wfTd.textContent = String(job.workflow || "");
    tr.appendChild(wfTd);

    const modeTd = document.createElement("td");
    modeTd.textContent = String(job.mode || "");
    tr.appendChild(modeTd);

    const workersTd = document.createElement("td");
    workersTd.textContent = job.workers === null || job.workers === undefined ? "" : String(job.workers);
    tr.appendChild(workersTd);

    const statusTd = document.createElement("td");
    statusTd.textContent = String(job.status || "");
    tr.appendChild(statusTd);

    const configTd = document.createElement("td");
    configTd.className = "text-left";
    configTd.textContent = String(job.config || "");
    tr.appendChild(configTd);

    const startedTd = document.createElement("td");
    startedTd.textContent = _fmtTime(job.started_utc);
    tr.appendChild(startedTd);

    const finishedTd = document.createElement("td");
    finishedTd.textContent = _fmtTime(job.finished_utc);
    tr.appendChild(finishedTd);

    const actionTd = document.createElement("td");
    const status = String(job.status || "");
    if (status === "queued" || status === "done" || status === "failed" || status === "cancelled" || status === "skipped_seen_key") {
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "secondary";
      removeBtn.textContent = "Remove";
      removeBtn.dataset.action = "remove";
      removeBtn.dataset.jobId = String(job.id);
      actionTd.appendChild(removeBtn);
    } else if (status === "submitted" || status === "running") {
      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "contrast";
      cancelBtn.textContent = "Cancel Run";
      cancelBtn.dataset.action = "cancel-run";
      actionTd.appendChild(cancelBtn);
    }
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  });
}

async function _refreshQueue() {
  try {
    const payload = await _requestJson("/batch/queue.json", { cache: "no-store" });
    const summaryEl = document.getElementById("cpBatchSummary");
    if (summaryEl) {
      summaryEl.textContent = _buildSummary(payload.summary, payload.running, payload.last_exit_code);
    }
    _renderRows(payload.jobs);

    const logEl = document.getElementById("cpBatchLog");
    if (logEl) {
      const logRes = await fetch("/batch/log-tail.txt", { cache: "no-store" });
      if (logRes.ok) {
        logEl.textContent = await logRes.text();
      }
    }
  } catch (err) {
    _setMessage(`Refresh failed: ${err}`, true);
  }
}

function _readEnqueuePayload() {
  const name = (document.getElementById("cpBatchName")?.value || "").trim();
  const config = (document.getElementById("cpBatchConfig")?.value || "").trim();
  const workflow = (document.getElementById("cpBatchWorkflow")?.value || "baseline").trim();
  const mode = (document.getElementById("cpBatchMode")?.value || "").trim();
  const workersRaw = (document.getElementById("cpBatchWorkers")?.value || "").trim();

  const payload = {
    name,
    config,
    workflow,
  };
  if (workflow === "run" && mode) {
    payload.mode = mode;
  }
  if (workersRaw) {
    payload.workers = Number(workersRaw);
  }
  return payload;
}

function _buildUi(section) {
  const card = document.createElement("div");
  card.className = "panel cp-batch-card";
  card.id = "cpBatchCard";
  card.innerHTML = `
    <h2>Batch Queue</h2>
    <div class="filter-group cp-batch-form">
      <label>Job Name
        <input id="cpBatchName" type="text" placeholder="optional">
      </label>
      <label>Config Path
        <input id="cpBatchConfig" type="text" placeholder="artifacts/sweep_config.json">
      </label>
      <label>Workflow
        <select id="cpBatchWorkflow">
          <option value="baseline">baseline</option>
          <option value="run">run</option>
        </select>
      </label>
      <label>Mode
        <select id="cpBatchMode" disabled>
          <option value="">(none)</option>
          <option value="combo">combo</option>
          <option value="refine">refine</option>
        </select>
      </label>
      <label>Workers
        <input id="cpBatchWorkers" type="number" min="1" step="1" placeholder="optional">
      </label>
    </div>
    <div class="row">
      <button id="cpBatchEnqueueBtn" type="button">Enqueue</button>
      <button id="cpBatchStartBtn" type="button">Start Batch</button>
      <button id="cpBatchCancelBtn" type="button" class="contrast">Cancel Batch</button>
      <button id="cpBatchClearBtn" type="button" class="secondary">Clear Queue</button>
      <span id="cpBatchMessage" class="note"></span>
    </div>
    <div id="cpBatchSummary" class="note"></div>
    <table class="cp-batch-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Name</th>
          <th>Workflow</th>
          <th>Mode</th>
          <th>Workers</th>
          <th>Status</th>
          <th>Config</th>
          <th>Started</th>
          <th>Finished</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="cpBatchBody"></tbody>
    </table>
    <div class="note">Batch log tail</div>
    <pre id="cpBatchLog" class="log-box cp-batch-log"></pre>
  `;
  section.prepend(card);
}

function _bindEvents() {
  const workflowEl = document.getElementById("cpBatchWorkflow");
  if (workflowEl) {
    workflowEl.onchange = () => _setWorkflowModeEnabled();
  }

  const enqueueBtn = document.getElementById("cpBatchEnqueueBtn");
  if (enqueueBtn) {
    enqueueBtn.onclick = async () => {
      try {
        const payload = _readEnqueuePayload();
        await _requestJson("/batch/enqueue", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        _setMessage("Job enqueued.");
        await _refreshQueue();
      } catch (err) {
        _setMessage(`Enqueue failed: ${err}`, true);
      }
    };
  }

  const startBtn = document.getElementById("cpBatchStartBtn");
  if (startBtn) {
    startBtn.onclick = async () => {
      try {
        await _requestJson("/batch/start", { method: "POST" });
        _setMessage("Batch started.");
        await _refreshQueue();
      } catch (err) {
        _setMessage(`Start failed: ${err}`, true);
      }
    };
  }

  const cancelBtn = document.getElementById("cpBatchCancelBtn");
  if (cancelBtn) {
    cancelBtn.onclick = async () => {
      try {
        await _requestJson("/batch/cancel", { method: "POST" });
        _setMessage("Batch cancelled.");
        await _refreshQueue();
      } catch (err) {
        _setMessage(`Cancel failed: ${err}`, true);
      }
    };
  }

  const clearBtn = document.getElementById("cpBatchClearBtn");
  if (clearBtn) {
    clearBtn.onclick = async () => {
      const yes = window.confirm("Clear the whole queue?");
      if (!yes) return;
      try {
        await _requestJson("/batch/clear", { method: "POST" });
        _setMessage("Queue cleared.");
        await _refreshQueue();
      } catch (err) {
        _setMessage(`Clear failed: ${err}`, true);
      }
    };
  }

  const tbody = document.getElementById("cpBatchBody");
  if (tbody) {
    tbody.onclick = async (event) => {
      const target = event.target;
      if (!target || !(target instanceof HTMLElement)) return;
      const action = target.dataset.action;
      if (!action) return;

      if (action === "remove") {
        try {
          const jobId = Number(target.dataset.jobId);
          await _requestJson("/batch/remove", {
            method: "POST",
            body: JSON.stringify({ job_id: jobId }),
          });
          _setMessage(`Job ${jobId} removed.`);
          await _refreshQueue();
        } catch (err) {
          _setMessage(`Remove failed: ${err}`, true);
        }
      } else if (action === "cancel-run") {
        try {
          await _requestJson("/batch/cancel", { method: "POST" });
          _setMessage("Batch cancelled.");
          await _refreshQueue();
        } catch (err) {
          _setMessage(`Cancel failed: ${err}`, true);
        }
      }
    };
  }
}

export function initBatchTab() {
  if (initialized) return;
  const section = document.querySelector('.cp-tab-panel[data-tab="control"]');
  if (!section) return;
  if (document.getElementById("cpBatchCard")) {
    initialized = true;
    return;
  }

  _buildUi(section);
  _bindEvents();
  _setWorkflowModeEnabled();
  _refreshQueue();

  pollTimer = window.setInterval(() => {
    _refreshQueue();
  }, POLL_INTERVAL_MS);

  initialized = true;
  void pollTimer;
}
