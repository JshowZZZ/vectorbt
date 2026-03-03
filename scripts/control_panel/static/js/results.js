// --- Results Tab ---
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson } from './api.js'
import { store, showToast, confirmAction } from './store.js'
import { L, PARAM_ORDER, PARAM_SHORT, NUM_COLS, TOP_COLS, isParamKey } from './i18n.js'

export const ResultsTab = {
  name: 'ResultsTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="skeleton skeleton-card h-20"></div>
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div v-for="n in 7" :key="'results-kpi-sk-' + n" class="skeleton skeleton-card h-16"></div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div v-for="n in 3" :key="'results-chart-sk-' + n" class="skeleton skeleton-card h-72"></div>
        </div>
        <div class="skeleton skeleton-card h-72"></div>
      </div>
      <template v-else>
      <!-- Filters Bar -->
      <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
        <div class="flex flex-wrap items-end gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('results_filter_timeframe', '時間週期') }}</span>
            <select v-model="filters.timeframe" class="cfg-input">
              <option value="all">{{ tr('results_filter_all', '全部') }}</option>
              <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('results_filter_oos_return', 'OOS 報酬 >=') }}</span>
            <input v-model.number="filters.minReturn" type="number" step="0.1" placeholder="0" class="cfg-input w-20" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('results_filter_win_rate', '勝率 >=') }}</span>
            <input v-model.number="filters.minWinRate" type="number" step="1" placeholder="50" class="cfg-input w-20" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('results_filter_daily_trades', '日均交易數 >=') }}</span>
            <input v-model.number="filters.minDailyTrades" type="number" step="0.1" placeholder="5" class="cfg-input w-20" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('results_filter_drawdown', '最大回撤 <=') }}</span>
            <input v-model.number="filters.maxDrawdown" type="number" step="0.1" placeholder="5" class="cfg-input w-20" />
          </label>
          <label class="inline-flex items-center gap-1.5 mt-5">
            <input type="checkbox" v-model="filters.oosPositive" class="rounded text-blue-600" />
            <span class="text-xs text-gray-600 dark:text-gray-400">OOS &gt; 0</span>
          </label>
          <div class="flex gap-2 ml-auto mt-5">
            <button @click="applyAndRender"
                    class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white transition-all">
              {{ tr('results_apply_filters', '套用篩選') }}
            </button>
            <button @click="resetFilters"
                    class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                           bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all">
              {{ tr('results_reset_filters', '重設') }}
            </button>
          </div>
        </div>
      </div>

      <!-- KPIs -->
      <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <div v-for="kpi in kpis" :key="kpi.label"
             class="kpi-card rounded-xl p-3 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="text-[10px] text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-0.5">{{ kpi.label }}</div>
          <div class="text-lg font-bold tabular-nums" :class="kpi.color">{{ kpi.value }}</div>
        </div>
      </div>
      <div v-if="dataNote" class="text-xs text-gray-500 dark:text-gray-400">{{ dataNote }}</div>

      <!-- Charts -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ tr('results_chart_return_vs_drawdown', '報酬 vs 回撤') }}</div>
          <div class="chart-container"><canvas ref="scatterRef"></canvas></div>
        </div>
        <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ tr('results_chart_return_hist', '報酬分佈') }}</div>
          <div class="chart-container"><canvas ref="histRef"></canvas></div>
        </div>
        <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ tr('results_chart_risk_return_frontier', '風險-報酬前緣') }}</div>
          <div class="chart-container"><canvas ref="frontierRef"></canvas></div>
        </div>
      </div>

      <!-- Advanced Analysis -->
      <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-3">
        <div class="flex flex-wrap items-end gap-3">
          <div class="text-sm font-semibold text-gray-900 dark:text-white mr-2">{{ tr('advanced_analytics_title', 'Advanced Analytics (Monte Carlo)') }}</div>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('advanced_trials', 'Trials') }}</span>
            <input v-model.number="advancedParams.nTrials" type="number" min="100" max="50000" step="100" class="cfg-input w-28" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('advanced_sample_size_optional', 'Sample Size (optional)') }}</span>
            <input v-model.number="advancedParams.sampleSize" type="number" min="1" step="1" class="cfg-input w-36" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('advanced_seed', 'Seed') }}</span>
            <input v-model.number="advancedParams.seed" type="number" step="1" class="cfg-input w-24" />
          </label>
          <button @click="loadAdvancedAnalysis" :disabled="advancedLoading"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-cyan-300 dark:border-cyan-700
                         bg-cyan-50 dark:bg-cyan-900/20 text-cyan-700 dark:text-cyan-200 hover:bg-cyan-100 dark:hover:bg-cyan-900/35 transition-all disabled:opacity-50">
            {{ advancedLoading ? tr('advanced_running', 'Running...') : tr('advanced_run_monte_carlo', 'Run Monte Carlo') }}
          </button>
          <button @click="downloadAdvancedJson" :disabled="downloadingAdvanced || !advancedAnalysis"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                         bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:opacity-50">
            {{ downloadingAdvanced ? tr('advanced_downloading', 'Downloading...') : tr('advanced_download_json', 'Download Analysis JSON') }}
          </button>
        </div>
        <div v-if="advancedAnalysis" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_return_mean', 'Return Mean') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ fmtNum(advancedAnalysis?.return_distribution?.mean) }}%</div>
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_percentiles', 'P05 / P50 / P95') }}</div>
            <div class="text-xs tabular-nums">
              {{ fmtNum(advancedAnalysis?.return_distribution?.p05) }} /
              {{ fmtNum(advancedAnalysis?.return_distribution?.p50) }} /
              {{ fmtNum(advancedAnalysis?.return_distribution?.p95) }}
            </div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_mc_mean', 'Monte Carlo Mean') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ fmtNum(advancedAnalysis?.monte_carlo?.mean_return_pct) }}%</div>
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_mc_percentiles', 'MC P05 / P95') }}</div>
            <div class="text-xs tabular-nums">
              {{ fmtNum(advancedAnalysis?.monte_carlo?.p05_return_pct) }} /
              {{ fmtNum(advancedAnalysis?.monte_carlo?.p95_return_pct) }}
            </div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_prob_positive', 'Prob Positive') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ fmtNum(advancedAnalysis?.monte_carlo?.prob_positive_pct) }}%</div>
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_cvar5', 'CVaR 5%') }}</div>
            <div class="text-xs tabular-nums">{{ fmtNum(advancedAnalysis?.monte_carlo?.cvar5_return_pct) }}%</div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_drawdown_mean', 'Drawdown Mean') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ fmtNum(advancedAnalysis?.drawdown_distribution?.mean) }}%</div>
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('advanced_data_points', 'Data Points') }}</div>
            <div class="text-xs tabular-nums">{{ advancedAnalysis?.return_distribution?.count || 0 }}</div>
          </div>
        </div>
      </div>

      <!-- Paper Feedback Loop -->
      <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <div class="text-sm font-semibold text-gray-900 dark:text-white mr-2">{{ tr('feedback_loop_title', 'Paper Feedback Loop') }}</div>
          <button @click="loadFeedbackData" :disabled="feedbackLoading"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-amber-300 dark:border-amber-700
                         bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/35 transition-all disabled:opacity-50">
            {{ feedbackLoading ? tr('feedback_refreshing', 'Refreshing...') : tr('feedback_refresh', 'Refresh Feedback') }}
          </button>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('feedback_total', 'Total Feedback') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ feedbackSummary?.total_feedback || 0 }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('feedback_latest_utc', 'Latest UTC') }}</div>
            <div class="text-xs tabular-nums break-all">{{ fmtUtc(feedbackSummary?.latest_timestamp_utc) }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('feedback_pnl_mean', 'PnL Mean') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ fmtNum(feedbackSummary?.pnl_pct?.mean_pct) }}%</div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-[11px] text-gray-500 dark:text-gray-400">{{ tr('feedback_pnl_win_rate', 'PnL Win Rate') }}</div>
            <div class="text-lg font-semibold tabular-nums">{{ fmtNum(feedbackSummary?.pnl_pct?.win_rate_pct) }}%</div>
          </div>
        </div>

        <div class="flex flex-wrap items-end gap-2">
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('feedback_recommend_profile', 'Recommendation Profile') }}</span>
            <select v-model="feedbackRecommendationProfile" class="cfg-input w-36">
              <option value="auto">auto</option>
              <option value="defensive">defensive</option>
              <option value="balanced">balanced</option>
              <option value="offensive">offensive</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ tr('feedback_min_samples', 'Min Samples') }}</span>
            <input v-model.number="feedbackRecommendationMinSamples" type="number" min="1" step="1" class="cfg-input w-24" />
          </label>
          <button @click="loadFeedbackData" :disabled="feedbackLoading"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-sky-300 dark:border-sky-700
                         bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-200 hover:bg-sky-100 dark:hover:bg-sky-900/35 transition-all disabled:opacity-50">
            {{ feedbackLoading ? tr('feedback_loading', 'Loading...') : tr('feedback_refresh_recommendations', 'Refresh Recommendations') }}
          </button>
          <button @click="exportFeedbackAdjustedConfig" :disabled="exportingFeedbackAdjusted"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-emerald-300 dark:border-emerald-700
                         bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-200 hover:bg-emerald-100 dark:hover:bg-emerald-900/35 transition-all disabled:opacity-50">
            {{ exportingFeedbackAdjusted ? tr('feedback_exporting', 'Exporting...') : tr('feedback_export_adjusted_config', 'Export Adjusted Config') }}
          </button>
          <button @click="enqueueFeedbackAdjustedBatch" :disabled="enqueuingFeedbackBatch"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-violet-300 dark:border-violet-700
                         bg-violet-50 dark:bg-violet-900/20 text-violet-700 dark:text-violet-200 hover:bg-violet-100 dark:hover:bg-violet-900/35 transition-all disabled:opacity-50">
            {{ enqueuingFeedbackBatch ? tr('feedback_enqueuing', 'Enqueuing...') : tr('feedback_enqueue_adjusted_batch', 'Enqueue Adjusted Batch') }}
          </button>
        </div>

        <div v-if="feedbackBatchPlan" class="rounded-lg border border-violet-200 dark:border-violet-800/60 bg-violet-50/60 dark:bg-violet-900/10 p-3 space-y-1">
          <div class="text-xs text-violet-800 dark:text-violet-200">
            {{ tr('feedback_last_enqueue', 'Last enqueue') }}: job #{{ feedbackBatchPlan.jobId }} ({{ feedbackBatchPlan.jobName || tr('feedback_unnamed_job', 'unnamed') }})
          </div>
          <div class="text-[11px] text-violet-700 dark:text-violet-300 font-mono break-all">
            {{ tr('feedback_config_path', 'config') }}: {{ feedbackBatchPlan.configPath || '--' }}
          </div>
          <div v-if="feedbackBatchPlan.signalConfigPath" class="text-[11px] text-violet-700 dark:text-violet-300 font-mono break-all">
            {{ tr('feedback_signal_config_path', 'signal config') }}: {{ feedbackBatchPlan.signalConfigPath }}
          </div>
          <div v-if="feedbackBatchPlan.warnings && feedbackBatchPlan.warnings.length"
               class="text-[11px] text-amber-700 dark:text-amber-300">
            {{ tr('feedback_guardrail_warnings', 'guardrails') }}: {{ formatFeedbackGuardrailWarnings(feedbackBatchPlan.warnings) }}
          </div>
          <div class="pt-1">
            <button @click="openBatchTabFromFeedbackPlan"
                    class="px-2.5 py-1 rounded text-[11px] font-medium border border-violet-300 dark:border-violet-700
                           bg-white dark:bg-gray-800 text-violet-700 dark:text-violet-200 hover:bg-violet-100 dark:hover:bg-violet-900/30 transition-all">
              {{ tr('feedback_open_batch_queue', 'Open Batch Queue') }}
            </button>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-6 gap-2">
          <input v-model.trim="feedbackForm.signalConfigId" placeholder="signal_config_id" class="cfg-input md:col-span-2" />
          <input v-model.trim="feedbackForm.symbol" :placeholder="tr('feedback_placeholder_symbol', 'symbol (e.g. ETH/BTC)')" class="cfg-input" />
          <input v-model.trim="feedbackForm.timeframe" :placeholder="tr('feedback_placeholder_timeframe', 'timeframe (e.g. 1h)')" class="cfg-input" />
          <select v-model="feedbackForm.action" class="cfg-input">
            <option v-for="act in feedbackActions" :key="act" :value="act">{{ act }}</option>
          </select>
          <input v-model.trim="feedbackForm.timestampUtc" :placeholder="tr('feedback_placeholder_timestamp_utc', 'timestamp_utc (ISO)')" class="cfg-input" />
          <input v-model.number="feedbackForm.pnlPct" type="number" step="0.0001" :placeholder="tr('feedback_placeholder_pnl_pct', 'pnl_pct (optional)')" class="cfg-input" />
          <input v-model.number="feedbackForm.qty" type="number" step="0.0001" :placeholder="tr('feedback_placeholder_qty', 'qty (optional)')" class="cfg-input" />
          <input v-model.trim="feedbackForm.paperRunId" :placeholder="tr('feedback_placeholder_paper_run_id', 'paper_run_id (optional)')" class="cfg-input" />
          <input v-model.trim="feedbackForm.note" :placeholder="tr('feedback_placeholder_note', 'note (optional)')" class="cfg-input md:col-span-2" />
          <button @click="submitFeedback" :disabled="submittingFeedback"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-emerald-300 dark:border-emerald-700
                         bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-200 hover:bg-emerald-100 dark:hover:bg-emerald-900/35 transition-all disabled:opacity-50">
            {{ submittingFeedback ? tr('feedback_submitting', 'Submitting...') : tr('feedback_submit', 'Submit Feedback') }}
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="min-w-full text-xs">
            <thead class="text-gray-500 dark:text-gray-400">
              <tr>
                <th class="text-left py-1 pr-3">{{ tr('feedback_col_timestamp', 'timestamp') }}</th>
                <th class="text-left py-1 pr-3">{{ tr('feedback_col_symbol', 'symbol') }}</th>
                <th class="text-left py-1 pr-3">{{ tr('feedback_col_tf', 'tf') }}</th>
                <th class="text-left py-1 pr-3">{{ tr('feedback_col_action', 'action') }}</th>
                <th class="text-right py-1 pr-3">{{ tr('feedback_col_pnl', 'pnl%') }}</th>
                <th class="text-left py-1 pr-3">{{ tr('feedback_col_note', 'note') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in feedbackRecent" :key="row.received_utc + '|' + row.timestamp_utc + '|' + row.action"
                  class="border-t border-gray-200 dark:border-gray-700">
                <td class="py-1 pr-3 tabular-nums">{{ fmtUtc(row.timestamp_utc) }}</td>
                <td class="py-1 pr-3">{{ row.symbol }}</td>
                <td class="py-1 pr-3">{{ row.timeframe }}</td>
                <td class="py-1 pr-3">{{ row.action }}</td>
                <td class="py-1 pr-3 text-right tabular-nums">{{ fmtNum(row.pnl_pct, 4) }}</td>
                <td class="py-1 pr-3">{{ row.note || '' }}</td>
              </tr>
              <tr v-if="!feedbackRecent.length">
                <td colspan="6" class="py-2 text-gray-500 dark:text-gray-400">{{ tr('feedback_no_records', 'No feedback records.') }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 overflow-x-auto">
            <div class="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">Top Signal Configs (by avg pnl%)</div>
            <table class="min-w-full text-xs">
              <thead class="text-gray-500 dark:text-gray-400">
                <tr>
                  <th class="text-left py-1 pr-3">signal_config_id</th>
                  <th class="text-right py-1 pr-3">count</th>
                  <th class="text-right py-1 pr-3">avg pnl%</th>
                  <th class="text-right py-1 pr-3">win%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in feedbackDiagnostics?.top_signal_configs || []" :key="'top-' + row.signal_config_id"
                    class="border-t border-gray-200 dark:border-gray-700">
                  <td class="py-1 pr-3 font-mono">{{ row.signal_config_id }}</td>
                  <td class="py-1 pr-3 text-right tabular-nums">{{ row.count }}</td>
                  <td class="py-1 pr-3 text-right tabular-nums">{{ fmtNum(row.avg_pnl_pct, 4) }}</td>
                  <td class="py-1 pr-3 text-right tabular-nums">{{ fmtNum(row.win_rate_pct, 2) }}</td>
                </tr>
                <tr v-if="!(feedbackDiagnostics?.top_signal_configs || []).length">
                  <td colspan="4" class="py-2 text-gray-500 dark:text-gray-400">No diagnostics yet.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 overflow-x-auto">
            <div class="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">Action Diagnostics</div>
            <table class="min-w-full text-xs">
              <thead class="text-gray-500 dark:text-gray-400">
                <tr>
                  <th class="text-left py-1 pr-3">action</th>
                  <th class="text-right py-1 pr-3">count</th>
                  <th class="text-right py-1 pr-3">avg pnl%</th>
                  <th class="text-right py-1 pr-3">win%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in feedbackDiagnostics?.action_diagnostics || []" :key="'act-' + row.action"
                    class="border-t border-gray-200 dark:border-gray-700">
                  <td class="py-1 pr-3">{{ row.action }}</td>
                  <td class="py-1 pr-3 text-right tabular-nums">{{ row.count }}</td>
                  <td class="py-1 pr-3 text-right tabular-nums">{{ fmtNum(row.avg_pnl_pct, 4) }}</td>
                  <td class="py-1 pr-3 text-right tabular-nums">{{ fmtNum(row.win_rate_pct, 2) }}</td>
                </tr>
                <tr v-if="!(feedbackDiagnostics?.action_diagnostics || []).length">
                  <td colspan="4" class="py-2 text-gray-500 dark:text-gray-400">No action diagnostics yet.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 overflow-x-auto">
          <div class="text-xs font-semibold text-gray-700 dark:text-gray-200 mb-2">Feedback Recommendations</div>
          <table class="min-w-full text-xs">
            <thead class="text-gray-500 dark:text-gray-400">
              <tr>
                <th class="text-left py-1 pr-3">symbol</th>
                <th class="text-left py-1 pr-3">tf</th>
                <th class="text-right py-1 pr-3">count</th>
                <th class="text-right py-1 pr-3">avg pnl%</th>
                <th class="text-left py-1 pr-3">profile</th>
                <th class="text-left py-1 pr-3">reason</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in feedbackRecommendations" :key="'rec-' + row.symbol + '|' + row.timeframe"
                  class="border-t border-gray-200 dark:border-gray-700">
                <td class="py-1 pr-3">{{ row.symbol }}</td>
                <td class="py-1 pr-3">{{ row.timeframe }}</td>
                <td class="py-1 pr-3 text-right tabular-nums">{{ row.count }}</td>
                <td class="py-1 pr-3 text-right tabular-nums">{{ fmtNum(row.avg_pnl_pct, 4) }}</td>
                <td class="py-1 pr-3">{{ row.recommended_profile }}</td>
                <td class="py-1 pr-3">{{ row.reason }}</td>
              </tr>
              <tr v-if="!feedbackRecommendations.length">
                <td colspan="6" class="py-2 text-gray-500 dark:text-gray-400">No recommendation rows.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <!-- Export buttons -->
      <div class="flex gap-2">
        <button @click="exportCsv('filtered_combos.csv', filtered, TOP_COLS)"
                class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                       bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all">
          {{ tr('results_export_filtered_csv', '匯出篩選結果 CSV') }}
        </button>
        <button @click="exportCsv('top10.csv', top10Display, TOP_COLS)"
                class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                       bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all">
          {{ tr('results_export_top10_csv', '匯出 Top10 CSV') }}
        </button>
        <button @click="exportTopSignalConfig" :disabled="exportingSignal"
                class="px-3 py-1.5 rounded-lg text-xs font-medium border border-emerald-300 dark:border-emerald-700
                       bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-200 hover:bg-emerald-100 dark:hover:bg-emerald-900/35 transition-all disabled:opacity-50">
          {{ exportingSignal ? tr('results_exporting_live_config', '匯出中...') : tr('results_export_top1_live_config', '匯出 Top1 Live Config') }}
        </button>
        <button @click="downloadFeedbackSpec" :disabled="downloadingFeedbackSpec"
                class="px-3 py-1.5 rounded-lg text-xs font-medium border border-indigo-300 dark:border-indigo-700
                       bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-200 hover:bg-indigo-100 dark:hover:bg-indigo-900/35 transition-all disabled:opacity-50">
          {{ downloadingFeedbackSpec ? tr('feedback_downloading_spec', '下載中...') : tr('feedback_spec_button', 'Paper Feedback 規格') }}
        </button>
      </div>

      <!-- Top 10 -->
      <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ tr('results_top10_title', 'Top 10') }}</h3>
          <div class="flex items-center gap-2">
            <!-- AWF-107: toggle between all-time best and latest-run top10 -->
            <div class="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600 text-xs">
              <button @click="top10Mode = 'history'"
                      :class="top10Mode === 'history' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700'"
                      class="px-2.5 py-1 font-medium transition-all">
                {{ tr('results_top10_mode_history', '全歷史最佳') }}
              </button>
              <button @click="top10Mode = 'latest'"
                      :class="top10Mode === 'latest' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700'"
                      class="px-2.5 py-1 font-medium transition-all border-l border-gray-300 dark:border-gray-600">
                {{ tr('results_top10_mode_latest', '本次結果') }}
              </button>
            </div>
            <button @click="retestTop" :disabled="retesting"
                    class="px-3 py-1 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-all disabled:opacity-50">
              {{ retesting ? tr('results_retesting', '重測中...') : tr('results_retest_top10', '重測 Top 10') }}
            </button>
          </div>
        </div>
        <div class="overflow-x-auto">
          <data-table :columns="top10Columns" :rows="top10Display" :page-size="10"
                      sort-key="return_pct" searchable expandable
                      :expanded-key="expandedKeyTop10"
                      @row-click="r => toggleDetail(r, 'top10')">
            <template #cell-indicator_tags="{ row }">
              <div class="flex flex-wrap gap-1">
                <span v-for="tag in getTags(row)" :key="tag"
                      class="tag-chip bg-blue-500/10 text-blue-400 border border-blue-500/20">{{ tag }}</span>
              </div>
            </template>
            <template #cell-indicator_params="{ row }">
              <span class="text-xs text-gray-500 dark:text-gray-400 font-mono" :title="getParamFull(row)">
                {{ getParamShort(row) }}
              </span>
            </template>
            <template #cell-_freshness="{ row }">
              <div class="flex items-center gap-1.5">
                <div class="w-14 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                  <div :style="{ width: Math.max(5, 100 - (row._freshnessDays||0)*5) + '%' }"
                       :class="(row._freshnessDays||0) <= 3 ? 'bg-emerald-500' : (row._freshnessDays||0) <= 7 ? 'bg-amber-400' : 'bg-red-500'"
                       class="h-full rounded-full transition-all"></div>
                </div>
                <span class="text-[10px] whitespace-nowrap" :class="(row._freshnessDays||0) <= 3 ? 'text-emerald-400' : (row._freshnessDays||0) <= 7 ? 'text-amber-400' : 'text-red-400'">
                  {{ row._freshnessDays != null ? (row._freshnessDays === 0 ? tr('results_freshness_today', '今日') : row._freshnessDays + tr('results_freshness_day_suffix', '天')) : '--' }}
                </span>
              </div>
            </template>
            <template #cell-_refine="{ row }">
              <button @click.stop="doRefineCombo(row)"
                      class="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white transition-all active:scale-[0.97] whitespace-nowrap">
                {{ tr('results_refine_btn', '精修') }}
              </button>
            </template>
            <template #detail="{ row }">
              <detail-panel :row="row" :get-param-full="getParamFull" :get-tags="getTags" />
            </template>
          </data-table>
        </div>
      </div>

      <!-- All Combos -->
      <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ tr('results_all_combos_title', '全部組合') }}</h3>
          <span class="text-xs text-gray-500 dark:text-gray-400">{{ filtered.length }} / {{ allRows.length }} {{ tr('results_rows_suffix', '筆') }}</span>
        </div>
        <div class="overflow-x-auto">
          <data-table :columns="tableColumns" :rows="filtered" :page-size="25"
                      sort-key="return_pct" searchable expandable
                      :expanded-key="expandedKeyAll"
                      @row-click="r => toggleDetail(r, 'all')">
            <template #cell-indicator_tags="{ row }">
              <div class="flex flex-wrap gap-1">
                <span v-for="tag in getTags(row)" :key="tag"
                      class="tag-chip bg-blue-500/10 text-blue-400 border border-blue-500/20">{{ tag }}</span>
              </div>
            </template>
            <template #cell-indicator_params="{ row }">
              <span class="text-xs text-gray-500 dark:text-gray-400 font-mono" :title="getParamFull(row)">
                {{ getParamShort(row) }}
              </span>
            </template>
            <template #detail="{ row }">
              <detail-panel :row="row" :get-param-full="getParamFull" :get-tags="getTags" />
            </template>
          </data-table>
        </div>
      </div>

      <!-- Leaderboard -->
      <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ tr('results_leaderboard_title', '歷史排行榜') }}</h3>
        </div>
        <div class="overflow-x-auto">
          <data-table :columns="lbColumns" :rows="leaderboard" :page-size="25"
                      sort-key="oos_avg_total_return_pct" searchable>
            <template #cell-report_file="{ value }">
              <a v-if="value" :href="'/artifacts/' + value" target="_blank"
                 class="text-blue-500 hover:text-blue-400 text-xs">{{ tr('results_open_report_link', '開啟報告') }}</a>
            </template>
          </data-table>
        </div>
      </div>
      </template>
    </div>
  `,
  setup() {
    const loading = ref(true)
    const payload = ref(null)
    const allRows = ref([])
    const filtered = ref([])
    const top10 = ref([])
    const top10LatestRun = ref([])          // AWF-107: latest-run data
    const top10Mode = ref('history')        // AWF-107: 'history' | 'latest'
    const leaderboard = ref([])
    const timeframes = ref([])
    const dataNote = ref('')
    const expandedKeyTop10 = ref(null)
    const expandedKeyAll = ref(null)

    // Expose L to window so DataTable's allDetailCols can use it
    window._AUTOWFO_L = L

    const filters = ref({
      timeframe: 'all', minReturn: null, minWinRate: null,
      minDailyTrades: null, maxDrawdown: null, oosPositive: false
    })

    const scatterRef = ref(null)
    const histRef = ref(null)
    const frontierRef = ref(null)
    let scatterChart = null, histChart = null, frontierChart = null
    let pollTimer = null

    function tr(key, fallback = '') {
      return L[key] || fallback || key
    }
    // Alias kept for compatibility with any old call sites.
    const t = tr

    const tableColumns = TOP_COLS.map(key => ({
      key,
      label: L[key] || key,
      numeric: NUM_COLS.has(key) || ['return_pct','max_drawdown_pct','avg_daily_trades_display','avg_hold_hours_display','win_rate_pct'].includes(key),
      sortable: true,
    }))

    // Top10 columns: same as tableColumns + freshness + refine action at the end
    const top10Columns = [
      ...tableColumns,
      { key: '_freshness', label: tr('results_top10_freshness', '新鮮度'), sortable: true, numeric: true },
      { key: '_refine', label: '', sortable: false },
    ]

    // AWF-107: active top10 source based on mode toggle
    const top10Display = computed(() => top10Mode.value === 'history' ? top10.value : top10LatestRun.value)

    const retesting = ref(false)
    const exportingSignal = ref(false)
    const downloadingFeedbackSpec = ref(false)
    const advancedAnalysis = ref(null)
    const advancedLoading = ref(false)
    const downloadingAdvanced = ref(false)
    const advancedParams = ref({
      nTrials: 2000,
      sampleSize: null,
      seed: 42,
    })
    const feedbackActions = ['enter_long', 'exit_long', 'enter_short', 'exit_short', 'hold', 'flat']
    const feedbackRows = ref([])
    const feedbackSummary = ref(null)
    const feedbackDiagnostics = ref(null)
    const feedbackRecommendations = ref([])
    const feedbackRecommendationProfile = ref('auto')
    const feedbackRecommendationMinSamples = ref(3)
    const exportingFeedbackAdjusted = ref(false)
    const enqueuingFeedbackBatch = ref(false)
    const feedbackBatchPlan = ref(null)
    const feedbackLoading = ref(false)
    const submittingFeedback = ref(false)
    const feedbackForm = ref({
      signalConfigId: '',
      timestampUtc: new Date().toISOString(),
      symbol: '',
      timeframe: '',
      action: 'hold',
      pnlPct: null,
      qty: null,
      paperRunId: '',
      note: '',
    })
    const feedbackRecent = computed(() => {
      const rows = Array.isArray(feedbackRows.value) ? feedbackRows.value : []
      return [...rows].reverse().slice(0, 12)
    })
    function doRefineCombo(row) {
      // AWF-123: set cross-tab pendingRunMode then navigate to Overview
      const label = [row.filter_name, row.regime_name, row.indicator_list].filter(Boolean).join(' | ')
      store.pendingRunMode = 'refine'
      store.activeTab = 'overview'
      showToast(tr('results_refine_toast', `精修模式：${label || '已選 combo'}`), 'success', 4000)
    }

    async function retestTop() {
      const confirmed = await confirmAction({
        title: tr('results_retest_confirm_title', '重測 Top 10？'),
        message: tr('results_retest_confirm_message', '會先刷新資料，然後啟動新一輪回測。'),
        confirmText: tr('results_retest_confirm_button', '重測'),
        variant: 'primary',
      })
      if (!confirmed) return
      retesting.value = true
      try {
        const res = await postJson('/start?refresh_data=1', {})
        if (res.ok) {
          showToast(tr('results_retest_started', '已啟動重測（含資料刷新）'), 'success')
        } else {
          showToast(res.message || tr('results_retest_failed', '啟動重測失敗'), 'error')
        }
      } catch (e) {
        showToast(tr('results_retest_failed', '啟動重測失敗') + ': ' + e.message, 'error')
      } finally {
        retesting.value = false
      }
    }

    async function exportTopSignalConfig() {
      const row = (top10.value && top10.value.length) ? top10.value[0] : null
      if (!row) {
        showToast(tr('results_no_top10_export', '目前沒有可匯出的 Top10 組合。'), 'warn')
        return
      }
      const confirmed = await confirmAction({
        title: tr('results_export_live_confirm_title', '匯出 Live Config'),
        message: tr('results_export_live_confirm_message', '要將目前 Top1 組合匯出為 live signal config JSON 嗎？'),
        confirmText: tr('results_export_live_confirm_button', '匯出'),
        variant: 'primary',
      })
      if (!confirmed) return
      exportingSignal.value = true
      try {
        const timeframe = filters.value.timeframe && filters.value.timeframe !== 'all'
          ? filters.value.timeframe
          : undefined
        const payload = await postJson('/signals/export-top-config', { rank: 1, timeframe, row })
        showToast(tr('results_export_live_success_prefix', 'Live config 已匯出') + ': ' + (payload.path || ''), 'success')
      } catch (e) {
        showToast(tr('results_export_live_failed', '匯出 live config 失敗') + ': ' + e.message, 'error')
      } finally {
        exportingSignal.value = false
      }
    }

    async function downloadFeedbackSpec() {
      downloadingFeedbackSpec.value = true
      try {
        const spec = await fetchJson('/signals/paper-feedback-spec.json')
        const text = JSON.stringify(spec, null, 2)
        const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'paper_feedback_spec.json'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        showToast(tr('feedback_download_spec_success', 'Downloaded paper feedback spec.'), 'success')
      } catch (e) {
        showToast(tr('feedback_download_spec_failed', 'Download spec failed') + ': ' + e.message, 'error')
      } finally {
        downloadingFeedbackSpec.value = false
      }
    }

    function fmtNum(value, digits = 2) {
      const n = Number(value)
      if (!Number.isFinite(n)) return '--'
      return n.toFixed(digits).replace(/\.?0+$/, '')
    }

    function fmtUtc(ts) {
      if (!ts) return '--'
      try {
        const d = new Date(ts)
        if (isNaN(d)) return String(ts)
        return d.toISOString().replace('.000Z', 'Z')
      } catch {
        return String(ts)
      }
    }

    function formatRiskValue(field, value) {
      const n = Number(value)
      if (!Number.isFinite(n)) return '--'
      if (field === 'max_hold') return String(Math.round(n))
      return n.toFixed(6).replace(/\.?0+$/, '')
    }

    function formatFeedbackGuardrailWarning(item) {
      if (!item || typeof item !== 'object') return ''
      const field = String(item.field || '').trim()
      const fieldLabel = L[field] || field || 'value'
      const inputText = formatRiskValue(field, item.input)
      const clampedText = formatRiskValue(field, item.clamped)
      const minText = formatRiskValue(field, item.min)
      const maxText = formatRiskValue(field, item.max)
      const hasRange = Number.isFinite(Number(item.min)) || Number.isFinite(Number(item.max))
      const rangeText = hasRange ? ` (${tr('feedback_guardrail_range', 'range')}: ${minText}~${maxText})` : ''
      return `${fieldLabel}: ${inputText} -> ${clampedText}${rangeText}`
    }

    function formatFeedbackGuardrailWarnings(items) {
      if (!Array.isArray(items) || !items.length) return '--'
      const rows = items
        .map(item => formatFeedbackGuardrailWarning(item))
        .filter(Boolean)
      return rows.length ? rows.join(' | ') : '--'
    }

    function primeFeedbackFormFromTop() {
      const top = (top10.value && top10.value.length) ? top10.value[0] : null
      if (!top) return
      if (!feedbackForm.value.symbol) {
        feedbackForm.value.symbol = String(top.plot_symbol || top.symbol || '').trim()
      }
      if (!feedbackForm.value.timeframe) {
        feedbackForm.value.timeframe = String(top.timeframe || '').trim()
      }
    }

    async function loadFeedbackData() {
      feedbackLoading.value = true
      try {
        const minSamples = Math.max(1, Number(feedbackRecommendationMinSamples.value || 1))
        const [rowsPayload, summaryPayload, diagPayload, recPayload] = await Promise.all([
          fetchJson('/signals/paper-feedback.json?limit=200'),
          fetchJson('/signals/paper-feedback-summary.json?limit=1000'),
          fetchJson('/signals/paper-feedback-diagnostics.json?limit=1000&top_n=8'),
          fetchJson('/signals/paper-feedback-recommendations.json?limit=1000&top_n=8&min_samples=' + encodeURIComponent(String(minSamples))),
        ])
        feedbackRows.value = rowsPayload.rows || []
        feedbackSummary.value = summaryPayload.summary || null
        feedbackDiagnostics.value = diagPayload.diagnostics || null
        feedbackRecommendations.value = recPayload.recommendations?.recommendations || []
      } catch (e) {
        showToast(tr('feedback_load_failed', 'Load feedback failed') + ': ' + e.message, 'error')
      } finally {
        feedbackLoading.value = false
      }
    }

    async function submitFeedback() {
      const f = feedbackForm.value
      if (!f.signalConfigId || !f.symbol || !f.timeframe || !f.action) {
        showToast(tr('feedback_missing_required_fields', 'Missing required feedback fields.'), 'warn')
        return
      }

      const payload = {
        signal_config_id: f.signalConfigId,
        timestamp_utc: f.timestampUtc || new Date().toISOString(),
        symbol: f.symbol,
        timeframe: f.timeframe,
        action: f.action,
      }
      if (f.pnlPct !== null && f.pnlPct !== '' && Number.isFinite(Number(f.pnlPct))) payload.pnl_pct = Number(f.pnlPct)
      if (f.qty !== null && f.qty !== '' && Number.isFinite(Number(f.qty))) payload.qty = Number(f.qty)
      if (f.paperRunId) payload.paper_run_id = f.paperRunId
      if (f.note) payload.note = f.note

      submittingFeedback.value = true
      try {
        await postJson('/signals/paper-feedback', payload)
        showToast(tr('feedback_submit_success', 'Paper feedback submitted.'), 'success')
        feedbackForm.value.timestampUtc = new Date().toISOString()
        feedbackForm.value.note = ''
        await loadFeedbackData()
      } catch (e) {
        showToast(tr('feedback_submit_failed', 'Submit feedback failed') + ': ' + e.message, 'error')
      } finally {
        submittingFeedback.value = false
      }
    }

    function pickRecommendationForTopRow(row) {
      if (!row || !feedbackRecommendations.value.length) return null
      const symbol = String(row.plot_symbol || row.symbol || '').trim()
      const timeframe = String(row.timeframe || '').trim()
      for (const rec of feedbackRecommendations.value) {
        if (!rec) continue
        if (String(rec.symbol || '').trim() === symbol && String(rec.timeframe || '').trim() === timeframe) {
          return rec
        }
      }
      return feedbackRecommendations.value[0] || null
    }

    async function exportFeedbackAdjustedConfig() {
      const row = (top10.value && top10.value.length) ? top10.value[0] : null
      if (!row) {
        showToast(tr('feedback_no_top10_adjust', 'No Top10 combo available to adjust.'), 'warn')
        return
      }

      const confirmed = await confirmAction({
        title: tr('feedback_export_adjusted_title', 'Export Adjusted Config'),
        message: tr('feedback_export_adjusted_confirm', 'Export Top1 with feedback-driven risk adjustment?'),
        confirmText: tr('feedback_export_adjusted_confirm_button', '匯出'),
        variant: 'primary',
      })
      if (!confirmed) return

      exportingFeedbackAdjusted.value = true
      try {
        const recommendation = pickRecommendationForTopRow(row)
        const timeframe = filters.value.timeframe && filters.value.timeframe !== 'all'
          ? filters.value.timeframe
          : undefined
        const payload = await postJson('/signals/export-feedback-adjusted-config', {
          profile: feedbackRecommendationProfile.value || 'auto',
          min_samples: Math.max(1, Number(feedbackRecommendationMinSamples.value || 1)),
          rank: 1,
          timeframe,
          row,
          recommendation,
        })
        showToast(tr('feedback_export_adjusted_success', 'Adjusted config exported') + ': ' + (payload.path || ''), 'success')
      } catch (e) {
        showToast(tr('feedback_export_adjusted_failed', 'Export adjusted config failed') + ': ' + e.message, 'error')
      } finally {
        exportingFeedbackAdjusted.value = false
      }
    }

    async function enqueueFeedbackAdjustedBatch() {
      const row = (top10.value && top10.value.length) ? top10.value[0] : null
      if (!row) {
        showToast(tr('feedback_no_top10_enqueue', 'No Top10 combo available to enqueue.'), 'warn')
        return
      }

      const confirmed = await confirmAction({
        title: tr('feedback_enqueue_adjusted_title', 'Enqueue Adjusted Batch'),
        message: tr('feedback_enqueue_adjusted_confirm', 'Create feedback-adjusted sweep config and enqueue a run job?'),
        confirmText: tr('feedback_enqueue_adjusted_confirm_button', '加入佇列'),
        variant: 'primary',
      })
      if (!confirmed) return

      enqueuingFeedbackBatch.value = true
      try {
        const recommendation = pickRecommendationForTopRow(row)
        const timeframe = filters.value.timeframe && filters.value.timeframe !== 'all'
          ? filters.value.timeframe
          : undefined
        const payload = await postJson('/signals/enqueue-feedback-adjusted-batch', {
          profile: feedbackRecommendationProfile.value || 'auto',
          min_samples: Math.max(1, Number(feedbackRecommendationMinSamples.value || 1)),
          rank: 1,
          timeframe,
          row,
          recommendation,
          workflow: 'run',
          mode: 'combo',
          auto_start: false,
        })
        feedbackBatchPlan.value = {
          jobId: payload?.job?.id ?? null,
          jobName: payload?.job?.name || '',
          configPath: payload?.config_path || '',
          signalConfigPath: payload?.signal_config_path || '',
          warnings: Array.isArray(payload?.warnings) ? payload.warnings : [],
        }
        const jobName = payload?.job?.name ? String(payload.job.name) : '(unnamed)'
        const jobIdText = payload?.job?.id != null ? ('#' + String(payload.job.id)) : ''
        const warningCount = feedbackBatchPlan.value.warnings.length
        const warningSuffix = warningCount > 0
          ? (' (' + warningCount + ' ' + tr('feedback_guardrail_warnings', 'guardrails') + ')')
          : ''
        showToast(tr('feedback_enqueue_success_prefix', 'Enqueued batch job') + ' ' + jobIdText + ': ' + jobName + warningSuffix, 'success')
      } catch (e) {
        showToast(tr('feedback_enqueue_adjusted_failed', 'Enqueue adjusted batch failed') + ': ' + e.message, 'error')
      } finally {
        enqueuingFeedbackBatch.value = false
      }
    }

    function openBatchTabFromFeedbackPlan() {
      store.activeTab = 'batch'
    }

    async function loadAdvancedAnalysis() {
      advancedLoading.value = true
      try {
        const tf = filters.value.timeframe && filters.value.timeframe !== 'all'
          ? filters.value.timeframe
          : ''
        const q = new URLSearchParams()
        if (tf) q.set('timeframe', tf)
        if (advancedParams.value.nTrials != null) q.set('n_trials', String(advancedParams.value.nTrials))
        if (advancedParams.value.seed != null) q.set('seed', String(advancedParams.value.seed))
        if (advancedParams.value.sampleSize != null && String(advancedParams.value.sampleSize).trim() !== '') {
          q.set('sample_size', String(advancedParams.value.sampleSize))
        }
        const path = '/results/advanced.json' + (q.toString() ? ('?' + q.toString()) : '')
        const res = await fetchJson(path)
        advancedAnalysis.value = res.analysis || null
      } catch (e) {
        showToast(tr('advanced_analysis_failed', 'Advanced analysis failed') + ': ' + e.message, 'error')
      } finally {
        advancedLoading.value = false
      }
    }

    async function downloadAdvancedJson() {
      if (!advancedAnalysis.value) {
        showToast(tr('advanced_no_payload', 'No advanced analysis payload to download.'), 'warn')
        return
      }
      downloadingAdvanced.value = true
      try {
        const payload = {
          generated_utc: new Date().toISOString(),
          timeframe: filters.value.timeframe,
          params: advancedParams.value,
          analysis: advancedAnalysis.value,
        }
        const text = JSON.stringify(payload, null, 2)
        const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'results_advanced_analysis.json'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        showToast(tr('advanced_download_success', 'Downloaded advanced analysis JSON.'), 'success')
      } catch (e) {
        showToast(tr('advanced_download_failed', 'Download analysis failed') + ': ' + e.message, 'error')
      } finally {
        downloadingAdvanced.value = false
      }
    }

    const lbColumns = [
      { key: 'timestamp_utc', label: tr('timestamp_utc', 'UTC 時間'), sortable: true },
      { key: 'run_id', label: tr('run_id', 'Run ID'), sortable: true },
      { key: 'plot_symbol', label: tr('plot_symbol', '標的'), sortable: true },
      { key: 'timeframe', label: tr('timeframe', '時間週期'), sortable: true },
      { key: 'data_days', label: tr('data_days', '資料天數'), numeric: true, sortable: true },
      { key: 'oos_avg_total_return_pct', label: tr('oos_avg_total_return_pct', 'OOS 平均報酬(%)'), numeric: true, sortable: true },
      { key: 'avg_total_return_pct', label: tr('avg_total_return_pct', '平均報酬(%)'), numeric: true, sortable: true },
      { key: 'avg_daily_trades', label: tr('avg_daily_trades', '日均交易數'), numeric: true, sortable: true },
      { key: 'avg_hold_hours', label: tr('avg_hold_hours', '平均持倉(hr)'), numeric: true, sortable: true },
      { key: 'min_total_trades', label: tr('min_total_trades', '最小交易數'), numeric: true, sortable: true },
      { key: 'report_file', label: tr('report_file', '報告'), sortable: false },
    ]

    function pickMetric(row, keys) {
      for (const k of keys) {
        const v = Number(row[k])
        if (Number.isFinite(v)) return v
      }
      return null
    }

    function _calcFreshnessDays(row) {
      const de = row.data_end
      if (!de) return null
      try {
        const end = new Date(de.replace(' ', 'T') + (de.includes('+') || de.includes('Z') ? '' : 'Z'))
        if (isNaN(end)) return null
        return Math.max(0, Math.round((Date.now() - end.getTime()) / 86400000))
      } catch { return null }
    }

    function decorateRow(row, idx) {
      const freshDays = _calcFreshnessDays(row)
      return {
        ...row,
        _expandKey: idx,
        _freshnessDays: freshDays,
        _freshness: freshDays,
        return_pct: pickMetric(row, ['oos_avg_total_return_pct','avg_total_return_pct','total_return_pct']),
        max_drawdown_pct: pickMetric(row, ['oos_avg_max_drawdown_pct','avg_max_drawdown_pct','max_drawdown_pct']),
        avg_daily_trades_display: pickMetric(row, ['oos_avg_daily_trades','avg_daily_trades']),
        avg_hold_hours_display: pickMetric(row, ['oos_avg_hold_hours','avg_hold_hours']),
        win_rate_pct: pickMetric(row, ['oos_avg_win_rate_pct','avg_win_rate_pct','win_rate_pct']),
        indicator_tags: getTags(row).join(' + '),
        indicator_params: getParamShort(row),
      }
    }

    function applyFilters(rows) {
      const f = filters.value
      return rows.filter(r => {
        if (f.timeframe !== 'all' && r.timeframe !== f.timeframe) return false
        const ret = pickMetric(r, ['oos_avg_total_return_pct','avg_total_return_pct'])
        const wr = pickMetric(r, ['oos_avg_win_rate_pct','avg_win_rate_pct'])
        const dt = pickMetric(r, ['oos_avg_daily_trades','avg_daily_trades'])
        const dd = pickMetric(r, ['oos_avg_max_drawdown_pct','avg_max_drawdown_pct'])
        if (f.minReturn != null && (ret === null || ret < f.minReturn)) return false
        if (f.minWinRate != null && (wr === null || wr < f.minWinRate)) return false
        if (f.minDailyTrades != null && (dt === null || dt < f.minDailyTrades)) return false
        if (f.maxDrawdown != null && (dd === null || dd > f.maxDrawdown)) return false
        if (f.oosPositive && (ret === null || ret <= 0)) return false
        return true
      })
    }

    function bestMetric(rows, key) {
      let best = null
      rows.forEach(r => {
        const v = Number(r[key])
        if (Number.isFinite(v) && (best === null || v > best)) best = v
      })
      return best
    }

    const kpis = computed(() => {
      const fr = filtered.value
      const all = allRows.value
      const fmtN = v => v === null ? '--' : Number.isFinite(v) ? v.toFixed(4).replace(/\.?0+$/, '') : '--'
      const bestRet = bestMetric(fr, 'oos_avg_total_return_pct') ?? bestMetric(fr, 'avg_total_return_pct')
      const bestAvg = bestMetric(fr, 'avg_total_return_pct')
      const bestDaily = bestMetric(fr, 'avg_daily_trades') ?? bestMetric(fr, 'oos_avg_daily_trades')
      return [
        { label: tr('results_kpi_filtered', '篩選後'), value: String(fr.length), color: '' },
        { label: tr('results_kpi_total', '總筆數'), value: String(all.length), color: '' },
        { label: tr('results_kpi_best_oos_return', '最佳 OOS 報酬'), value: fmtN(bestRet), color: bestRet > 0 ? 'text-profit' : bestRet < 0 ? 'text-loss' : '' },
        { label: tr('results_kpi_best_avg_return', '最佳平均報酬'), value: fmtN(bestAvg), color: bestAvg > 0 ? 'text-profit' : bestAvg < 0 ? 'text-loss' : '' },
        { label: tr('results_kpi_best_daily_trades', '最佳日均交易數'), value: fmtN(bestDaily), color: '' },
        { label: tr('results_kpi_latest_report', '最新報告'), value: payload.value?.latest_report || '--', color: '' },
        { label: tr('results_kpi_rows', '資料列'), value: String(payload.value?.combo?.total || 0), color: '' },
      ]
    })

    // Build a fingerprint for dedup: identity = non-metric columns
    const _METRIC_RE = /^(avg_|sym_avg_|sym_min_|oos_|min_total_)/
    function _rowFingerprint(row) {
      return Object.keys(row)
        .filter(k => !k.startsWith('_') && !_METRIC_RE.test(k) && !['return_pct','max_drawdown_pct','avg_daily_trades_display','avg_hold_hours_display','win_rate_pct','indicator_tags','indicator_params','config_sha256','data_fingerprint'].includes(k))
        .sort()
        .map(k => k + '=' + (row[k] ?? ''))
        .join('|')
    }

    function applyAndRender() {
      if (!payload.value) return
      const rows = payload.value.combo?.rows || []
      allRows.value = rows.map((r, i) => decorateRow(r, i))
      filtered.value = applyFilters(allRows.value)
      // Top 10: sort by return_pct descending, then deduplicate by identity fingerprint
      const sorted = [...filtered.value].sort((a, b) => (b.return_pct ?? -Infinity) - (a.return_pct ?? -Infinity))
      const seen = new Set()
      const deduped = []
      for (const r of sorted) {
        const fp = _rowFingerprint(r)
        if (seen.has(fp)) continue
        seen.add(fp)
        deduped.push(r)
        if (deduped.length >= 10) break
      }
      top10.value = deduped
      // AWF-107: populate latest-run top10 from backend payload
      top10LatestRun.value = (payload.value.top10_latest_run?.rows || []).map((r, i) => decorateRow(r, i))
      primeFeedbackFormFromTop()
      leaderboard.value = payload.value.leaderboard?.rows || []
      updateCharts()
    }

    function resetFilters() {
      filters.value = { timeframe: 'all', minReturn: null, minWinRate: null, minDailyTrades: null, maxDrawdown: null, oosPositive: false }
      applyAndRender()
    }

    async function loadResults() {
      try {
        const tf = filters.value.timeframe
        const q = tf && tf !== 'all' ? `?timeframe=${encodeURIComponent(tf)}` : ''
        payload.value = await fetchJson('/results.json' + q)
        // Extract timeframes
        const tfs = new Set()
        ;(payload.value.timeframes || []).forEach(v => { if (v && v !== 'nan') tfs.add(v) })
        ;(payload.value.combo?.rows || []).forEach(r => { if (r.timeframe && r.timeframe !== 'nan') tfs.add(r.timeframe) })
        timeframes.value = [...tfs].sort()
        if (payload.value.errors?.length) {
          dataNote.value = payload.value.errors.join(' | ')
        } else {
          dataNote.value = payload.value.combo?.truncated
            ? `${tr('results_note_showing', '顯示')} ${payload.value.combo.rows.length} / ${payload.value.combo.total} ${tr('results_note_rows', '筆')}`
            : `${tr('results_note_updated', '更新時間')}: ${payload.value.generated_utc || ''}`
        }
        applyAndRender()
      } catch (e) { dataNote.value = tr('results_note_load_failed', '載入失敗') + ': ' + e }
      finally { loading.value = false }
    }

    // --- Chart helpers using Chart.js ---
    function updateCharts() {
      const fr = filtered.value
      const isDark = document.documentElement.classList.contains('dark')
      const gridColor = isDark ? 'rgba(55,65,81,0.5)' : 'rgba(209,213,219,0.5)'
      const textColor = isDark ? '#9ca3af' : '#6b7280'

      // Scatter: return vs drawdown
      const scatterData = fr.map(r => ({
        x: pickMetric(r, ['oos_avg_max_drawdown_pct', 'avg_max_drawdown_pct']),
        y: pickMetric(r, ['oos_avg_total_return_pct', 'avg_total_return_pct'])
      })).filter(p => p.x !== null && p.y !== null)

      if (scatterChart) scatterChart.destroy()
      if (scatterRef.value) {
        scatterChart = new Chart(scatterRef.value, {
          type: 'scatter',
          data: { datasets: [{
            data: scatterData,
            backgroundColor: scatterData.map(p => p.y >= 0 ? '#10b981' : '#ef4444'),
            pointRadius: 3,
          }]},
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { title: { display: true, text: tr('results_axis_drawdown_pct', '回撤(%)'), color: textColor }, grid: { color: gridColor }, ticks: { color: textColor } },
              y: { title: { display: true, text: tr('results_axis_return_pct', '報酬(%)'), color: textColor }, grid: { color: gridColor }, ticks: { color: textColor } },
            }
          }
        })
      }

      // Histogram
      const histValues = fr.map(r => pickMetric(r, ['oos_avg_total_return_pct', 'avg_total_return_pct'])).filter(v => v !== null)
      if (histChart) histChart.destroy()
      if (histRef.value && histValues.length) {
        const min = Math.min(...histValues), max = Math.max(...histValues)
        const bins = 15, span = max - min || 1
        const counts = Array(bins).fill(0)
        const labels = []
        histValues.forEach(v => { counts[Math.min(bins - 1, Math.floor(((v - min) / span) * bins))]++ })
        for (let i = 0; i < bins; i++) labels.push((min + (i + 0.5) * span / bins).toFixed(1))
        histChart = new Chart(histRef.value, {
          type: 'bar',
          data: { labels, datasets: [{ data: counts, backgroundColor: '#3b82f6', borderRadius: 3 }] },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { display: false }, ticks: { color: textColor, maxRotation: 45 } },
              y: { grid: { color: gridColor }, ticks: { color: textColor } },
            }
          }
        })
      }

      // Frontier
      if (frontierChart) frontierChart.destroy()
      if (frontierRef.value && scatterData.length) {
        const sorted = [...scatterData].sort((a, b) => a.x - b.x)
        const frontier = []
        let bestY = -Infinity
        sorted.forEach(p => { if (p.y > bestY) { frontier.push(p); bestY = p.y } })
        frontierChart = new Chart(frontierRef.value, {
          type: 'scatter',
          data: { datasets: [
            { data: scatterData, backgroundColor: 'rgba(156,163,175,0.3)', pointRadius: 2, label: tr('results_frontier_all_points', '全部點') },
            { data: frontier, backgroundColor: '#3b82f6', borderColor: '#3b82f6', pointRadius: 4, showLine: true, fill: false, label: tr('results_frontier_points', '前緣點') },
          ]},
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: textColor } } },
            scales: {
              x: { title: { display: true, text: tr('results_axis_drawdown_pct', '回撤(%)'), color: textColor }, grid: { color: gridColor }, ticks: { color: textColor } },
              y: { title: { display: true, text: tr('results_axis_return_pct', '報酬(%)'), color: textColor }, grid: { color: gridColor }, ticks: { color: textColor } },
            }
          }
        })
      }
    }

    // --- Helpers ---
    function getTags(row) {
      const raw = row.indicator_list || row.filter_name || ''
      const decoded = String(raw).replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>')
      if (!decoded) return []
      return [...new Set(decoded.split(/[,+;|\/]+/).map(s => s.replace(/[()\[\]]/g,'').trim()).filter(Boolean))]
    }

    function getParamShort(row) {
      const pairs = []
      PARAM_ORDER.forEach(k => {
        const v = row[k]
        if (v !== null && v !== undefined && v !== '') {
          const n = Number(v)
          pairs.push((PARAM_SHORT[k] || k) + '=' + (Number.isFinite(n) ? n.toFixed(2).replace(/\.?0+$/,'') : v))
        }
      })
      const text = pairs.join(', ')
      return text.length > 60 ? text.slice(0, 57) + '...' : text
    }

    function getParamFull(row) {
      const pairs = []
      PARAM_ORDER.forEach(k => {
        const v = row[k]
        if (v !== null && v !== undefined && v !== '') pairs.push((L[k] || k) + '=' + v)
      })
      return pairs.join(', ')
    }

    function toggleDetail(row, tableId) {
      const key = row._expandKey
      if (tableId === 'top10') {
        expandedKeyTop10.value = expandedKeyTop10.value === key ? null : key
      } else {
        expandedKeyAll.value = expandedKeyAll.value === key ? null : key
      }
    }

    function exportCsv(filename, rows, columns) {
      if (!rows.length) { showToast(tr('results_export_no_data', '沒有可匯出的資料'), 'warn'); return }
      const cols = columns
      const lines = [cols.map(c => L[c] || c).join(',')]
      rows.forEach(row => {
        lines.push(cols.map(c => {
          const v = row[c] ?? ''
          return '"' + String(v).replace(/"/g, '""') + '"'
        }).join(','))
      })
      const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url)
      showToast(tr('results_export_success_prefix', '已匯出') + ' ' + filename, 'success')
    }

    onMounted(() => {
      loadResults()
      loadAdvancedAnalysis()
      loadFeedbackData()
      pollTimer = setInterval(loadResults, 30000)
    })
    watch(() => filters.value.timeframe, () => {
      loadAdvancedAnalysis()
    })
    onUnmounted(() => {
      clearInterval(pollTimer)
      if (scatterChart) scatterChart.destroy()
      if (histChart) histChart.destroy()
      if (frontierChart) frontierChart.destroy()
    })

      return { loading, filters, timeframes, kpis, dataNote, allRows, filtered, top10, leaderboard,
               tableColumns, top10Columns, lbColumns, scatterRef, histRef, frontierRef, TOP_COLS,
               expandedKeyTop10, expandedKeyAll, retesting, retestTop, exportingSignal, exportTopSignalConfig,
               top10Display, top10LatestRun, top10Mode,
               downloadingFeedbackSpec, downloadFeedbackSpec, advancedAnalysis, advancedLoading,
               downloadingAdvanced, advancedParams, loadAdvancedAnalysis, downloadAdvancedJson, fmtNum,
               feedbackActions, feedbackRows, feedbackSummary, feedbackDiagnostics, feedbackRecommendations,
               feedbackRecommendationProfile, feedbackRecommendationMinSamples, exportingFeedbackAdjusted, enqueuingFeedbackBatch,
               feedbackBatchPlan, openBatchTabFromFeedbackPlan, t, tr, formatFeedbackGuardrailWarnings,
               feedbackLoading, submittingFeedback, feedbackForm, feedbackRecent, loadFeedbackData, submitFeedback,
               exportFeedbackAdjustedConfig, enqueueFeedbackAdjustedBatch, fmtUtc,
               applyAndRender, resetFilters, loadResults,
               getTags, getParamShort, getParamFull, toggleDetail, exportCsv, doRefineCombo }
  }
}

