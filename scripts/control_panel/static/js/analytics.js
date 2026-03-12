import { ref, computed, onMounted } from 'vue'
import { fetchJson } from './api.js'
import { showToast } from './store.js'
import { L } from './i18n.js'

function _toNumber(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function _decodeIndicatorPart(raw) {
  if (raw === null || raw === undefined) return ''
  if (Array.isArray(raw)) {
    return raw.map(v => String(v)).join('+')
  }
  const text = String(raw).trim()
  if (!text) return ''
  try {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) return parsed.map(v => String(v)).join('+')
    if (typeof parsed === 'string') return parsed
  } catch (_) {
    // keep raw text
  }
  return text
}

function _indicatorId(row) {
  const direct = _decodeIndicatorPart(row.indicator_id)
  if (direct) return direct
  const trigger = _decodeIndicatorPart(row.trigger_indicators)
  const action = _decodeIndicatorPart(row.action_indicators)
  if (trigger && action) return `${trigger} -> ${action}`
  return trigger || action || '--'
}

function _projectLeaderboardRow(row, index) {
  return {
    _row_id: String(row.indicator_id || row.trigger_indicators || row.action_indicators || `lb-${index}`),
    indicator_id: _indicatorId(row),
    avg_oos_sharpe: _toNumber(row.avg_oos_sharpe ?? row.avg_sharpe),
    win_rate: _toNumber(row.win_rate ?? row.avg_oos_win_rate ?? row.avg_win_rate),
    combo_count: Number.parseInt(row.combo_count ?? row.total_combos ?? row.n_combos ?? 0, 10) || 0,
  }
}

function _projectBestRow(row, index) {
  return {
    _row_id: String(row.combo_id || `best-${index}`),
    combo_id: String(row.combo_id || '--'),
    experiment_id: String(row.experiment_id || '--'),
    oos_sharpe: _toNumber(row.oos_sharpe),
    direction: String(row.direction || '--'),
  }
}

function _projectCoverageRow(row, index) {
  return {
    _row_id: `${row.indicator_a || '--'}|${row.indicator_b || '--'}|${index}`,
    indicator_a: String(row.indicator_a || '--'),
    indicator_b: String(row.indicator_b || '--'),
    tested: Boolean(row.tested),
    avg_sharpe: _toNumber(row.avg_sharpe),
    total_combos: Number.parseInt(row.total_combos ?? 0, 10) || 0,
  }
}

