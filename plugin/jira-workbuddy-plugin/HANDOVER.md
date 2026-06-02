# WorkBuddy + Jira + SVN + 企业微信 集成交接文档

> 创建时间：2026-05-26  
> 工作目录：`H:\workbuddy\jira\`  
> Python：`C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe` (3.13.12)  
> pip 镜像：`https://mirrors.aliyun.com/pypi/simple/`（PyPI 直连有 SSL 问题）

---

## 一、Jira 连接

### 基本信息

| 项目 | 值 |
|------|-----|
| 版本 | Server 9.12.5 |
| 地址 | `http://ctjira1.lmdgame.com:8080` |
| 内网 IP | 192.168.8.34 |
| 项目 | 足球小将 (CT) |

### 认证 — Personal Access Token（永久，不淘汰）

CAPTCHA 拦截了用户名/密码的 Basic Auth。解决方案是创建了一个 PAT（个人访问令牌）：

```
Token: NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG
名称: WorkBuddy MCP
有效期: 永久
```

**使用方式**：HTTP Header `Authorization: Bearer {token}`  
**管理入口**：Jira → 头像 → 个人设置 → 个人访问令牌（可随时吊销）

### JQL 注意事项

- 字段名：`fixVersion`（单数，JQL）、`fixVersions`（复数，API 返回字段）
- 状态名是**中文**：完成、迭代关闭、拒绝/取消、可发布（已完成类）/ 规划中、处理中、待处理 等
- 用户查询需用**英文账号名**（如 `pengjiajun` 而非 `彭家俊`）

### 关键 API

| 用途 | 端点 |
|------|------|
| 获取字段列表 | `/rest/api/2/field` |
| 搜索用户 | `/rest/api/2/user/search?username={name}` |
| 创建 PAT | `POST /rest/pat/latest/tokens` |
| 开发信息（提交） | `/rest/dev-status/1.0/issue/detail?issueId={id}&applicationType=fecru&dataType=repository` |

---

## 二、MCP Server（8 个 Tool）

### 文件

```
H:\workbuddy\jira\wecom-jira-bridge\
├── jira_mcp_server.py    # MCP Server 主文件（FastMCP）
├── jira_api.py           # Jira REST 客户端（PAT 认证、中文状态适配）
├── server.py             # Flask 桥接服务（企业微信回调，待部署）
├── wecom_crypto.py       # 企业微信 WXBizMsgCrypt 加解密
└── .env                  # 环境配置
```

### 全局 MCP 配置

文件：`~/.workbuddy/mcp.json`

```json
{
  "mcpServers": {
    "jira": {
      "command": "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe",
      "args": [
        "H:/workbuddy/jira/wecom-jira-bridge/jira_mcp_server.py"
      ],
      "env": {
        "JIRA_BASE_URL": "http://ctjira1.lmdgame.com:8080",
        "JIRA_PAT": "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG",
        "SVN_URL": "https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3",
        "SVN_USERNAME": "lidaichao",
        "SVN_PASSWORD": "123456",
        "NO_PROXY": "*"
      }
    }
  }
}
```

### Tool 清单

| # | 工具名 | 参数 | 功能 | 依赖 |
|---|--------|------|------|------|
| 1 | `jira_test_connection` | 无 | 连通性测试 | Jira API |
| 2 | `jira_list_projects` | 无 | 列出项目 | Jira API |
| 3 | `jira_search` | `jql: str` | 自定义 JQL 查询 | Jira API |
| 4 | `jira_my_open_issues` | 无 | 当前用户未完成任务 | Jira API |
| 5 | `jira_this_week_issues` | 无 | 本周未完成任务 | Jira API |
| 6 | `jira_get_issue` | `issue_key: str` | 单任务详情 | Jira API |
| 7 | `jira_get_commits` | `issue_key: str` | 关联提交信息+文件清单+增减统计 | Jira dev-status API |
| 8 | `jira_get_svn_diff` | `issue_key: str, max_files: int` | 完整代码 Diff 内容 | SVN CLI |

### 变更后需重启 WorkBuddy 生效

---

## 三、SVN 代码仓库

### 信息

| 项目 | 值 |
|------|-----|
| 地址 | `https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3` |
| 账号 | `lidaichao` / `123456` |
| FishEye | `http://192.168.8.34:8060`（仓库名 CT-V3） |
| 提交与 Issue 关联 | 通过 Jira dev-status API (`applicationType=fecru`) |

### SVN 命令示例

```bash
# 查看某个 revision 的变更文件
svn --non-interactive \
  --trust-server-cert-failures=unknown-ca,cn-mismatch,expired,not-yet-valid,other \
  --username lidaichao --password 123456 \
  diff --summarize -c {rev} https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3

# 查看完整 diff
svn ... diff -c {rev} https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3
```

---

## 四、企业微信集成（未完成）

### 已尝试的方案

| 方案 | 结果 | 原因 |
|------|------|------|
| frp 内网穿透 | ❌ | 本机公网 IP (118.167.4.82) 在 CGNAT 后，外部不可达 |
| Claw 长连接 | ⚠️ 部分成功 | 消息到达但 Claw 独立会话无法使用 Jira MCP 工具 |
| Bridge 部署 Jira 服务器 | ⏸ 未执行 | 需要 Jira 服务器操作权限 |

### 当前 WeCom 凭据

| 字段 | 值 |
|------|-----|
| CorpID | `ww8f190d9dbd657ef1` |
| Token（URL回调用） | `nQGqqnwApNgrQ3bbIoRAp` |
| EncodingAESKey | `OFvKlEXx5WOt4vAoYCM1ww0lG72nY1Ni5mVfbh6rxBU` |
| Bot ID（长连接用） | `aibE7xUfH0EsWc2AKgoYh3YNGe2BH1zQBT7` |
| Secret（长连接用） | `sT2fkh78IBQcdecBWpSAJdHIPlXzjGulTSllTaqISbx` |

### Bridge 备用方案（代码就绪，待部署）

`server.py` 已实现完整的企业微信智能机器人回调逻辑：
- 接收加密消息 → 解密 → 解析意图 → 查询 Jira → 加密回复
- 支持命令：本周未完成任务、我的任务、查询 JQL、连接测试、帮助
- 端口：9090（`.env` 中 `SERVER_PORT`）

**部署条件**：需要一个企业微信服务器可达的 URL（公网 IP 或已备案域名）。

---

## 五、关键经验教训

1. **不能用 npm 的 jira-rest-mcp-server** — 文档不可获取，认证方式不确定。自建 Python MCP Server 更可控。
2. **PAT > Session Cookie** — 永远不要依赖 session cookie，过期就要找用户要。创建 PAT 一劳永逸。
3. **SVN 不用 clone** — `svn diff -c {rev}` 直接远程拉，不需要下载整个仓库。
4. **中文 Jira 踩坑**：状态名是中文，JQL 中 `/` 是保留字（如 "拒绝/取消" 需加引号）。
5. **pip 走阿里云镜像** — 直连 PyPI 有 SSL 问题。
6. **CGNAT 导致公网不可达** — 118.167.4.82 看似公网 IP，实际运营商做了 NAT，外部连不进来。
7. **Claw 长连接 ≠ 原生 WorkBuddy 对话** — Claw 使用独立会话上下文，不共享 MCP 工具。
8. **`.env` 加载需要绝对路径** — `load_dotenv()` 默认从 CWD 找，需显式传 `load_dotenv(os.path.join(script_dir, ".env"))`。
