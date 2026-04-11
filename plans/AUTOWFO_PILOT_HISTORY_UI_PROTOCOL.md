# AUTOWFO Pilot History UI Protocol

## Objective
Add a sortable, searchable "Pilot History" table to the control panel's
Results page so operators can browse all `pilot-analysis` report summaries
without opening raw JSON files.

## Motivation
The control panel already has a leaderboard table for trusted-run results
(read from `artifacts/leaderboard.csv`). But pilot-analysis reports — the
breadth/family/boundary/sensitivity experiments — are only available as
individual JSON files under `artifacts/reports/pilot_analysis_*.json`. There
is no unified view to compare them, sort by gate-passed count, or search by
run ID.

This ticket reuses the existing `DataTable` component (no modifications to
it) and adds one backend endpoint plus one frontend section.

## Architecture Reference

### DataTable component
- File: `autowfo/control_panel/static/js/components.js` L247–L425
- Name: `DataTable`
- Props: `columns` (array of `{key, label, numeric, sortable}`), `rows`,
  `pageSize`, `sortKey`, `sortDir`, `searchable`, `expandable`, `expandedKey`
- Already supports: click-to-sort, full-text search, pagination (25/50/100/200),
  expandable detail rows via named slot `#detail`
- **Do not modify this component.**

### Results page backend
- File: `autowfo/control_panel/results.py`
- `try_handle_get()` at L461 routes `/results.json`
- Leaderboard reads `ARTIFACTS / "leaderboard.csv"` at L303

### Results page frontend
- File: `autowfo/control_panel/static/js/results.js`
- Leaderboard section at L476–L485
- `lbColumns` definition at L931–L943
- Data loaded from `/results.json`, leaderboard rows at L1054

### Pilot-analysis JSON structure
Produced by `autowfo/pilot_analysis.py` `compare_pilot_runs()` at L895–L936:
```json
{
  "schema_version": "1.0.0",
  "identity_fields": [...],
  "thresholds": {
    "require_all_symbols_nonnegative": true,
    "min_combo_return": 0.0,
    "min_combo_trades": 0.5,
    "trade_gate_policy": "flat",
    "...": "..."
  },
  "main_run": { "run_id": "...", "run_root": "..." },
  "sensitivity_run": { "run_id": "...", "run_root": "..." },
  "summary": {
    "main_combo_rows": N,
    "sensitivity_combo_rows": N,
    "compared_combo_rows": N,
    "stable_positive_rows": N,
    "gate_passed_rows": N,
    "canonical_gate_passed_rows": N,
    "redundant_gate_passed_rows": N
  },
  "protocol_summary": {
    "canonical_gate_passed": { "row_count": N, "field_values": {...} }
  },
  "top_gate_passed": [ { "indicator_list": "...", "min_return": ..., "regime_name": "...", ... } ],
  "top_stable_positive": [ ... ]
}
```

## Implementation

### Backend: new `/pilot-history.json` GET endpoint

Add to `autowfo/control_panel/results.py`.

#### Route
In `try_handle_get()`, add before the final return:
```python
if path == "/pilot-history.json":
    payload = _build_pilot_history()
    # return JSON response with payload
    return True
```

#### `_build_pilot_history()` logic
1. Scan `ARTIFACTS / "reports"` for all files matching `pilot_analysis_*.json`
2. For each file:
   - Read and parse JSON
   - Apply schema guard before accepting the row:
     - require `schema_version`
     - require `main_run.run_id`
     - require `sensitivity_run.run_id`
     - require `summary.compared_combo_rows`
     - files that fail this contract must be skipped without aborting the endpoint
   - Extract a row dict with these fields:
     - `filename`: file name only (no path)
     - `created_utc`: file mtime in UTC ISO format
     - `created_ts`: file mtime as Unix timestamp for stable default sort
     - `main_run_id`: `payload["main_run"]["run_id"]`
     - `sens_run_id`: `payload["sensitivity_run"]["run_id"]`
     - `compared_rows`: `payload["summary"]["compared_combo_rows"]`
     - `stable_positive_rows`: `payload["summary"]["stable_positive_rows"]`
     - `gate_passed_rows`: `payload["summary"]["gate_passed_rows"]`
     - `canonical_gate_passed_rows`: `payload["summary"]["canonical_gate_passed_rows"]`
     - `min_combo_trades`: `payload["thresholds"]["min_combo_trades"]`
     - `top_indicator_list`: first entry of `top_gate_passed[0]["indicator_list"]`,
       fallback to `top_stable_positive[0]["indicator_list"]`, fallback to `null`
     - `top_min_return`: first entry of `top_gate_passed[0]["min_return"]`,
       same fallback chain
     - `top_regime`: first entry of `top_gate_passed[0]["regime_name"]`,
       same fallback chain
   - If a file fails to parse: skip it, log a warning, do not abort the endpoint
