import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import zhCn from 'element-plus/dist/locale/zh-cn.mjs';

// Element Plus theme mapping
document.documentElement.style.setProperty('--el-color-primary', '#0c66e4');
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import './styles/design-tokens.css';
import './styles/admin-motion.css';
import './styles/admin-theme.css';
import App from './App.vue';

const app = createApp(App);
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}
app.use(ElementPlus, { locale: zhCn });
app.mount('#app');
