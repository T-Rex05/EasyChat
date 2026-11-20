// 主题切换（亮/暗/跟随系统）— 参照 modern-web-guidance dark-mode-toggle 三态模型
//
// 数据模型：
// - localStorage 'af-theme' = 'light' | 'dark'（用户显式覆盖）
// - 无存储值 = 跟随系统 prefers-color-scheme
// - 渲染结果始终落在 <html data-theme="..."> + .dark（Element Plus 深色变量开关）
import { ref } from 'vue'

type Theme = 'light' | 'dark'

const THEME_KEY = 'af-theme'

function stored(): Theme | null {
  const v = localStorage.getItem(THEME_KEY)
  return v === 'light' || v === 'dark' ? v : null
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolved(): Theme {
  return stored() ?? systemTheme()
}

function apply(theme: Theme) {
  current.value = theme
  document.documentElement.dataset.theme = theme
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

const current = ref<Theme>(resolved())
apply(current.value)

// 系统偏好变化时，仅在无显式覆盖的情况下跟随（存储值一旦存在永久保留）
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (!stored()) apply(systemTheme())
})

// 其他页签改动时保持同步
window.addEventListener('storage', (e) => {
  if (e.key === THEME_KEY) apply(resolved())
})

export function useTheme() {
  function toggle() {
    const target: Theme = current.value === 'dark' ? 'light' : 'dark'
    // 目标与系统偏好一致 = 用户在撤销覆盖，删除存储值让后续跟随系统；
    // 不一致才落盘，避免把巧合钉死成永久覆盖
    if (target === systemTheme()) {
      localStorage.removeItem(THEME_KEY)
    } else {
      localStorage.setItem(THEME_KEY, target)
    }
    apply(target)
  }

  return { theme: current, toggle }
}
