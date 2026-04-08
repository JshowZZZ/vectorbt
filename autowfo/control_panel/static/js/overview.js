import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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

const MODE_OPTIONS = [
  {
    id: 'combo',
    label: 'Combo 掃描',
    hint: '從完整候選組合開始跑，適合第一次覆蓋整個搜尋空間。',
  },
  {
    id: 'refine',
    label: 'Refine 精修',
    hint: '聚焦已有亮點的候選，縮短迭代時間並快速驗證想法。',
  },
]

export const OverviewTab = {
  name: 'OverviewTab',
  template: `
    <div class="space-y-6 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div class="xl:col-span-5 skeleton skeleton-card h-64"></div>
          <div class="xl:col-span-3 skeleton skeleton-card h-64"></div>
          <div class="xl:col-span-4 skeleton skeleton-card h-64"></div>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <div v-for="n in 5" :key="'overview-kpi-sk-' + n" class="skeleton skeleton-card h-24"></div>
        </div>
        <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div class="xl:col-span-8 skeleton skeleton-card h-72"></div>
          <div class="xl:col-span-4 skeleton skeleton-card h-72"></div>
        </div>
        <div class="skeleton skeleton-card h-60"></div>
      </div>

      <template v-else>
        <section class="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div class="xl:col-span-5 cp-hero-panel rounded-3xl p-5 md:p-6">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-blue-700/80 dark:text-blue-200/80">
                  Current Situation
                </div>
                <h2 class="mt-3 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">{{ nextAction.title }}</h2>
                <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{{ nextAction.message }}</p>
              </div>
              <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/75 text-3xl shadow-sm dark:bg-slate-950/40">
                {{ nextAction.icon }}
              </div>
            </div>

            <div class="mt-5 grid grid-cols-2 gap-3">
              <div v-for="item in executionSummary"
                   :key="item.label"
                   class="rounded-2xl border border-white/70 bg-white/70 px-4 py-3 shadow-sm dark:border-slate-900/40 dark:bg-slate-950/30">
                <div class="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{{ item.label }}</div>
                <div class="mt-2 text-sm font-semibold text-slate-950 dark:text-white" :class="item.valueClass">{{ item.value }}</div>
              </div>
            </div>

            <div class="mt-5 flex flex-wrap gap-2">
              <action-button v-if="nextAction.actionLabel"
                             @click="goToTab(nextAction.actionTab)"
                             variant="primary"
                             :icon="nextAction.actionIcon"
                             :label="nextAction.actionLabel">
              </action-button>
              <action-button @click="goToTab('config')"
                             variant="default"
                             icon="⚙"
                             label="檢查設定">
              </action-button>
              <action-button @click="goToTab('results')"
                             variant="default"
                             icon="◨"
                             label="查看結果">
              </action-button>
            </div>
          </div>

          <div class="xl:col-span-3 cp-panel rounded-3xl p-5 md:p-6">
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Queue Snapshot</div>
                <h3 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">測試序列</h3>
              </div>
              <span class="inline-flex rounded-full bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-700 dark:text-blue-200">
                {{ experimentNext.queue_depth || 0 }} jobs
              </span>
            </div>

            <div class="mt-4 space-y-3">
              <div class="rounded-2xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 dark:border-slate-800/80 dark:bg-slate-900/60">
                <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Next Experiment</div>
                <div class="mt-1 text-sm font-semibold text-slate-950 dark:text-white font-mono">{{ experimentNext.next_experiment_id || '--' }}</div>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                  <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Scheduler</div>
                  <div class="mt-1 text-sm font-semibold text-slate-950 dark:text-white">{{ experimentNext.scheduler_enabled ? 'Enabled' : 'Disabled' }}</div>
                </div>
                <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                  <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Discovery Pool</div>
                  <div class="mt-1 text-sm font-semibold text-slate-950 dark:text-white">{{ experimentNext.discovery_candidates || 0 }}</div>
                </div>
              </div>
              <div class="rounded-2xl border border-slate-200/80 bg-white/70 px-4 py-3 dark:border-slate-800/80 dark:bg-slate-900/40">
                <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Latest Run</div>
                <div v-if="experimentNext.latest_run_summary" class="mt-1 text-sm text-slate-700 dark:text-slate-200">
                  <div class="font-mono font-semibold">{{ experimentNext.latest_run_summary.experiment_id }}</div>
                  <div class="mt-1 font-mono text-xs text-slate-500 dark:text-slate-400">{{ experimentNext.latest_run_summary.run_id }}</div>
                </div>
                <div v-else class="mt-1 text-sm text-slate-500 dark:text-slate-400">尚無最近的實驗執行紀錄。</div>
              </div>
            </div>
          </div>

          <div class="xl:col-span-4 cp-panel rounded-3xl p-5 md:p-6">
            <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Operator Checklist</div>
            <h3 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">下一步操作建議</h3>
            <div class="mt-4 space-y-3">
              <div v-for="item in runChecklist"
                   :key="item.title"
                   class="flex items-start gap-3 rounded-2xl border px-4 py-3"
                   :class="item.cardClass">
                <span class="mt-0.5 inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold" :class="item.badgeClass">
                  {{ item.badge }}
                </span>
                <div class="min-w-0">
                  <div class="text-sm font-semibold text-slate-950 dark:text-white">{{ item.title }}</div>
                  <div class="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">{{ item.description }}</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
          <kpi-card v-for="kpi in kpis"
                    :key="kpi.label"
                    :title="kpi.label"
                    :value="kpi.value"
                    :subtitle="kpi.subtitle"
                    :icon="kpi.icon"
                    :color="kpi.color">
          </kpi-card>
        </section>

        <section class="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div class="xl:col-span-8 cp-panel rounded-3xl p-5 md:p-6">
            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Run Progress</div>
                <h3 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('overview_progress_title', '執行進度') }}</h3>
              </div>
              <span class="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full"
                    :class="stageClass">
                <span class="w-1.5 h-1.5 rounded-full" :class="stageDotClass"></span>
                {{ stageLabel(status.stage) }}
              </span>
            </div>

            <div class="mb-4">
              <div class="flex justify-between text-xs text-slate-500 dark:text-slate-400 mb-2">
                <span>{{ status.done || 0 }} / {{ status.total || 0 }} {{ t('overview_done_total_suffix', 'combos') }}</span>
                <span>{{ status.percent || 0 }}%</span>
              </div>
              <div class="h-3 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div class="h-full rounded-full transition-all duration-700 ease-out"
                     :class="pctNum >= 100 ? 'bg-emerald-500' : 'bg-blue-500'"
                     :style="{ width: Math.min(100, pctNum) + '%' }"></div>
              </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{{ t('overview_skipped', 'Skipped') }}</div>
                <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ status.skipped || 0 }}</div>
              </div>
              <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{{ t('overview_remaining', 'Remaining') }}</div>
                <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ status.remaining || 0 }}</div>
              </div>
              <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{{ t('overview_elapsed', 'Elapsed') }}</div>
                <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ status.elapsed || '00:00:00' }}</div>
              </div>
              <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{{ t('overview_eta', 'ETA') }}</div>
                <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ status.eta || '00:00:00' }}</div>
              </div>
            </div>

            <div class="mt-4 rounded-2xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 text-xs leading-6 text-slate-600 dark:border-slate-800/80 dark:bg-slate-900/50 dark:text-slate-300">
              <span class="font-semibold text-slate-900 dark:text-white">判讀提示：</span>
              執行中先看進度、剩餘與 ETA；完成後直接前往「結果」與「分析」頁檢查是否有值得精修的候選。
              <div class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                {{ t('overview_updated', 'Updated') }}: {{ fmtTime(status.updated) }}
              </div>
            </div>
          </div>

          <div class="xl:col-span-4 cp-panel rounded-3xl p-5 md:p-6">
            <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Quick Actions</div>
            <h3 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('overview_quick_actions', '快速操作') }}</h3>

            <div class="mt-4 space-y-2">
              <button v-for="option in modeOptions"
                      :key="option.id"
                      @click="selectRunMode(option.id)"
                      class="w-full rounded-2xl border px-4 py-3 text-left transition-all"
                      :class="runMode === option.id
                        ? 'border-blue-500/40 bg-blue-500/10 shadow-sm'
                        : 'border-slate-200/80 bg-white/70 hover:border-slate-300 hover:bg-white dark:border-slate-800/80 dark:bg-slate-900/40 dark:hover:border-slate-700 dark:hover:bg-slate-900/70'">
                <div class="flex items-center justify-between gap-3">
                  <div class="text-sm font-semibold text-slate-950 dark:text-white">{{ option.label }}</div>
                  <span class="text-xs font-medium" :class="runMode === option.id ? 'text-blue-700 dark:text-blue-200' : 'text-slate-500 dark:text-slate-400'">
                    {{ runMode === option.id ? '已選擇' : '點擊切換' }}
                  </span>
                </div>
                <div class="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">{{ option.hint }}</div>
              </button>
            </div>

            <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
              <action-button @click="doStart"
                             :loading="actionLoading"
                             variant="primary"
                             icon="▶"
                             :label="t('overview_action_start', '開始回測')"
                             class="sm:col-span-2">
              </action-button>
              <action-button @click="doPause"
                             :loading="actionLoading"
                             variant="default"
                             icon="Ⅱ"
                             :label="t('overview_action_pause', '暫停')">
              </action-button>
              <action-button @click="doResume"
                             :loading="actionLoading"
                             variant="default"
                             icon="↻"
                             :label="t('overview_action_resume', '繼續')">
              </action-button>
              <action-button @click="doClearLog"
                             :loading="actionLoading"
                             variant="default"
                             icon="⌫"
                             :label="t('overview_action_clear_log', '清空紀錄')"
                             class="sm:col-span-2">
              </action-button>
            </div>

            <div class="mt-4 rounded-2xl border border-amber-200/80 bg-amber-50/70 px-4 py-3 text-xs leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100">
              <div class="font-semibold">操作提醒</div>
              <div class="mt-1">
                若只是檢查設定或結果，優先使用「設定」「結果」「分析」頁。只有確定參數與資料視窗後，再從這裡啟動新的執行。
              </div>
            </div>

            <div class="mt-4 flex flex-wrap gap-2 text-xs">
              <a href="/status" target="_blank" class="rounded-full border border-slate-200/80 px-3 py-1.5 text-slate-600 hover:text-slate-950 hover:bg-slate-50 dark:border-slate-700/80 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-900/80">
                狀態
              </a>
              <a href="/report" target="_blank" class="rounded-full border border-slate-200/80 px-3 py-1.5 text-slate-600 hover:text-slate-950 hover:bg-slate-50 dark:border-slate-700/80 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-900/80">
                報告
              </a>
              <a href="/log" target="_blank" class="rounded-full border border-slate-200/80 px-3 py-1.5 text-slate-600 hover:text-slate-950 hover:bg-slate-50 dark:border-slate-700/80 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-900/80">
                執行紀錄
              </a>
              <a href="/log.txt" target="_blank" class="rounded-full border border-slate-200/80 px-3 py-1.5 text-slate-600 hover:text-slate-950 hover:bg-slate-50 dark:border-slate-700/80 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-900/80">
                Log TXT
              </a>
            </div>
          </div>
        </section>

        <section class="cp-panel rounded-3xl p-5 md:p-6">
          <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Storage Health</div>
              <h3 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">資料儲存健康狀態</h3>
            </div>
            <div class="flex items-center gap-2">
              <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold"
                    :class="storageSummary.ok
                      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                      : 'bg-rose-500/15 text-rose-700 dark:text-rose-300'">
                {{ storageSummary.ok ? 'Healthy' : 'Needs Attention' }}
              </span>
              <a href="/ops/storage-health.json"
                 target="_blank"
                 class="rounded-full border border-slate-200/80 px-3 py-1.5 text-xs text-slate-600 hover:text-slate-950 hover:bg-slate-50 dark:border-slate-700/80 dark:text-slate-300 dark:hover:text-white dark:hover:bg-slate-900/80">
                JSON
              </a>
            </div>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
              <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Warnings</div>
              <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ storageSummary.warnings }}</div>
            </div>
            <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
              <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Errors</div>
              <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ storageSummary.errors }}</div>
            </div>
            <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
              <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Legacy Run Meta</div>
              <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ storageSummary.runMetaLegacy }}</div>
            </div>
            <div class="rounded-2xl border border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
              <div class="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Analytics Schema</div>
              <div class="mt-1 text-sm font-semibold font-mono text-slate-950 dark:text-white">{{ storageSummary.analyticsSchema }}</div>
            </div>
          </div>

          <div class="mt-4 rounded-2xl border px-4 py-3 text-xs leading-5"
               :class="storageSummary.needsMigration
                 ? 'border-amber-200/80 bg-amber-50/70 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100'
                 : 'border-slate-200/80 bg-slate-50/80 text-slate-600 dark:border-slate-800/80 dark:bg-slate-900/50 dark:text-slate-300'">
            <span class="font-semibold">Ops 提示：</span>
            <span v-if="storageSummary.needsMigration">
              發現可正規化的 legacy payload。建議先跑 <code>python -m autowfo storage migrate --dry-run --cwd .</code>，確認後再正式 migrate。
            </span>
            <span v-else>
              目前 schema version 狀態一致。若 analytics 需要重建，可執行 <code>python -m autowfo storage rebuild-analytics --cwd .</code>。
            </span>
          </div>
        </section>

        <section class="cp-panel rounded-3xl p-5 md:p-6">
          <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Patrol History</div>
              <h3 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">巡邏計畫歷史</h3>
            </div>
            <div class="rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {{ patrolTrendText }}
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-slate-50/90 dark:bg-slate-900/80">
                  <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase border-b border-slate-200 dark:border-slate-800">時間 (UTC)</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase border-b border-slate-200 dark:border-slate-800">產生</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase border-b border-slate-200 dark:border-slate-800">已加入佇列</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase border-b border-slate-200 dark:border-slate-800">執行次數</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase border-b border-slate-200 dark:border-slate-800">佇列</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!patrolHistory.length">
                  <td colspan="5" class="px-3 py-8 text-center text-sm text-slate-400 dark:text-slate-500">沒有巡邏計畫歷史紀錄</td>
                </tr>
                <tr v-for="row in patrolHistory"
                    :key="row.utc + '-' + row.runs_executed"
                    class="border-b border-slate-100 dark:border-slate-900">
                  <td class="px-3 py-3 text-xs font-mono text-slate-700 dark:text-slate-300">{{ row.utc || '--' }}</td>
                  <td class="px-3 py-3 text-xs text-slate-700 dark:text-slate-300">{{ row.tick_generated }}</td>
                  <td class="px-3 py-3 text-xs text-slate-700 dark:text-slate-300">{{ row.tick_enqueued }}</td>
                  <td class="px-3 py-3 text-xs text-slate-700 dark:text-slate-300">{{ row.runs_executed }}</td>
                  <td class="px-3 py-3 text-xs text-slate-700 dark:text-slate-300">{{ row.queue_remaining }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key
    const loading = ref(true)
    const status = ref({})
    const experimentNext = ref({})
    const patrolHistory = ref([])
    const storageHealth = ref({})
    const actionLoading = ref(false)
    const runMode = ref('combo')
    let statusTimer = null

    watch(
      () => store.pendingRunMode,
      mode => {
        if (!mode) return
        runMode.value = mode
        store.pendingRunMode = null
        showToast(t('overview_toast_refine_mode', `已切換為 ${mode} 模式`), 'success')
      }
    )

    const pctNum = computed(() => Number(status.value.percent) || 0)

    const nextAction = computed(() => {
      const stage = String(status.value.stage || '').toLowerCase()
      const done = Number(status.value.done) || 0
      const total = Number(status.value.total) || 0
      if (stage === 'running' || stage === 'combo' || stage === 'refine') {
        return {
          icon: '🔄',
          title: t('overview_next_running', '執行進行中'),
          message: `${done} / ${total} ` + t('overview_next_running_msg', '組合已完成，請等待結束後查看結果。'),
          actionLabel: '前往結果',
          actionTab: 'results',
          actionIcon: '◨',
        }
      }
      if (stage === 'complete' || stage === 'done') {
        return {
          icon: '✅',
          title: t('overview_next_complete', '執行完成'),
          message: t('overview_next_complete_msg', '結果已生成，建議先看結果頁，再到分析與覆蓋率頁確認下一輪要精修的方向。'),
          actionLabel: t('overview_next_goto_results', '查看結果'),
          actionTab: 'results',
          actionIcon: '◨',
        }
      }
      return {
        icon: '⚙️',
        title: t('overview_next_idle', '準備開始新測試'),
        message: t('overview_next_idle_msg', '請先確認設定、選擇執行模式，然後再啟動新的執行。'),
        actionLabel: t('overview_next_goto_config', '前往設定'),
        actionTab: 'config',
        actionIcon: '⚙',
      }
    })

    const executionSummary = computed(() => [
      {
        label: '階段',
        value: stageLabel(status.value.stage),
        valueClass: '',
      },
      {
        label: '進度',
        value: `${status.value.percent || 0}%`,
        valueClass: pctNum.value >= 100 ? 'text-emerald-600 dark:text-emerald-300' : 'text-blue-600 dark:text-blue-300',
      },
      {
        label: '模式',
        value: runMode.value === 'refine' ? 'Refine 精修' : 'Combo 掃描',
        valueClass: '',
      },
      {
        label: '更新',
        value: fmtTime(status.value.updated),
        valueClass: 'text-xs',
      },
    ])

    const kpis = computed(() => {
      const s = status.value
      return [
        {
          label: t('overview_kpi_done', '完成'),
          value: String(s.done || 0),
          subtitle: '已完成的組合數',
          icon: '✓',
          color: 'green',
        },
        {
          label: t('overview_kpi_total', '總數'),
          value: String(s.total || 0),
          subtitle: '本輪預計測試的組合',
          icon: 'Σ',
          color: 'gray',
        },
        {
          label: t('overview_kpi_skipped', '已跳過'),
          value: String(s.skipped || 0),
          subtitle: '略過或不再重跑的組合',
          icon: '↷',
          color: 'gray',
        },
        {
          label: t('overview_kpi_progress', '進度'),
          value: (s.percent || 0) + '%',
          subtitle: '目前整體完成比例',
          icon: '◔',
          color: pctNum.value >= 100 ? 'green' : 'blue',
        },
        {
          label: t('overview_kpi_elapsed', '耗時'),
          value: s.elapsed || '00:00:00',
          subtitle: '本輪執行已經花費時間',
          icon: '⏱',
          color: 'gray',
        },
      ]
    })

    const patrolTrendText = computed(() => {
      if (!patrolHistory.value.length) return 'runs trend: n/a'
      const recent = patrolHistory.value.slice(0, 5).map(row => Number(row.runs_executed) || 0)
      return 'runs trend: ' + recent.join(' -> ')
    })

    const storageSummary = computed(() => {
      const payload = storageHealth.value && typeof storageHealth.value === 'object' ? storageHealth.value : {}
      const summary = payload.summary && typeof payload.summary === 'object' ? payload.summary : {}
      const components = payload.components && typeof payload.components === 'object' ? payload.components : {}
      return {
        ok: Boolean(payload.ok),
        needsMigration: Boolean(payload.needs_migration),
        warnings: Number(summary.warnings || 0),
        errors: Number(summary.errors || 0),
        runMetaLegacy: Number(summary.run_meta_legacy_files || 0),
        analyticsSchema: (components.analytics && components.analytics.schema_version) || '--',
      }
    })

    const runChecklist = computed(() => {
      const stage = String(status.value.stage || '').toLowerCase()
      return [
        {
          badge: '1',
          title: '確認設定與資料範圍',
          description: '先到設定頁確認時間框架、資料天數與 guardrails，避免跑出不打算採納的結果。',
          cardClass: 'border-slate-200/80 bg-white/70 dark:border-slate-800/80 dark:bg-slate-900/40',
          badgeClass: 'bg-slate-900 text-white dark:bg-white dark:text-slate-900',
        },
        {
          badge: '2',
          title: '選擇合適的執行模式',
          description: runMode.value === 'refine'
            ? '你目前選的是 Refine 精修，適合用在已經有明顯候選之後。'
            : '你目前選的是 Combo 掃描，適合先建立完整基準。 ',
          cardClass: 'border-blue-200/80 bg-blue-50/80 dark:border-blue-900/60 dark:bg-blue-950/20',
          badgeClass: 'bg-blue-600 text-white',
        },
        {
          badge: stage === 'complete' || stage === 'done' ? '✓' : '3',
          title: '完成後先看結果，再看分析',
          description: stage === 'complete' || stage === 'done'
            ? '本輪已完成，建議直接切去結果頁篩選，再到分析頁檢查是否值得展開下一輪。'
            : '執行完成後，先從結果頁看排名與風險報酬，再用分析頁確認長期趨勢。',
          cardClass: stage === 'complete' || stage === 'done'
            ? 'border-emerald-200/80 bg-emerald-50/80 dark:border-emerald-900/60 dark:bg-emerald-950/20'
            : 'border-slate-200/80 bg-white/70 dark:border-slate-800/80 dark:bg-slate-900/40',
          badgeClass: stage === 'complete' || stage === 'done'
            ? 'bg-emerald-600 text-white'
            : 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
        },
      ]
    })

    function goToTab(tabId) {
      store.activeTab = tabId
    }

    function selectRunMode(mode) {
      runMode.value = mode
    }

    function stageLabel(raw) {
      const stage = String(raw || '').trim().toLowerCase()
      if (!stage) return t('status_idle', 'Idle')
      const key = STAGE_I18N[stage]
      if (key) return t(key, stage)
      return stage
    }

    const stageClass = computed(() => {
      const stage = String(status.value.stage || '').toLowerCase()
      if (stage === 'running' || stage === 'combo' || stage === 'refine') return 'bg-blue-500/15 text-blue-500 dark:text-blue-300'
      if (stage === 'complete' || stage === 'done') return 'bg-emerald-500/15 text-emerald-500 dark:text-emerald-300'
      return 'bg-slate-500/15 text-slate-500 dark:text-slate-300'
    })

    const stageDotClass = computed(() => {
      const stage = String(status.value.stage || '').toLowerCase()
      if (stage === 'running' || stage === 'combo' || stage === 'refine') return 'bg-blue-400 animate-pulse'
      if (stage === 'complete' || stage === 'done') return 'bg-emerald-400'
      return 'bg-slate-400'
    })

    function fmtTime(raw) {
      if (!raw) return '--'
      const parsed = Date.parse(raw)
      return Number.isNaN(parsed) ? String(raw) : new Date(parsed).toLocaleString()
    }

    async function refreshStatus() {
      try {
        status.value = await fetchJson('/status.json')
      } catch (_) {
        status.value = {}
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
        patrolHistory.value = Array.isArray(payload?.history) ? payload.history.slice(0, 20) : []
      } catch (_) {
        patrolHistory.value = []
      }
    }

    async function refreshStorageHealth() {
      try {
        storageHealth.value = await fetchJson('/ops/storage-health.json')
      } catch (_) {
        storageHealth.value = {}
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
      } catch (error) {
        showToast(String(error), 'error')
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
      } catch (error) {
        showToast(String(error), 'error')
      } finally {
        actionLoading.value = false
      }
    }

    const doPause = () =>
      doAction('/pause', 'overview_toast_paused', 'Paused', {
        title: t('overview_confirm_pause_title', 'Pause current run?'),
        message: t('overview_confirm_pause_message', 'This will pause the active process.'),
        confirmText: t('overview_action_pause', 'Pause'),
        variant: 'warn',
      })

    const doResume = () => doAction('/resume', 'overview_toast_resumed', 'Resumed')

    const doClearLog = () =>
      doAction('/clear-log', 'overview_toast_log_cleared', 'Run log cleared', {
        title: t('overview_confirm_clear_log_title', 'Clear run log?'),
        message: t('overview_confirm_clear_log_message', 'This action cannot be undone.'),
        confirmText: t('overview_action_clear_log', 'Clear Log'),
        variant: 'danger',
      })

    onMounted(() => {
      Promise.all([refreshStatus(), refreshExperimentNext(), refreshPatrolHistory(), refreshStorageHealth()]).finally(() => {
        loading.value = false
      })
      statusTimer = setInterval(() => {
        refreshStatus()
        refreshExperimentNext()
        refreshPatrolHistory()
        refreshStorageHealth()
      }, 3000)
    })

    onUnmounted(() => {
      clearInterval(statusTimer)
    })

    return {
      actionLoading,
      doClearLog,
      doPause,
      doResume,
      doStart,
      executionSummary,
      experimentNext,
      fmtTime,
      goToTab,
      kpis,
      loading,
      modeOptions: MODE_OPTIONS,
      nextAction,
      patrolHistory,
      patrolTrendText,
      pctNum,
      runChecklist,
      runMode,
      selectRunMode,
      storageSummary,
      stageClass,
      stageDotClass,
      stageLabel,
      status,
      t,
    }
  },
}
