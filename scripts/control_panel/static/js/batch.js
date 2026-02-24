import { ref, onMounted, onUnmounted } from 'vue'
import { fetchJson, postJson, fetchText } from './api.js'
import { showToast, confirmAction } from './store.js'
import { L } from './i18n.js'

export const BatchTab = {
  name: 'BatchTab',
  template: `
    <div class="space-y-4 animate-fade-in">
      <div v-if="loading" class="space-y-4">
        <div class="skeleton skeleton-card h-32"></div>
        <div class="skeleton skeleton-card h-14"></div>
        <div class="skeleton skeleton-card h-72"></div>
        <div class="skeleton skeleton-card h-52"></div>
      </div>
      <template v-else>
        <div class="rounded-xl p-5 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 space-y-4">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('batch_enqueue_title', 'Enqueue Batch Job') }}</h3>
          <div class="flex flex-wrap items-end gap-3">
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('batch_job_name', 'Job Name') }}</span>
              <input v-model="form.name" type="text" :placeholder="t('batch_optional', 'optional')" class="cfg-input" />
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('batch_config_path', 'Config Path') }}</span>
              <input v-model="form.config" type="text" placeholder="artifacts/sweep_config.json" class="cfg-input w-64" />
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('batch_workflow', 'Workflow') }}</span>
              <select v-model="form.workflow" @change="onWorkflowChange" class="cfg-input">
                <option value="baseline">baseline</option>
                <option value="run">run</option>
              </select>
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('batch_mode', 'Mode') }}</span>
              <select v-model="form.mode" :disabled="form.workflow !== 'run'" class="cfg-input">
                <option value="">{{ t('batch_none', 'none') }}</option>
                <option value="combo">combo</option>
                <option value="refine">refine</option>
              </select>
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ t('batch_workers', 'Workers') }}</span>
              <input v-model.number="form.workers" type="number" min="1" :placeholder="t('batch_optional', 'optional')" class="cfg-input w-20" />
            </label>
            <button @click="enqueue" :disabled="enqueuing"
                    class="px-4 py-2 rounded-lg text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white
                           shadow-sm shadow-blue-500/25 transition-all active:scale-[0.97] disabled:opacity-50 mt-5">
              {{ enqueuing ? t('batch_enqueuing', 'Enqueuing...') : t('batch_enqueue', 'Enqueue') }}
            </button>
          </div>
        </div>

        <div class="rounded-xl p-4 border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50">
          <div class="flex flex-wrap items-center gap-3">
            <div class="flex-1 text-xs font-mono text-gray-600 dark:text-gray-300">{{ summaryText }}</div>
            <div class="flex gap-2">
              <button @click="startBatch" :disabled="batchBusy"
                      class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-all disabled:opacity-50">
                {{ t('batch_start', 'Start Batch') }}
              </button>
              <button @click="cancelBatch" :disabled="batchBusy"
                      class="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-600 hover:bg-red-700 text-white transition-all disabled:opacity-50">
                {{ t('batch_cancel', 'Cancel') }}
              </button>
              <button @click="clearQueue" :disabled="batchBusy"
                      class="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-gray-600
                             bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all disabled:opacity-50">
                {{ t('batch_clear_queue', 'Clear Queue') }}
              </button>
            </div>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="overflow-x-auto">
            <table class="data-table">
              <thead>
                <tr class="bg-gray-50 dark:bg-gray-800/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">ID</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_job_name', 'Job Name') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_workflow', 'Workflow') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_mode', 'Mode') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_workers', 'Workers') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_status', 'Status') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_config_path', 'Config Path') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_started_at', 'Started') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_finished_at', 'Finished') }}</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase border-b border-gray-200 dark:border-gray-700">{{ t('batch_actions', 'Actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!jobs.length">
                  <td colspan="10" class="px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">{{ t('datatable_no_data', 'No data') }}</td>
                </tr>
                <tr v-for="job in jobs" :key="job.id"
                    class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 font-mono">{{ job.id }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ job.name || t('batch_unnamed_job', 'unnamed') }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ job.workflow }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ job.mode || t('batch_none', 'none') }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 font-mono">{{ job.workers ?? t('batch_none', 'none') }}</td>
                  <td class="px-3 py-2">
                    <span class="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full"
                          :class="statusClass(job.status)">
                      <span class="w-1.5 h-1.5 rounded-full" :class="statusDot(job.status)"></span>
                      {{ statusLabel(job.status) }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 font-mono max-w-[200px] truncate" :title="job.config">{{ job.config }}</td>
                  <td class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">{{ fmtTime(job.started_utc) }}</td>
                  <td class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">{{ fmtTime(job.finished_utc) }}</td>
                  <td class="px-3 py-2">
                    <button v-if="canRemove(job.status)" @click="removeJob(job.id)"
                            class="px-2 py-1 rounded text-xs font-medium border border-gray-300 dark:border-gray-600
                                   bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 transition-all">
                      {{ t('batch_remove', 'Remove') }}
                    </button>
                    <button v-else-if="canCancel(job.status)" @click="cancelBatch"
                            class="px-2 py-1 rounded text-xs font-medium bg-red-600 hover:bg-red-700 text-white transition-all">
                      {{ t('batch_cancel', 'Cancel') }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="rounded-xl border bg-white dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 overflow-hidden">
          <div class="px-4 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <span class="text-xs font-semibold text-gray-600 dark:text-gray-300">{{ t('batch_log_title', 'Batch Log') }}</span>
          </div>
          <div class="log-panel p-3 bg-gray-950 text-gray-300 text-xs">{{ logText || t('batch_log_empty', 'No log yet...') }}</div>
        </div>
      </template>
    </div>
  `,
  setup() {
    const t = (key, fallback = '') => L[key] || fallback || key

    const loading = ref(true)
    const form = ref({
      name: '',
      config: 'artifacts/sweep_config.json',
      workflow: 'baseline',
      mode: '',
      workers: null,
    })
    const enqueuing = ref(false)
    const batchBusy = ref(false)
    const jobs = ref([])
    const summaryText = ref('status=idle')
    const logText = ref('')
    let pollTimer = null

    function fmtTime(raw) {
      if (!raw) return '--'
      const d = Date.parse(raw)
      return Number.isNaN(d) ? String(raw) : new Date(d).toLocaleString()
    }

    function statusClass(status) {
      if (['running', 'submitted'].includes(status)) return 'bg-blue-500/15 text-blue-400'
      if (status === 'done') return 'bg-emerald-500/15 text-emerald-400'
      if (status === 'failed') return 'bg-red-500/15 text-red-400'
      if (status === 'queued') return 'bg-amber-500/15 text-amber-400'
      return 'bg-gray-500/15 text-gray-400'
    }

    function statusDot(status) {
      if (['running', 'submitted'].includes(status)) return 'bg-blue-400 animate-pulse'
      if (status === 'done') return 'bg-emerald-400'
      if (status === 'failed') return 'bg-red-400'
      if (status === 'queued') return 'bg-amber-400'
      return 'bg-gray-400'
    }

    function statusLabel(status) {
      const stage = String(status || '').trim().toLowerCase()
      if (stage === 'running') return t('status_running', 'Running')
      if (stage === 'submitted') return t('status_submitted', 'Submitted')
      if (stage === 'done') return t('status_done', 'Done')
      if (stage === 'failed') return t('status_failed', 'Failed')
      if (stage === 'queued') return t('status_queued', 'Queued')
      if (stage === 'cancelled') return t('status_cancelled', 'Cancelled')
      if (stage === 'skipped_seen_key') return t('status_skipped_seen_key', 'Skipped')
      return t('status_idle', 'Idle')
    }

    function canRemove(status) {
      return ['queued', 'done', 'failed', 'cancelled', 'skipped_seen_key'].includes(status)
    }

    function canCancel(status) {
      return ['submitted', 'running'].includes(status)
    }

    function onWorkflowChange() {
      if (form.value.workflow !== 'run') {
        form.value.mode = ''
      }
    }

    async function refreshQueue() {
      try {
        const payload = await fetchJson('/batch/queue.json')
        jobs.value = payload.jobs || []
        const summary = payload.summary || {}
        const run = payload.running ? 'running' : 'idle'
        summaryText.value = `${t('batch_summary_status', 'status')}=${run} | ` +
          `${t('batch_summary_total', 'total')}=${summary.total || 0} ` +
          `${t('batch_summary_queued', 'queued')}=${summary.queued || 0} ` +
          `${t('batch_summary_active', 'active')}=${(summary.running || 0) + (summary.submitted || 0)} ` +
          `${t('batch_summary_done', 'done')}=${summary.done || 0} ` +
          `${t('batch_summary_failed', 'failed')}=${summary.failed || 0} ` +
          `${t('batch_summary_skipped', 'skipped')}=${summary.skipped_seen_key || 0} ` +
          `${t('batch_summary_cancelled', 'cancelled')}=${summary.cancelled || 0}`
        const logResponse = await fetchText('/batch/log-tail.txt').catch(() => '')
        logText.value = logResponse
      } catch (_) {
        // no-op
      } finally {
        loading.value = false
      }
    }

    async function enqueue() {
      enqueuing.value = true
      try {
        const payload = { name: form.value.name, config: form.value.config, workflow: form.value.workflow }
        if (form.value.workflow === 'run' && form.value.mode) payload.mode = form.value.mode
        if (form.value.workers) payload.workers = form.value.workers
        await postJson('/batch/enqueue', payload)
        showToast(t('batch_toast_enqueued', 'Batch job enqueued'), 'success')
        refreshQueue()
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        enqueuing.value = false
      }
    }

    async function startBatch() {
      const confirmed = await confirmAction({
        title: t('batch_confirm_start_title', 'Start batch jobs?'),
        message: t('batch_confirm_start_message', 'This will run queued jobs in order.'),
        confirmText: t('batch_start', 'Start Batch'),
        variant: 'primary',
      })
      if (!confirmed) return
      batchBusy.value = true
      try {
        await postJson('/batch/start')
        showToast(t('batch_toast_started', 'Batch started'), 'success')
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        batchBusy.value = false
        refreshQueue()
      }
    }

    async function cancelBatch() {
      const confirmed = await confirmAction({
        title: t('batch_confirm_cancel_title', 'Cancel running batch?'),
        message: t('batch_confirm_cancel_message', 'Active jobs will be terminated.'),
        confirmText: t('batch_cancel', 'Cancel'),
        variant: 'warn',
      })
      if (!confirmed) return
      batchBusy.value = true
      try {
        await postJson('/batch/cancel')
        showToast(t('batch_toast_cancelled', 'Cancel requested'), 'warn')
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        batchBusy.value = false
        refreshQueue()
      }
    }

    async function clearQueue() {
      const confirmed = await confirmAction({
        title: t('batch_confirm_clear_title', 'Clear queue?'),
        message: t('batch_confirm_clear_message', 'All queued jobs will be removed.'),
        confirmText: t('batch_clear_queue', 'Clear Queue'),
        variant: 'danger',
      })
      if (!confirmed) return
      batchBusy.value = true
      try {
        await postJson('/batch/clear')
        showToast(t('batch_toast_cleared', 'Queue cleared'), 'success')
      } catch (e) {
        showToast(String(e), 'error')
      } finally {
        batchBusy.value = false
        refreshQueue()
      }
    }

    async function removeJob(id) {
      const confirmed = await confirmAction({
        title: t('batch_confirm_remove_title', 'Remove this job?'),
        message: t('batch_confirm_remove_message', 'This will remove job') + ' #' + id + '.',
        confirmText: t('batch_remove', 'Remove'),
        variant: 'danger',
      })
      if (!confirmed) return
      try {
        await postJson('/batch/remove', { job_id: id })
        showToast(t('batch_toast_removed', 'Job removed'), 'success')
        refreshQueue()
      } catch (e) {
        showToast(String(e), 'error')
      }
    }

    onMounted(() => {
      refreshQueue()
      pollTimer = setInterval(refreshQueue, 4000)
    })

    onUnmounted(() => {
      clearInterval(pollTimer)
    })

    return {
      loading,
      form,
      enqueuing,
      batchBusy,
      jobs,
      summaryText,
      logText,
      fmtTime,
      statusClass,
      statusDot,
      statusLabel,
      canRemove,
      canCancel,
      onWorkflowChange,
      enqueue,
      startBatch,
      cancelBatch,
      clearQueue,
      removeJob,
      t,
    }
  },
}
