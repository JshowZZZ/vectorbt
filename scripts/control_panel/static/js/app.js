// ─── Main App Entry Point ───
import { createApp, ref, computed, onMounted } from 'vue'
import { store, setTheme, toggleTheme } from './store.js'
import { OverviewTab } from './overview.js'
import { ConfigTab } from './config.js'
import { ResultsTab } from './results.js'
import { BatchTab } from './batch.js'
import { CoverageTab } from './coverage.js'
import { DashboardTab } from './dashboard.js'
import { ToastContainer, ConfirmModal, ErrorBoundary, DataTable, DetailPanel } from './components.js'
import { L } from './i18n.js'

const TABS = [
  { id: 'overview',  icon: '📊', labelKey: 'app_tab_overview', fallback: '總覽' },
  { id: 'config',    icon: '⚙️', labelKey: 'app_tab_config', fallback: '設定' },
  { id: 'results',   icon: '📋', labelKey: 'app_tab_results', fallback: '結果' },
  { id: 'batch',     icon: '🚀', labelKey: 'app_tab_batch', fallback: '批次' },
  { id: 'coverage',  icon: '🗺️', labelKey: 'app_tab_coverage', fallback: '覆蓋' },
  { id: 'dashboard', icon: '📈', labelKey: 'app_tab_dashboard', fallback: '分析' },
]

const App = {
  template: `
    <!-- Outer wrapper: full-screen flex column -->
    <div class="min-h-screen flex flex-col bg-gray-50 dark:bg-[#0d1117] text-gray-900 dark:text-gray-100 transition-colors">

      <!-- Top Navbar -->
      <header class="sticky top-0 z-40 flex items-center h-12 px-4 gap-4
                      bg-white/80 dark:bg-[#161b22]/90 backdrop-blur-md
                      border-b border-gray-200 dark:border-gray-700/60 shadow-sm">
        <div class="font-bold tracking-tight text-sm whitespace-nowrap select-none">
          <span class="text-blue-500">AUTOWFO</span>
          <span class="text-gray-400 ml-1 font-normal text-xs">Control Panel</span>
        </div>
        <nav class="flex items-center gap-1 flex-1 overflow-x-auto ml-4">
          <button v-for="tab in tabs" :key="tab.id"
                  @click="store.activeTab = tab.id"
                  class="relative px-3 py-1.5 text-xs font-medium rounded-lg transition-all whitespace-nowrap"
                  :class="store.activeTab === tab.id
                    ? 'bg-blue-600/15 text-blue-500 dark:text-blue-400'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'">
            <span class="mr-1">{{ tab.icon }}</span>{{ tab.label }}
            <span v-if="store.activeTab === tab.id"
                  class="absolute bottom-0 left-1/2 -translate-x-1/2 w-5 h-0.5 bg-blue-500 rounded-full"></span>
          </button>
        </nav>
        <div class="flex items-center gap-2 ml-auto">
          <a href="/report" target="_blank"
             class="text-xs text-blue-500 hover:text-blue-400 font-medium transition-colors hidden sm:block">{{ t('app_report_link', '報告 ↗') }}</a>
          <button @click="toggleTheme()"
                  class="w-8 h-8 rounded-lg flex items-center justify-center
                         hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  :title="store.theme === 'dark' ? t('app_theme_light', '切換淺色') : t('app_theme_dark', '切換深色')">
            {{ store.theme === 'dark' ? '☀️' : '🌙' }}
          </button>
        </div>
      </header>

      <!-- Tab Content -->
      <main class="flex-1 w-full max-w-[1600px] mx-auto px-4 py-5">
        <error-boundary :key="'tab-' + store.activeTab" :tab-id="store.activeTab">
          <component :is="activeComponent" :key="'tab-component-' + store.activeTab" />
        </error-boundary>
      </main>

      <!-- Footer -->
      <footer class="text-center text-[10px] text-gray-400 dark:text-gray-600 py-2 border-t border-gray-200 dark:border-gray-800">
        AUTOWFO Control Panel · vectorbt · Phase 15 UI
      </footer>

      <!-- Toasts -->
      <confirm-modal />
      <toast-container />
    </div>
  `,
  setup() {
    window._AUTOWFO_L = L

    const t = (key, fallback = '') => L[key] || fallback || key
    const tabs = TABS.map(tab => ({
      ...tab,
      label: t(tab.labelKey, tab.fallback),
    }))

    const tabComponents = {
      overview: OverviewTab,
      config: ConfigTab,
      results: ResultsTab,
      batch: BatchTab,
      coverage: CoverageTab,
      dashboard: DashboardTab,
    }

    const activeComponent = computed(() => tabComponents[store.activeTab] || OverviewTab)

    onMounted(() => {
      setTheme(store.theme)
    })

    return { store, tabs, toggleTheme, activeComponent, t }
  }
}

const app = createApp(App)

// Register components globally
app.component('overview-tab', OverviewTab)
app.component('config-tab', ConfigTab)
app.component('results-tab', ResultsTab)
app.component('batch-tab', BatchTab)
app.component('coverage-tab', CoverageTab)
app.component('dashboard-tab', DashboardTab)
app.component('error-boundary', ErrorBoundary)
app.component('toast-container', ToastContainer)
app.component('confirm-modal', ConfirmModal)
app.component('data-table', DataTable)
app.component('detail-panel', DetailPanel)

app.mount('#app')
