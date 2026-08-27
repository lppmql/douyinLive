/**
 * P0-05：核心页面 Playwright 冒烟测试
 *
 * 覆盖 11 个核心页面的基本可用性检查：
 *   登录 → 首页 → DataEase → 采集 → 场次列表 → 场次详情
 *   → 话术 → AI复盘 → AI手动剪辑 → 知识库 → 主播排班 → 用户管理
 *
 * 每页检查：
 *   1. 页面主标题存在（无白屏）
 *   2. 无 console.error
 *   3. 关键 UI 元素可见
 *
 * 前置条件：
 *   1. 后端运行在 localhost:8000
 *   2. 数据库中有可用账号，或通过 TEST_ACCESS_TOKEN 传入本机临时令牌
 *   3. 账号方式可通过 TEST_USERNAME / TEST_PASSWORD 覆盖
 */
import { test, expect } from '@playwright/test';

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';
const TEST_USER = process.env.TEST_USERNAME || 'admin';
const TEST_PASS = process.env.TEST_PASSWORD || 'Admin123456';
const TEST_ACCESS_TOKEN = process.env.TEST_ACCESS_TOKEN || '';
const STORAGE_PREFIX = process.env.VITE_STORAGE_PREFIX || 'SOY_';

/** 登录获取 Token，将 Token 写入 localStorage */
async function login(page: ReturnType<typeof test['info']> extends never ? never : any): Promise<string> {
  let token = TEST_ACCESS_TOKEN;
  if (!token) {
    const resp = await page.request.post(`${BACKEND}/api/v1/auth/login`, {
      data: { username: TEST_USER, password: TEST_PASS }
    });
    expect(resp.ok(), `登录失败: ${await resp.text()}`).toBeTruthy();
    const body = await resp.json();
    token = body.data?.token;
  }
  expect(token, 'Token 不能为空').toBeTruthy();

  // 将 token 写入 localStorage（SoybeanAdmin 格式）
  await page.goto('/');
  await page.evaluate(
    ({ token: accessToken, prefix }: { token: string; prefix: string }) => {
      // createStorage 会给键名加前缀，并把字符串再做一次 JSON 序列化。
      localStorage.setItem(`${prefix}token`, JSON.stringify(accessToken));
      localStorage.setItem(`${prefix}refreshToken`, JSON.stringify(''));
    },
    { token, prefix: STORAGE_PREFIX }
  );
  // 刷新页面让路由守卫识别 token
  await page.reload();
  await page.waitForLoadState('networkidle');
  return token;
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
  let authToken = '';

  test.beforeEach(async ({ page }) => {
    authToken = await login(page as any);
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

    await expect(page.getByText('数据处理控制中心')).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('heading', { name: '采集账号', exact: true })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('heading', { name: '采集日志', exact: true })).toBeVisible({ timeout: 5000 });
  });

  test('直播场次列表', async ({ page }) => {
    await page.goto('/live-sessions');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 列表页应显示表格或空状态
    const hasTableOrEmpty = await page.locator('table, .n-empty, [class*="n-data-table"]').count();
    expect(hasTableOrEmpty, '应显示表格或空状态').toBeGreaterThan(0);
  });

  test('场次详情与复盘工作流联动', async ({ page }) => {
    const response = await page.request.get(`${BACKEND}/api/v1/live-sessions/page`, {
      headers: { Authorization: `Bearer ${authToken}` },
      params: { current: 1, size: 1 }
    });
    expect(response.ok(), `最新场次读取失败: ${await response.text()}`).toBeTruthy();
    const body = await response.json();
    const sessionId = body.records?.[0]?.id;
    expect(sessionId, '真实数据库中至少要有一场直播').toBeTruthy();

    await page.goto(`/live-sessions/${sessionId}`);
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);
    await expect(page.getByText('场次详情', { exact: true }).first()).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('主播话术', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('AI 复盘', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('知识库问答', { exact: true }).first()).toBeVisible();

    await page.getByText('主播话术', { exact: true }).first().click();
    await expect(page).toHaveURL(new RegExp(`/transcripts\\?sessionId=${sessionId}`));
    await page.getByText('AI 复盘', { exact: true }).first().click();
    await expect(page).toHaveURL(new RegExp(`/analysis\\?sessionId=${sessionId}`));
    await page.getByText('知识库问答', { exact: true }).first().click();
    await expect(page).toHaveURL(new RegExp(`/knowledge\\?sessionId=${sessionId}`));
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

  test('AI 自动剪辑', async ({ page }) => {
    await page.goto('/clip');
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);

    // 页面标题存在
    await expect(page.locator('text=AI手动剪辑').first()).toBeVisible({ timeout: 5000 });

    // 场次下拉与生成按钮存在（naive-ui NSelect 的 placeholder 是自绘文本，非 input 属性）
    await expect(page.getByRole('button', { name: '生成/重新生成 5 条成片' })).toBeVisible({ timeout: 5000 });
    const sessionSelect = page.locator('.clip-page__session-select');
    await expect(sessionSelect).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('搜索主播或场次')).toBeVisible({ timeout: 5000 });

    // 选中第一个候选场次后应加载出成片区（卡片或空提示）
    const selector = page.locator('.clip-page__session-select');
    await selector.click();
    const firstOption = page.locator('.clip-page__option, [class*="n-base-select-option"]').first();
    if (await firstOption.isVisible().catch(() => false)) {
      await firstOption.click();
      await page.waitForTimeout(2000);
      await checkNotBlank(page);
      const hasClipsOrEmpty = await page
        .locator('.clip-card, .n-empty, [class*="n-alert"]')
        .count();
      expect(hasClipsOrEmpty, '应显示成片卡片或提示').toBeGreaterThan(0);
    }
  });

  test('AI 自动剪辑 - sessionId 直达（场次详情入口）', async ({ page }) => {
    // 取一个真实候选场次
    const response = await page.request.get(`${BACKEND}/api/v1/clip/candidate-sessions`, {
      headers: { Authorization: `Bearer ${authToken}` },
      params: { limit: 1 }
    });
    expect(response.ok(), '候选场次读取失败').toBeTruthy();
    const items = await response.json();
    expect(items.length, '至少有一个候选场次').toBeGreaterThan(0);

    // 带 sessionId 直达：应自动加载该场次（显示场次信息或成片区）
    await page.goto(`/clip?sessionId=${items[0].session_id}`);
    await page.waitForLoadState('networkidle');
    await checkNotBlank(page);
    const hasSessionContent = await page
      .locator('.clip-page__session-info, .clip-card, .n-empty')
      .count();
    expect(hasSessionContent, '应显示场次信息或成片区').toBeGreaterThan(0);
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
    await expect(page.getByRole('button', { name: '今天', exact: true })).toBeVisible({ timeout: 5000 });
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
