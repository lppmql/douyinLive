import { createApp } from 'vue';
import './plugins/assets';
import { setupVueRootValidator } from 'vite-plugin-vue-transition-root-validator/client';
import { setupAppVersionNotification, setupDayjs, setupIconifyOffline, setupLoading, setupNProgress } from './plugins';
import { setupStore } from './store';
import { setupRouter } from './router';
import { getLocale, setupI18n } from './locales';
import App from './App.vue';

// ⚠️ 全局错误诊断：捕获 "Cannot read properties of undefined (reading 'map')" 并输出精确堆栈
const DIAG_PREFIX = '[MAP-CRASH-DIAG]';
window.addEventListener('error', event => {
  if (event.message?.includes("reading 'map'")) {
    // eslint-disable-next-line no-console
    console.error(
      `${DIAG_PREFIX} window.onerror 捕获:\n  文件: ${event.filename}:${event.lineno}:${event.colno}\n  消息: ${event.message}\n  堆栈: ${event.error?.stack || '无堆栈'}`
    );
  }
});
window.addEventListener('unhandledrejection', event => {
  if (event.reason?.message?.includes("reading 'map'")) {
    // eslint-disable-next-line no-console
    console.error(
      `${DIAG_PREFIX} unhandledrejection 捕获:\n  消息: ${event.reason?.message}\n  堆栈: ${event.reason?.stack || '无堆栈'}`
    );
  }
});

async function setupApp() {
  setupLoading();

  setupNProgress();

  setupIconifyOffline();

  setupDayjs();

  const app = createApp(App);

  // Vue 全局错误处理器
  app.config.errorHandler = (err, _instance, info) => {
    if (err instanceof Error && err.message?.includes("reading 'map'")) {
      // eslint-disable-next-line no-console
      console.error(
        `${DIAG_PREFIX} Vue errorHandler 捕获:\n  组件信息: ${info}\n  消息: ${err.message}\n  堆栈: ${err.stack || '无堆栈'}`
      );
    } else if (err instanceof Error) {
      // 也输出其他 Vue 错误以便排查
      // eslint-disable-next-line no-console
      console.error(`[VUE-ERROR] ${err.message}\n  组件: ${info}\n  堆栈: ${err.stack}`);
    }
  };

  setupStore(app);

  await setupRouter(app);

  setupI18n(app);

  setupAppVersionNotification();

  setupVueRootValidator(app, {
    lang: getLocale() === 'zh-CN' ? 'zh' : 'en'
  });

  app.mount('#app');
}

setupApp();
