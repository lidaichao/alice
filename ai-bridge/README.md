# 爱丽丝 AI Gateway

> Jira AI 助手后端服务 — 独立于桌面客户端运行的 Python AI 引擎

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实的 Jira 地址和 API Key

# 3. 启动服务
python ai_bridge.py
# 监听 http://127.0.0.1:9099
```

## 核心模块

| 文件 | 功能 |
|------|------|
| `ai_bridge.py` | Flask 主服务，多数据源检索 + DeepSeek SSE 流式返回 |
| `jira_api.py` | Jira REST API 客户端 |
| `jira_mcp_server.py` | MCP 工具服务（供 WorkBuddy 调用） |
| `intent_classifier.py` | 5 类意图分类 + 危险操作拦截 |
| `jira_operation_manager.py` | Jira 写操作确认卡状态机 + 失败恢复 |
| `audit_gateway.py` | 操作安全审计 + 速率限制 |
| `skills/registry.yaml` | 插件/工具注册表 |

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 核心聊天端点（SSE 流式） |
| `/health` | GET | 健康检查 |
| `/operations/<id>` | GET | 获取确认卡详情 |
| `/operations/<id>/confirm` | POST | 确认 Jira 写操作 |
| `/operations/<id>/reject` | POST | 拒绝 Jira 写操作 |

## 开发

```bash
# 运行测试
python intent_classifier.py
python jira_operation_manager.py
python audit_gateway.py
```
