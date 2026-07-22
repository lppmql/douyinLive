# ADR 0009：API 统一鉴权与 Schema 契约专项

- **日期**：2026-07-22
- **状态**：✅ 已执行

---

## 背景

项目 16 个子路由中，仅 `user_mgmt` 实现了管理员鉴权，其余 15 个路由（采集、复盘、场次、话术、知识库等）所有接口只依赖 `get_db`，无需登录即可调用。

同时，`ReviewFindingOut` 和 `ComplianceRuleOut` 两个 Pydantic Schema 与数据库模型字段严重错配：
- ReviewFindingOut 缺失 `finding_type`、`description`、`severity`、`evidence_type` 等 9 个核心字段，反而定义了模型中不存在的 `evidence_summary`、`recommendation`
- ComplianceRuleOut 使用 `title`/`description` 替代模型真正的 `name`/`guidance`/`pattern`

这导致更新 finding 状态后，前端拿到的响应丢失全部证据数据。

---

## 决策

### 1. 统一鉴权策略

- **所有业务 API 统一要求登录**：在 `v1_router` 层面添加 `dependencies=[Depends(get_current_user)]`
- **auth 路由例外**：`/api/v1/auth/login` 和 `/api/v1/auth/refreshToken` 保持公开，通过单独注册到 app 实现
- **粒度**：当前只区分"未登录"和"已登录"，不按角色细分 API 权限（user_mgmt 已有独立管理员检查）

### 2. Schema 契约

- ReviewFindingOut 和 ComplianceRuleOut 完全对齐数据库模型字段
- `_row_dict` 增加 datetime → ISO 字符串转换（Pydantic Schema 使用 `str` 而非 `datetime`）
- 新增契约测试：每个复盘端点的真实返回值都经过 `model_validate()` 校验

### 3. 管理员保护

- 不能删除 / 降级最后一个 `R_SUPER` 管理员
- 新增 `_count_super_admins()` 和 `_guard_last_super_admin()` 辅助函数

### 4. 前端冒烟测试

- 引入 Playwright，覆盖 10 个核心页面
- 每页检查：标题可见、非白屏、无致命控制台错误
- 独立 `make test-frontend-e2e` 目标（不与 CI 的 typecheck 混在一起）

---

## 影响

- **所有现有 API 调用方**必须携带 JWT Token（前端 SoybeanAdmin 已自动处理）
- **测试全部更新**：collector、dashboard 测试添加 `auth_headers` fixture
- **新增 12 个契约测试** + 10 个 Playwright 冒烟测试
- **conftest 同步更新**：test_app 也单独注册 auth_router

---

## 关联

- [[0004-前后端契约测试与协调验收]]
- [[0006-项目维护标准与红线]]
