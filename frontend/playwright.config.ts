/**
 * Playwright 冒烟测试配置
 *
 * 用途：启动前端 dev server，检查 10 个核心页面是否正常加载。
 * 前提：后端必须已运行在 localhost:8000，且数据库中有可用测试用户。
 *
 * 运行方式：
 *   cd frontend
 *   pnpm exec playwright install chromium     # 首次需安装浏览器
 *   pnpm exec playwright test                 # 运行所有冒烟测试
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
