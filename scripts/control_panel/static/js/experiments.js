import { ref, onMounted } from 'vue'
import { fetchJson, postJson } from './api.js'
import { confirmAction, showToast } from './store.js'
import { L } from './i18n.js'

const KNOWN_INDICATORS = new Set(['RSI', 'MACD', 'BB', 'EMA', 'Volume'])
const KNOWN_OPERATORS = new Set([
  'below',
  'above',
  'crossover',
  'crossunder',
  'near_lower',
  'near_upper',
  'above_avg',
  'pct_move',
])

function _defaultTrigger() {
  return {
    asset: 'BTC/USDT',
    timeframe: '1h',
    indicators: ['RSI'],
    conditions: {
      RSI: {
        operator: 'below',
        param_name: 'rsi_period',
        param_values: [14],
        threshold_values: [30],
      },
    },
    require_all: true,
  }
}

function _defaultAction() {
  return {
    asset: 'ETH/USDT',
    timeframe: '4h',
    indicators: ['EMA'],
    conditions: {
      EMA: {
        operator: 'above',
        param_name: 'ema_period',
        param_values: [20],
        threshold_values: [0],
      },
    },
    require_all: true,
    direction: 'both',
  }
}

function _defaultRisk() {
  return {
    stoploss_pct_values: [-3],
    take_profit_pct_values: [5],
    max_hold_bars_values: [24],
  }
}

function _defaultWf() {
  return {
    train_days: 90,
    test_days: 30,
    step_days: 30,
  }
}

function _jsonOrThrow(raw, label) {
  try {
    const payload = JSON.parse(String(raw || '').trim())
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error(`${label} must be JSON object`)
    }
    return payload
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    throw new Error(`${label} JSON parse failed: ${message}`)
  }
}

function _toList(raw, fallback = []) {
  if (Array.isArray(raw)) return raw
  if (raw === undefined || raw === null) return fallback
  return [raw]
}

function _preValidateConfig(config) {
  const errors = []
  const experimentId = String(config.experiment_id || '').trim()
  if (!/^[A-Za-z0-9_]+$/.test(experimentId)) {
    errors.push('experiment_id must be non-empty alphanumeric/underscore')
  }

  const mode = String(config.mode || '').trim().toLowerCase()
  if (!['hypothesis', 'discovery'].includes(mode)) {
    errors.push("mode must be 'hypothesis' or 'discovery'")
  }

  const trigger = config.trigger
  const action = config.action
  if (!trigger || typeof trigger !== 'object' || Array.isArray(trigger)) {
    errors.push('trigger must be an object')
  }
  if (!action || typeof action !== 'object' || Array.isArray(action)) {
    errors.push('action must be an object')
  }

  if (trigger && action && typeof trigger === 'object' && typeof action === 'object') {
    if (!String(trigger.asset || '').trim() || !String(action.asset || '').trim()) {
      errors.push('trigger.asset and action.asset must be non-empty strings')
    }
    if (!String(trigger.timeframe || '').trim() || !String(action.timeframe || '').trim()) {
      errors.push('trigger.timeframe and action.timeframe must be non-empty strings')
    }
  }

  for (const side of ['trigger', 'action']) {
    const block = config[side]
    if (!block || typeof block !== 'object' || Array.isArray(block)) continue

    if (!Array.isArray(block.indicators)) {
      errors.push(`${side}.indicators must be a list`)
    } else {
      for (const indicator of block.indicators) {
        const ind = String(indicator || '').trim()
        if (!ind) {
          errors.push(`${side}.indicators contains empty indicator`)
        } else if (!KNOWN_INDICATORS.has(ind)) {
          errors.push(`${side}.indicators contains unknown indicator: ${ind}`)
        }
      }
    }

    const conditions = block.conditions
    if (!conditions || typeof conditions !== 'object' || Array.isArray(conditions)) {
      errors.push(`${side}.conditions must be an object`)
      continue
    }
    for (const [name, cfg] of Object.entries(conditions)) {
      if (!cfg || typeof cfg !== 'object' || Array.isArray(cfg)) {
        errors.push(`${side}.conditions[${name}] must be an object`)
        continue
      }
      const operator = String(cfg.operator || '').trim()
      if (!KNOWN_OPERATORS.has(operator)) {
        errors.push(`${side}.conditions[${name}].operator is invalid: ${operator}`)
      }
    }
  }

  const wf = config.wf
  if (!wf || typeof wf !== 'object' || Array.isArray(wf)) {
    errors.push('wf must be an object')
  } else {
    const train = Number.parseInt(wf.train_days, 10)
    const test = Number.parseInt(wf.test_days, 10)
    const step = Number.parseInt(wf.step_days, 10)
    if (!Number.isInteger(train) || !Number.isInteger(test) || !Number.isInteger(step)) {
      errors.push('wf.train_days/wf.test_days/wf.step_days must be integers')
    } else if (train < 7 || test < 1 || step < test) {
      errors.push('wf must satisfy: train_days >= 7, test_days >= 1, step_days >= test_days')
    }
  }

  const risk = config.risk
  if (!risk || typeof risk !== 'object' || Array.isArray(risk)) {
    errors.push('risk must be an object')
  } else {
    const stoploss = _toList(risk.stoploss_pct_values, [-1])
    const takeProfit = _toList(risk.take_profit_pct_values, [1])
    if (stoploss.some(v => Number(v) >= 0)) {
      errors.push('risk.stoploss_pct_values must all be negative')
    }
    if (takeProfit.some(v => Number(v) <= 0)) {
      errors.push('risk.take_profit_pct_values must all be positive')
    }
  }
  return errors
}

