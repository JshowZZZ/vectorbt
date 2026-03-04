// ─── AUTOWFO Shared Vue Components ───
import { ref, computed, watch, onMounted, onUnmounted, onErrorCaptured } from 'vue'
import { store, showToast, removeToast, resolveConfirm } from './store.js'
import { L as I18N } from './i18n.js'

// ═══ Toast Container ═══
export const ToastContainer = {
  name: 'ToastContainer',
  template: `
    <div class="toast-container">
      <div v-for="t in store.toasts" :key="t.id"
           class="toast-item rounded-lg px-4 py-3 shadow-lg border text-sm font-medium flex items-center gap-2"
           :class="[
             t.removing ? 'toast-exit' : '',
             t.type === 'success' ? 'bg-emerald-900/90 border-emerald-700 text-emerald-200' :
             t.type === 'error'   ? 'bg-red-900/90 border-red-700 text-red-200' :
             t.type === 'warn'    ? 'bg-amber-900/90 border-amber-700 text-amber-200' :
                                    'bg-gray-800/90 border-gray-600 text-gray-200'
           ]">
        <span>{{ t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : t.type === 'warn' ? '⚠' : 'ℹ' }}</span>
        <span class="flex-1">{{ t.message }}</span>
        <button @click="dismiss(t.id)" class="ml-2 opacity-60 hover:opacity-100 text-xs">✕</button>
      </div>
    </div>
  `,
  setup() {
    return { store, dismiss: removeToast }
  }
}

