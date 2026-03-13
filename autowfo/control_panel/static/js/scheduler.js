import { ref, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson } from './api.js'
import { confirmAction, showToast } from './store.js'
import { L } from './i18n.js'

export const SchedulerTab = {
  name: 'SchedulerTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ t('scheduler_title', 'Scheduler') }}</h2>
          <action-button @click="refreshStatus" variant="secondary"
                  :label="t('scheduler_refresh', 'Refresh')">
          </action-button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-gray-500 dark:text-gray-400">queue_depth</div>
            <div class="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-100">{{ status.queue_depth || 0 }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-gray-500 dark:text-gray-400">is_running</div>
            <div class="text-lg font-semibold tabular-nums" :class="status.is_running ? 'text-blue-500' : 'text-gray-900 dark:text-gray-100'">
              {{ status.is_running ? 'true' : 'false' }}
            </div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-gray-500 dark:text-gray-400">next_experiment_id</div>
            <div class="text-sm font-mono text-gray-900 dark:text-gray-100 break-all">{{ status.next_experiment_id || '--' }}</div>
          </div>
          <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <div class="text-gray-500 dark:text-gray-400">last_error</div>
            <div class="text-xs font-mono break-all" :class="status.last_error ? 'text-red-500' : 'text-gray-900 dark:text-gray-100'">
              {{ status.last_error || '--' }}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">experiment_id</span>
            <input v-model.trim="form.experimentId" type="text" class="cfg-input" placeholder="exp_demo" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-500 dark:text-gray-400">priority</span>
            <select v-model="form.priority" class="cfg-input">
              <option value="user_submitted">user_submitted</option>
              <option value="discovery">discovery</option>
              <option value="refine">refine</option>
            </select>
          </label>
          <label class="inline-flex items-center gap-2 mb-2">
            <input type="checkbox" v-model="form.autoStart" class="rounded text-blue-600" />
            <span class="text-xs text-gray-600 dark:text-gray-400">auto_start_worker</span>
          </label>
          <action-button @click="enqueueExperiment" :loading="enqueuing" variant="primary"
                         :label="t('scheduler_enqueue', 'Enqueue')">
          </action-button>
        </div>

        <div class="flex flex-wrap gap-2">
          <action-button @click="startWorker" :loading="workingControl" variant="primary"
                         :label="t('scheduler_start_worker', 'Start Worker')">
          </action-button>
          <action-button @click="stopWorker" :loading="workingControl" variant="secondary"
                         :label="t('scheduler_stop_worker', 'Stop Worker')">
          </action-button>
        </div>
      </div>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key
    const status = ref({})
    const enqueuing = ref(false)
    const workingControl = ref(false)
    const form = ref({
      experimentId: '',
      priority: 'user_submitted',
      autoStart: true,
    })
    let timer = null

    async function refreshStatus() {
      try {
        status.value = await fetchJson('/scheduler/status.json')
      } catch (err) {
        showToast(String(err), 'error')
      }
    }

    async function _loadExperimentConfig(experimentId) {
      return fetchJson(`/experiments/${encodeURIComponent(experimentId)}/config.json`)
    }

    async function enqueueExperiment() {
      const experimentId = String(form.value.experimentId || '').trim()
      if (!experimentId) {
        showToast('experiment_id is required', 'warn')
        return
      }
      enqueuing.value = true
      try {
        const config = await _loadExperimentConfig(experimentId)
        const payload = {
          experiment_config: config,
          priority: String(form.value.priority || 'user_submitted'),
          auto_start: Boolean(form.value.autoStart),
        }
        const res = await postJson('/experiments/queue', payload)
        if (res.queued) {
          showToast(`queued: ${experimentId}`, 'success')
        } else {
          showToast(`already queued: ${experimentId}`, 'warn')
        }
        await refreshStatus()
      } catch (err) {
        const statusCode = Number(err?.status || 0)
        if (statusCode === 404) {
          showToast(`experiment not found: ${experimentId}`, 'warn')
        } else {
          showToast(String(err), 'error')
        }
      } finally {
        enqueuing.value = false
      }
    }

    async function startWorker() {
      const nextId = String(status.value.next_experiment_id || '').trim()
      if (!nextId) {
        showToast('queue is empty', 'warn')
        return
      }
      workingControl.value = true
      try {
        const config = await _loadExperimentConfig(nextId)
        const payload = {
          experiment_config: config,
          priority: 'discovery',
          auto_start: true,
        }
        await postJson('/experiments/queue', payload)
        showToast('worker start triggered', 'success')
        await refreshStatus()
      } catch (err) {
        showToast(String(err), 'error')
      } finally {
        workingControl.value = false
      }
    }

    async function stopWorker() {
      const ok = await confirmAction({
        title: 'Stop scheduler worker?',
        message: 'This will request graceful stop before next queued experiment.',
        confirmText: 'Confirm',
        variant: 'warn',
      })
      if (!ok) return
      workingControl.value = true
      try {
        const res = await postJson('/scheduler/stop', {})
        if (res.ok && res.stopped) {
          showToast('worker stopped', 'success')
        } else {
          showToast('worker stop requested', 'warn')
        }
        await refreshStatus()
      } catch (err) {
        showToast(String(err), 'error')
      } finally {
        workingControl.value = false
      }
    }

    onMounted(() => {
      refreshStatus()
      timer = setInterval(refreshStatus, 4000)
    })
    onUnmounted(() => {
      clearInterval(timer)
    })

    return {
      t,
      status,
      form,
      enqueuing,
      workingControl,
      refreshStatus,
      enqueueExperiment,
      startWorker,
      stopWorker,
    }
  },
}
