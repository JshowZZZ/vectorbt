import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson, fetchText } from './api.js'
import { showToast, confirmAction } from './store.js'
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

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <button @click="testOpen = !testOpen"
                  class="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold
                         text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
            <span>{{ t('overview_test_title', 'Quick Test') }}</span>
            <span class="text-xs text-gray-400">{{ testOpen ? '^' : 'v' }}</span>
          </button>
          <div v-show="testOpen" class="px-5 pb-4 space-y-3 border-t border-gray-200 dark:border-gray-700">
            <div class="flex flex-wrap gap-2 mt-3">
              <button @click="doTestStart"
                      class="px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition-all">
                {{ t('overview_test_start', 'Start Test') }}
              </button>
              <button @click="doTestStop"
                      class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                             bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 transition-all">
                {{ t('overview_test_stop', 'Stop Test') }}
              </button>
              <button @click="doTestClearLog"
                      class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                             bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 transition-all">
                {{ t('overview_test_clear_log', 'Clear Test Log') }}
              </button>
            </div>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_test_stage', 'Stage') }}</span>
                   <span class="ml-1 font-semibold text-gray-900 dark:text-gray-100">{{ stageLabel(testStatus.stage) }}</span></div>
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_test_elapsed', 'Elapsed') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ testStatus.elapsed || '--' }}</span></div>
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_test_return_code', 'Return Code') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ testStatus.return_code ?? '--' }}</span></div>
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_test_started', 'Started At') }}</span>
                   <span class="ml-1 font-mono text-gray-900 dark:text-gray-100">{{ fmtTime(testStatus.started) }}</span></div>
            </div>
            <div class="log-panel rounded-lg p-3 bg-gray-950 text-gray-300 border border-gray-800">{{ testLog || t('overview_test_log_empty', 'No test log yet...') }}</div>
          </div>
        </div>
      </template>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key

    const loading = ref(true)
    const status = ref({})
    const testStatus = ref({})
    const testLog = ref('')
    const testOpen = ref(false)
    const actionLoading = ref(false)
    let statusTimer = null
    let testTimer = null

    const pctNum = computed(() => Number(status.value.percent) || 0)

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

    async function refreshTest() {
      try {
        testStatus.value = await fetchJson('/tests/status.json')
        testLog.value = await fetchText('/tests/log-tail.txt')
      } catch (_) {
        // no-op
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

    const doStart = () => doAction('/start', 'overview_toast_started', 'Backtest started')

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

    const doTestStart = () => doAction('/tests/start', 'overview_toast_test_started', 'Test started')

    const doTestStop = () => doAction('/tests/stop', 'overview_toast_test_stopped', 'Test stopped', {
      title: t('overview_confirm_test_stop_title', 'Stop test process?'),
      message: t('overview_confirm_test_stop_message', 'The current test process will be terminated.'),
      confirmText: t('overview_test_stop', 'Stop Test'),
      variant: 'warn',
    })

    const doTestClearLog = () => doAction('/tests/clear-log', 'overview_toast_test_log_cleared', 'Test log cleared', {
      title: t('overview_confirm_test_clear_title', 'Clear test log?'),
      message: t('overview_confirm_test_clear_message', 'This action cannot be undone.'),
      confirmText: t('overview_test_clear_log', 'Clear Test Log'),
      variant: 'danger',
    })

    onMounted(() => {
      Promise.all([refreshStatus(), refreshTest()]).finally(() => {
        loading.value = false
      })
      statusTimer = setInterval(refreshStatus, 3000)
      testTimer = setInterval(refreshTest, 5000)
    })

    onUnmounted(() => {
      clearInterval(statusTimer)
      clearInterval(testTimer)
    })

    return {
      loading,
      status,
      testStatus,
      testLog,
      testOpen,
      actionLoading,
      pctNum,
      kpis,
      stageClass,
      stageDotClass,
      fmtTime,
      stageLabel,
      doStart,
      doPause,
      doResume,
      doClearLog,
      doTestStart,
      doTestStop,
      doTestClearLog,
      t,
    }
  },
}