export const ConfirmModal = {
  name: 'ConfirmModal',
  template: `
    <div v-if="store.confirm.open" class="modal-overlay" @click.self="cancel">
      <div class="modal-content rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-xl p-5">
        <div class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {{ store.confirm.title || t('confirm_title_default', '請確認') }}
        </div>
        <div class="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-line">
          {{ store.confirm.message || t('confirm_message_default', '確定要執行這個操作嗎？') }}
        </div>
        <div class="mt-5 flex justify-end gap-2">
          <button @click="cancel"
                  class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                         bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all">
            {{ store.confirm.cancelText || t('confirm_cancel_default', '取消') }}
          </button>
          <button @click="confirm" class="px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all"
                  :class="confirmBtnClass">
            {{ store.confirm.confirmText || t('confirm_confirm_default', '確認') }}
          </button>
        </div>
      </div>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => I18N[key] || fallback || key
    const confirmBtnClass = computed(() => {
      const variant = store.confirm.variant || 'danger'
      if (variant === 'warn') return 'bg-amber-600 hover:bg-amber-700'
      if (variant === 'success') return 'bg-emerald-600 hover:bg-emerald-700'
      if (variant === 'primary') return 'bg-blue-600 hover:bg-blue-700'
      return 'bg-red-600 hover:bg-red-700'
    })

    const confirm = () => resolveConfirm(true)
    const cancel = () => resolveConfirm(false)

    const onKeydown = event => {
      if (!store.confirm.open) return
      if (event.key === 'Escape') cancel()
      if (event.key === 'Enter') confirm()
    }

    onMounted(() => window.addEventListener('keydown', onKeydown))
    onUnmounted(() => window.removeEventListener('keydown', onKeydown))

    return { store, confirmBtnClass, confirm, cancel, t }
  },
}

export const ErrorBoundary = {
  name: 'ErrorBoundary',
  props: {
    tabId: { type: String, default: '' },
  },
  template: `
    <div v-if="errorMessage" class="rounded-xl border border-red-300 dark:border-red-800/70 bg-red-50 dark:bg-red-900/20 p-5">
      <div class="text-sm font-semibold text-red-700 dark:text-red-300 mb-1.5">{{ t('error_boundary_title', '分頁發生錯誤') }}</div>
      <div class="text-xs text-red-700/90 dark:text-red-200/90 break-words">{{ errorMessage }}</div>
      <div class="mt-4 flex gap-2">
        <button @click="retry"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-700 text-white transition-all">
          {{ t('error_boundary_retry', '重試') }}
        </button>
      </div>
    </div>
    <slot v-else />
  `,
  setup(props) {
    const t = (key, fallback = '') => I18N[key] || fallback || key
    const errorMessage = ref('')

    onErrorCaptured((err, instance, info) => {
      const base = err instanceof Error ? (err.message || String(err)) : String(err)
      const compName = instance?.type?.name || instance?.type?.__name || 'unknown'
      const infoText = info ? String(info) : ''
      const stack = err instanceof Error ? (err.stack || '') : ''
      const parts = [base, `tab=${props.tabId || 'unknown'}`, `component=${compName}`]
      if (infoText) parts.push(`info=${infoText}`)
      errorMessage.value = parts.join(' | ')
      console.error('[ErrorBoundary]', {
        tabId: props.tabId || '',
        component: compName,
        info: infoText,
        error: err,
        stack,
      })
      showToast(`${t('error_boundary_toast_prefix', '分頁錯誤')}: ${props.tabId || ''}`, 'error', 5000)
      return false
    })

    watch(() => props.tabId, () => {
      errorMessage.value = ''
    })

    function retry() {
      errorMessage.value = ''
    }

    return { errorMessage, retry, t }
  },
}

// ═══ KPI Card ═══
export const KpiCard = {
  name: 'KpiCard',
  props: {
    label: String,
    value: [String, Number],
    icon: { type: String, default: '' },
    trend: { type: String, default: '' }, // 'up', 'down', ''
    href: { type: String, default: '' },
  },
  template: `
    <div class="kpi-card rounded-xl p-4 border
                bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
      <div class="flex items-center gap-2 mb-1">
        <span v-if="icon" class="text-base">{{ icon }}</span>
        <span class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{{ label }}</span>
      </div>
      <div class="flex items-baseline gap-2">
        <a v-if="href" :href="href" target="_blank"
           class="text-xl font-bold text-blue-600 dark:text-blue-400 hover:underline truncate">{{ display }}</a>
        <span v-else class="text-xl font-bold truncate"
              :class="colorClass">{{ display }}</span>
        <span v-if="trend === 'up'" class="text-xs text-profit">▲</span>
        <span v-if="trend === 'down'" class="text-xs text-loss">▼</span>
      </div>
    </div>
  `,
  setup(props) {
    const display = computed(() => {
      if (props.value === null || props.value === undefined) return '—'
      if (typeof props.value === 'number') {
        return Number.isFinite(props.value) ? props.value.toFixed(4).replace(/\.?0+$/, '') : '—'
      }
      return String(props.value)
    })
    const colorClass = computed(() => {
      if (typeof props.value !== 'number' || !Number.isFinite(props.value)) return 'text-gray-900 dark:text-gray-100'
      if (props.value > 0) return 'text-profit'
      if (props.value < 0) return 'text-loss'
      return 'text-gray-900 dark:text-gray-100'
    })
    return { display, colorClass }
  }
}

// ═══ Status Badge ═══
export const StatusBadge = {
  name: 'StatusBadge',
  props: { status: String },
  template: `
    <span class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full"
          :class="cls">
      <span class="w-1.5 h-1.5 rounded-full" :class="dotCls"></span>
      {{ label }}
    </span>
  `,
  setup(props) {
    const t = (key, fallback = '') => I18N[key] || fallback || key
    const map = {
      running:  { cls: 'bg-blue-500/15 text-blue-400', dot: 'bg-blue-400 animate-pulse', label: t('status_running', '執行中') },
      complete: { cls: 'bg-emerald-500/15 text-emerald-400', dot: 'bg-emerald-400', label: t('status_complete', '完成') },
      idle:     { cls: 'bg-gray-500/15 text-gray-400', dot: 'bg-gray-400', label: t('status_idle', '閒置') },
      done:     { cls: 'bg-emerald-500/15 text-emerald-400', dot: 'bg-emerald-400', label: t('status_done', '完成') },
      failed:   { cls: 'bg-red-500/15 text-red-400', dot: 'bg-red-400', label: t('status_failed', '失敗') },
      queued:   { cls: 'bg-amber-500/15 text-amber-400', dot: 'bg-amber-400', label: t('status_queued', '等待中') },
      cancelled:{ cls: 'bg-gray-500/15 text-gray-400', dot: 'bg-gray-400', label: t('status_cancelled', '已取消') },
      submitted:{ cls: 'bg-blue-500/15 text-blue-400', dot: 'bg-blue-400 animate-pulse', label: t('status_submitted', '提交中') },
      skipped_seen_key: { cls: 'bg-gray-500/15 text-gray-400', dot: 'bg-gray-400', label: t('status_skipped_seen_key', '已跳過') },
      tested:   { cls: 'bg-emerald-500/15 text-emerald-400', dot: 'bg-emerald-400', label: t('status_tested', '已測試') },
      untested: { cls: 'bg-gray-500/15 text-gray-400', dot: 'bg-gray-400', label: t('status_untested', '未測試') },
    }
    const entry = computed(() => map[props.status] || map.idle)
    const cls = computed(() => entry.value.cls)
    const dotCls = computed(() => entry.value.dot)
    const label = computed(() => entry.value.label)
    return { cls, dotCls, label }
  }
}

// ═══ Data Table (sortable, paginated, expandable) ═══
export const DataTable = {
  name: 'DataTable',
  props: {
    columns: Array,   // [{ key, label, numeric, sortable, width }]
    rows: Array,
    emptyIcon: { type: String, default: '\u2205' },
    emptyTitle: { type: String, default: '' },
    emptyAction: { type: String, default: '' },
    pageSize: { type: Number, default: 25 },
    sortKey: { type: String, default: '' },
    sortDir: { type: String, default: 'desc' },
    searchable: { type: Boolean, default: false },
    expandable: { type: Boolean, default: false },
    expandedKey: { type: [String, Number, null], default: null }, // unique key of expanded row
  },
  emits: ['row-click'],
  template: `
    <div>
      <div v-if="searchable || rows.length > pageSize" class="flex flex-wrap items-center gap-3 mb-3">
        <input v-if="searchable" v-model="search" type="text" :placeholder="t('datatable_search_placeholder', '搜尋...')"
               class="px-3 py-1.5 rounded-lg text-sm border
                      bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600
                      text-gray-900 dark:text-gray-100 placeholder-gray-400
                      focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none w-48" />
        <span class="text-xs text-gray-500 dark:text-gray-400 ml-auto">
          {{ filteredRows.length }} {{ t('datatable_rows_suffix', '筆') }}
          <template v-if="totalPages > 1"> · {{ t('datatable_page_prefix', '第') }} {{ page + 1 }}/{{ totalPages }} {{ t('datatable_page_suffix', '頁') }}</template>
        </span>
        <select v-if="rows.length > 25" v-model.number="perPage"
                class="px-2 py-1 rounded text-xs border
                       bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600
                       text-gray-900 dark:text-gray-100">
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
        </select>
      </div>
      <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700/50">
        <table class="data-table">
          <thead>
            <tr class="bg-gray-50 dark:bg-gray-800/80">
              <th v-if="expandable" class="px-2 py-2.5 w-8 border-b border-gray-200 dark:border-gray-700"></th>
              <th v-for="col in columns" :key="col.key"
                  @click="col.sortable !== false && toggleSort(col.key)"
                  class="px-3 py-2.5 text-left text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700"
                  :class="{ 'sort-asc': currentSort === col.key && currentDir === 'asc',
                            'sort-desc': currentSort === col.key && currentDir === 'desc' }">
                {{ col.label }}
                <span v-if="col.sortable !== false" class="sort-icon">
                  {{ currentSort === col.key ? (currentDir === 'asc' ? '▲' : '▼') : '↕' }}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-if="pagedRows.length === 0">
              <tr>
                <td :colspan="columns.length + (expandable ? 1 : 0)">
                  <div v-if="emptyTitle" class="py-12 flex flex-col items-center justify-center text-center px-4">
                    <div class="text-4xl text-gray-300 dark:text-gray-600 mb-3">{{ emptyIcon }}</div>
                    <h3 class="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{{ emptyTitle }}</h3>
                    <p v-if="emptyAction" class="text-xs text-gray-500 dark:text-gray-400 max-w-sm">{{ emptyAction }}</p>
                  </div>
                  <div v-else class="text-center py-8 text-gray-500 dark:text-gray-400 text-sm">
                    {{ t('datatable_empty', '暫無資料') }}
                  </div>
                </td>
              </tr>
            </template>
            <template v-for="(row, idx) in pagedRows" :key="idx">
              <!-- Data row -->
              <tr @click="expandable && $emit('row-click', row)"
                  class="border-b border-gray-100 dark:border-gray-800 transition-colors"
                  :class="[
                    expandable ? 'cursor-pointer' : '',
                    isExpanded(row) ? 'bg-blue-50/60 dark:bg-blue-900/10' : 'hover:bg-gray-50 dark:hover:bg-gray-700/30'
                  ]">
                <!-- Expand toggle -->
                <td v-if="expandable" class="px-2 py-2 text-center text-gray-400 select-none">
                  <span class="text-xs transition-transform inline-block"
                        :class="isExpanded(row) ? 'rotate-90 text-blue-400' : ''">
                    ▶
                  </span>
                </td>
                <td v-for="col in columns" :key="col.key"
                    class="px-3 py-2 text-gray-800 dark:text-gray-200"
                    :class="{ 'text-right font-mono': col.numeric }">
                  <slot :name="'cell-' + col.key" :row="row" :value="row[col.key]">
                    <span :class="cellColor(row, col)">{{ cellValue(row, col) }}</span>
                  </slot>
                </td>
              </tr>
              <!-- Detail expand row -->
              <tr v-if="expandable && isExpanded(row)"
                  class="border-b border-blue-200 dark:border-blue-800/50 bg-gray-50 dark:bg-gray-900/50">
                <td :colspan="columns.length + 1" class="px-4 py-3">
                  <slot name="detail" :row="row">
                    <!-- default detail: all non-null fields in a grid -->
                    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-x-6 gap-y-1.5 text-xs">
                      <div v-for="col in allDetailCols(row)" :key="col.key" class="flex gap-1 min-w-0">
                        <span class="text-gray-500 dark:text-gray-400 shrink-0">{{ col.label }}:</span>
                        <span class="font-mono text-gray-900 dark:text-gray-100 truncate" :class="col.color">{{ col.value }}</span>
                      </div>
                    </div>
                  </slot>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-3">
        <button @click="page = 0" :disabled="page === 0"
                class="px-2 py-1 rounded text-xs border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-30">«</button>
        <button @click="page = Math.max(0, page - 1)" :disabled="page === 0"
                class="px-2 py-1 rounded text-xs border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-30">‹</button>
        <template v-for="p in visiblePages" :key="p">
          <button @click="page = p" class="px-2.5 py-1 rounded text-xs border font-medium"
                  :class="p === page ? 'bg-blue-600 border-blue-600 text-white' : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300'">
            {{ p + 1 }}
          </button>
        </template>
        <button @click="page = Math.min(totalPages - 1, page + 1)" :disabled="page >= totalPages - 1"
                class="px-2 py-1 rounded text-xs border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-30">›</button>
        <button @click="page = totalPages - 1" :disabled="page >= totalPages - 1"
                class="px-2 py-1 rounded text-xs border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 disabled:opacity-30">»</button>
      </div>
    </div>
  `,
  setup(props) {
    const t = (key, fallback = '') => I18N[key] || fallback || key
    const search = ref('')
    const page = ref(0)
    const perPage = ref(props.pageSize)
    const currentSort = ref(props.sortKey)
    const currentDir = ref(props.sortDir)

    function isExpanded(row) {
      if (!props.expandable || props.expandedKey === null) return false
      return props.expandedKey === row._expandKey
    }

    function toggleSort(key) {
      if (currentSort.value === key) {
        currentDir.value = currentDir.value === 'asc' ? 'desc' : 'asc'
      } else {
        currentSort.value = key
        currentDir.value = 'desc'
      }
      page.value = 0
    }

    const filteredRows = computed(() => {
      let r = props.rows || []
      if (search.value.trim()) {
        const q = search.value.trim().toLowerCase()
        r = r.filter(row => Object.values(row).some(v =>
          v !== null && v !== undefined && String(v).toLowerCase().includes(q)
        ))
      }
      return r
    })

    const sortedRows = computed(() => {
      const r = [...filteredRows.value]
      if (!currentSort.value) return r
      const key = currentSort.value
      const dir = currentDir.value === 'asc' ? 1 : -1
      const col = (props.columns || []).find(c => c.key === key)
      const isNum = col?.numeric
      r.sort((a, b) => {
        let va = a[key], vb = b[key]
        if (isNum) {
          va = va === null || va === undefined ? -Infinity : Number(va)
          vb = vb === null || vb === undefined ? -Infinity : Number(vb)
          if (!Number.isFinite(va)) va = -Infinity
          if (!Number.isFinite(vb)) vb = -Infinity
        } else {
          va = va == null ? '' : String(va)
          vb = vb == null ? '' : String(vb)
        }
        if (va < vb) return -1 * dir
        if (va > vb) return 1 * dir
        return 0
      })
      return r
    })

    const totalPages = computed(() => Math.max(1, Math.ceil(sortedRows.value.length / perPage.value)))
    const pagedRows = computed(() => {
      const start = page.value * perPage.value
      return sortedRows.value.slice(start, start + perPage.value)
    })
    const visiblePages = computed(() => {
      const total = totalPages.value
      const current = page.value
      const pages = []
      const start = Math.max(0, current - 2)
      const end = Math.min(total - 1, current + 2)
      for (let i = start; i <= end; i++) pages.push(i)
      return pages
    })

    watch(() => props.rows, () => { page.value = 0 })

    function fmtNum(v) {
      if (v === null || v === undefined) return ''
      const n = Number(v)
      if (!Number.isFinite(n)) return String(v)
      return n.toFixed(4).replace(/\.?0+$/, '')
    }
    function cellValue(row, col) {
      const v = row[col.key]
      if (v === null || v === undefined) return ''
      if (col.numeric) return fmtNum(v)
      return String(v)
    }
    function cellColor(row, col) {
      if (!col.numeric) return ''
      const v = Number(row[col.key])
      if (!Number.isFinite(v)) return ''
      if (col.key?.includes('drawdown') || col.key?.includes('penalty')) {
        return v > 0 ? 'text-loss' : v < 0 ? 'text-profit' : ''
      }
      return v > 0 ? 'text-profit' : v < 0 ? 'text-loss' : ''
    }

    // Build detail col list from all non-null row keys
    function allDetailCols(row) {
      const SKIP = new Set(['_expandKey', 'indicator_tags', 'indicator_params'])
      return Object.keys(row)
        .filter(k => !SKIP.has(k) && row[k] !== null && row[k] !== undefined && row[k] !== '')
        .map(k => {
          const rawV = row[k]
          const n = Number(rawV)
          const isNum = Number.isFinite(n) && rawV !== '' && rawV !== true && rawV !== false
          const formatted = isNum ? n.toFixed(4).replace(/\.?0+$/, '') : String(rawV)
          let color = ''
          if (isNum) {
            if (k.includes('drawdown') || k.includes('penalty')) color = n > 0 ? 'text-loss' : n < 0 ? 'text-profit' : ''
            else color = n > 0 ? 'text-profit' : n < 0 ? 'text-loss' : ''
          }
          const label = (window._AUTOWFO_L && window._AUTOWFO_L[k]) || k
          return { key: k, label, value: formatted, color }
        })
    }

    return { search, page, perPage, currentSort, currentDir, toggleSort, isExpanded,
             filteredRows, sortedRows, pagedRows, totalPages, visiblePages,
             cellValue, cellColor, allDetailCols, t }
  }
}

// ═══ Progress Bar ═══
export const ProgressBar = {
  name: 'ProgressBar',
  props: { percent: { type: Number, default: 0 }, height: { type: String, default: 'h-2' } },
  template: `
    <div class="w-full rounded-full overflow-hidden" :class="[height, 'bg-gray-200 dark:bg-gray-700']">
      <div class="h-full rounded-full transition-all duration-500 ease-out"
           :class="percent >= 100 ? 'bg-emerald-500' : 'bg-blue-500'"
           :style="{ width: Math.min(100, Math.max(0, percent)) + '%' }"></div>
    </div>
  `,
}

// ═══ Action Button ═══

// ═══ Detail Panel (row expand content for Results tab) ═══
export const DetailPanel = {
  name: 'DetailPanel',
  props: {
    row: Object,
    getParamFull: Function,
    getTags: Function,
  },
  template: `
    <div class="space-y-3">
      <!-- Tags -->
      <div v-if="tags.length" class="flex flex-wrap gap-1.5">
        <span v-for="tag in tags" :key="tag"
              class="tag-chip bg-indigo-500/15 text-indigo-400 border border-indigo-500/25 text-xs font-semibold">
          {{ tag }}
        </span>
      </div>
      <!-- Section: 指標參數 -->
      <div v-if="paramPairs.length">
        <div class="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5 font-semibold">指標參數</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-x-5 gap-y-1">
          <div v-for="p in paramPairs" :key="p.k" class="flex gap-1 text-xs min-w-0">
            <span class="text-gray-500 dark:text-gray-400 shrink-0">{{ p.label }}:</span>
            <span class="font-mono text-gray-900 dark:text-gray-100 font-medium">{{ p.v }}</span>
          </div>
        </div>
      </div>
      <!-- Section: OOS 指標 -->
      <div v-if="oosMetrics.length">
        <div class="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5 font-semibold">OOS 績效</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-x-5 gap-y-1">
          <div v-for="m in oosMetrics" :key="m.k" class="flex gap-1 text-xs min-w-0">
            <span class="text-gray-500 dark:text-gray-400 shrink-0">{{ m.label }}:</span>
            <span class="font-mono font-semibold" :class="m.color">{{ m.v }}</span>
          </div>
        </div>
      </div>
      <!-- Section: 平均績效 -->
      <div v-if="avgMetrics.length">
        <div class="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5 font-semibold">平均績效</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-x-5 gap-y-1">
          <div v-for="m in avgMetrics" :key="m.k" class="flex gap-1 text-xs min-w-0">
            <span class="text-gray-500 dark:text-gray-400 shrink-0">{{ m.label }}:</span>
            <span class="font-mono font-semibold" :class="m.color">{{ m.v }}</span>
          </div>
        </div>
      </div>
      <!-- Section: 其他 -->
      <div v-if="otherFields.length">
        <div class="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5 font-semibold">其他欄位</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-x-5 gap-y-1">
          <div v-for="f in otherFields" :key="f.k" class="flex gap-1 text-xs min-w-0">
            <span class="text-gray-500 dark:text-gray-400 shrink-0 truncate max-w-[120px]">{{ f.label }}:</span>
            <span class="font-mono text-gray-900 dark:text-gray-100 truncate">{{ f.v }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
  setup(props) {
    const L = window._AUTOWFO_L || {}
    const PARAM_ORDER_KEYS = [
      'vol_lookback','vol_z','mom_lookback','trade_mom_lookback',
      'rsi_window','rsi_long','rsi_short','bb_width','atr_ratio','ma_fast','ma_slow',
      'macd_hist_ratio','stoch_long','stoch_short','obv_lookback','volume_lookback','volume_z',
      'roc_lookback','roc_threshold','mfi_long','mfi_short','cmf_lookback','cmf_threshold',
      'vroc_lookback','vroc_threshold','ad_lookback','tp_stop','sl_stop','max_hold',
    ]
    const OOS_KEYS = ['oos_avg_total_return_pct','oos_avg_win_rate_pct','oos_avg_avg_trade_pct',
      'oos_avg_max_drawdown_pct','oos_avg_daily_trades','oos_avg_hold_hours',
      'oos_min_total_trades','oos_avg_total_trades','oos_avg_position_coverage_pct',
      'oos_sharpe_like','oos_return_std','oos_positive_segment_ratio']
    const AVG_KEYS = ['avg_total_return_pct','avg_win_rate_pct','avg_avg_trade_pct',
      'avg_max_drawdown_pct','avg_daily_trades','avg_hold_hours',
      'avg_total_trades','min_total_trades','avg_position_coverage_pct',
      'composite_score','bh_return_pct','alpha_vs_bh']
    const SKIP = new Set(['_expandKey','indicator_tags','indicator_params',
      ...PARAM_ORDER_KEYS, ...OOS_KEYS, ...AVG_KEYS])

    function fmtV(v, k) {
      const n = Number(v)
      if (!Number.isFinite(n) || v === '' || v === true || v === false) return String(v)
      return n.toFixed(4).replace(/\.?0+$/, '')
    }
    function colorFor(k, v) {
      const n = Number(v)
      if (!Number.isFinite(n)) return ''
      if (k.includes('drawdown') || k.includes('penalty')) return n > 0 ? 'text-loss' : n < 0 ? 'text-profit' : ''
      return n > 0 ? 'text-profit' : n < 0 ? 'text-loss' : ''
    }
    function mkEntry(k, v) {
      return { k, label: L[k] || k, v: fmtV(v, k), color: colorFor(k, v) }
    }

    const tags = computed(() => props.getTags ? props.getTags(props.row) : [])
    const paramPairs = computed(() =>
      PARAM_ORDER_KEYS.filter(k => props.row[k] !== null && props.row[k] !== undefined && props.row[k] !== '')
                       .map(k => mkEntry(k, props.row[k]))
    )
    const oosMetrics = computed(() =>
      OOS_KEYS.filter(k => props.row[k] !== null && props.row[k] !== undefined && props.row[k] !== '')
               .map(k => mkEntry(k, props.row[k]))
    )
    const avgMetrics = computed(() =>
      AVG_KEYS.filter(k => props.row[k] !== null && props.row[k] !== undefined && props.row[k] !== '')
               .map(k => mkEntry(k, props.row[k]))
    )
    const otherFields = computed(() =>
      Object.keys(props.row)
        .filter(k => !SKIP.has(k) && props.row[k] !== null && props.row[k] !== undefined && props.row[k] !== '')
        .map(k => mkEntry(k, props.row[k]))
    )

    return { tags, paramPairs, oosMetrics, avgMetrics, otherFields }
  }
}


