---
name: alice-visual-snapshot-test
description: >-
  Playwright visual snapshot testing for Alice frontend (Chat) and Admin UI.
  Run npm run test:visual to detect CSS/component layout regressions across
  five key pages. Includes data-testid conventions, mask rules for dynamic
  regions, baseline management, and visual.config.ts integration.
---

# Alice Playwright 视觉快照测试

本 Skill 为 Alice 项目提供 Playwright 视觉快照（visual snapshot）测试能力。
基于 pm-Carroll/docs/alice-visual-snapshot-test-skill.md 设计，由卡罗尔出品、
兔子审核通过（AL-269 Epic）。

## 概述

视觉快照测试的核心价值：CSS/组件改动后，本地跑 30 秒自动检测"有没有意外影响其他页面"。
避免手动打开 5 个页面逐页检查——功能测试全绿但布局漂了 4px 的隐蔽回归。

## 测试范围（5 页覆盖）

| # | 文件 | 页面 | data-testid 依赖 |
|---|------|------|:--:|
| 1 | `tests/visual/chat-home.spec.ts` | Chat 首页 | engine-selector, chat-sidebar, chat-input 等 |
| 2 | `tests/visual/agent-stream.spec.ts` | Agent SSE 流式输出 | mode-agent, agent-response, confirm-card |
| 3 | `tests/visual/admin-integration.spec.ts` | 系统集成页签 | tab-integration, health-status, dify-config |
| 4 | `tests/visual/admin-approval.spec.ts` | 审批中心页签 | tab-approval, approval-list |
| 5 | `tests/visual/admin-kb.spec.ts` | 知识库页签 | tab-kb, kb-list |

## 关键配置

```typescript
// visual.config.ts
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/visual',
  snapshotDir: './tests/visual-snapshots',
  use: {
    baseURL: 'http://192.168.72.147:5000',
    viewport: { width: 1440, height: 900 },
  },
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,  // 超过 1% 像素差异即报红
    },
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'tablet', use: { viewport: { width: 768, height: 1024 } } },
  ],
});
```

## data-testid 命名规范

- **全小写 kebab-case**：`engine-selector`、`chat-input`、`health-status`
- **语义化**：看到名字即知道对应组件
- **页面内唯一**：每个 data-testid 值在同页面内不重复
- **最外层元素**：添加在组件的最外层 DOM 元素

### Chat 前端 data-testid 清单（11 个）

| 组件 | data-testid 值 |
|------|---------------|
| 引擎选择器 | `engine-selector` |
| 侧边栏 | `chat-sidebar` |
| 输入区 | `chat-input` |
| Agent 模式按钮 | `mode-agent` |
| Ask 模式按钮 | `mode-ask` |
| Auto 模式按钮 | `mode-auto` |
| Plan 模式按钮 | `mode-plan` |
| Agent 响应区域 | `agent-response` |
| Jira 查询结果 | `jira-query-result` |
| ConfirmCard | `confirm-card` |
| 时间戳 | `timestamp` |

### Admin UI data-testid 清单（9 个）

| 组件 | data-testid 值 |
|------|---------------|
| 系统集成页签 | `tab-integration` |
| 审批中心页签 | `tab-approval` |
| 知识库页签 | `tab-kb` |
| 探活状态 | `health-status` |
| 连接时间 | `connection-time` |
| Jira 项目选择器 | `jira-project-select` |
| Dify 配置表单 | `dify-config-form` |
| 审批列表容器 | `approval-list` |
| 知识库列表容器 | `kb-list` |

## mask 动态区域规则

**核心原则：遮数据内容，不遮布局结构。**

| 区域 | 原因 | mask 方式 |
|------|------|----------|
| Jira 查询结果列表 | 数据随项目变化 | `locator('[data-testid="jira-query-result"]')` → mask |
| KB 文档列表 | 文档内容变化 | `locator('[data-testid="kb-list"]')` → mask |
| 探活状态指示器 | 连接状态波动 | mask 状态图标/文字，不 mask 容器 |
| 连接时间戳 | 每次运行不同 | mask 时间文字 |
| 审批列表内容 | 审批数据变化 | `locator('[data-testid="approval-list"]')` → mask |
| SSE 时间戳 | 动态时间 | mask 时间文字 |

```typescript
// 示例：在 snapshot 配置中指定 mask
await expect(page).toHaveScreenshot('chat-home.png', {
  mask: [
    page.locator('[data-testid="jira-query-result"]'),
    page.locator('[data-testid="timestamp"]'),
  ],
});
```

## 基线管理规则

1. **首次创建**：运行 `npm run test:visual` → Playwright 自动在 `tests/visual-snapshots/` 生成基线截图
2. **基线随代码提交**：基线截图大小约 50-200KB/张，纳入 Git 仓库
3. **更新基线**：仅兔子审核通过或卡罗尔验收通过的前端改动才可 `--update-snapshots`
4. **禁止无审批更新基线**：日常开发中不允许随意更新基线

```bash
# 正常运行（对比基线）
npm run test:visual

# 更新基线（需审批）
npm run test:visual -- --update-snapshots
```

## package.json 脚本

```json
{
  "scripts": {
    "test:visual": "playwright test --config=visual.config.ts"
  }
}
```

## 开发流程

### 新增 visual 测试的步骤

1. 确认目标组件的 data-testid 已添加（参考上方清单）
2. 在 `tests/visual/` 下创建 `.spec.ts` 文件
3. 使用 `page.waitForSelector('[data-testid="xxx"]')` 等待组件渲染
4. 调用 `expect(page).toHaveScreenshot('name.png', { mask: [...] })`
5. 首次运行 `--update-snapshots` 生成基线
6. 故意改歪一行 CSS → 确认对应页面报红 → diff 图正确标记

### 常见问题

**Q: 快照测试报红怎么办？**
A: 检查 diff 图。若是预期的布局变更 → 审批后更新基线；若是意外回归 → 修复 CSS。

**Q: 动态数据导致误报？**
A: 检查 mask 配置是否覆盖该区域。遵循"遮数据内容，不遮布局结构"原则。

**Q: Admin 页面需要登录怎么办？**
A: AL-272 已实现白名单鉴权——服务器本地 IP（127.0.0.1/192.168.72.147）跳过认证。
Playwright 在服务器本地跑时无需登录流程。

## 关联 Jira

- Epic: [AL-269](http://ctjira1.lmdgame.com:8080/browse/AL-269) Playwright 视觉快照
- 子任务: AL-274 (data-testid) → AL-271 (Chat+Agent) → AL-272 (Admin) → AL-273 (基线)
