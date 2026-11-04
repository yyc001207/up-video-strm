import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import 'element-plus/dist/index.css'
import './styles/variables.scss'
import './styles/dark.scss'
import './styles/element-reset.scss'
import './styles/global.scss'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}
app.mount('#app')

// 桌面外壳（托盘菜单）通过 window.__upVideoStrmNavigate('/settings') 直接切页，
// 避免用 load_url 整页重载丢失当前界面状态。
declare global {
  interface Window {
    __upVideoStrmNavigate?: (path: string) => unknown
  }
}

window.__upVideoStrmNavigate = (path: string) => router.push(path)
