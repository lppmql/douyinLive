# ADR 0010：前端运行时稳定性 — ErrorBoundary 与全局错误处理

- **日期**：2026-07-22
- **状态**：✅ 已执行

---

## 背景

前端目前有三层错误处理，但都只有日志没有用户体验反馈：

1. `app.config.errorHandler` — 只 `console.error`，用户看不到
2. `window.onerror` — 只诊断 `"reading 'map'"` 崩溃
3. `window.unhandledrejection` — 同上

当某个页面组件渲染崩溃时（比如后端返回数据结构变了、数据为 `undefined` 调了 `.map()`），用户看到的是**白屏**，没有任何提示。唯一的恢复方式是手动刷新浏览器。

路由守卫也没有异常保护——如果 `initRoute()` 或 `initAuthRoute()` 抛异常，整个导航卡死。

---

## 决策

### 1. ErrorBoundary 组件（Vue 3 `onErrorCaptured`）

- 在 `App.vue` 的 `<RouterView>` 外层包裹 `<ErrorBoundary>`
- 子组件崩溃时，`onErrorCaptured` 返回 `false`（阻止错误继续冒泡）
- 显示友好降级 UI：
  - 大图标 + "页面组件渲染出错"
  - 错误消息摘要
  - "重试"按钮（清除错误状态，让子组件重新挂载）
  - "返回首页"按钮
  - 折叠的"错误详情"（调试用，显示堆栈）

**为什么不全局干掉错误**：ErrorBoundary 只捕获子组件树的渲染错误，不影响 `app.config.errorHandler` 覆盖不到的场景（比如生命周期钩子外抛出的错误）。

### 2. 增强 `app.config.errorHandler`

在原有日志基础上，加入 `window.$message.error()` 用户提示：
- 错误消息截断到 80 字符（防止超长弹窗）
- 6 秒自动消失，带关闭按钮
- 检查 `window.$message` 是否存在（naive-ui 挂载前不报错）

### 3. 增强 `unhandledrejection`

对所有未捕获的 Promise 拒绝（不只是 `"reading 'map'"`）：
- 输出完整堆栈到控制台
- 给用户 toast 提示

### 4. 路由守卫 `try-catch`

`beforeEach` 整体包裹 `try-catch`：
- 任何异常（store 未初始化、localStorage 损坏、路由配置错误等）都会被捕获
- 安全回退：`return { name: 'root' }` 跳回首页
- 给用户 toast："页面导航出错了，已返回首页"

---

## 影响

- **白屏变降级 UI**：组件崩溃时用户能看到错误提示和操作按钮，不再是空白页
- **静默错误变可见**：全局异常和未捕获 Promise 拒绝会弹出 toast
- **路由异常可恢复**：导航出错自动回首页，不会卡死

---

## 关联

- [[0006-项目维护标准与红线]]
- [[0009-API鉴权与Schema契约专项]]
