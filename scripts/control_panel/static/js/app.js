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
import { ToastContainer, ConfirmModal, ErrorBoundary, DataTable, DetailPanel, ActionButton } from './components.js'
import { L } from './i18n.js'

const SIDEBAR_GROUPS = [
  {
    id: 'monitoring',
    labelKey: 'app_group_monitoring',
    fallback: '監控大廳',
    icon: '📊',
    tabs: [
      { id: 'overview', labelKey: 'app_tab_overview', fallback: '總覽' },
      { id: 'dashboard', labelKey: 'app_tab_dashboard', fallback: '儀表板' }
    ]
  },
  {
    id: 'strategy',
    labelKey: 'app_group_strategy',
    fallback: '策略與探索',
    icon: '🔬',
    tabs: [
      { id: 'experiments', labelKey: 'app_tab_experiments', fallback: '實驗' },
      { id: 'discovery', labelKey: 'app_tab_discovery', fallback: '探索' }
    ]
  },
  {
    id: 'execution',
    labelKey: 'app_group_execution',
    fallback: '執行與排程',
    icon: '⚡',
    tabs: [
      { id: 'config', labelKey: 'app_tab_config', fallback: '設定' },
      { id: 'batch', labelKey: 'app_tab_batch', fallback: '批次' },
      { id: 'coverage', labelKey: 'app_tab_coverage', fallback: '覆蓋率' },
      { id: 'scheduler', labelKey: 'app_tab_scheduler', fallback: '排程' }
    ]
  },
  {
    id: 'analytics',
    labelKey: 'app_group_analytics',
    fallback: '分析與報告',
    icon: '📈',
    tabs: [
      { id: 'results', labelKey: 'app_tab_results', fallback: '結果' },
      { id: 'analytics', labelKey: 'app_tab_analytics', fallback: '分析' }
    ]
  }
]

