import { reactive } from 'vue'
import { L } from './i18n.js'

const t = (key, fallback = '') => L[key] || fallback || key

export const store = reactive({
  theme: localStorage.getItem('autowfo-theme') || 'dark',
  activeTab: 'overview',
  pendingRunMode: null,   // cross-tab: set by Results "精修" action, consumed by Overview
  toasts: [],
  _toastId: 0,
  confirm: {
    open: false,
    title: '',
    message: '',
    confirmText: t('confirm_confirm_default', 'Confirm'),
    cancelText: t('confirm_cancel_default', 'Cancel'),
    variant: 'danger',
    _resolve: null,
  },
})

export function setTheme(theme) {
  store.theme = theme
  localStorage.setItem('autowfo-theme', theme)
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

export function toggleTheme() {
  setTheme(store.theme === 'dark' ? 'light' : 'dark')
}

export function showToast(message, type = 'info', duration = 3000) {
  const id = ++store._toastId
  store.toasts.push({ id, message, type, removing: false })
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration)
  }
  return id
}

export function removeToast(id) {
  const idx = store.toasts.findIndex(t => t.id === id)
  if (idx < 0) return
  store.toasts[idx].removing = true
  setTimeout(() => {
    const i = store.toasts.findIndex(t => t.id === id)
    if (i >= 0) store.toasts.splice(i, 1)
  }, 200)
}

export function confirmAction(options = {}) {
  const {
    title = t('confirm_title_default', 'Please Confirm'),
    message = t('confirm_message_default', 'Are you sure you want to continue?'),
    confirmText = t('confirm_confirm_default', 'Confirm'),
    cancelText = t('confirm_cancel_default', 'Cancel'),
    variant = 'danger',
  } = options

  return new Promise(resolve => {
    if (typeof store.confirm._resolve === 'function') {
      store.confirm._resolve(false)
    }
    store.confirm.open = true
    store.confirm.title = title
    store.confirm.message = message
    store.confirm.confirmText = confirmText
    store.confirm.cancelText = cancelText
    store.confirm.variant = variant
    store.confirm._resolve = resolve
  })
}

export function resolveConfirm(accepted) {
  const resolver = store.confirm._resolve
  store.confirm.open = false
  store.confirm._resolve = null
  if (typeof resolver === 'function') {
    resolver(Boolean(accepted))
  }
}