export const AnalyticsTab = {
  name: 'AnalyticsTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('analytics_title', 'Analytics') }}</h2>
          <action-button @click="refresh" :loading="loading" variant="secondary"
                         :label="t('analytics_refresh', 'Refresh')">
          </action-button>
        </div>

        <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Growth</div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div v-for="card in growthCards" :key="card.label" class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
              <div class="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ card.label }}</div>
              <div class="text-lg font-semibold tabular-nums text-gray-800 dark:text-gray-100">{{ card.value }}</div>
            </div>
          </div>
        </div>

        <div class="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-800/70">
            Indicator Leaderboard
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    <button @click="setSort('indicator_id')" class="hover:text-blue-500 transition-colors">indicator_id</button>
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    <button @click="setSort('avg_oos_sharpe')" class="hover:text-blue-500 transition-colors">avg_oos_sharpe</button>
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    <button @click="setSort('win_rate')" class="hover:text-blue-500 transition-colors">win_rate</button>
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">
                    <button @click="setSort('combo_count')" class="hover:text-blue-500 transition-colors">combo_count</button>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!sortedLeaderboard.length">
                  <td colspan="4" class="px-4 py-6 text-center text-gray-400 dark:text-gray-500 text-sm">No leaderboard data</td>
                </tr>
                <tr v-for="row in sortedLeaderboard" :key="row._row_id" class="border-b border-gray-100 dark:border-gray-800">
                  <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.indicator_id }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ fmtNum(row.avg_oos_sharpe) }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ fmtNum(row.win_rate) }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.combo_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-800/70">
            All-Time Best
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">combo_id</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">experiment_id</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">oos_sharpe</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">direction</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!bestRows.length">
                  <td colspan="4" class="px-4 py-6 text-center text-gray-400 dark:text-gray-500 text-sm">No best combo data</td>
                </tr>
                <tr v-for="row in bestRows" :key="row._row_id" class="border-b border-gray-100 dark:border-gray-800">
                  <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.combo_id }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.experiment_id }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ fmtNum(row.oos_sharpe) }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.direction }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-800/70">
            Indicator Coverage Map
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">indicator_a</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">indicator_b</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">tested</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">avg_sharpe</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!coverageRows.length">
                  <td colspan="4" class="px-4 py-6 text-center text-gray-400 dark:text-gray-500 text-sm">No coverage data</td>
                </tr>
                <tr v-for="row in coverageRows" :key="row._row_id" class="border-b border-gray-100 dark:border-gray-800">
                  <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.indicator_a }}</td>
                  <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.indicator_b }}</td>
                  <td class="px-3 py-2 text-xs">
                    <span
                      class="px-2 py-0.5 rounded-full font-medium"
                      :class="row.tested
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'"
                    >
                      {{ row.tested ? 'yes' : 'no' }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ fmtNum(row.avg_sharpe) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="isEmpty" class="rounded-lg border border-blue-200 dark:border-blue-700/40 bg-blue-50 dark:bg-blue-900/20 p-4 text-sm text-blue-700 dark:text-blue-300">
          尚無分析資料，請先執行實驗
        </div>
      </div>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key
    const loading = ref(true)
    const leaderboardRows = ref([])
    const bestRows = ref([])
    const coverageRows = ref([])
    const growth = ref({
      total_experiments: 0,
      total_runs: 0,
      total_combos: 0,
      leaderboard_size: 0,
    })
    const sortKey = ref('avg_oos_sharpe')
    const sortDesc = ref(true)

    const sortedLeaderboard = computed(() => {
      const rows = [...leaderboardRows.value]
      rows.sort((left, right) => {
        const key = sortKey.value
        const lval = left[key]
        const rval = right[key]
        if (key === 'indicator_id') {
          const cmp = String(lval || '').localeCompare(String(rval || ''))
          return sortDesc.value ? -cmp : cmp
        }
        const ln = _toNumber(lval)
        const rn = _toNumber(rval)
        if (ln === null && rn === null) return 0
        if (ln === null) return 1
        if (rn === null) return -1
        const cmp = ln - rn
        return sortDesc.value ? -cmp : cmp
      })
      return rows
    })

    const isEmpty = computed(() => {
      return !leaderboardRows.value.length && !bestRows.value.length && !coverageRows.value.length
    })

    const growthCards = computed(() => {
      return [
        { label: 'total_experiments', value: Number(growth.value.total_experiments || 0) },
        { label: 'total_runs', value: Number(growth.value.total_runs || 0) },
        { label: 'total_combos', value: Number(growth.value.total_combos || 0) },
        { label: 'leaderboard_size', value: Number(growth.value.leaderboard_size || 0) },
      ]
    })

    function setSort(key) {
      if (sortKey.value === key) {
        sortDesc.value = !sortDesc.value
        return
      }
      sortKey.value = key
      sortDesc.value = key !== 'indicator_id'
    }

    function fmtNum(value) {
      const num = _toNumber(value)
      if (num === null) return '--'
      return String(Math.round(num * 10000) / 10000)
    }

    async function refresh() {
      loading.value = true
      try {
        const [leaderboard, best, coverage, growthPayload] = await Promise.all([
          fetchJson('/analytics/leaderboard.json'),
          fetchJson('/analytics/best.json'),
          fetchJson('/analytics/coverage-map.json'),
          fetchJson('/analytics/growth.json'),
        ])
        const rawLeaderboard = Array.isArray(leaderboard?.indicators) ? leaderboard.indicators : []
        const rawBest = Array.isArray(best?.combos) ? best.combos : []
        const rawCoverage = Array.isArray(coverage?.pairs) ? coverage.pairs : []
        const rawGrowth = growthPayload && typeof growthPayload.growth === 'object' ? growthPayload.growth : {}

        leaderboardRows.value = rawLeaderboard.map((row, index) => _projectLeaderboardRow(row, index))
        bestRows.value = rawBest.map((row, index) => _projectBestRow(row, index))
        coverageRows.value = rawCoverage.map((row, index) => _projectCoverageRow(row, index))
        growth.value = {
          total_experiments: Number(rawGrowth.total_experiments || 0),
          total_runs: Number(rawGrowth.total_runs || 0),
          total_combos: Number(rawGrowth.total_combos || 0),
          leaderboard_size: Number(rawGrowth.leaderboard_size || 0),
        }
      } catch (err) {
        showToast(String(err), 'error')
        leaderboardRows.value = []
        bestRows.value = []
        coverageRows.value = []
        growth.value = {
          total_experiments: 0,
          total_runs: 0,
          total_combos: 0,
          leaderboard_size: 0,
        }
      } finally {
        loading.value = false
      }
    }

    onMounted(refresh)

    return {
      t,
      loading,
      bestRows,
      coverageRows,
      growthCards,
      sortedLeaderboard,
      isEmpty,
      refresh,
      setSort,
      fmtNum,
    }
  },
}
