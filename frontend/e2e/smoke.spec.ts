/**
 * P0-05：核心页面 Playwright 冒烟测试
 *
 * 覆盖 11 个核心页面的基本可用性检查：
 *   登录 → 首页 → 原生经营大屏 → 采集 → 场次列表 → 场次详情
 *   → 话术 → AI复盘 → AI手动剪辑 → 知识库 → 主播排班 → 用户管理
 *
 * 每页检查：
 *   1. 页面主标题存在（无白屏）
 *   2. 无 console.error
 *   3. 关键 UI 元素可见
 *
 * 前置条件：
 *   1. 后端运行在 localhost:8000
 *   2. 推荐通过 TEST_ACCESS_TOKEN 传入本机临时令牌
 *   3. 也可同时配置 TEST_USERNAME / TEST_PASSWORD 使用真实测试账号
 */
import { test, expect } from '@playwright/test';

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';
const TEST_USER = process.env.TEST_USERNAME?.trim() || '';
const TEST_PASS = process.env.TEST_PASSWORD || '';
const TEST_ACCESS_TOKEN = process.env.TEST_ACCESS_TOKEN || '';
const STORAGE_PREFIX = process.env.VITE_STORAGE_PREFIX || 'SOY_';
let cachedAccessToken = TEST_ACCESS_TOKEN;
const browserErrors = new WeakMap<any, string[]>();

/** 在导航前监听浏览器错误，避免漏掉首屏初始化异常。 */
function monitorBrowserErrors(page: any) {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on('console', (msg: any) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (error: Error) => errors.push(error.message));
}

function assertNoFatalErrors(page: any) {
  const fatalErrors = (browserErrors.get(page) || []).filter(
    error =>
      !error.includes('favicon') &&
      !error.includes('third-party') &&
      !error.includes('hydrated') &&
      // 连续切换工作流页面时，Chromium 会把已取消的旧页面请求记为该网络错误。
      !error.includes('net::ERR_NETWORK_IO_SUSPENDED')
  );
  expect(fatalErrors, `页面不应出现浏览器错误：${fatalErrors.slice(0, 3).join(' | ')}`).toEqual([]);
}

/** 登录获取 Token，将 Token 写入 localStorage */
async function login(page: ReturnType<typeof test['info']> extends never ? never : any): Promise<string> {
  let token = cachedAccessToken;
  if (!token) {
    expect(
      TEST_USER && TEST_PASS,
      '未配置 E2E 登录信息：请设置 TEST_ACCESS_TOKEN，或同时设置 TEST_USERNAME 和 TEST_PASSWORD'
    ).toBeTruthy();
    const resp = await page.request.post(`${BACKEND}/api/v1/auth/login`, {
      data: { username: TEST_USER, password: TEST_PASS }
    });
    expect(resp.ok(), `登录失败: ${await resp.text()}`).toBeTruthy();
    const body = await resp.json();
    token = body.data?.token;
    cachedAccessToken = token;
  }
  expect(token, 'Token 不能为空').toBeTruthy();

  // 在首个业务页面脚本执行前写入 Token，避免先打开未认证首页再刷新的竞态和无效请求。
  await page.addInitScript(
    ({ token: accessToken, prefix }: { token: string; prefix: string }) => {
      // createStorage 会给键名加前缀，并把字符串再做一次 JSON 序列化。
      localStorage.setItem(`${prefix}token`, JSON.stringify(accessToken));
      localStorage.setItem(`${prefix}refreshToken`, JSON.stringify(''));
    },
    { token, prefix: STORAGE_PREFIX }
  );
  return token;
}

/** 打开业务页。页面包含轮询和长请求时，不能用 networkidle 判断是否渲染完成。 */
async function openPage(page: any, path: string) {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await expect(page).not.toHaveURL(/\/login(?:\/|\?|$)/);
  await expect(page.locator('main')).toBeVisible({ timeout: 25_000 });
}

// ── 通用页面检查辅助函数 ──

/** 判断页面不是白屏（body 有可见内容） */
async function checkNotBlank(page: any) {
  // 检查 body 是否有足够高度的可见内容
  const bodyHeight = await page.evaluate(() => document.body.scrollHeight);
  expect(bodyHeight, '页面 body 高度应 > 50px（非白屏）').toBeGreaterThan(50);
}

// ── 逐页测试 ──

