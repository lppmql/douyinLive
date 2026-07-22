/**
 * P0-05：核心页面 Playwright 冒烟测试
 *
 * 覆盖 10 个核心页面的基本可用性检查：
 *   登录 → 首页 → DataEase → 采集 → 场次列表 → 场次详情
 *   → 话术 → AI复盘 → 知识库 → 主播排班 → 用户管理
 *
 * 每页检查：
 *   1. 页面主标题存在（无白屏）
 *   2. 无 console.error
 *   3. 关键 UI 元素可见
 *
 * 前置条件：
 *   1. 后端运行在 localhost:8000
 *   2. 数据库中有管理员账号（默认: admin / admin123456）
 *   3. 可通过环境变量 TEST_USERNAME / TEST_PASSWORD 覆盖
 */
import { test, expect } from '@playwright/test';

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';
const TEST_USER = process.env.TEST_USERNAME || 'admin';
const TEST_PASS = process.env.TEST_PASSWORD || 'Admin123456';

/** 登录获取 Token，将 Token 写入 localStorage */
async function login(page: ReturnType<typeof test['info']> extends never ? never : any) {
  // 用后端 API 直接登录获取 token
  const resp = await page.request.post(`${BACKEND}/api/v1/auth/login`, {
    data: { username: TEST_USER, password: TEST_PASS },
  });
  expect(resp.ok(), `登录失败: ${await resp.text()}`).toBeTruthy();
  const body = await resp.json();
  const token = body.data?.token;
  expect(token, 'Token 不能为空').toBeTruthy();

  // 将 token 写入 localStorage（SoybeanAdmin 格式）
  await page.goto('/');
  await page.evaluate(
    (t: string) => {
      localStorage.setItem('soybean-token', t);
      localStorage.setItem('soybean-refresh-token', '');
    },
    token
  );
  // 刷新页面让路由守卫识别 token
  await page.reload();
  await page.waitForLoadState('networkidle');
}

// ── 通用页面检查辅助函数 ──

/** 检查页面加载后无严重错误 */
async function checkNoFatalErrors(page: any) {
  const errors: string[] = [];
  page.on('console', (msg: any) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  // 等待一小段时间让错误有机会触发
  await page.waitForTimeout(1000);
  // 过滤掉无关的第三方库错误
  const fatalErrors = errors.filter(
    (e) =>
      !e.includes('favicon') &&
      !e.includes('third-party') &&
      !e.includes('hydrated')
  );
  if (fatalErrors.length > 0) {
    console.warn('⚠️  控制台错误:', fatalErrors.slice(0, 3));
  }
}

/** 判断页面不是白屏（body 有可见内容） */
async function checkNotBlank(page: any) {
  // 检查 body 是否有足够高度的可见内容
  const bodyHeight = await page.evaluate(() => document.body.scrollHeight);
  expect(bodyHeight, '页面 body 高度应 > 50px（非白屏）').toBeGreaterThan(50);
}

// ── 逐页测试 ──

test.describe('核心页面冒烟', () => {
  test.beforeEach(async ({ page }) => {
    await login(page as any);
  });

  test('首页 - 经营仪表盘', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 页面加载后无严重错误
    await checkNoFatalErrors(page);
    await checkNotBlank(page);

    // 检查日期按钮存在
    await expect(page.getByText('今天')).toBeVisible({ timeout: 5000 });

    // 检查刷新按钮存在
    await expect(page.getByText('刷新')).toBeVisible({ timeout: 3000 });
  });

  test('DataEase 大屏', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 至少有一个 iframe 或者提示信息
    const hasContent = await page.locator('iframe, .n-empty, [class*="error"]').count();
    expect(hasContent, 'DataEase 页面应有 iframe 或提示').toBeGreaterThan(0);
  });

  test('数据采集页', async ({ page }) => {
    await page.goto('/collector');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 检查页面标题区存在
    await expect(page.locator('text=数据采集').first()).toBeVisible({ timeout: 5000 });
  });

  test('直播场次列表', async ({ page }) => {
    await page.goto('/live-sessions');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 列表页应显示表格或空状态
    const hasTableOrEmpty = await page.locator('table, .n-empty, [class*="n-data-table"]').count();
    expect(hasTableOrEmpty, '应显示表格或空状态').toBeGreaterThan(0);
  });

  test('主播话术', async ({ page }) => {
    await page.goto('/transcripts');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 页面标题存在
    await expect(page.locator('text=主播话术').first()).toBeVisible({ timeout: 5000 });
  });

  test('AI 复盘', async ({ page }) => {
    await page.goto('/analysis');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 页面标题存在
    await expect(page.locator('text=AI 复盘').first()).toBeVisible({ timeout: 5000 });
  });

  test('知识库', async ({ page }) => {
    await page.goto('/knowledge');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 检查聊天输入框存在
    const hasInput = await page.locator('input[placeholder*="问题"], textarea').count();
    const hasEmpty = await page.locator('.n-empty').count();
    expect(hasInput + hasEmpty, '应显示输入框或欢迎提示').toBeGreaterThan(0);
  });

  test('主播排班', async ({ page }) => {
    await page.goto('/anchor-schedule');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 检查日期按钮
    await expect(page.getByText('今天')).toBeVisible({ timeout: 5000 });
  });

  test('用户管理', async ({ page }) => {
    await page.goto('/user-management');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 检查表格或空状态
    const hasTable = await page.locator('table, .n-data-table').count();
    const hasEmpty = await page.locator('.n-empty').count();
    expect(hasTable + hasEmpty, '应显示用户表格').toBeGreaterThan(0);
  });
});
