import { createApp } from 'vue';
import './plugins/assets';
import { setupVueRootValidator } from 'vite-plugin-vue-transition-root-validator/client';
import { setupAppVersionNotification, setupDayjs, setupIconifyOffline, setupLoading, setupNProgress } from './plugins';
import { setupStore } from './store';
import { setupRouter } from './router';
import { getLocale, setupI18n } from './locales';
import App from './App.vue';

// ⚠️ 全局错误诊断：捕获 "Cannot read properties of undefined (reading 'map')" 并输出精确堆栈
// ✨ 2026-07-22 增强：不再只诊断 'map' 崩溃，所有未捕获错误都会输出并在控制台可见
const DIAG_PREFIX = '[MAP-CRASH-DIAG]';
window.addEventListener('error', event => {
  if (event.message?.includes("reading 'map'")) {
    // eslint-disable-next-line no-console
    console.error(
      `${DIAG_PREFIX} window.onerror 捕获:\n  文件: ${event.filename}:${event.lineno}:${event.colno}\n  消息: ${event.message}\n  堆栈: ${event.error?.stack || '无堆栈'}`
    );
  } else {
    // 其他 JS 运行时错误也记录
    // eslint-disable-next-line no-console
    console.error(
      `[GLOBAL-ERROR] ${event.message}\n  文件: ${event.filename}:${event.lineno}:${event.colno}\n  堆栈: ${event.error?.stack || '无堆栈'}`
    );
  }
});
window.addEventListener('unhandledrejection', event => {
  if (event.reason?.message?.includes("reading 'map'")) {
    // eslint-disable-next-line no-console
    console.error(
      `${DIAG_PREFIX} unhandledrejection 捕获:\n  消息: ${event.reason?.message}\n  堆栈: ${event.reason?.stack || '无堆栈'}`
    );
  } else {
    // 其他未捕获的 Promise 拒绝也记录
    const reason = event.reason instanceof Error ? event.reason.message : String(event.reason);
    // eslint-disable-next-line no-console
    console.error(
      `[UNHANDLED-REJECTION] ${reason}\n  堆栈: ${event.reason?.stack || '无堆栈'}`
    );
    // 给用户友好提示
    if (window.$message) {
      window.$message.error(`操作异常: ${reason.slice(0, 80)}`, { duration: 5000, closable: true });
    }
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
    } else {
      // eslint-disable-next-line no-console
      console.error('[VUE-ERROR]', err, '\n  组件:', info);
    }

    // ✨ 给用户友好提示（如果 naive-ui 的 message 已挂载到 window）
    const msg = err instanceof Error ? err.message : String(err);
    const shortMsg = msg.length > 80 ? msg.slice(0, 80) + '…' : msg;
    if (window.$message) {
      window.$message.error(`页面出错了: ${shortMsg}`, { duration: 6000, closable: true });
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