3. Sort rows by `created_ts` descending (newest first)
4. Return `{"rows": [...], "total": len(rows)}`

### Frontend: Results page additions

Modify `autowfo/control_panel/static/js/results.js`.

#### 1. Template: new section after leaderboard (after L485)

```html
<h3 class="text-sm font-semibold text-gray-900 dark:text-white mt-6">
  {{ tr('results_pilot_history_title', 'Pilot 歷史紀錄') }}
</h3>
<p class="text-xs text-gray-500 dark:text-gray-400 mb-3">
  {{ tr('results_pilot_history_desc', '所有 pilot-analysis report 的摘要') }}
</p>
<data-table :columns="pilotHistoryColumns" :rows="pilotHistory" :page-size="25"
            sort-key="created_utc" searchable expandable
            :expanded-key="expandedKeyPilot"
            @row-click="row => toggleDetail(row, 'pilot')">
  <template #detail="{ row }">
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5 text-xs">
      <div v-if="row.top_indicator_list">
        <span class="text-gray-500">Top Indicators:</span>
        <span class="font-mono">{{ row.top_indicator_list }}</span>
      </div>
      <div v-if="row.top_regime">
        <span class="text-gray-500">Regime:</span>
        <span class="font-mono">{{ row.top_regime }}</span>
      </div>
      <div v-if="row.top_min_return != null">
        <span class="text-gray-500">Min Return:</span>
        <span class="font-mono"
              :class="row.top_min_return > 0 ? 'text-green-600' : 'text-red-500'">
          {{ Number(row.top_min_return).toFixed(4) }}%
        </span>
      </div>
      <div>
        <span class="text-gray-500">Trade Floor:</span>
        <span class="font-mono">{{ row.min_combo_trades }}</span>
      </div>
      <div>
        <span class="text-gray-500">Filename:</span>
        <span class="font-mono text-xs break-all">{{ row.filename }}</span>
      </div>
    </div>
  </template>
</data-table>
```

#### 2. Data and column definitions (in setup())

```js
const pilotHistory = ref([])
const expandedKeyPilot = ref(null)

const pilotHistoryColumns = [
  { key: 'created_utc', label: tr('pilot_created', '時間'), sortable: true },
  { key: 'main_run_id', label: tr('pilot_main_run', 'Main Run'), sortable: true },
  { key: 'sens_run_id', label: tr('pilot_sens_run', 'Sens Run'), sortable: true },
  { key: 'compared_rows', label: tr('pilot_compared', '比較數'), numeric: true, sortable: true },
  { key: 'stable_positive_rows', label: tr('pilot_stable', '穩定正'), numeric: true, sortable: true },
  { key: 'gate_passed_rows', label: tr('pilot_gate', '通過門檻'), numeric: true, sortable: true },
  { key: 'canonical_gate_passed_rows', label: tr('pilot_canonical', 'Canonical'), numeric: true, sortable: true },
]
```

#### 3. Fetch data (alongside existing /results.json fetch)

```js
fetch(`${BASE}/pilot-history.json`)
  .then(r => r.json())
  .then(data => {
    pilotHistory.value = (data.rows || []).map((r, i) => ({ ...r, _expandKey: i }))
  })
  .catch(() => {})
```

#### 4. toggleDetail handler

In the existing `toggleDetail(row, tableId)` function, add:
```js
if (tableId === 'pilot') {
  expandedKeyPilot.value = expandedKeyPilot.value === row._expandKey ? null : row._expandKey
}
```

#### 5. Return from setup()

Add `pilotHistory`, `pilotHistoryColumns`, `expandedKeyPilot` to the returned
object.

### i18n

Add the following keys to `autowfo/control_panel/static/js/i18n.js`:
- `results_pilot_history_title`
- `results_pilot_history_desc`
- `pilot_created`
- `pilot_main_run`
- `pilot_sens_run`
- `pilot_compared`
- `pilot_stable`
- `pilot_gate`
- `pilot_canonical`

Only add keys used above. Do not add extras.

## Non-Goals
- Do not modify the existing leaderboard data source or logic
- Do not write pilot-analysis results into `leaderboard.csv`
- Do not modify the `DataTable` component itself
- Do not add a new tab or separate page
- Do not add charts or visualizations

## Validation
- `python -m pytest tests/test_control_panel.py -q` passes
- Manual verification via control panel:
  - Results page shows "Pilot 歷史紀錄" section below leaderboard
  - Table displays all `artifacts/reports/pilot_analysis_*.json` summaries
  - Column header click sorts correctly (numeric and text)
  - Search box filters rows
  - Row click expands detail panel with top indicators, regime, min return
  - Empty state (no pilot JSON files) renders cleanly without errors
