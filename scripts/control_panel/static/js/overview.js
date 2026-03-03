import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson } from './api.js'
import { store, showToast, confirmAction } from './store.js'
import { L } from './i18n.js'

const STAGE_I18N = {
  running: 'status_running',
  combo: 'status_running',
  refine: 'status_running',
  complete: 'status_complete',
  done: 'status_done',
  idle: 'status_idle',
}

export const OverviewTab = {
  name: 'OverviewTab',
  template: `
    <div class="space-y-6 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <div v-for="n in 5" :key="'overview-kpi-sk-' + n" class="skeleton skeleton-card h-20"></div>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div class="lg:col-span-2 skeleton skeleton-card h-56"></div>
          <div class="skeleton skeleton-card h-56"></div>
        </div>
        <div class="skeleton skeleton-card h-44"></div>
      </div>
      <template v-else>
        <div class="rounded-xl p-4 border flex items-start gap-3"
             :class="{
               'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-700/50': nextAction.variant === 'blue',
               'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700/50': nextAction.variant === 'green',
               'bg-gray-50 dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50': nextAction.variant === 'gray',
             }">
          <div class="text-2xl leading-none mt-0.5">{{ nextAction.icon }}</div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ nextAction.title }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ nextAction.message }}</div>
          </div>
          <button v-if="nextAction.actionLabel" @click="goToTab(nextAction.actionTab)"
                  class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-all active:scale-[0.97]">
            {{ nextAction.actionLabel }}
          </button>
        </div>

        <div v-if="experimentNext.scheduler_enabled"
             class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">測試序列</h3>
            <span class="text-xs font-mono text-blue-500">{{ experimentNext.queue_depth || 0 }}</span>
          </div>
          <div class="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-gray-600 dark:text-gray-300">
            <div>下一個: <span class="font-mono">{{ experimentNext.next_experiment_id || '--' }}</span></div>
            <div>執行中: <span class="font-mono">{{ experimentNext.is_running ? 'true' : 'false' }}</span></div>
            <div>探索中: <span class="font-mono">{{ experimentNext.discovery_candidates || 0 }}</span></div>
          </div>
          <div v-if="experimentNext.latest_run_summary" class="mt-2 text-xs text-gray-500 dark:text-gray-400">
            最新: <span class="font-mono">{{ experimentNext.latest_run_summary.experiment_id }}</span>
            / <span class="font-mono">{{ experimentNext.latest_run_summary.run_id }}</span>
          </div>
        </div>

        <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">巡邏計畫歷史</h3>
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ patrolTrendText }}</span>
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">時間 (UTC)</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">產生</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">已加入佇列</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">執行次數</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">佇列</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!patrolHistory.length">
                  <td colspan="5" class="px-3 py-4 text-center text-xs text-gray-400 dark:text-gray-500">沒有 巡邏計畫歷史紀錄</td>
                </tr>
                <tr v-for="row in patrolHistory" :key="row.utc + '-' + row.runs_executed" class="border-b border-gray-100 dark:border-gray-800">
                  <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.utc || '--' }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.tick_generated }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.tick_enqueued }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.runs_executed }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.queue_remaining }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <div v-for="kpi in kpis" :key="kpi.label"
               class="kpi-card rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
            <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
              {{ kpi.label }}
            </div>
            <div class="text-2xl font-bold tabular-nums" :class="kpi.color">{{ kpi.value }}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div class="lg:col-span-2 rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('overview_progress_title', 'Run Progress') }}</h3>
              <span class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full"
                    :class="stageClass">
                <span class="w-1.5 h-1.5 rounded-full" :class="stageDotClass"></span>
                {{ stageLabel(status.stage) }}
              </span>
            </div>
            <div class="mb-3">
              <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
                <span>{{ status.done || 0 }} / {{ status.total || 0 }} {{ t('overview_done_total_suffix', 'combos') }}</span>
                <span>{{ status.percent || 0 }}%</span>
              </div>
              <div class="w-full h-3 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                <div class="h-full rounded-full transition-all duration-700 ease-out"
                     :class="pctNum >= 100 ? 'bg-emerald-500' : 'bg-blue-500'"
                     :style="{ width: Math.min(100, pctNum) + '%' }"></div>
              </div>
            </div>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_skipped', 'Skipped') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ status.skipped || 0 }}</span></div>
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_remaining', 'Remaining') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ status.remaining || 0 }}</span></div>
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_elapsed', 'Elapsed') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ status.elapsed || '00:00:00' }}</span></div>
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_eta', 'ETA') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ status.eta || '00:00:00' }}</span></div>
            </div>
            <div class="mt-2 text-[10px] text-gray-400 dark:text-gray-500">
              {{ t('overview_updated', 'Updated') }}: {{ fmtTime(status.updated) }}
            </div>
          </div>

          <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-4">{{ t('overview_quick_actions', 'Quick Actions') }}</h3>
            <div class="flex flex-col gap-2">
              <div class="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600 text-xs font-medium">
                <button v-for="m in ['combo', 'refine']" :key="m"
                        @click="runMode = m"
                        class="flex-1 py-1.5 transition-colors"
                        :class="runMode === m
                          ? 'bg-blue-600 text-white'
                          : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'">
                  {{ m }}
                </button>
              </div>
              <button @click="doStart" :disabled="actionLoading"
                      class="w-full px-4 py-2.5 rounded-lg text-sm font-semibold
                             bg-blue-600 hover:bg-blue-700 text-white
                             shadow-sm shadow-blue-500/25 transition-all active:scale-[0.97]
                             disabled:opacity-50">
                {{ t('overview_action_start', 'Start Run') }}
              </button>
              <div class="grid grid-cols-2 gap-2">
                <button @click="doPause" :disabled="actionLoading"
                        class="px-3 py-2 rounded-lg text-xs font-medium border
                               bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600
                               text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600
                               transition-all active:scale-[0.97] disabled:opacity-50">
                  {{ t('overview_action_pause', 'Pause') }}
                </button>
                <button @click="doResume" :disabled="actionLoading"
                        class="px-3 py-2 rounded-lg text-xs font-medium border
                               bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600
                               text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600
                               transition-all active:scale-[0.97] disabled:opacity-50">
                  {{ t('overview_action_resume', 'Resume') }}
                </button>
              </div>
              <button @click="doClearLog" :disabled="actionLoading"
                      class="w-full px-3 py-2 rounded-lg text-xs font-medium border
                             bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600
                             text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600
                             transition-all active:scale-[0.97] disabled:opacity-50">
                {{ t('overview_action_clear_log', 'Clear Log') }}
              </button>
            </div>
            <div class="flex flex-wrap gap-2 mt-4 text-xs">
              <a href="/status" target="_blank" class="text-blue-500 hover:text-blue-400 hover:underline">{{ t('overview_link_status', 'Status') }}</a>
              <a href="/report" target="_blank" class="text-blue-500 hover:text-blue-400 hover:underline">{{ t('overview_link_report', 'Report') }}</a>
              <a href="/log" target="_blank" class="text-blue-500 hover:text-blue-400 hover:underline">{{ t('overview_link_log', 'Run Log') }}</a>
              <a href="/log.txt" target="_blank" class="text-blue-500 hover:text-blue-400 hover:underline">{{ t('overview_link_log_download', 'Log TXT') }}</a>
            </div>
          </div>
        </div>

      </template>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key

    const loading = ref(true)
    const status = ref({})
    const experimentNext = ref({})
    const patrolHistory = ref([])
    const actionLoading = ref(false)
    const runMode = ref('combo')
    let statusTimer = null

    // Consume cross-tab pendingRunMode set by Results "精修" action
    watch(() => store.pendingRunMode, mode => {
      if (mode) {
        runMode.value = mode
        store.pendingRunMode = null
        showToast(t('overview_toast_refine_mode', `已切換為 ${mode} 模式`), 'success')
      }
    })

    const pctNum = computed(() => Number(status.value.percent) || 0)

    const nextAction = computed(() => {
      const stage = String(status.value.stage || '').toLowerCase()
      const done = Number(status.value.done) || 0
      const total = Number(status.value.total) || 0
      if (stage === 'running' || stage === 'combo' || stage === 'refine') {
        return {
          variant: 'blue',
          icon: '🔄',
          title: t('overview_next_running', '執行進行中'),
          message: `${done} / ${total} ` + t('overview_next_running_msg', '組合已完成，請等待結束後查看結果'),
          actionLabel: null,
          actionTab: null,
        }
      }
      if (stage === 'complete' || stage === 'done') {
        return {
          variant: 'green',
          icon: '✅',
          title: t('overview_next_complete', '執行完成'),
          message: t('overview_next_complete_msg', '結果已生成，可查看排名或前往覆蓋矩陣填補缺口'),
          actionLabel: t('overview_next_goto_results', '查看結果'),
          actionTab: 'results',
        }
      }
      return {
        variant: 'gray',
        icon: '⚙️',
        title: t('overview_next_idle', '尚未開始'),
        message: t('overview_next_idle_msg', '請先確認設定，然後在此頁啟動執行'),
        actionLabel: t('overview_next_goto_config', '前往設定'),
        actionTab: 'config',
      }
    })

    function goToTab(tabId) {
      store.activeTab = tabId
    }

    const kpis = computed(() => {
      const s = status.value
      return [
        { label: t('overview_kpi_done', 'Done'), value: String(s.done || 0), color: 'text-gray-900 dark:text-gray-100' },
        { label: t('overview_kpi_total', 'Total'), value: String(s.total || 0), color: 'text-gray-900 dark:text-gray-100' },
        { label: t('overview_kpi_skipped', 'Skipped'), value: String(s.skipped || 0), color: '' },
        { label: t('overview_kpi_progress', 'Progress'), value: (s.percent || 0) + '%', color: pctNum.value >= 100 ? 'text-profit' : 'text-blue-500' },
        { label: t('overview_kpi_elapsed', 'Elapsed'), value: s.elapsed || '00:00:00', color: '' },
      ]
    })

    const patrolTrendText = computed(() => {
      if (!patrolHistory.value.length) return 'runs trend: n/a'
      const recent = patrolHistory.value.slice(0, 5).map(row => Number(row.runs_executed) || 0)
      return 'runs trend: ' + recent.join(' -> ')
    })

    function stageLabel(raw) {
      const stage = String(raw || '').trim().toLowerCase()
      if (!stage) return t('status_idle', 'Idle')
      const key = STAGE_I18N[stage]
      if (key) return t(key, stage)
      return stage
    }

    const stageClass = computed(() => {
      const s = String(status.value.stage || '').toLowerCase()
      if (s === 'running' || s === 'combo' || s === 'refine') return 'bg-blue-500/15 text-blue-400'
      if (s === 'complete' || s === 'done') return 'bg-emerald-500/15 text-emerald-400'
      return 'bg-gray-500/15 text-gray-400'
    })

    const stageDotClass = computed(() => {
      const s = String(status.value.stage || '').toLowerCase()
      if (s === 'running' || s === 'combo' || s === 'refine') return 'bg-blue-400 animate-pulse'
      if (s === 'complete' || s === 'done') return 'bg-emerald-400'
      return 'bg-gray-400'
    })

    function fmtTime(raw) {
      if (!raw) return '--'
      const d = Date.parse(raw)
      return Number.isNaN(d) ? String(raw) : new Date(d).toLocaleString()
    }

    async function refreshStatus() {
      try {
        status.value = await fetchJson('/status.json')
      } catch (_) {
        // no-op
      }
    }

    async function refreshExperimentNext() {
      try {
        experimentNext.value = await fetchJson('/overview/next-action.json')
      } catch (_) {
        experimentNext.value = {}
      }
    }

    async function refreshPatrolHistory() {
      try {
        const payload = await fetchJson('/overview/patrol-history.json')
        const rows = Array.isArray(payload?.history) ? payload.history : []
        patrolHistory.value = rows.slice(0, 20)
      } catch (_) {
        patrolHistory.value = []
      }
    }

    async function doAction(url, toastKey, toastFallback, confirmOpts = null) {
      if (confirmOpts) {
        const confirmed = await confirmAction(confirmOpts)
        if (!confirmed) return
      }
      actionLoading.value = true
      try {
        const response = await postJson(url)
        showToast(response.message || t(toastKey, toastFallback), 'success')
        refreshStatus()
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        actionLoading.value = false
      }
    }

    async function doStart() {
      actionLoading.value = true
      try {
        const response = await postJson('/start', { search_mode: runMode.value })
        showToast(response.message || t('overview_toast_started', 'Backtest started'), 'success')
        refreshStatus()
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        actionLoading.value = false
      }
    }

    const doPause = () => doAction('/pause', 'overview_toast_paused', 'Paused', {
      title: t('overview_confirm_pause_title', 'Pause current run?'),
      message: t('overview_confirm_pause_message', 'This will pause the active process.'),
      confirmText: t('overview_action_pause', 'Pause'),
      variant: 'warn',
    })

    const doResume = () => doAction('/resume', 'overview_toast_resumed', 'Resumed')

    const doClearLog = () => doAction('/clear-log', 'overview_toast_log_cleared', 'Run log cleared', {
      title: t('overview_confirm_clear_log_title', 'Clear run log?'),
      message: t('overview_confirm_clear_log_message', 'This action cannot be undone.'),
      confirmText: t('overview_action_clear_log', 'Clear Log'),
      variant: 'danger',
    })

    onMounted(() => {
      Promise.all([refreshStatus(), refreshExperimentNext(), refreshPatrolHistory()]).finally(() => {
        loading.value = false
      })
      statusTimer = setInterval(() => {
        refreshStatus()
        refreshExperimentNext()
        refreshPatrolHistory()
      }, 3000)
    })

    onUnmounted(() => {
      clearInterval(statusTimer)
    })

    return {
      loading,
      status,
      experimentNext,
      patrolHistory,
      patrolTrendText,
      actionLoading,
      runMode,
      pctNum,
      kpis,
      nextAction,
      goToTab,
      stageClass,
      stageDotClass,
      fmtTime,
      stageLabel,
      doStart,
      doPause,
      doResume,
      doClearLog,
      t,
    }
  },
}