test.describe('核心页面冒烟', () => {
  let authToken = '';
  let clipCandidateSessionId = '';

  test.beforeEach(async ({ page }) => {
    monitorBrowserErrors(page);
    authToken = await login(page as any);
  });

  test.afterEach(async ({ page }) => {
    assertNoFatalErrors(page);
  });

  test('首页 - 经营仪表盘', async ({ page }) => {
    await openPage(page, '/');

    await checkNotBlank(page);

    // 检查日期按钮存在
    await expect(page.getByText('今天')).toBeVisible({ timeout: 5000 });

    // 检查刷新按钮存在
    await expect(page.getByText('刷新')).toBeVisible({ timeout: 3000 });
  });

  test('原生经营大屏', async ({ page }) => {
    await openPage(page, '/dashboard');
    await checkNotBlank(page);

    await expect(page.getByText('零食店直播经营大屏')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('iframe')).toHaveCount(0);
    const hasContent = await page.locator('.n-card, .n-empty, [class*="error"]').count();
    expect(hasContent, '原生经营大屏应显示经营卡片或真实空状态').toBeGreaterThan(0);
  });

  test('数据采集页', async ({ page }) => {
    await openPage(page, '/collector');
    await checkNotBlank(page);

    await expect(page.getByText('数据处理控制中心')).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('heading', { name: '采集账号', exact: true })).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('heading', { name: '采集日志', exact: true })).toBeVisible({ timeout: 5000 });
  });

  test('直播场次列表', async ({ page }) => {
    await openPage(page, '/live-sessions');
    await checkNotBlank(page);

    // 列表页应显示表格或空状态
    await expect(page.locator('.n-data-table, .n-empty').first(), '应显示表格或空状态').toBeVisible({
      timeout: 10_000
    });
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

    await openPage(page, `/live-sessions/${sessionId}`);
    await checkNotBlank(page);
    const workflow = page.getByRole('navigation', { name: '场次复盘工作流' });
    await expect(workflow).toContainText(`场次 #${sessionId}`, { timeout: 8000 });
    await expect(workflow.getByRole('button', { name: '场次详情', exact: true })).toBeVisible();
    await expect(workflow.getByRole('button', { name: '主播话术', exact: true })).toBeVisible();
    await expect(workflow.getByRole('button', { name: 'AI 复盘', exact: true })).toBeVisible();
    await expect(workflow.getByRole('button', { name: '知识库问答', exact: true })).toBeVisible();

    // 连续快速跳转，验证公共工作流始终携带同一个真实场次，而不是回退到最新场次。
    await workflow.getByRole('button', { name: '主播话术', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/transcripts\\?sessionId=${sessionId}`));
    await expect(workflow).toContainText(`场次 #${sessionId}`);
    await workflow.getByRole('button', { name: 'AI 复盘', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/analysis\\?sessionId=${sessionId}`));
    await expect(workflow).toContainText(`场次 #${sessionId}`);
    await workflow.getByRole('button', { name: '知识库问答', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/knowledge\\?sessionId=${sessionId}`));
  });

  test('主播话术', async ({ page }) => {
    await openPage(page, '/transcripts');
    await checkNotBlank(page);

    // 页面标题存在
    await expect(page.locator('text=主播话术').first()).toBeVisible({ timeout: 5000 });
  });

  test('主播话术 - 历史场次滚动加载且列表不跳顶', async ({ page }) => {
    // 本用例只验收场次分页；历史头像域名的独立降级不应干扰滚动断言。
    await page.route('**/live-sessions/*/avatar', route => route.fulfill({ status: 204 }));
    const firstPagePromise = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/live-sessions/selector-options') && url.searchParams.get('offset') === '0';
    });
    await openPage(page, '/transcripts');
    const firstPageResponse = await firstPagePromise;
    expect(firstPageResponse.ok(), `场次第一页读取失败: ${await firstPageResponse.text()}`).toBeTruthy();
    expect(new URL(firstPageResponse.url()).searchParams.get('limit')).toBe('100');

    const selector = page.locator('.transcript-workbench .session-selector__main .n-select');
    await expect(selector).toBeVisible({ timeout: 10_000 });
    await selector.click();
    await expect(page.getByText('向下滚动加载更多场次')).toBeVisible({ timeout: 5000 });

    // NSelect 开启虚拟滚动后，真正承载 scrollTop 的是 VirtualList，而不是 NScrollbar。
    const menuScrollbar = page.locator('.n-base-select-menu .n-virtual-list').last();
    await expect(menuScrollbar).toBeVisible({ timeout: 5000 });
    const nextPagePromise = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/live-sessions/selector-options') && url.searchParams.get('offset') === '100';
    });
    await menuScrollbar.evaluate(element => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
    const nextPageResponse = await nextPagePromise;
    expect(nextPageResponse.ok(), `场次下一页读取失败: ${await nextPageResponse.text()}`).toBeTruthy();
    expect((await nextPageResponse.json()).length).toBeGreaterThan(0);

    // 分页追加会改变 options；此时菜单必须保持在历史位置，不能恢复到 scrollTop=0。
    await expect.poll(() => menuScrollbar.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  });

  test('AI 复盘', async ({ page }) => {
    await openPage(page, '/analysis');
    await checkNotBlank(page);

    // 页面标题存在
    await expect(page.locator('text=AI 复盘').first()).toBeVisible({ timeout: 5000 });
  });

  test('AI 自动剪辑', async ({ page }) => {
    await openPage(page, '/clip');
    await checkNotBlank(page);

    // 页面标题存在
    await expect(page.locator('text=AI手动剪辑').first()).toBeVisible({ timeout: 5000 });

    // 场次下拉与生成按钮存在（naive-ui NSelect 的 placeholder 是自绘文本，非 input 属性）
    await expect(page.getByRole('button', { name: /^(重新)?生成本场成片$/ })).toBeVisible({ timeout: 5000 });
    const sessionSelect = page.locator('.clip-page__session-select');
    await expect(sessionSelect).toBeVisible({ timeout: 5000 });
    await expect(page).toHaveURL(/\/clip\?sessionId=\d+/, { timeout: 30_000 });
    clipCandidateSessionId = new URL(page.url()).searchParams.get('sessionId') || '';
    expect(clipCandidateSessionId, 'AI 剪辑页应选中一个真实候选场次').toBeTruthy();

    // 选中第一个候选场次后应加载出成片区（卡片或空提示）
    const selector = page.locator('.clip-page__session-select .session-selector__main .n-select');
    await expect(selector, '场次选择下拉应可操作').toBeVisible({ timeout: 10_000 });
    await selector.click();
    const firstOption = page.locator('.clip-page__option, [class*="n-base-select-option"]').first();
    await expect(firstOption, '真实候选场次应出现在下拉列表中').toBeVisible({ timeout: 10_000 });
    await firstOption.click();
    await checkNotBlank(page);
    await expect(
      page.locator('.clip-card, .clip-page__session-info, .n-empty, [class*="n-alert"]').first(),
      '应显示场次信息、成片卡片或提示'
    ).toBeVisible({ timeout: 20_000 });
  });

  test('AI 自动剪辑 - sessionId 直达（场次详情入口）', async ({ page }) => {
    test.setTimeout(90_000);
    // Worker 重试会清空模块变量；此时先由页面自身选出一个真实候选场次。
    if (!clipCandidateSessionId) {
      await openPage(page, '/clip');
      await expect(page).toHaveURL(/\/clip\?sessionId=\d+/, { timeout: 45_000 });
      clipCandidateSessionId = new URL(page.url()).searchParams.get('sessionId') || '';
    }
    expect(clipCandidateSessionId, '至少有一个真实候选场次').toBeTruthy();

    // 带 sessionId 直达：应自动加载该场次（显示场次信息或成片区）
    await openPage(page, `/clip?sessionId=${clipCandidateSessionId}`);
    await checkNotBlank(page);
    await expect(page).toHaveURL(new RegExp(`/clip\\?sessionId=${clipCandidateSessionId}`));
    await expect(
      page.locator('.clip-page__session-info, .clip-card, .n-empty').first(),
      '应显示指定场次信息或成片区'
    ).toBeVisible({ timeout: 30_000 });
  });

  test('知识库', async ({ page }) => {
    await openPage(page, '/knowledge');
    await checkNotBlank(page);

    // 检查聊天输入框存在
    await expect(
      page.locator('textarea[placeholder*="问题"], .n-empty').first(),
      '应显示输入框或欢迎提示'
    ).toBeVisible({ timeout: 10_000 });
  });

  test('主播排班', async ({ page }) => {
    await openPage(page, '/anchor-schedule');
    await checkNotBlank(page);

    // 检查日期按钮
    await expect(page.getByRole('button', { name: '今天', exact: true })).toBeVisible({ timeout: 5000 });
  });

  test('用户管理', async ({ page }) => {
    await openPage(page, '/user-management');
    await checkNotBlank(page);

    // 检查表格或空状态
    await expect(page.locator('.n-data-table, .n-empty').first(), '应显示用户表格').toBeVisible({ timeout: 10_000 });
  });
});