const App = {
  template: `
    <div class="min-h-screen flex bg-gray-50 dark:bg-[#0A0F1C] text-gray-900 dark:text-gray-100 transition-colors overflow-hidden font-sans">
      <!-- Mobile Overlay Backdrop -->
      <transition name="fade">
        <div v-if="mobileSidebarOpen"
             class="fixed inset-0 bg-black/50 z-40 md:hidden backdrop-blur-sm"
             @click="mobileSidebarOpen = false"></div>
      </transition>
           
      <!-- Sidebar -->
      <aside :class="[
          'sidebar fixed md:relative top-0 h-full z-50 flex flex-col bg-white dark:bg-[#0d1117] border-r border-gray-200 dark:border-gray-800 transition-all duration-300 shadow-sm flex-shrink-0',
          sidebarExpanded ? 'w-56' : 'w-14',
          mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        ]">
        <!-- Logo Area -->
        <div class="h-12 flex items-center justify-between px-3 border-b border-gray-200/50 dark:border-gray-800/50 flex-shrink-0">
          <div class="flex items-center gap-2 overflow-hidden cursor-pointer" @click="selectTab('overview')">
            <div class="w-8 h-8 rounded-lg bg-blue-600/10 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold flex-shrink-0">A</div>
            <div v-show="sidebarExpanded" class="whitespace-nowrap font-bold tracking-tight text-blue-900 dark:text-blue-100">AUTOWFO</div>
          </div>
          <button @click="mobileSidebarOpen = false" class="md:hidden p-1.5 text-gray-400 hover:text-gray-900 dark:hover:text-white rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
            ✕
          </button>
        </div>
        
        <!-- Navigation Groups -->
        <nav class="flex-1 overflow-y-auto py-3 scrollbar-hide space-y-4 px-2">
          <div v-for="group in groups" :key="group.id" class="sidebar-group">
            <div v-show="sidebarExpanded" class="px-2 mb-1.5 text-[10px] font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider sidebar-group-header">
              {{ t(group.labelKey, group.fallback) }}
            </div>
            
            <button
              v-for="tab in group.tabs"
              :key="tab.id"
              @click="selectTab(tab.id)"
              :class="[
                'w-full flex items-center gap-3 px-2 py-2 mb-0.5 rounded-lg transition-all duration-200 sidebar-item group relative',
                store.activeTab === tab.id 
                  ? 'sidebar-item-active bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium' 
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white'
              ]"
              :title="!sidebarExpanded ? t(tab.labelKey, tab.fallback) : ''"
            >
              <span class="text-base opacity-80 group-hover:opacity-100 transition-opacity w-5 text-center flex-shrink-0" :class="store.activeTab === tab.id ? 'opacity-100' : ''">
                {{ !sidebarExpanded || (store.activeTab !== tab.id && tab.id !== 'dashboard' && tab.id !== 'config') ? group.icon : '·' }}
              </span>
              <span v-show="sidebarExpanded" class="text-sm whitespace-nowrap">{{ t(tab.labelKey, tab.fallback) }}</span>
              <!-- Active Indicator Line -->
              <span v-if="store.activeTab === tab.id" class="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r-full bg-blue-500"></span>
            </button>
          </div>
        </nav>
        
        <!-- Sidebar Footer -->
        <div class="mt-auto p-2 border-t border-gray-200/50 dark:border-gray-800/50 flex flex-col gap-1.5 flex-shrink-0">
          <button @click="toggleTheme()" class="w-full flex items-center gap-3 px-2 py-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" :title="sidebarExpanded ? '' : '切換主題'">
            <span class="text-base w-5 text-center flex-shrink-0 opacity-80">{{ store.theme === 'dark' ? '🌙' : '☀️' }}</span>
            <span v-show="sidebarExpanded" class="text-sm">{{ store.theme === 'dark' ? '深色模式' : '淺色模式' }}</span>
          </button>
          
          <button @click="toggleSidebar()" class="w-full hidden md:flex items-center gap-3 px-2 py-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" :title="sidebarExpanded ? '收合側邊欄' : '展開側邊欄'">
            <span class="text-xs w-5 text-center flex-shrink-0 opacity-50">{{ sidebarExpanded ? '◀' : '▶' }}</span>
            <span v-show="sidebarExpanded" class="text-sm">收合選單</span>
          </button>
        </div>
      </aside>

      <!-- Main Content Area -->
      <div class="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-gray-50/50 dark:bg-[#0A0F1C]">
        <!-- Top Header for Mobile & Actions -->
        <header class="h-12 flex items-center justify-between px-4 md:px-6 bg-white/80 dark:bg-[#0A0F1C]/80 backdrop-blur-md border-b border-gray-200/80 dark:border-gray-800/80 flex-shrink-0 z-10 transition-colors">
          <div class="flex items-center gap-3">
            <button @click="mobileSidebarOpen = true" class="md:hidden p-1.5 -ml-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
            </button>
            <h1 class="font-bold text-lg text-gray-800 dark:text-gray-100 tracking-tight">
              {{ currentTabTitle }}
            </h1>
          </div>
          <div class="flex items-center gap-3">
             <a href="/report" target="_blank" class="text-xs text-blue-500 hover:text-blue-600 dark:hover:text-blue-400 font-medium transition-colors hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-blue-200 dark:border-blue-900 border-opacity-50 hover:bg-blue-50 dark:hover:bg-blue-900/30">
               {{ t('app_report_link', 'Report') }}
               <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
             </a>
          </div>
        </header>

        <!-- Dynamic View -->
        <main class="flex-1 overflow-y-auto p-4 md:p-6 pb-20 scrollbar-hide">
          <div class="w-full max-w-[1600px] mx-auto">
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
    
    // Default to true but read from localStorage
    const sidebarExpanded = ref(true)
    onMounted(() => {
      const stored = localStorage.getItem('autowfo-sidebar-collapsed')
      if (stored === 'true') {
        sidebarExpanded.value = false
      }
    })
    
    const mobileSidebarOpen = ref(false)
    
    const selectTab = (id) => {
      store.activeTab = id
      mobileSidebarOpen.value = false
    }

    const toggleSidebar = () => {
      sidebarExpanded.value = !sidebarExpanded.value
      localStorage.setItem('autowfo-sidebar-collapsed', (!sidebarExpanded.value).toString())
    }

    const groups = SIDEBAR_GROUPS

    const currentTabTitle = computed(() => {
      for (const g of groups) {
        for (const tmb of g.tabs) {
          if (tmb.id === store.activeTab) return t(tmb.labelKey, tmb.fallback)
        }
      }
      return ''
    })

    const tabComponents = {
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

    const activeComponent = computed(() => tabComponents[store.activeTab] || OverviewTab)

    onMounted(() => setTheme(store.theme))
    
    return { 
      store, groups, sidebarExpanded, mobileSidebarOpen, currentTabTitle,
      activeComponent, toggleTheme, toggleSidebar, selectTab, t 
    }
  }
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
app.mount('#app')
