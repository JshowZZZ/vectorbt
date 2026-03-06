import { createApp, computed, onMounted, ref } from 'vue'
import { store, setTheme, toggleTheme } from './store.js'
import { OverviewTab } from './overview.js'
import { ConfigTab } from './config.js'
import { ResultsTab } from './results.js'
import { BatchTab } from './batch.js'
import { CoverageTab } from './coverage.js'
import { DashboardTab } from './dashboard.js'
import { ExperimentsTab } from './experiments.js'
import { SchedulerTab } from './scheduler.js'
import { DiscoveryTab } from './discovery.js'
import { AnalyticsTab } from './analytics.js'
import {
  ToastContainer,
  ConfirmModal,
  ErrorBoundary,
  DataTable,
  DetailPanel,
  ActionButton,
  KpiCard,
} from './components.js'
import { L } from './i18n.js'

const TAB_META = {
  overview: {
    labelKey: 'app_tab_overview',
    fallback: '總覽',
    icon: '◉',
    description: '先看系統狀態、下一步動作與目前進度。',
  },
  dashboard: {
    labelKey: 'app_tab_dashboard',
    fallback: '儀表板',
    icon: '▣',
    description: '查看跨執行報表、排行榜與最近端點錯誤。',
  },
  experiments: {
    labelKey: 'app_tab_experiments',
    fallback: '實驗',
    icon: '⌘',
    description: '建立、排隊與追蹤策略實驗生命週期。',
  },
  discovery: {
    labelKey: 'app_tab_discovery',
    fallback: '探索',
    icon: '✦',
    description: '管理探索候選池與發現流程。',
  },
  config: {
    labelKey: 'app_tab_config',
    fallback: '設定',
    icon: '⚙',
    description: '調整回測參數、資料視窗與 guardrails。',
  },
  batch: {
    labelKey: 'app_tab_batch',
    fallback: '批次',
    icon: '▤',
    description: '檢視批次佇列、執行狀態與批次紀錄。',
  },
  coverage: {
    labelKey: 'app_tab_coverage',
    fallback: '覆蓋率',
    icon: '▦',
    description: '找出尚未測到的區塊與覆蓋缺口。',
  },
  scheduler: {
    labelKey: 'app_tab_scheduler',
    fallback: '排程',
    icon: '⏱',
    description: '觀察排程器、佇列深度與執行節奏。',
  },
  results: {
    labelKey: 'app_tab_results',
    fallback: '結果',
    icon: '◨',
    description: '篩選、比較與導出表現最佳的結果。',
  },
  analytics: {
    labelKey: 'app_tab_analytics',
    fallback: '分析',
    icon: '✳',
    description: '查看排行榜、覆蓋熱點與成長趨勢。',
  },
}

const SIDEBAR_GROUPS = [
  {
    id: 'monitoring',
    labelKey: 'app_group_monitoring',
    fallback: '監控大廳',
    tabs: ['overview', 'dashboard'],
  },
  {
    id: 'strategy',
    labelKey: 'app_group_strategy',
    fallback: '策略與探索',
    tabs: ['experiments', 'discovery'],
  },
  {
    id: 'execution',
    labelKey: 'app_group_execution',
    fallback: '執行與排程',
    tabs: ['config', 'batch', 'coverage', 'scheduler'],
  },
  {
    id: 'analytics',
    labelKey: 'app_group_analytics',
    fallback: '分析與報告',
    tabs: ['results', 'analytics'],
  },
]

const PRIMARY_TABS = ['overview', 'config', 'results', 'analytics']

const TAB_COMPONENTS = {
  overview: OverviewTab,
  config: ConfigTab,
  results: ResultsTab,
  batch: BatchTab,
  coverage: CoverageTab,
  dashboard: DashboardTab,
  experiments: ExperimentsTab,
  scheduler: SchedulerTab,
  analytics: AnalyticsTab,
  discovery: DiscoveryTab,
}

