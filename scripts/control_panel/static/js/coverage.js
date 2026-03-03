import { ref, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson } from './api.js'
import { showToast, confirmAction } from './store.js'
import { L } from './i18n.js'

export const CoverageTab = {
  name: 'CoverageTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="skeleton skeleton-card h-44"></div>
        <div class="skeleton skeleton-card h-3"></div>
        <div class="skeleton skeleton-card h-80"></div>
      </div>
      <template v-else>
        <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('coverage_title', 'Coverage Matrix') }}</h2>
            <div class="flex gap-2">
              <button @click="refresh"
                      class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                             bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all">
                {{ t('coverage_refresh', 'Refresh') }}
              </button>
              <button @click="fillAllGaps" :disabled="fillBusy || summary.untested === 0"
                      class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white transition-all disabled:opacity-50">
                {{ fillBusy ? t('coverage_filling', 'Filling...') : t('coverage_fill_all_gaps', '填補全部缺口') }}
                <span v-if="!fillBusy && summary.untested > 0" class="ml-1 opacity-75">({{ summary.untested }})</span>
              </button>
            </div>
          </div>

          <div class="flex flex-wrap items-end gap-3">
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('coverage_workflow', 'Workflow') }}</span>
              <select v-model="workflow" @change="onWorkflowChange" class="cfg-input">
                <option value="baseline">baseline</option>
                <option value="run">run</option>
              </select>
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('coverage_mode', 'Mode') }}</span>
              <select v-model="mode" :disabled="workflow !== 'run'" class="cfg-input">
                <option value="">{{ t('coverage_none', 'none') }}</option>
                <option value="combo">combo</option>
                <option value="refine">refine</option>
              </select>
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('coverage_workers', 'Workers') }}</span>
              <input v-model.number="workers" type="number" min="1" :placeholder="t('coverage_optional', 'optional')" class="cfg-input w-20" />
            </label>
          </div>

          <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('coverage_hint', 'Click an untested cell to enqueue a focused job for that timeframe-symbol pair.') }}</p>

          <div class="flex flex-wrap gap-4 text-xs">
            <span class="text-gray-600 dark:text-gray-300">
              {{ t('coverage_total', 'total') }}=<strong>{{ summary.total || 0 }}</strong>
              {{ t('coverage_tested', 'tested') }}=<strong class="text-profit">{{ summary.tested || 0 }}</strong>
              {{ t('coverage_queued', 'queued') }}=<strong class="text-warn">{{ summary.queued || 0 }}</strong>
              {{ t('coverage_untested', 'untested') }}=<strong class="text-gray-500">{{ summary.untested || 0 }}</strong>
            </span>
            <div class="flex-1"></div>
            <span class="font-semibold text-gray-900 dark:text-white">{{ t('coverage_percent', 'coverage') }}={{ summary.coverage_pct || 0 }}%</span>
          </div>

          <div class="flex gap-3">
            <span class="inline-flex items-center gap-1 text-xs">
              <span class="w-3 h-3 rounded bg-emerald-500/30 border border-emerald-500/50"></span> {{ t('coverage_legend_tested', 'Tested') }}
            </span>
            <span class="inline-flex items-center gap-1 text-xs">
              <span class="w-3 h-3 rounded bg-amber-500/30 border border-amber-500/50"></span> {{ t('coverage_legend_queued', 'Queued') }}
            </span>
            <span class="inline-flex items-center gap-1 text-xs">
              <span class="w-3 h-3 rounded bg-gray-500/20 border border-gray-500/30"></span> {{ t('coverage_legend_untested', 'Untested') }}
            </span>
          </div>
        </div>

        <div class="w-full h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
          <div class="h-full rounded-full bg-emerald-500 transition-all duration-500"
               :style="{ width: (summary.coverage_pct || 0) + '%' }"></div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="overflow-x-auto p-4">
            <table v-if="tfs.length && syms.length" class="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ t('coverage_matrix_symbol_tf', 'Symbol \\ TF') }}
                  </th>
                  <th v-for="tf in tfs" :key="tf"
                      class="px-3 py-2 text-center text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    {{ tf }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sym in syms" :key="sym"
                    class="border-b border-gray-100 dark:border-gray-800">
                  <td class="px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-300">{{ sym }}</td>
                  <td v-for="tf in tfs" :key="tf" class="px-2 py-2 text-center">
                    <button @click="cellClick(tf, sym, cellStatus(tf, sym))"
                            class="cov-cell inline-block px-3 py-1.5 rounded-lg text-xs font-semibold"
                            :class="cellClass(cellStatus(tf, sym))">
                      {{ cellLabel(cellStatus(tf, sym)) }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="text-center text-gray-400 dark:text-gray-500 py-8 text-sm">
              {{ t('coverage_empty_state', 'No coverage data. Run') }} <code>autowfo plan</code> {{ t('coverage_empty_state_suffix', 'to bootstrap matrix targets.') }}
            </div>
          </div>
        </div>
      </template>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key

    const loading = ref(true)
    const tfs = ref([])
    const syms = ref([])
    const cells = ref(new Map())
    const summary = ref({})
    const workflow = ref('baseline')
    const mode = ref('')
    const workers = ref(null)
    const fillBusy = ref(false)
    let pollTimer = null

    function onWorkflowChange() {
      if (workflow.value !== 'run') {
        mode.value = ''
      }
    }

    function cellStatus(tf, sym) {
      return cells.value.get(tf + '||' + sym) || 'untested'
    }

    function cellClass(status) {
      if (status === 'tested') return 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
      if (status === 'queued') return 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
      return 'bg-gray-500/10 text-gray-500 border border-gray-500/20 hover:bg-blue-500/10 hover:text-blue-400 hover:border-blue-500/30'
    }

    function cellLabel(status) {
      if (status === 'tested') return t('coverage_cell_tested', 'Tested')
      if (status === 'queued') return t('coverage_cell_queued', 'Queued')
      return t('coverage_cell_untested', 'Untested')
    }

    async function refresh() {
      try {
        const payload = await fetchJson('/coverage/matrix.json')
        tfs.value = payload.timeframes || []
        syms.value = payload.symbols || []
        const next = new Map()
        ;(payload.cells || []).forEach(cell => {
          if (cell.timeframe && cell.symbol) {
            next.set(cell.timeframe + '||' + cell.symbol, cell.status || 'untested')
          }
        })
        cells.value = next
        summary.value = payload.summary || {}
      } catch (e) {
        showToast(t('coverage_toast_load_failed', 'Failed to load coverage') + ': ' + e, 'error')
      } finally {
        loading.value = false
      }
    }

    async function cellClick(tf, sym, status) {
      if (status === 'tested') return
      try {
        const payload = { timeframe: tf, symbol: sym, workflow: workflow.value }
        if (workflow.value === 'run' && mode.value) payload.mode = mode.value
        if (workers.value) payload.workers = workers.value
        await postJson('/coverage/enqueue', payload)
        showToast(t('coverage_toast_enqueued_pair', 'Enqueued pair') + ': ' + tf + ' x ' + sym, 'success')
        refresh()
      } catch (e) {
        showToast(String(e), 'error')
      }
    }

    async function fillAllGaps() {
      const confirmed = await confirmAction({
        title: t('coverage_confirm_fill_title', '填補全部缺口？'),
        message: t('coverage_confirm_fill_message', '將所有未測試的 (timeframe × symbol) 組合加入批次佇列。'),
        confirmText: t('coverage_fill_all_gaps', '填補全部缺口'),
        variant: 'warn',
      })
      if (!confirmed) return
      fillBusy.value = true
      try {
        const payload = { workflow: workflow.value }
        if (workflow.value === 'run' && mode.value) payload.mode = mode.value
        if (workers.value) payload.workers = workers.value
        const r = await postJson('/coverage/fill-all-gaps', payload)
        showToast(r.message || t('coverage_toast_fill_done', '缺口已加入佇列'), 'success')
        refresh()
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        fillBusy.value = false
      }
    }

    onMounted(() => {
      refresh()
      pollTimer = setInterval(refresh, 5000)
    })

    onUnmounted(() => {
      clearInterval(pollTimer)
    })

    return {
      loading,
      tfs,
      syms,
      cells,
      summary,
      workflow,
      mode,
      workers,
      fillBusy,
      onWorkflowChange,
      cellStatus,
      cellClass,
      cellLabel,
      refresh,
      cellClick,
      fillAllGaps,
      t,
    }
  },
}
