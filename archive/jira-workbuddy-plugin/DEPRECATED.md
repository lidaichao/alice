# DEPRECATED — Jira Plugin Route Discontinued

> 日期：2026-06-03 | 决策人：兔子（架构师）

## 废弃说明

该 Java Jira 插件（基于 Atlassian OSGi 架构）已于 2026-06-03 正式废弃。

## 迁移路径

核心业务逻辑已完全迁移至以下新架构：

- **后端**：`backend/` (Python Flask + Waitress, :9099)
- **前端**：`frontend/` (React 19 + TypeScript + Vite)
- **容器**：`desktop/` (Electron 28)

## 保留原因

仅作历史参考。严禁在该插件代码上进行任何新业务特性的开发。
