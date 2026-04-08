import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson, fetchText } from './api.js'
import { showToast } from './store.js'
import { L } from './i18n.js'

const TIMEFRAME_OPTIONS = [
  '1m', '5m', '15m', '30m',
  '1h', '2h', '4h', '6h', '8h', '12h',
  '1d', '3d', '1w',
]

export const ConfigTab = {
  name: 'ConfigTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="skeleton skeleton-card h-12"></div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div v-for="n in 4" :key="'cfg-sk-' + n" class="skeleton skeleton-card h-72"></div>
        </div>
      </div>
      <template v-else>
        <div class="flex items-center justify-between gap-3">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('config_title', 'Sweep Config') }}</h2>
          <div class="flex gap-2">
            <action-button @click="loadCfg" :loading="loading" variant="secondary"
                           :label="t('config_reload', 'Reload')">
            </action-button>
            <action-button @click="saveCfg" :loading="saving" :disabled="!canSave" variant="primary"
                           :label="t('config_save', 'Save Config')">
            </action-button>
          </div>
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400">
          {{ t('config_hint_path', 'Edits the base sweep template in artifacts/sweep_config.json. Each new run copies it into run-local runtime/sweep_config.json for reproducibility.') }}
        </p>

        <div v-if="presets.length" class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
          <div class="flex items-start justify-between gap-4">
            <div class="space-y-1">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
                {{ t('config_campaign_title', 'Rerun Campaign Presets') }}
              </h3>
              <p class="text-xs text-gray-500 dark:text-gray-400">
                {{ t('config_campaign_hint', 'Apply a documented rerun wave to the base sweep template before using Coverage or Batch.') }}
              </p>
            </div>
            <span v-if="presetLoading" class="text-[11px] text-gray-400 dark:text-gray-500">
              {{ t('config_campaign_loading', 'Loading...') }}
            </span>
          </div>
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <div v-for="preset in presets" :key="preset.preset_id"
                 class="rounded-xl border border-gray-200 dark:border-gray-700/60 bg-gray-50 dark:bg-gray-900/30 p-4 space-y-3">
              <div class="flex items-start justify-between gap-3">
                <div class="space-y-1">
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">{{ preset.title }}</div>
                  <p class="text-xs text-gray-500 dark:text-gray-400">{{ preset.summary }}</p>
                </div>
                <span v-if="preset.optional"
                      class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                  {{ t('config_campaign_optional', 'Optional') }}
                </span>
              </div>
              <div class="space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                <p>{{ t('config_timeframe', 'Timeframe') }}: {{ formatPresetTimeframes(preset.timeframes) }}</p>
                <p>{{ t('config_campaign_symbols', 'Symbols') }}: {{ formatPresetSymbols(preset.trade_symbols) }}</p>
                <p v-if="preset.operator_note">{{ preset.operator_note }}</p>
              </div>
              <action-button
                @click="applyPreset(preset.preset_id)"
                :loading="presetApplying === preset.preset_id"
                variant="secondary"
                :label="t('config_campaign_apply', 'Apply Preset')"
              >
              </action-button>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <span>cfg</span> {{ t('config_section_basic', 'Basic Settings') }}
            </h3>
            <div class="grid grid-cols-2 gap-3">
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_search_mode', 'Search Mode') }}</span>
                <select v-model="cfg.search_mode" class="cfg-input">
                  <option value="combo">{{ t('config_search_mode_combo', 'combo (full search)') }}</option>
                  <option value="refine">{{ t('config_search_mode_refine', 'refine (top candidates)') }}</option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_timeframe', 'Timeframe') }}</span>
                <select v-model="cfg.timeframe" class="cfg-input">
                  <option v-for="tf in timeframeOptions" :key="tf" :value="tf">{{ tf }}</option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_data_days', 'Data Days') }}</span>
                <input v-model.number="cfg.data_days" type="number" min="1" placeholder="180" class="cfg-input" />
              </label>
              <div class="space-y-1 col-span-2">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_combo_sizes', 'Combo Sizes') }}</span>
                <div class="flex flex-wrap gap-2 mt-1">
                  <label v-for="n in [2,3,4,5]" :key="n"
                         class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border cursor-pointer select-none transition-all"
                         :class="cfg.combo_sizes.includes(n)
                           ? 'bg-blue-600/20 border-blue-500/50 text-blue-400'
                           : 'bg-gray-100 dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:border-blue-400'">
                    <input type="checkbox" :value="n" v-model="cfg.combo_sizes" class="sr-only" />
                    <span v-if="cfg.combo_sizes.includes(n)">ok</span>
                    {{ n }}
                  </label>
                </div>
                <p class="text-[10px] text-gray-400 dark:text-gray-500 mt-1">
                  {{ t('config_combo_sizes_selected', 'Selected') }}: {{ sortedComboSizes || t('config_none', 'none') }}
                </p>
              </div>
            </div>

            <h4 class="text-xs font-semibold text-gray-600 dark:text-gray-300 mt-2">{{ t('config_walk_forward_title', 'Walk-Forward') }}</h4>
            <div class="grid grid-cols-3 gap-3">
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_wf_train_days', 'Train Days') }}</span>
                <input v-model.number="cfg.wf_train_days" type="number" min="1" placeholder="120" class="cfg-input" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_wf_test_days', 'Test Days') }}</span>
                <input v-model.number="cfg.wf_test_days" type="number" min="1" placeholder="30" class="cfg-input" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_wf_step_days', 'Step Days') }}</span>
                <input v-model.number="cfg.wf_step_days" type="number" :min="wfStepMinForInput" placeholder="30"
                       :class="['cfg-input', wfGuardrailError ? 'border-red-500 dark:border-red-500 ring-1 ring-red-500/40' : '']" />
              </label>
            </div>
            <p class="text-[11px] text-gray-500 dark:text-gray-400">
              {{ t('config_wf_guardrail_hint', '規則：步進天數需大於等於測試天數，避免 OOS 區間重疊。') }}
            </p>
            <p v-if="wfGuardrailError" class="text-[11px] text-red-600 dark:text-red-400">
              {{ wfGuardrailError }}
            </p>
          </div>

          <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <span>risk</span> {{ t('config_section_capital', 'Capital Settings') }}
            </h3>
            <div class="grid grid-cols-2 gap-3">
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_capital_mode', 'Capital Mode') }}</span>
                <select v-model="cfg.capital_mode" class="cfg-input">
                  <option value="shared">{{ t('config_capital_mode_shared', 'shared') }}</option>
                  <option value="per_symbol">{{ t('config_capital_mode_per_symbol', 'per_symbol') }}</option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_init_cash', 'Initial Cash (USDT)') }}</span>
                <input v-model.number="cfg.init_cash" type="number" min="0" placeholder="1000" class="cfg-input" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_order_size_pct', 'Order Size (%)') }}</span>
                <input v-model.number="cfg.order_size_pct" type="number" min="0" step="1" placeholder="50" class="cfg-input" />
              </label>
              <label class="space-y-1">
                <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_max_positions', 'Max Positions') }}</span>
                <input v-model.number="cfg.max_positions" type="number" min="1" placeholder="2" class="cfg-input" />
              </label>
            </div>
          </div>

          <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <span>sym</span> {{ t('config_section_symbols', 'Trade Symbols') }}
              </h3>
              <action-button @click="loadTopSymbols"
                             variant="secondary"
                             class="!px-2 !py-0.5 !text-[10px] !bg-transparent !border-0 !text-blue-500 hover:!text-blue-400 !shadow-none"
                             :label="t('config_load_top_symbols', 'Load Top 10')">
              </action-button>
            </div>
            <div class="flex flex-wrap gap-2">
              <label v-for="sym in availableSymbols" :key="sym"
                     class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border cursor-pointer transition-all"
                     :class="selectedSymbols.has(sym)
                       ? 'bg-blue-600/20 border-blue-500/50 text-blue-400'
                       : 'bg-gray-100 dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:border-blue-400'">
                <input type="checkbox" :value="sym" v-model="symbolList" class="sr-only" />
                <span v-if="selectedSymbols.has(sym)" class="text-blue-400">ok</span>
                {{ sym }}
              </label>
            </div>
            <input v-model="cfg.trade_symbols_raw" type="text"
                   :placeholder="t('config_symbols_placeholder', 'Comma-separated symbols, e.g. ETH/USDT,BNB/USDT')"
                   class="cfg-input w-full text-xs" />
          </div>

          <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
            <button @click="advOpen = !advOpen"
                    class="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold
                           text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
              <span>{{ t('config_advanced_title', 'Advanced Settings') }}</span>
              <span class="text-xs text-gray-400">{{ advOpen ? '^' : 'v' }}</span>
            </button>
            <div v-show="advOpen" class="px-5 pb-4 space-y-3 border-t border-gray-200 dark:border-gray-700">
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_combo_seed', 'Combo Seed') }}</span>
                  <input v-model.number="cfg.combo_seed" type="number" placeholder="42" class="cfg-input" />
                </label>
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_slippage_bps', 'Slippage (bps)') }}</span>
                  <input v-model.number="cfg.slippage_bps" type="number" step="0.1" placeholder="2" class="cfg-input" />
                </label>
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_spread_bps', 'Spread (bps)') }}</span>
                  <input v-model.number="cfg.spread_bps" type="number" step="0.1" placeholder="2" class="cfg-input" />
                </label>
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_funding_rate_daily', 'Funding Rate Daily') }}</span>
                  <input v-model.number="cfg.funding_rate" type="number" step="0.0001" placeholder="0.0003" class="cfg-input" />
                </label>
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_segment_start', 'Combo Segment Start') }}</span>
                  <input v-model.number="cfg.seg_start" type="number" placeholder="0" class="cfg-input" />
                </label>
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_segment_size', 'Combo Segment Size') }}</span>
                  <input v-model.number="cfg.seg_size" type="number" :placeholder="t('config_none', 'none')" class="cfg-input" />
                </label>
                <label class="space-y-1">
                  <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('config_top_n_refine', 'Top N Refine') }}</span>
                  <input v-model.number="cfg.top_n_refine" type="number" placeholder="50" class="cfg-input" />
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <button @click="devOpen = !devOpen"
                  class="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold
                         text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
            <span>{{ t('config_dev_test_title', 'Quick Test') }}</span>
            <span class="text-xs text-gray-400">{{ devOpen ? '^' : 'v' }}</span>
          </button>
          <div v-show="devOpen" class="px-5 pb-4 space-y-3 border-t border-gray-200 dark:border-gray-700">
            <div class="flex flex-wrap gap-2 mt-3">
              <action-button @click="doTestStart"
                             variant="secondary"
                             class="!bg-indigo-600 !text-white hover:!bg-indigo-700 !border-0"
                             :label="t('overview_test_start', 'Start Test')">
              </action-button>
              <action-button @click="doTestStop"
                             variant="secondary"
                             :label="t('overview_test_stop', 'Stop Test')">
              </action-button>
              <action-button @click="doTestClearLog"
                             variant="secondary"
                             :label="t('overview_test_clear_log', 'Clear Test Log')">
              </action-button>
            </div>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div><span class="text-gray-500 dark:text-gray-400">{{ t('overview_test_stage', 'Stage') }}</span>
                   <span class="ml-1 font-semibold text-gray-900 dark:text-gray-100">{{ testStatus.stage || '--' }}</span></div>
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
    const cfg = ref({
      search_mode: 'combo',
      timeframe: '4h',
      data_days: null,
      wf_train_days: null,
      wf_test_days: null,
      wf_step_days: null,
      capital_mode: 'shared',
      init_cash: null,
      order_size_pct: null,
      max_positions: null,
      trade_symbols_raw: '',
      combo_sizes: [2, 3, 4],
      combo_seed: null,
      slippage_bps: null,
      spread_bps: null,
      funding_rate: null,
      seg_start: null,
      seg_size: null,
      top_n_refine: null,
    })
    const saving = ref(false)
    const advOpen = ref(false)
    const devOpen = ref(false)
    const presets = ref([])
    const presetLoading = ref(false)
    const presetApplying = ref('')
    const testStatus = ref({})
    const testLog = ref('')
    let testTimer = null
    const availableSymbols = ref([])
    const symbolList = ref([])

    const timeframeOptions = TIMEFRAME_OPTIONS
    const selectedSymbols = computed(() => new Set(symbolList.value))
    const sortedComboSizes = computed(() => {
      const values = Array.isArray(cfg.value.combo_sizes) ? cfg.value.combo_sizes.slice().sort((a, b) => a - b) : []
      return values.join(', ')
    })
    const toPositiveInt = value => {
      const n = Number(value)
      if (!Number.isFinite(n)) return null
      const intVal = Math.trunc(n)
      return intVal >= 1 ? intVal : null
    }
    const wfStepMinForInput = computed(() => {
      const testDays = toPositiveInt(cfg.value.wf_test_days)
      return testDays || 1
    })
    const wfGuardrailError = computed(() => {
      const testDays = toPositiveInt(cfg.value.wf_test_days)
      const stepDays = toPositiveInt(cfg.value.wf_step_days)
      if (testDays === null || stepDays === null) return ''
      if (stepDays < testDays) {
        return t(
          'config_wf_guardrail_error',
          `步進天數必須大於等於測試天數（目前 step=${stepDays}, test=${testDays}）`
        )
      }
      return ''
    })
    const canSave = computed(() => !wfGuardrailError.value)

    watch(symbolList, values => {
      if (Array.isArray(values) && values.length) {
        cfg.value.trade_symbols_raw = values.join(',')
      }
    })

    function applyConfigToForm(c) {
      const configPayload = c || {}
      const tf = configPayload.timeframes?.[0] || {}
      cfg.value.search_mode = configPayload.search_mode || 'combo'
      cfg.value.timeframe = tf.timeframe || ''
      cfg.value.data_days = tf.days || null
      cfg.value.wf_train_days = configPayload.wf_train_days ?? null
      cfg.value.wf_test_days = configPayload.wf_test_days ?? null
      cfg.value.wf_step_days = configPayload.wf_step_days ?? null
      cfg.value.capital_mode = configPayload.capital_mode || 'shared'
      cfg.value.init_cash = configPayload.init_cash_usdt ?? null
      const pct = configPayload.order_size_pct ?? null
      cfg.value.order_size_pct = pct > 0 && pct <= 1 ? pct * 100 : pct
      cfg.value.max_positions = configPayload.max_concurrent_positions ?? null
      const syms = Array.isArray(configPayload.trade_symbols) ? configPayload.trade_symbols : []
      cfg.value.trade_symbols_raw = syms.join(',')
      cfg.value.combo_sizes = Array.isArray(configPayload.combo_sizes) ? configPayload.combo_sizes.map(Number) : [2, 3, 4]
      cfg.value.combo_seed = configPayload.combo_seed ?? null
      cfg.value.slippage_bps = configPayload.slippage_bps ?? null
      cfg.value.spread_bps = configPayload.spread_bps ?? null
      cfg.value.funding_rate = configPayload.funding_rate_daily ?? null
      cfg.value.seg_start = configPayload.combo_segment_start ?? null
      cfg.value.seg_size = configPayload.combo_segment_size ?? null
      cfg.value.top_n_refine = configPayload.top_n_refine ?? null
      availableSymbols.value = syms
      symbolList.value = [...syms]
    }

    async function loadCfg() {
      try {
        const c = await fetchJson('/config.json')
        applyConfigToForm(c)
        showToast(t('config_toast_loaded', 'Config loaded'), 'success')
      } catch (e) {
        showToast(t('config_toast_load_failed', 'Failed to load config') + ': ' + e, 'error')
      } finally {
        loading.value = false
      }
    }

    async function loadPresets() {
      presetLoading.value = true
      try {
        const data = await fetchJson('/config/presets.json')
        presets.value = Array.isArray(data.presets) ? data.presets : []
      } catch (e) {
        showToast(t('config_campaign_load_failed', 'Failed to load rerun presets') + ': ' + e, 'error')
      } finally {
        presetLoading.value = false
      }
    }

    async function saveCfg() {
      if (wfGuardrailError.value) {
        showToast(wfGuardrailError.value, 'error')
        return
      }
      saving.value = true
      try {
        const c = cfg.value
        const symbols = c.trade_symbols_raw.split(',').map(s => s.trim()).filter(Boolean)
        const payload = {
          search_mode: c.search_mode || 'combo',
          timeframes: c.timeframe && c.data_days ? [{ timeframe: c.timeframe, days: c.data_days }] : [],
          wf_train_days: c.wf_train_days,
          wf_test_days: c.wf_test_days,
          wf_step_days: c.wf_step_days,
          capital_mode: c.capital_mode || 'shared',
          init_cash_usdt: c.init_cash,
          order_size_pct: c.order_size_pct,
          max_concurrent_positions: c.max_positions,
          trade_symbols: symbols,
          combo_sizes: c.combo_sizes.slice().sort((a, b) => a - b),
          combo_seed: c.combo_seed,
          slippage_bps: c.slippage_bps,
          spread_bps: c.spread_bps,
          funding_rate_daily: c.funding_rate,
          combo_segment_start: c.seg_start,
          combo_segment_size: c.seg_size,
          top_n_refine: c.top_n_refine,
        }
        const response = await postJson('/config', payload)
        showToast(response.message || t('config_toast_saved', 'Config saved'), 'success')
      } catch (e) {
        showToast(t('config_toast_save_failed', 'Failed to save config') + ': ' + e, 'error')
      } finally {
        saving.value = false
      }
    }

    async function applyPreset(presetId) {
      presetApplying.value = String(presetId || '')
      try {
        const response = await postJson('/config/apply-preset', { preset_id: presetId })
        applyConfigToForm(response.config || {})
        showToast(response.message || t('config_campaign_applied', 'Preset applied and saved'), 'success')
      } catch (e) {
        showToast(t('config_campaign_apply_failed', 'Failed to apply preset') + ': ' + e, 'error')
      } finally {
        presetApplying.value = ''
      }
    }

    async function loadTopSymbols() {
      try {
        const data = await fetchJson('/symbols/top?limit=10')
        const syms = data.symbols || []
        availableSymbols.value = syms
        symbolList.value = [...syms]
        cfg.value.trade_symbols_raw = syms.join(',')
        showToast(t('config_toast_top_symbols_loaded', 'Loaded top symbols'), 'success')
      } catch (e) {
        showToast(t('config_toast_top_symbols_failed', 'Failed to load symbols') + ': ' + e, 'error')
      }
    }

    function fmtTime(raw) {
      if (!raw) return '--'
      const d = Date.parse(raw)
      return Number.isNaN(d) ? String(raw) : new Date(d).toLocaleString()
    }

    function formatPresetTimeframes(timeframes) {
      if (!Array.isArray(timeframes) || !timeframes.length) return '--'
      return timeframes
        .map(item => `${item?.timeframe || '--'} / ${item?.days || '--'}d`)
        .join(', ')
    }

    function formatPresetSymbols(symbols) {
      return Array.isArray(symbols) && symbols.length ? symbols.join(', ') : '--'
    }

    async function refreshTest() {
      try {
        testStatus.value = await fetchJson('/tests/status.json')
        testLog.value = await fetchText('/tests/log-tail.txt')
      } catch (_) {
        // no-op
      }
    }

    async function doTestStart() {
      try {
        const r = await postJson('/tests/start')
        showToast(r.message || t('overview_toast_test_started', 'Test started'), 'success')
        refreshTest()
      } catch (e) {
        showToast(String(e), 'error')
      }
    }

    async function doTestStop() {
      try {
        const r = await postJson('/tests/stop')
        showToast(r.message || t('overview_toast_test_stopped', 'Test stopped'), 'success')
        refreshTest()
      } catch (e) {
        showToast(String(e), 'error')
      }
    }

    async function doTestClearLog() {
      try {
        const r = await postJson('/tests/clear-log')
        showToast(r.message || t('overview_toast_test_log_cleared', 'Test log cleared'), 'success')
        refreshTest()
      } catch (e) {
        showToast(String(e), 'error')
      }
    }

    onMounted(() => {
      loadCfg()
      loadPresets()
      refreshTest()
      testTimer = setInterval(refreshTest, 5000)
    })

    onUnmounted(() => {
      clearInterval(testTimer)
    })

    return {
      loading,
      cfg,
      saving,
      advOpen,
      devOpen,
      presets,
      presetLoading,
      presetApplying,
      testStatus,
      testLog,
      availableSymbols,
      symbolList,
      selectedSymbols,
      timeframeOptions,
      sortedComboSizes,
      wfStepMinForInput,
      wfGuardrailError,
      canSave,
      fmtTime,
      loadCfg,
      loadPresets,
      saveCfg,
      applyPreset,
      loadTopSymbols,
      formatPresetTimeframes,
      formatPresetSymbols,
      doTestStart,
      doTestStop,
      doTestClearLog,
      t,
    }
  },
}
