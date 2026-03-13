import { ref } from 'vue'
import { postJson } from './api.js'
import { showToast } from './store.js'
import { L } from './i18n.js'

const DEFAULT_POOL = {
  indicator_ids: ['RSI', 'EMA', 'MACD'],
  combo_size_range: [2, 2],
  pruning: { enabled: false },
}

function _parsePoolConfig(raw) {
  try {
    const payload = JSON.parse(String(raw || '').trim())
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      throw new Error('pool config must be object')
    }
    return payload
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    throw new Error(`pool_config parse failed: ${msg}`)
  }
}

export const DiscoveryTab = {
  name: 'DiscoveryTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('discovery_title', 'Discovery') }}</h2>
        </div>

        <label class="space-y-1 block">
          <span class="text-xs text-gray-500 dark:text-gray-400">pool_config (JSON)</span>
          <textarea v-model="poolConfigJson" class="cfg-input font-mono h-52"></textarea>
        </label>

        <label class="inline-flex items-center gap-2">
          <input type="checkbox" v-model="autoStart" class="rounded text-blue-600" />
          <span class="text-xs text-gray-600 dark:text-gray-400">auto_start_worker</span>
        </label>

        <div class="flex gap-2">
          <action-button @click="runTick" :loading="running" variant="primary"
                         :label="t('discovery_run_tick', 'Run Discovery Tick')">
          </action-button>
        </div>

        <div v-if="lastTick" class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 text-xs grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <div class="text-gray-500 dark:text-gray-400">generated</div>
            <div class="text-lg font-semibold tabular-nums">{{ lastTick.generated || 0 }}</div>
          </div>
          <div>
            <div class="text-gray-500 dark:text-gray-400">enqueued</div>
            <div class="text-lg font-semibold tabular-nums">{{ lastTick.enqueued || 0 }}</div>
          </div>
          <div>
            <div class="text-gray-500 dark:text-gray-400">skipped_existing</div>
            <div class="text-lg font-semibold tabular-nums">{{ lastTick.skipped_existing || 0 }}</div>
          </div>
          <div>
            <div class="text-gray-500 dark:text-gray-400">queue_depth</div>
            <div class="text-lg font-semibold tabular-nums">{{ lastTick.queue_depth || 0 }}</div>
          </div>
        </div>

        <div class="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div class="px-4 py-2 text-sm font-semibold text-gray-800 dark:text-gray-100 bg-gray-50 dark:bg-gray-800/70">
            Recent Tick History
          </div>
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">timestamp</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">generated</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">enqueued</th>
                  <th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">skipped</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!tickHistory.length">
                  <td colspan="4" class="px-3 py-4 text-center text-xs text-gray-400 dark:text-gray-500">No tick history</td>
                </tr>
                <tr v-for="row in tickHistory" :key="row.id" class="border-b border-gray-100 dark:border-gray-800">
                  <td class="px-3 py-2 text-xs font-mono text-gray-700 dark:text-gray-300">{{ row.timestamp }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.generated }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.enqueued }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ row.skipped_existing }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key
    const running = ref(false)
    const autoStart = ref(false)
    const lastTick = ref(null)
    const tickHistory = ref([])
    const poolConfigJson = ref(JSON.stringify(DEFAULT_POOL, null, 2))

    async function runTick() {
      running.value = true
      try {
        const poolConfig = _parsePoolConfig(poolConfigJson.value)
        const payload = {
          pool_config: poolConfig,
          auto_start: Boolean(autoStart.value),
        }
        const response = await postJson('/discovery/tick', payload)
        lastTick.value = response.tick || null
        if (response.tick && typeof response.tick === 'object') {
          const now = new Date()
          const entry = {
            id: String(now.getTime()) + '-' + String(Math.random()).slice(2),
            timestamp: now.toISOString(),
            generated: Number(response.tick.generated || 0),
            enqueued: Number(response.tick.enqueued || 0),
            skipped_existing: Number(response.tick.skipped_existing || 0),
          }
          tickHistory.value = [entry, ...tickHistory.value].slice(0, 5)
        }
        showToast('discovery tick completed', 'success')
      } catch (err) {
        showToast(String(err), 'error')
      } finally {
        running.value = false
      }
    }

    return {
      t,
      running,
      autoStart,
      lastTick,
      tickHistory,
      poolConfigJson,
      runTick,
    }
  },
}
