import { createApp, h } from 'vue'
import { RouterView } from 'vue-router'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-tag.css'
import './style.css'
import { router } from './router'

createApp({ render: () => h(RouterView) }).use(router).mount('#app')