export const ActionButton = {
  name: 'ActionButton',
  props: {
    label: String,
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    variant: { type: String, default: 'primary' },
    icon: String
  },
  emits: ['click'],
  template: `
    <button
      @click="$emit('click', $event)"
      :disabled="disabled || loading"
      :class="[
        'relative inline-flex items-center justify-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-150',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variantClasses
      ]"
    >
      <span v-if="loading" class="animate-spin flex-shrink-0">
        <svg class="w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </span>
      <span v-else-if="icon" class="flex-shrink-0">{{ icon }}</span>
      <span :class="{'opacity-0': loading && !label}">{{ label || ' ' }}</span>
      <span v-if="loading && label" class="absolute inset-0 flex items-center justify-center bg-inherit rounded-lg">
        <svg class="w-4 h-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </span>
    </button>
  `,
  computed: {
    variantClasses() {
      if (this.variant === 'primary') return 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm focus:ring-2 focus:ring-blue-500/30'
      if (this.variant === 'danger') return 'bg-rose-600 text-white hover:bg-rose-700 shadow-sm focus:ring-2 focus:ring-rose-500/30'
      if (this.variant === 'success') return 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm focus:ring-2 focus:ring-emerald-500/30'
      return 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 focus:ring-2 focus:ring-gray-500/30'
    }
  }
}