const App = {
  template: `
    <div class="cp-app-shell min-h-screen flex text-gray-900 dark:text-gray-100 transition-colors overflow-hidden font-sans">
      <div class="cp-app-backdrop" aria-hidden="true"></div>

      <transition name="fade">
        <div v-if="mobileSidebarOpen"
             class="fixed inset-0 bg-slate-950/45 z-40 md:hidden backdrop-blur-sm"
             @click="mobileSidebarOpen = false"></div>
      </transition>

      <aside :class="[
          'cp-sidebar fixed md:relative top-0 h-full z-50 flex flex-col transition-all duration-300 flex-shrink-0',
          sidebarExpanded ? 'w-72' : 'w-20',
          mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        ]">
        <div class="cp-sidebar-brand flex items-center justify-between px-4 py-4 flex-shrink-0">
          <button class="flex items-center gap-3 min-w-0 text-left" @click="selectTab('overview')">
            <span class="cp-brand-mark">A</span>
            <span v-show="sidebarExpanded" class="min-w-0">
              <span class="block text-sm font-semibold tracking-[0.18em] uppercase text-slate-500 dark:text-slate-400">AUTOWFO</span>
              <span class="block text-base font-semibold text-slate-950 dark:text-white truncate">Control Panel</span>
            </span>
          </button>
          <button @click="mobileSidebarOpen = false"
                  class="md:hidden inline-flex items-center justify-center h-9 w-9 rounded-xl text-slate-500 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors"
                  aria-label="Close menu">
            ✕
          </button>
        </div>

        <div v-show="sidebarExpanded" class="mx-3 mb-3 rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white/85 dark:bg-slate-900/75 px-4 py-4 shadow-sm">
          <div class="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Operator Flow</div>
          <div class="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{{ currentTabTitle }}</div>
          <p class="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">{{ currentTabMeta.description }}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button v-for="tabId in primaryTabs"
                    :key="'intro-' + tabId"
                    @click="selectTab(tabId)"
                    class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors"
                    :class="store.activeTab === tabId
                      ? 'border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-200'
                      : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-500'">
              <span>{{ tabMeta[tabId].icon }}</span>
              <span>{{ tabTitle(tabId) }}</span>
            </button>
          </div>
        </div>

        <nav class="flex-1 overflow-y-auto px-3 pb-4 scrollbar-hide space-y-5">
          <div v-for="group in groups" :key="group.id" class="cp-sidebar-group">
            <div v-show="sidebarExpanded"
                 class="px-3 mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
              {{ t(group.labelKey, group.fallback) }}
            </div>

            <button v-for="tabId in group.tabs"
                    :key="tabId"
                    @click="selectTab(tabId)"
                    :title="!sidebarExpanded ? tabTitle(tabId) : ''"
                    :class="[
                      'cp-sidebar-item w-full flex items-center gap-3 rounded-2xl px-3 py-3 text-left transition-all duration-200',
                      store.activeTab === tabId
                        ? 'cp-sidebar-item-active'
                        : 'text-slate-600 dark:text-slate-300 hover:bg-white/70 dark:hover:bg-slate-900/75 hover:text-slate-950 dark:hover:text-white'
                    ]">
              <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100/90 text-lg text-slate-700 shadow-sm dark:bg-slate-800/90 dark:text-slate-200">
                {{ tabMeta[tabId].icon }}
              </span>
              <span v-show="sidebarExpanded" class="min-w-0 flex-1">
                <span class="block text-sm font-semibold truncate">{{ tabTitle(tabId) }}</span>
                <span class="block text-[11px] leading-5 text-slate-500 dark:text-slate-400 truncate">
                  {{ tabMeta[tabId].description }}
                </span>
              </span>
              <span v-if="sidebarExpanded && store.activeTab === tabId"
                    class="inline-flex items-center rounded-full bg-blue-500/12 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-700 dark:text-blue-200">
                目前
              </span>
            </button>
          </div>
        </nav>

        <div class="mt-auto border-t border-slate-200/80 dark:border-slate-800/80 p-3 flex flex-col gap-2 flex-shrink-0">
          <button @click="toggleTheme()"
                  class="inline-flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-white/70 dark:hover:bg-slate-900/75 transition-colors">
            <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100/90 text-lg text-slate-700 shadow-sm dark:bg-slate-800/90 dark:text-slate-200">
              {{ store.theme === 'dark' ? '☾' : '☼' }}
            </span>
            <span v-show="sidebarExpanded">{{ store.theme === 'dark' ? '切換到淺色模式' : '切換到深色模式' }}</span>
          </button>

          <button @click="toggleSidebar()"
                  class="hidden md:inline-flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-white/70 dark:hover:bg-slate-900/75 transition-colors">
            <span class="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100/90 text-sm text-slate-700 shadow-sm dark:bg-slate-800/90 dark:text-slate-200">
              {{ sidebarExpanded ? '←' : '→' }}
            </span>
            <span v-show="sidebarExpanded">{{ sidebarExpanded ? '收合側欄' : '展開側欄' }}</span>
          </button>
        </div>
      </aside>

      <div class="cp-shell-main flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <header class="cp-shell-header flex-shrink-0 px-4 py-4 md:px-6 md:py-5">
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-start gap-3 min-w-0">
              <button @click="mobileSidebarOpen = true"
                      class="md:hidden mt-1 inline-flex items-center justify-center h-10 w-10 rounded-2xl border border-slate-200/80 bg-white/80 text-slate-600 shadow-sm dark:border-slate-700/80 dark:bg-slate-900/70 dark:text-slate-300">
                ☰
              </button>
              <div class="min-w-0">
                <div class="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">AUTOWFO Operator Console</div>
                <div class="mt-2 flex items-start gap-3 min-w-0">
                  <span class="mt-0.5 text-2xl">{{ currentTabMeta.icon }}</span>
                  <div class="min-w-0">
                    <h1 class="text-2xl md:text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">{{ currentTabTitle }}</h1>
                    <p class="mt-1 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">{{ currentTabMeta.description }}</p>
                  </div>
                </div>
              </div>
            </div>

            <div class="hidden lg:flex items-center gap-3">
              <div class="rounded-full border border-slate-200/80 bg-white/80 px-3 py-2 text-xs text-slate-600 shadow-sm dark:border-slate-700/80 dark:bg-slate-900/70 dark:text-slate-300">
                建議流程：設定 → 實驗 → 結果 → 分析
              </div>
              <a href="/report"
                 target="_blank"
                 class="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3.5 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-900/30">
                <span>查看報告</span>
                <span>↗</span>
              </a>
            </div>
          </div>

          <div class="cp-main-stage mt-4 flex flex-wrap items-center gap-2">
            <button v-for="tabId in primaryTabs"
                    :key="'quick-' + tabId"
                    @click="selectTab(tabId)"
                    class="cp-quick-nav inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-all"
                    :class="store.activeTab === tabId
                      ? 'bg-slate-950 text-white shadow-sm dark:bg-white dark:text-slate-950'
                      : 'bg-white/80 text-slate-600 hover:text-slate-950 hover:bg-white shadow-sm dark:bg-slate-900/75 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-white'">
              <span>{{ tabMeta[tabId].icon }}</span>
              <span>{{ tabTitle(tabId) }}</span>
            </button>
          </div>
        </header>

        <main class="flex-1 overflow-y-auto px-4 pb-8 md:px-6 md:pb-10 scrollbar-hide">
          <div class="w-full max-w-7xl mx-auto">
            <error-boundary :key="'tab-' + store.activeTab" :tab-id="store.activeTab">
              <transition name="tab-transition" mode="out-in">
                <component :is="activeComponent" :key="'tab-component-' + store.activeTab" />
              </transition>
            </error-boundary>
          </div>
        </main>
      </div>

      <confirm-modal />
      <toast-container />
    </div>
  `,
  setup() {
    window._AUTOWFO_L = L
    const t = (key, fallback = '') => L[key] || fallback || key
    const sidebarExpanded = ref(true)
    const mobileSidebarOpen = ref(false)

    onMounted(() => {
      const stored = localStorage.getItem('autowfo-sidebar-collapsed')
      if (stored === 'true') {
        sidebarExpanded.value = false
      }
      setTheme(store.theme)
    })

    const selectTab = tabId => {
      store.activeTab = tabId
      mobileSidebarOpen.value = false
    }

    const toggleSidebar = () => {
      sidebarExpanded.value = !sidebarExpanded.value
      localStorage.setItem('autowfo-sidebar-collapsed', (!sidebarExpanded.value).toString())
    }

    const groups = SIDEBAR_GROUPS
    const tabMeta = TAB_META
    const primaryTabs = PRIMARY_TABS

    const tabTitle = tabId => {
      const meta = TAB_META[tabId]
      if (!meta) return tabId
      return t(meta.labelKey, meta.fallback)
    }

    const currentTabMeta = computed(() => TAB_META[store.activeTab] || TAB_META.overview)
    const currentTabTitle = computed(() => tabTitle(store.activeTab))
    const activeComponent = computed(() => TAB_COMPONENTS[store.activeTab] || OverviewTab)

    return {
      activeComponent,
      currentTabMeta,
      currentTabTitle,
      groups,
      mobileSidebarOpen,
      primaryTabs,
      selectTab,
      sidebarExpanded,
      store,
      tabMeta,
      tabTitle,
      t,
      toggleSidebar,
      toggleTheme,
    }
  },
}

const app = createApp(App)
app.component('overview-tab', OverviewTab)
app.component('config-tab', ConfigTab)
app.component('results-tab', ResultsTab)
app.component('batch-tab', BatchTab)
app.component('coverage-tab', CoverageTab)
app.component('dashboard-tab', DashboardTab)
app.component('experiments-tab', ExperimentsTab)
app.component('scheduler-tab', SchedulerTab)
app.component('analytics-tab', AnalyticsTab)
app.component('discovery-tab', DiscoveryTab)
app.component('error-boundary', ErrorBoundary)
app.component('toast-container', ToastContainer)
app.component('confirm-modal', ConfirmModal)
app.component('data-table', DataTable)
app.component('detail-panel', DetailPanel)
app.component('action-button', ActionButton)
app.component('kpi-card', KpiCard)
app.mount('#app')
