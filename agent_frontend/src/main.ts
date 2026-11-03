import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import { router } from './router/index.js'
import './styles/design-system.css'
import { useAuthStore } from '@/stores/auth'

const app = createApp(App)

// 创建 Pinia 实例
const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// v-perm 全局指令：无权限时移除元素
app.directive('perm', {
  mounted(el, binding) {
    const auth = useAuthStore()
    if (!auth.hasPerm(binding.value)) {
      el.remove()
    }
  },
})

app.mount('#app')