async function _deleteExperiment(experimentId) {
  const res = await fetch(`/experiments/${encodeURIComponent(experimentId)}`, { method: 'DELETE' })
  const payload = await res.json().catch(() => ({}))
  if (!res.ok || payload.ok === false) {
    const error = new Error(String(payload.error || `HTTP ${res.status}`))
    error.status = res.status
    error.payload = payload
    throw error
  }
  return payload
}

export const ExperimentsTab = {
  name: 'ExperimentsTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('exp_title', 'Experiments') }}</h2>
          <action-button @click="refresh" :loading="loading" variant="secondary"
                         :label="t('exp_refresh', 'Refresh')">
          </action-button>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">experiment_id</span>
            <input v-model.trim="form.experimentId" type="text" placeholder="exp_demo" class="cfg-input" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">mode</span>
            <select v-model="form.mode" class="cfg-input">
              <option value="hypothesis">hypothesis</option>
              <option value="discovery">discovery</option>
            </select>
          </label>
          <label class="space-y-1 md:col-span-2">
            <span class="text-xs text-gray-500 dark:text-gray-400">description</span>
            <input v-model.trim="form.description" type="text" class="cfg-input" />
          </label>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">trigger (JSON)</span>
            <textarea v-model="form.triggerJson" class="cfg-input font-mono h-40"></textarea>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">action (JSON)</span>
            <textarea v-model="form.actionJson" class="cfg-input font-mono h-40"></textarea>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">risk (JSON)</span>
            <textarea v-model="form.riskJson" class="cfg-input font-mono h-32"></textarea>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">wf (JSON)</span>
            <textarea v-model="form.wfJson" class="cfg-input font-mono h-32"></textarea>
          </label>
        </div>

        <div v-if="validationErrors.length" class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-3">
          <div class="text-xs font-semibold text-amber-700 dark:text-amber-300 mb-1">{{ t('exp_validate_title', 'Validation errors') }}</div>
          <ul class="text-xs text-amber-700 dark:text-amber-200 list-disc pl-4 space-y-0.5">
            <li v-for="(err, idx) in validationErrors" :key="'exp-err-' + idx">{{ err }}</li>
          </ul>
        </div>

        <div class="flex gap-2">
          <action-button @click="createExperiment" :loading="creating" variant="primary"
                         :label="t('exp_create', 'Create Experiment')">
          </action-button>
          <action-button @click="resetForm" variant="secondary"
                         :label="t('exp_reset', 'Reset')">
          </action-button>
        </div>
      </div>

      <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="data-table">
            <thead>
              <tr class="bg-gray-50 dark:bg-gray-800/80">
                <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">experiment_id</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">mode</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">runs</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">last_run_utc</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">best_oos_sharpe</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('exp_actions', 'Actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!rows.length">
                <td colspan="6" class="px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">{{ t('datatable_no_data', 'No data') }}</td>
              </tr>
              <tr v-for="row in rows" :key="row.experiment_id"
                  class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.experiment_id }}</td>
                <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.mode || '' }}</td>
                <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.runs || 0 }}</td>
                <td class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">{{ row.last_run_utc || '--' }}</td>
                <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ fmtNum(row.best_oos_sharpe) }}</td>
                <td class="px-3 py-2">
                  <action-button @click="deleteExperiment(row.experiment_id)" :loading="deletingId === row.experiment_id" variant="secondary"
                                 :label="t('exp_delete', 'Delete')" class="!px-2 !py-1 !text-xs text-red-600 hover:text-red-700">
                  </action-button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key

    const loading = ref(true)
    const creating = ref(false)
    const deletingId = ref('')
    const validationErrors = ref([])
    const rows = ref([])

    const form = ref({
      experimentId: '',
      mode: 'hypothesis',
      description: '',
      triggerJson: JSON.stringify(_defaultTrigger(), null, 2),
      actionJson: JSON.stringify(_defaultAction(), null, 2),
      riskJson: JSON.stringify(_defaultRisk(), null, 2),
      wfJson: JSON.stringify(_defaultWf(), null, 2),
    })

    function fmtNum(value) {
      const num = Number(value)
      if (!Number.isFinite(num)) return '--'
      return String(Math.round(num * 10000) / 10000)
    }

    async function refresh() {
      try {
        const payload = await fetchJson('/experiments.json')
        rows.value = Array.isArray(payload.experiments) ? payload.experiments : []
      } catch (err) {
        showToast(String(err), 'error')
      } finally {
        loading.value = false
      }
    }

    function resetForm() {
      form.value.experimentId = ''
      form.value.mode = 'hypothesis'
      form.value.description = ''
      form.value.triggerJson = JSON.stringify(_defaultTrigger(), null, 2)
      form.value.actionJson = JSON.stringify(_defaultAction(), null, 2)
      form.value.riskJson = JSON.stringify(_defaultRisk(), null, 2)
      form.value.wfJson = JSON.stringify(_defaultWf(), null, 2)
      validationErrors.value = []
    }

    function buildPayload() {
      const trigger = _jsonOrThrow(form.value.triggerJson, 'trigger')
      const action = _jsonOrThrow(form.value.actionJson, 'action')
      const risk = _jsonOrThrow(form.value.riskJson, 'risk')
      const wf = _jsonOrThrow(form.value.wfJson, 'wf')
      return {
        experiment_id: String(form.value.experimentId || '').trim(),
        description: String(form.value.description || '').trim(),
        version: 1,
        created_utc: new Date().toISOString(),
        mode: String(form.value.mode || '').trim(),
        trigger,
        action,
        risk,
        wf,
      }
    }

    async function createExperiment() {
      creating.value = true
      validationErrors.value = []
      try {
        const payload = buildPayload()
        const errors = _preValidateConfig(payload)
        if (errors.length) {
          validationErrors.value = errors
          showToast(t('exp_validate_failed', 'Pre-validation failed'), 'warn')
          return
        }
        await postJson('/experiments/create', payload)
        showToast(t('exp_created', 'Experiment created'), 'success')
        await refresh()
      } catch (err) {
        const status = Number(err?.status || 0)
        if (status === 409) {
          showToast(t('exp_error_409', 'Experiment already exists (409)'), 'warn')
        } else if (status === 404) {
          showToast(t('exp_error_404', 'Endpoint not found (404)'), 'error')
        } else {
          showToast(String(err), 'error')
        }
      } finally {
        creating.value = false
      }
    }

    async function deleteExperiment(experimentId) {
      const ok = await confirmAction({
        title: t('exp_confirm_delete_title', 'Delete experiment?'),
        message: `${t('exp_confirm_delete_message', 'This will delete experiment')}: ${experimentId}`,
        confirmText: t('exp_delete', 'Delete'),
        variant: 'danger',
      })
      if (!ok) return

      deletingId.value = String(experimentId || '')
      try {
        await _deleteExperiment(experimentId)
        showToast(t('exp_deleted', 'Experiment deleted'), 'success')
        await refresh()
      } catch (err) {
        const status = Number(err?.status || 0)
        if (status === 409) {
          showToast(t('exp_delete_409', 'Cannot delete: experiment has runs (409)'), 'warn')
        } else if (status === 404) {
          showToast(t('exp_delete_404', 'Experiment not found (404)'), 'warn')
        } else {
          showToast(String(err), 'error')
        }
      } finally {
        deletingId.value = ''
      }
    }

    onMounted(refresh)

    return {
      t,
      loading,
      creating,
      deletingId,
      validationErrors,
      rows,
      form,
      fmtNum,
      refresh,
      resetForm,
      createExperiment,
      deleteExperiment,
    }
  },
}
