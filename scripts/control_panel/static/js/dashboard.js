import { ref, watch, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson, formatApiError } from './api.js'
import { showToast } from './store.js'
import { L } from './i18n.js'

export const DashboardTab = {
  name: 'DashboardTab',
  template: `
    <div class="space-y-6 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="skeleton skeleton-card h-12"></div>
        <div class="skeleton skeleton-card h-28"></div>
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div v-for="n in 7" :key="'dashboard-kpi-sk-' + n" class="skeleton skeleton-card h-16"></div>
        </div>
        <div class="skeleton skeleton-card h-72"></div>
        <div class="skeleton skeleton-card h-72"></div>
        <div class="skeleton skeleton-card h-72"></div>
      </div>

      <template v-else>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('dashboard_title', 'Cross-Run Dashboard') }}</h2>
          <div class="flex items-center gap-3">
            <label class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
              {{ t('dashboard_top_n', 'Top N') }}
              <input v-model.number="topN" type="number" min="1" class="cfg-input w-16" />
            </label>
            <label class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
              <input v-model="autoRefresh" type="checkbox" class="rounded border-gray-300 dark:border-gray-600" />
              {{ t('dashboard_auto_refresh', 'Auto Refresh') }}
            </label>
            <label class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
              {{ t('dashboard_poll_seconds', 'Poll (s)') }}
              <select v-model.number="pollSeconds" :disabled="!autoRefresh" class="cfg-input w-20">
                <option :value="5">5</option>
                <option :value="8">8</option>
                <option :value="15">15</option>
                <option :value="30">30</option>
              </select>
            </label>
            <button
              @click="refresh"
              class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                     bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
            >
              {{ t('dashboard_refresh', 'Refresh') }}
            </button>
            <button
              @click="genReport"
              :disabled="generating"
              class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white transition-all disabled:opacity-50"
            >
              {{ generating ? t('dashboard_generating', 'Generating...') : t('dashboard_generate_report', 'Generate Report') }}
            </button>
            <a
              href="/dashboard/report"
              target="_blank"
              class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                     bg-white dark:bg-gray-800 text-blue-500 hover:text-blue-400 transition-all"
            >
              {{ t('dashboard_open_report', 'Open Report ↗') }}
            </a>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex flex-wrap items-center gap-2">
            <span class="text-xs font-semibold text-gray-700 dark:text-gray-200">{{ t('dashboard_payload_source', 'Payload Source') }}</span>
            <span class="tag-chip" :class="sourceBadgeClass(payloadSource)">{{ payloadSourceLabel(payloadSource) }}</span>
            <span v-if="payloadReasonCode" class="tag-chip bg-amber-500/15 text-amber-600 dark:text-amber-300">
              {{ t('dashboard_reason_code', 'Reason Code') }}: {{ payloadReasonCode }}
            </span>
            <span v-if="reportMeta.source" class="tag-chip bg-blue-500/15 text-blue-600 dark:text-blue-300">
              {{ t('dashboard_last_report_source', 'Report Source') }}: {{ payloadSourceLabel(reportMeta.source) }}
            </span>
            <span v-if="lastRequestId" class="tag-chip bg-gray-500/15 text-gray-600 dark:text-gray-300">
              {{ t('dashboard_request_id', 'Request ID') }}: {{ lastRequestId }}
            </span>
          </div>

          <div class="px-4 py-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            <div v-for="row in sourceRows" :key="row.label" class="flex items-start gap-2">
              <span class="text-gray-500 dark:text-gray-400 shrink-0">{{ row.label }}:</span>
              <span class="font-mono text-gray-900 dark:text-gray-100 break-all">{{ row.value || '-' }}</span>
            </div>
          </div>

          <div v-if="sourceErrorRows.length" class="px-4 py-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
            <div class="text-xs font-semibold text-amber-600 dark:text-amber-300">{{ t('dashboard_fallback_error_title', 'Fallback Trigger Diagnostics') }}</div>
            <div
              v-for="(err, idx) in sourceErrorRows"
              :key="'source-err-' + idx"
              class="rounded-lg border border-amber-300/60 dark:border-amber-700/60 bg-amber-50 dark:bg-amber-900/20 p-2"
            >
              <div class="text-[11px] text-amber-700 dark:text-amber-200 font-mono">
                {{ err.stage }} | {{ t('dashboard_error_code', 'code') }}={{ err.code || '-' }} | {{ t('dashboard_error_type', 'type') }}={{ err.type || '-' }}
              </div>
              <div class="text-xs text-amber-800 dark:text-amber-100 break-words">{{ err.message || '-' }}</div>
            </div>
          </div>
        </div>

        <div v-if="diagnostics" class="rounded-xl border border-red-300 dark:border-red-800/60 bg-red-50 dark:bg-red-900/15 overflow-hidden">
          <div class="px-4 py-3 border-b border-red-200 dark:border-red-800/60 flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-red-700 dark:text-red-300">{{ t('dashboard_error_panel_title', 'Last Endpoint Failure') }}</div>
            <div class="flex items-center gap-2">
              <button
                @click="copyDiagnostics"
                class="px-2 py-1 rounded text-[11px] border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30"
              >
                {{ t('dashboard_error_panel_copy_json', 'Copy JSON') }}
              </button>
              <button
                @click="clearDiagnostics"
                class="px-2 py-1 rounded text-[11px] border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30"
              >
                {{ t('dashboard_error_panel_clear', 'Clear') }}
              </button>
            </div>
          </div>
          <div class="px-4 py-3 space-y-2 text-xs">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div><span class="text-red-600/80 dark:text-red-300/80">endpoint:</span> <span class="font-mono">{{ diagnostics.endpoint }}</span></div>
              <div><span class="text-red-600/80 dark:text-red-300/80">status:</span> <span class="font-mono">{{ diagnostics.status || '-' }}</span></div>
              <div><span class="text-red-600/80 dark:text-red-300/80">request_id:</span> <span class="font-mono">{{ diagnostics.request_id || '-' }}</span></div>
              <div><span class="text-red-600/80 dark:text-red-300/80">error_code:</span> <span class="font-mono">{{ diagnostics.error_code || '-' }}</span></div>
              <div><span class="text-red-600/80 dark:text-red-300/80">cache_error_code:</span> <span class="font-mono">{{ diagnostics.cache_error_code || '-' }}</span></div>
              <div class="md:col-span-2"><span class="text-red-600/80 dark:text-red-300/80">message:</span> <span class="font-mono break-words">{{ diagnostics.message || '-' }}</span></div>
              <div><span class="text-red-600/80 dark:text-red-300/80">time:</span> <span class="font-mono">{{ fmtTime(diagnostics.at) }}</span></div>
            </div>

            <div v-if="diagnostics.live_error" class="rounded-lg border border-red-300/70 dark:border-red-800/70 bg-white/70 dark:bg-red-950/20 p-2">
              <div class="text-[11px] font-semibold text-red-700 dark:text-red-300">live_error</div>
              <div class="font-mono text-[11px] text-red-700 dark:text-red-200">{{ diagnostics.live_error.code || '-' }} | {{ diagnostics.live_error.type || '-' }}</div>
              <div class="text-[11px] text-red-800 dark:text-red-100 break-words">{{ diagnostics.live_error.message || '-' }}</div>
            </div>

            <div v-if="diagnostics.cache_error" class="rounded-lg border border-red-300/70 dark:border-red-800/70 bg-white/70 dark:bg-red-950/20 p-2">
              <div class="text-[11px] font-semibold text-red-700 dark:text-red-300">cache_error</div>
              <div class="font-mono text-[11px] text-red-700 dark:text-red-200">{{ diagnostics.cache_error.code || '-' }} | {{ diagnostics.cache_error.type || '-' }}</div>
              <div class="text-[11px] text-red-800 dark:text-red-100 break-words">{{ diagnostics.cache_error.message || '-' }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700 space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('dashboard_recent_errors_title', 'Recent Errors') }}</h3>
              <div class="flex items-center gap-2">
                <button
                  @click="refreshRecentErrors"
                  :disabled="loadingRecentErrors"
                  class="px-2.5 py-1 rounded text-xs font-medium border border-gray-300 dark:border-gray-600
                         bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:opacity-50"
                >
                  {{ loadingRecentErrors ? t('dashboard_recent_errors_refreshing', 'Refreshing...') : t('dashboard_recent_errors_refresh', 'Refresh') }}
                </button>
                <button
                  @click="clearRecentErrors"
                  :disabled="loadingRecentErrors"
                  class="px-2.5 py-1 rounded text-xs font-medium border border-red-300 dark:border-red-700
                         text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30 transition-all disabled:opacity-50"
                >
                  {{ t('dashboard_recent_errors_clear', 'Clear') }}
                </button>
                <button
                  @click="exportRecentErrors"
                  :disabled="loadingRecentErrors"
                  class="px-2.5 py-1 rounded text-xs font-medium border border-gray-300 dark:border-gray-600
                         bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:opacity-50"
                >
                  {{ t('dashboard_recent_errors_export', 'Export') }}
                </button>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-8 gap-2">
              <input
                v-model.trim="recentFilters.endpoint"
                class="cfg-input text-xs"
                :placeholder="t('dashboard_recent_errors_filter_endpoint', 'Filter endpoint')"
              />
              <input
                v-model.trim="recentFilters.requestId"
                class="cfg-input text-xs font-mono"
                :placeholder="t('dashboard_recent_errors_filter_request_id', 'Filter request_id')"
              />
              <select v-model="recentFilters.kind" class="cfg-input text-xs">
                <option value="">{{ t('dashboard_recent_errors_filter_kind_all', 'All kinds') }}</option>
                <option value="error">{{ t('dashboard_recent_errors_kind_error', 'Error') }}</option>
                <option value="cache_fallback">{{ t('dashboard_recent_errors_kind_cache_fallback', 'Cache Fallback') }}</option>
              </select>
              <select v-model.number="recentFilters.sinceHours" class="cfg-input text-xs">
                <option :value="0">{{ t('dashboard_recent_errors_filter_since_all', 'All time') }}</option>
                <option :value="1">{{ t('dashboard_recent_errors_filter_since_1h', 'Last 1h') }}</option>
                <option :value="6">{{ t('dashboard_recent_errors_filter_since_6h', 'Last 6h') }}</option>
                <option :value="24">{{ t('dashboard_recent_errors_filter_since_24h', 'Last 24h') }}</option>
                <option :value="72">{{ t('dashboard_recent_errors_filter_since_72h', 'Last 72h') }}</option>
              </select>
              <select v-model="recentFilters.status" class="cfg-input text-xs">
                <option value="">{{ t('dashboard_recent_errors_filter_status_all', 'All status') }}</option>
                <option value="200">200</option>
                <option value="500">500</option>
              </select>
              <input
                v-model.trim="recentFilters.errorCode"
                class="cfg-input text-xs font-mono"
                :placeholder="t('dashboard_recent_errors_filter_error_code', 'Filter error_code')"
              />
              <input
                v-model.trim="recentFilters.cacheErrorCode"
                class="cfg-input text-xs font-mono"
                :placeholder="t('dashboard_recent_errors_filter_cache_error_code', 'Filter cache_error_code')"
              />
              <input
                v-model.trim="recentFilters.messageContains"
                class="cfg-input text-xs"
                :placeholder="t('dashboard_recent_errors_filter_message_contains', 'Filter message contains')"
              />
            </div>

            <div class="flex flex-wrap items-center gap-2 text-[11px]">
              <span class="tag-chip bg-slate-500/15 text-slate-600 dark:text-slate-300">
                {{ t('dashboard_recent_errors_summary_total', 'Total') }}: {{ recentPagination.totalAvailable || 0 }}
              </span>
              <span class="tag-chip bg-gray-500/15 text-gray-600 dark:text-gray-300">
                {{ t('dashboard_recent_errors_summary_matched', 'Matched') }}: {{ recentSummary.matched_count || 0 }}
              </span>
              <span class="tag-chip bg-red-500/15 text-red-600 dark:text-red-300">
                {{ t('dashboard_recent_errors_summary_error', 'Errors') }}: {{ recentSummaryCount('error') }}
              </span>
              <span class="tag-chip bg-amber-500/15 text-amber-600 dark:text-amber-300">
                {{ t('dashboard_recent_errors_summary_fallback', 'Fallbacks') }}: {{ recentSummaryCount('cache_fallback') }}
              </span>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_time', 'Time') }}
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_endpoint', 'Endpoint') }}
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_kind', 'Kind') }}
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_request_id', 'Request ID') }}
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_status', 'Status') }}
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_codes', 'Codes') }}
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('dashboard_recent_errors_col_message', 'Message') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!recentErrors.length">
                  <td :colspan="7" class="px-4 py-8 text-center text-gray-400 text-sm">{{ t('datatable_no_data', 'No data') }}</td>
                </tr>
                <tr
                  v-for="(row, i) in recentErrors"
                  :key="'recent-err-' + i"
                  class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                >
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 font-mono">{{ fmtTime(row.event_utc) || '-' }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300"><span class="font-mono">{{ row.endpoint || '-' }}</span></td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                    <span class="tag-chip" :class="recentKindBadgeClass(row.kind)">{{ recentKindLabel(row.kind) }}</span>
                  </td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 font-mono">{{ row.request_id || '-' }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 font-mono">{{ row.status || '-' }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 font-mono">{{ recentCodes(row) }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                    <span class="block truncate max-w-[28rem]" :title="row.message || '-'">{{ row.message || '-' }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="recentPagination.hasMore" class="px-4 py-3 border-t border-gray-200 dark:border-gray-700">
            <button
              @click="loadMoreRecentErrors"
              :disabled="loadingRecentErrors"
              class="px-2.5 py-1 rounded text-xs font-medium border border-gray-300 dark:border-gray-600
                     bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:opacity-50"
            >
              {{ loadingRecentErrors ? t('dashboard_recent_errors_loading_more', 'Loading...') : t('dashboard_recent_errors_load_more', 'Load More') }}
            </button>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div
            v-for="kpi in summaryKpis"
            :key="kpi.label"
            class="kpi-card rounded-xl p-3 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50"
          >
            <div class="text-[10px] text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-0.5">{{ kpi.label }}</div>
            <div class="text-lg font-bold tabular-nums" :class="kpi.color || ''">{{ kpi.value }}</div>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('dashboard_global_leaderboard', 'Global Leaderboard') }}</h3>
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th
                    v-for="h in lbHeaders"
                    :key="h"
                    class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!lbRows.length">
                  <td :colspan="lbHeaders.length" class="px-4 py-8 text-center text-gray-400 text-sm">{{ t('datatable_no_data', 'No data') }}</td>
                </tr>
                <tr
                  v-for="(row, i) in lbRows"
                  :key="'lb-' + i"
                  class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                >
                  <td v-for="(cell, j) in row" :key="'lb-cell-' + i + '-' + j" class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('dashboard_combo_stability', 'Combo Stability') }}</h3>
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th
                    v-for="h in comboHeaders"
                    :key="h"
                    class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!comboRows.length">
                  <td :colspan="comboHeaders.length" class="px-4 py-8 text-center text-gray-400 text-sm">{{ t('datatable_no_data', 'No data') }}</td>
                </tr>
                <tr
                  v-for="(row, i) in comboRows"
                  :key="'combo-' + i"
                  class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                >
                  <td v-for="(cell, j) in row" :key="'combo-cell-' + i + '-' + j" class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('dashboard_run_history', 'Run History') }}</h3>
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th
                    v-for="h in histHeaders"
                    :key="h"
                    class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700"
                  >
                    {{ h }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!histRows.length">
                  <td :colspan="histHeaders.length" class="px-4 py-8 text-center text-gray-400 text-sm">{{ t('datatable_no_data', 'No data') }}</td>
                </tr>
                <tr
                  v-for="(row, i) in histRows"
                  :key="'hist-' + i"
                  class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                >
                  <td v-for="(cell, j) in row" :key="'hist-cell-' + i + '-' + j" class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>
  `,

  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key

    const loading = ref(true)
    const topN = ref(20)
    const generating = ref(false)
    const autoRefresh = ref(true)
    const pollSeconds = ref(8)

    const summaryKpis = ref([])
    const lbHeaders = ref([])
    const lbRows = ref([])
    const comboHeaders = ref([])
    const comboRows = ref([])
    const histHeaders = ref([])
    const histRows = ref([])

    const payloadSource = ref('live')
    const payloadReasonCode = ref('')
    const sourceRows = ref([])
    const sourceErrorRows = ref([])
    const diagnostics = ref(null)
    const reportMeta = ref({ source: '', reasonCode: '', at: '', requestId: '' })
    const lastRequestId = ref('')
    const loadingRecentErrors = ref(false)
    const recentErrors = ref([])
    const recentErrorsLimit = ref(20)
    const recentSummary = ref({ matched_count: 0, by_kind: {} })
    const recentPagination = ref({ offset: 0, hasMore: false, nextOffset: null, totalAvailable: 0 })
    const recentFilters = ref({
      endpoint: '',
      requestId: '',
      kind: '',
      sinceHours: 0,
      status: '',
      errorCode: '',
      cacheErrorCode: '',
      messageContains: '',
    })

    let pollTimer = null

    function fmtN(v, d = 4) {
      const n = Number(v)
      if (!Number.isFinite(n)) return v == null ? '' : String(v)
      return n.toFixed(d).replace(/\.?0+$/, '')
    }

    function fmtTime(raw) {
      if (!raw) return ''
      const d = Date.parse(raw)
      return Number.isNaN(d) ? String(raw) : new Date(d).toLocaleString()
    }

    function payloadSourceLabel(source) {
      if (source === 'cache_fallback') return t('dashboard_source_cache_fallback', 'Cache Fallback')
      return t('dashboard_source_live', 'Live')
    }

    function sourceBadgeClass(source) {
      if (source === 'cache_fallback') {
        return 'bg-amber-500/15 text-amber-600 dark:text-amber-300'
      }
      return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300'
    }

    function clearDiagnostics() {
      diagnostics.value = null
    }

    function setDiagnostics(endpoint, meta) {
      const resolvedEndpoint = meta.endpoint || endpoint
      const resolvedAt = meta.error_utc || new Date().toISOString()
      diagnostics.value = {
        endpoint: resolvedEndpoint,
        status: meta.status || 0,
        request_id: meta.request_id || '',
        message: meta.message || '',
        error_code: meta.error_code || '',
        cache_error_code: meta.cache_error_code || '',
        live_error: meta.live_error || null,
        cache_error: meta.cache_error || null,
        at: resolvedAt,
      }
    }

    function makeErrorToast(prefix, meta) {
      const parts = [prefix, meta.message || '']
      const codes = []
      if (meta.request_id) codes.push(`req=${meta.request_id}`)
      if (meta.error_code) codes.push(`live=${meta.error_code}`)
      if (meta.cache_error_code) codes.push(`cache=${meta.cache_error_code}`)
      if (codes.length) parts.push(`[${codes.join(', ')}]`)
      return parts.filter(Boolean).join(': ')
    }

    function recentKindLabel(kind) {
      if (kind === 'cache_fallback') {
        return t('dashboard_recent_errors_kind_cache_fallback', 'Cache Fallback')
      }
      if (kind === 'error') {
        return t('dashboard_recent_errors_kind_error', 'Error')
      }
      return kind || '-'
    }

    function recentKindBadgeClass(kind) {
      if (kind === 'cache_fallback') {
        return 'bg-amber-500/15 text-amber-600 dark:text-amber-300'
      }
      if (kind === 'error') {
        return 'bg-red-500/15 text-red-600 dark:text-red-300'
      }
      return 'bg-gray-500/15 text-gray-600 dark:text-gray-300'
    }

    function recentCodes(row) {
      const parts = []
      if (row?.error_code) parts.push(`live:${row.error_code}`)
      if (row?.cache_error_code) parts.push(`cache:${row.cache_error_code}`)
      return parts.length ? parts.join(' | ') : '-'
    }

    function recentSummaryCount(kind) {
      const byKind = recentSummary.value?.by_kind && typeof recentSummary.value.by_kind === 'object'
        ? recentSummary.value.by_kind
        : {}
      return Number(byKind[kind] || 0)
    }

    function buildRecentFilterQuery({ includePagination = true, append = false, forceLimit = null } = {}) {
      const qs = new URLSearchParams()
      const limitVal = Number(forceLimit || recentErrorsLimit.value)
      qs.set('limit', String(Math.max(1, limitVal)))
      if (includePagination) {
        const requestOffset = append ? Number(recentPagination.value.nextOffset || 0) : 0
        qs.set('offset', String(Math.max(0, requestOffset)))
      }
      if (recentFilters.value.endpoint) qs.set('endpoint', recentFilters.value.endpoint)
      if (recentFilters.value.requestId) qs.set('request_id', recentFilters.value.requestId)
      if (recentFilters.value.kind) qs.set('kind', recentFilters.value.kind)
      if (Number(recentFilters.value.sinceHours) > 0) qs.set('since_hours', String(recentFilters.value.sinceHours))
      if (recentFilters.value.status) qs.set('status', recentFilters.value.status)
      if (recentFilters.value.errorCode) qs.set('error_code', recentFilters.value.errorCode)
      if (recentFilters.value.cacheErrorCode) qs.set('cache_error_code', recentFilters.value.cacheErrorCode)
      if (recentFilters.value.messageContains) qs.set('message_contains', recentFilters.value.messageContains)
      return qs
    }

    async function loadRecentErrors(options = {}) {
      const silent = Boolean(options?.silent)
      const append = Boolean(options?.append)
      if (!silent) loadingRecentErrors.value = true
      try {
        const qs = buildRecentFilterQuery({ includePagination: true, append })
        const payload = await fetchJson(`/dashboard/errors.json?${qs.toString()}`)
        const rows = Array.isArray(payload?.rows) ? payload.rows : []
        recentErrors.value = append ? recentErrors.value.concat(rows) : rows
        recentSummary.value = {
          matched_count: Number(payload?.matched_count || 0),
          by_kind: payload?.summary?.by_kind && typeof payload.summary.by_kind === 'object' ? payload.summary.by_kind : {},
        }
        recentPagination.value = {
          offset: Number(payload?.offset || 0),
          hasMore: Boolean(payload?.has_more),
          nextOffset: payload?.next_offset == null ? null : Number(payload.next_offset),
          totalAvailable: Number(payload?.total_available || 0),
        }
      } catch (error) {
        if (!silent) {
          const meta = formatApiError(error)
          showToast(
            makeErrorToast(t('dashboard_recent_errors_load_failed', 'Failed to load recent errors'), meta),
            'warn',
            5000,
          )
        }
      } finally {
        if (!silent) loadingRecentErrors.value = false
      }
    }

    async function refreshRecentErrors() {
      await loadRecentErrors({ silent: false, append: false })
    }

    async function loadMoreRecentErrors() {
      await loadRecentErrors({ silent: false, append: true })
    }

    async function clearRecentErrors() {
      loadingRecentErrors.value = true
      try {
        const payload = await postJson('/dashboard/errors/clear', {
          endpoint: recentFilters.value.endpoint || '',
          request_id: recentFilters.value.requestId || '',
          kind: recentFilters.value.kind || '',
          since_hours: Number(recentFilters.value.sinceHours) || 0,
          status: recentFilters.value.status || '',
          error_code: recentFilters.value.errorCode || '',
          cache_error_code: recentFilters.value.cacheErrorCode || '',
          message_contains: recentFilters.value.messageContains || '',
        })
        showToast(
          `${t('dashboard_recent_errors_cleared', 'Recent errors cleared')}: ${payload?.cleared ?? 0}`,
          'success',
          3500,
        )
        await loadRecentErrors({ silent: true })
      } catch (error) {
        const meta = formatApiError(error)
        showToast(
          makeErrorToast(t('dashboard_recent_errors_clear_failed', 'Failed to clear recent errors'), meta),
          'error',
          5000,
        )
      } finally {
        loadingRecentErrors.value = false
      }
    }

    async function exportRecentErrors() {
      loadingRecentErrors.value = true
      try {
        const exportLimit = Math.max(recentErrorsLimit.value, Number(recentPagination.value.totalAvailable || 0), 1)
        const qs = buildRecentFilterQuery({ includePagination: false, forceLimit: exportLimit })
        const response = await fetch(`/dashboard/errors/export.ndjson?${qs.toString()}`, { cache: 'no-store' })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const text = await response.text()
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const stamp = new Date().toISOString().replace(/[:.]/g, '-')
        const a = document.createElement('a')
        a.href = url
        a.download = `dashboard_errors_${stamp}.ndjson`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        showToast(t('dashboard_recent_errors_exported', 'Recent errors exported'), 'success', 3000)
      } catch (error) {
        const meta = formatApiError(error)
        showToast(
          makeErrorToast(t('dashboard_recent_errors_export_failed', 'Failed to export recent errors'), meta),
          'error',
          5000,
        )
      } finally {
        loadingRecentErrors.value = false
      }
    }

    function updateTelemetry(payload) {
      const source = String(payload?.payload_source || 'live')
      const fallback = payload?.cache_fallback && typeof payload.cache_fallback === 'object'
        ? payload.cache_fallback
        : null

      payloadSource.value = source
      payloadReasonCode.value = fallback?.reason_code || ''
      lastRequestId.value = String(payload?.request_id || '')

      const rows = [
        { label: t('dashboard_payload_source', 'Payload Source'), value: payloadSourceLabel(source) },
        { label: t('dashboard_payload_generated_at', 'Payload Generated At'), value: fmtTime(payload?.generated_utc) },
        { label: t('dashboard_request_id', 'Request ID'), value: payload?.request_id || '' },
        {
          label: t('dashboard_refresh_state', 'Refresh State'),
          value: autoRefresh.value ? t('dashboard_refresh_on', 'On') : t('dashboard_refresh_off', 'Off'),
        },
        {
          label: t('dashboard_refresh_interval', 'Refresh Interval'),
          value: `${Math.max(1, Number(pollSeconds.value) || 8)}s`,
        },
      ]

      if (fallback) {
        rows.push({ label: t('dashboard_fallback_source', 'Fallback Source'), value: fallback.source || '' })
        rows.push({ label: t('dashboard_fallback_time', 'Fallback Time'), value: fmtTime(fallback.fallback_utc) })
        rows.push({ label: t('dashboard_reason_code', 'Reason Code'), value: fallback.reason_code || '' })
      }

      if (reportMeta.value.source) {
        rows.push({
          label: t('dashboard_last_report_source', 'Last Report Source'),
          value: `${payloadSourceLabel(reportMeta.value.source)}${reportMeta.value.reasonCode ? ` (${reportMeta.value.reasonCode})` : ''}`,
        })
        rows.push({ label: t('dashboard_last_report_time', 'Last Report Time'), value: fmtTime(reportMeta.value.at) })
        rows.push({ label: t('dashboard_last_report_request_id', 'Last Report Request ID'), value: reportMeta.value.requestId || '' })
      }

      sourceRows.value = rows

      const errorRows = []
      if (fallback?.live_error && typeof fallback.live_error === 'object') {
        errorRows.push({
          stage: 'live_error',
          code: fallback.live_error.code || '',
          type: fallback.live_error.type || '',
          message: fallback.live_error.message || '',
        })
      }
      sourceErrorRows.value = errorRows
    }

    async function refresh() {
      try {
        const payload = await fetchJson(`/dashboard/cross_run.json?top_n=${topN.value}`)
        const summary = payload.summary || {}

        diagnostics.value = null
        updateTelemetry(payload)

        summaryKpis.value = [
          { label: t('dashboard_kpi_total_runs', 'Total Runs'), value: summary.total_runs ?? '--' },
          { label: t('dashboard_kpi_unique_symbols', 'Unique Symbols'), value: summary.unique_symbols ?? '--' },
          { label: t('dashboard_kpi_unique_timeframes', 'Unique Timeframes'), value: summary.unique_timeframes ?? '--' },
          {
            label: t('dashboard_kpi_avg_oos_return', 'Avg OOS Return%'),
            value: fmtN(summary.avg_oos_return_pct),
            color: Number(summary.avg_oos_return_pct) > 0 ? 'text-profit' : 'text-loss',
          },
          { label: t('dashboard_kpi_coverage', 'Coverage%'), value: fmtN(summary.coverage_pct, 2) },
          { label: t('dashboard_kpi_latest_run', 'Latest Run'), value: summary.latest_run_id || '--' },
          { label: t('dashboard_kpi_generated_at', 'Generated At'), value: fmtTime(payload.generated_utc) },
        ]

        lbHeaders.value = [
          t('dashboard_lb_header_run_id', 'Run ID'),
          t('dashboard_lb_header_time', 'Time'),
          t('dashboard_lb_header_mode', 'Mode'),
          t('dashboard_lb_header_best_tf', 'Best TF'),
          t('dashboard_lb_header_oos_return', 'OOS Return%'),
          t('dashboard_lb_header_avg_return', 'Avg Return%'),
          t('dashboard_lb_header_symbols', 'Symbols'),
        ]

        const leaderboardRows = Array.isArray(payload.global_leaderboard)
          ? payload.global_leaderboard
          : (Array.isArray(payload.leaderboard) ? payload.leaderboard : [])

        lbRows.value = leaderboardRows.map(row => [
          row.run_id || '',
          fmtTime(row.timestamp_utc),
          row.search_mode || '',
          row.best_timeframe || '',
          fmtN(row.oos_avg_total_return_pct),
          fmtN(row.avg_total_return_pct),
          Array.isArray(row.trade_symbols) ? row.trade_symbols.join(',') : '',
        ])

        comboHeaders.value = [
          t('dashboard_combo_header_key', 'Combo Key'),
          t('dashboard_combo_header_appearances', 'Appearances'),
          t('dashboard_combo_header_avg_oos_return', 'Avg OOS Return%'),
          t('dashboard_combo_header_best_oos_return', 'Best OOS Return%'),
          t('dashboard_combo_header_avg_drawdown', 'Avg Drawdown%'),
          t('dashboard_combo_header_run_ids', 'Run IDs'),
        ]

        comboRows.value = (payload.combo_stability || []).map(row => [
          row.combo_key || '',
          row.appearances || 0,
          fmtN(row.avg_oos_return_pct),
          fmtN(row.best_oos_return_pct),
          fmtN(row.avg_oos_drawdown_pct),
          Array.isArray(row.run_ids) ? row.run_ids.join(', ') : '',
        ])

        histHeaders.value = [
          t('dashboard_hist_header_run_id', 'Run ID'),
          t('dashboard_hist_header_time', 'Time'),
          t('dashboard_hist_header_mode', 'Mode'),
          t('dashboard_hist_header_timeframes', 'Timeframes'),
          t('dashboard_hist_header_symbols', 'Symbols'),
          t('dashboard_hist_header_oos_return', 'OOS Return%'),
          t('dashboard_hist_header_report', 'Report'),
        ]

        const historyRows = Array.isArray(payload.run_history)
          ? payload.run_history
          : (Array.isArray(payload.history) ? payload.history : [])

        histRows.value = historyRows.map(row => [
          row.run_id || '',
          fmtTime(row.timestamp_utc),
          row.search_mode || '',
          Array.isArray(row.timeframes) ? row.timeframes.join(',') : '',
          Array.isArray(row.trade_symbols) ? row.trade_symbols.join(',') : '',
          fmtN(row.oos_avg_total_return_pct),
          row.report_file || '',
        ])
      } catch (error) {
        const meta = formatApiError(error)
        setDiagnostics('/dashboard/cross_run.json', meta)
        showToast(makeErrorToast(t('dashboard_load_failed', 'Dashboard load failed'), meta), 'error', 6000)
      } finally {
        loading.value = false
        await loadRecentErrors({ silent: true })
      }
    }

    async function genReport() {
      generating.value = true
      try {
        const payload = await postJson('/dashboard/report/generate', { top_n: topN.value })
        const source = String(payload?.payload_source || 'live')
        const fallback = payload?.cache_fallback && typeof payload.cache_fallback === 'object'
          ? payload.cache_fallback
          : null

        reportMeta.value = {
          source,
          reasonCode: fallback?.reason_code || '',
          at: new Date().toISOString(),
          requestId: String(payload?.request_id || ''),
        }
        lastRequestId.value = String(payload?.request_id || '')

        if (source === 'cache_fallback') {
          showToast(
            `${t('dashboard_report_generated_cache_fallback', 'Report generated from cache fallback')} (${fallback?.reason_code || 'unknown'})`,
            'warn',
            5000,
          )
        } else {
          showToast(t('dashboard_report_generated', 'Report generated'), 'success')
        }

        diagnostics.value = null
        await refresh()
      } catch (error) {
        const meta = formatApiError(error)
        setDiagnostics('/dashboard/report/generate', meta)
        showToast(makeErrorToast(t('dashboard_report_generate_failed', 'Report generation failed'), meta), 'error', 6000)
      } finally {
        generating.value = false
        await loadRecentErrors({ silent: true })
      }
    }

    async function copyDiagnostics() {
      if (!diagnostics.value) return
      const text = JSON.stringify(diagnostics.value, null, 2)
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text)
        } else {
          throw new Error('clipboard_unavailable')
        }
        showToast(t('dashboard_error_panel_copy_success', 'Diagnostics JSON copied'), 'success', 2500)
      } catch (_) {
        showToast(t('dashboard_error_panel_copy_failed', 'Copy diagnostics failed'), 'error', 3500)
      }
    }

    function schedulePolling() {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
      if (!autoRefresh.value) return
      const sec = Math.max(1, Number(pollSeconds.value) || 8)
      pollTimer = setInterval(refresh, sec * 1000)
    }

    watch(autoRefresh, () => {
      schedulePolling()
    })

    watch(pollSeconds, () => {
      schedulePolling()
    })

    onMounted(() => {
      refresh()
      schedulePolling()
    })

    onUnmounted(() => {
      if (pollTimer) clearInterval(pollTimer)
    })

    return {
      loading,
      topN,
      generating,
      autoRefresh,
      pollSeconds,
      summaryKpis,
      lbHeaders,
      lbRows,
      comboHeaders,
      comboRows,
      histHeaders,
      histRows,
      payloadSource,
      payloadReasonCode,
      sourceRows,
      sourceErrorRows,
      diagnostics,
      reportMeta,
      lastRequestId,
      loadingRecentErrors,
      recentErrors,
      recentSummary,
      recentPagination,
      recentFilters,
      refresh,
      refreshRecentErrors,
      loadMoreRecentErrors,
      clearRecentErrors,
      exportRecentErrors,
      genReport,
      clearDiagnostics,
      copyDiagnostics,
      fmtTime,
      recentKindLabel,
      recentKindBadgeClass,
      recentCodes,
      recentSummaryCount,
      sourceBadgeClass,
      payloadSourceLabel,
      t,
    }
  },
}

