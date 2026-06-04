# jira-workbuddy-plugin 开发指导手册 v3

> 版本：3.0 | 日期：2026-05-28 02:17 | 基于 TechDoc + PRD + 最新代码
> 目标：Jira Server 9.12.5 内嵌 AI 聊天面板 — 可部署、可维护、自包含

---

## 一、当前架构（v3 最终形态）

### 1.1 数据流

```
┌──────────────────────────────────────────────────────────────┐
│                    Jira 浏览器页面                             │
│  ┌────────────────────────────────────────────────────┐      │
│  │  chat.js (~100行, 薄壳)                            │      │
│  │  → createFAB() 创建 "💬 AI" 按钮                   │      │
│  │  → createOverlay() 创建 670px 侧边栏               │      │
│  │  → fetch /plugins/servlet/wb/chat-dialog           │      │
│  │  → innerHTML 注入 + 脚本重建                        │      │
│  │  → POST /plugins/servlet/wb/chat 发消息            │      │
│  └────────────────────────────────────────────────────┘      │
│                                                               │
│  ┌────────────────────────────────────────────────────┐      │
│  │  admin.html (79KB, static 嵌入)                     │      │
│  │  → 左侧配置 + 右侧对话框                             │      │
│  │  → 3 标签页：基础配置 / 角色配置 / 快捷发言          │      │
│  │  → 7 种连通性测试 (svn/notion/notion_auto/gdrive/  │      │
│  │     ai/ai_models/local_ip)                          │      │
│  │  → fetch /plugins/servlet/wb/chat-dialog 共用对话框  │      │
│  └────────────────────────────────────────────────────┘      │
└─────────────────────────┬────────────────────────────────────┘
                          │ HttpServlet
                          ▼
┌──────────────────────────────────────────────────────────────┐
│               Java Plugin (OSGi Bundle, 303KB)                │
│                                                               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────┐  │
│  │ AdminServlet     │  │ ChatDialogServlet│  │ChatEndpoint│  │
│  │ (300行)          │  │ (32行)           │  │ (192行)    │  │
│  │ /wb-admin        │  │ /wb/chat-dialog  │  │ /wb/chat   │  │
│  │                  │  │                  │  │            │  │
│  │ serveStaticHtml  │  │ serveStaticHtml  │  │ Jira直接查 │  │
│  │ (admin.html)     │  │ (chat-dialog.   │  │ Notion→Bridge│  │
│  │ 鉴权+save+test   │  │  html)           │  │ GDrive→Bridge│  │
│  │ +proxy转发       │  │ 公开, 缓存1h     │  │ DeepSeek直连│  │
│  └──────────────────┘  └──────────────────┘  └───────────┘  │
│                                                               │
│  ┌──────────────────┐  ┌──────────────────┐                  │
│  │ ConfigService    │  │ HttpUtil         │                  │
│  │ PluginSettings   │  │ HTTP GET/POST    │                  │
│  │ 18个配置键       │  │ esc/escHtml      │                  │
│  └──────────────────┘  └──────────────────┘                  │
│                                                               │
│  静态资源 (嵌入JAR):                                           │
│  static/admin.html (79KB)  static/chat-dialog.html (31KB)     │
│  css/chat.css (10KB)       js/chat.js (~100行)                │
│  META-INF/lib/gson-2.10.1.jar (内嵌)                          │
└─────────────────────────┬────────────────────────────────────┘
                          │ HTTP (AI Bridge)  HTTP (DeepSeek)
                          ▼
┌──────────────────────────────────────────────────────────────┐
│            AI Bridge (Flask, 端口 9099, 875行)                │
│  → L1/L2 分层检索 (4源并行 + LLM决策)                        │
│  → 12 endpoints (/v1/chat/completions, /proxy/*, /health)    │
│  → 缓存: (Issue × Intent × Recency) 三级键, TTL 300s         │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| **共享对话框** | chat-dialog.html 统一管理 | DRY原则，一处修改两处生效 |
| **混合代理** | Notion/GDrive→Bridge, DeepSeek直连, Jira本地 | 代理解决公网访问，直连保证AI性能 |
| **构建系统** | build_plugin.py (javac+jar) 替代 Maven | 无需Maven仓库网络访问，JDK 11即可 |
| **热部署** | api_hotdeploy.py → UPM REST API | CSS/JS变更秒生效，Java变更5秒 |
| **配置存储** | PluginSettings (Jira内部DB) | 安全，按实例隔离，不写文件系统 |
| **静态嵌入** | admin.html + chat-dialog.html 打包进JAR | 零外部依赖，安装即用 |

---

## 二、文件清单（精确）

| # | 文件 | 大小/行数 | 职责 |
|---|------|----------|------|
| 1 | `AdminServlet.java` | 300行 | 配置管理 + 鉴权 + save/test/proxy |
| 2 | `ChatEndpoint.java` | 192行 | AI对话：Jira本地查 + 外部API走Bridge |
| 3 | `ChatDialogServlet.java` | 32行 | 提供共享chat-dialog.html片段 |
| 4 | `ConfigService.java` | ~85行 | PluginSettings 18键读写 |
| 5 | `HttpUtil.java` | 94行 | 共享HTTP GET/POST/esc/escHtml/readBody |
| 6 | `atlassian-plugin.xml` | 33行 | 3 servlet + 5 component-import + web-resource |
| 7 | `static/admin.html` | 79KB | 配置管理页（3标签页 + 右侧对话框） |
| 8 | `static/chat-dialog.html` | 31KB | 共享对话框 UI + CSS + JS（唯一真相源） |
| 9 | `css/chat.css` | 10KB | 对话面板壳样式（FAB+容器+关闭按钮） |
| 10 | `js/chat.js` | ~100行 | 薄壳：生命周期管理 + fetch chat-dialog |
| 11 | `build_plugin.py` | — | 构建脚本（javac 5类 → jar 303KB） |
| 12 | `api_hotdeploy.py` | — | UPM REST API 热部署 |
| 13 | `ai_bridge.py` | 875行 | AI Bridge (Flask, L1/L2 + 12 endpoints) |

---

## 三、构建系统（重大变更：Maven → javac）

### 3.1 构建流程 (build_plugin.py)

```
1. 清理 target/classes 旧编译产物
2. 收集 .m2/repository/ 下所有 JAR (18个) → classpath
3. javac 编译 5 个 .java → .class
4. 生成 OSGi MANIFEST.MF (Import-Package, Export-Package)
5. 复制资源: css/, js/, static/, atlassian-plugin.xml
6. 内嵌 gson-2.10.1.jar → META-INF/lib/
7. jar 命令打包 → jira-workbuddy-plugin-1.0.0.jar (~303KB)
```

### 3.2 编译命令

```bash
cd H:\workbuddy\jira\jira-workbuddy-plugin
python build_plugin.py
# → target/jira-workbuddy-plugin-1.0.0.jar
```

### 3.3 热部署 (api_hotdeploy.py)

```bash
python api_hotdeploy.py
# 1. GET /rest/plugins/1.0/?os_authType=basic → 获取 upm-token
# 2. POST /rest/plugins/1.0/?token={token} → multipart 上传 JAR
# 3. 等待 5s OSGi 容器重载 → 生效
```

---

## 四、Java 层设计详解

### 4.1 AdminServlet (300行)

| 路由 | 方法 | action | 功能 |
|------|------|--------|------|
| `/wb-admin` | GET | — | 读取 static/admin.html 输出 |
| `/wb-admin` | GET | `test&type=svn` | SVN 确认 |
| `/wb-admin` | GET | `test&type=notion` | Notion 连接测试 |
| `/wb-admin` | GET | `test&type=notion_auto` | 自动搜索 Notion 数据库 |
| `/wb-admin` | GET | `test&type=gdrive` | GDrive 连接测试 (via Bridge) |
| `/wb-admin` | GET | `test&type=ai` | AI API 真实测试 (发送"hi") |
| `/wb-admin` | GET | `test&type=local_ip` | 本机IP检测 |
| `/wb-admin` | GET | `proxy&path=/proxy/xxx` | 转发到 AI Bridge |
| `/wb-admin` | POST | `save` | 保存全部配置到 PluginSettings |

**新增能力**：
- `getProxy()` — 从配置读取 proxy.ip:proxy.port，支持所有外部 HTTP 调用走代理
- `bridge.url` 配置键 — AI Bridge 地址可配置（默认 localhost:9099）
- GDrive 测试改为走 AI Bridge 代理（解决内网无法出公网问题）
- AI 测试改为真实 API 调用（发"hi"，检查 response 含 "choices"）

### 4.2 ChatEndpoint (192行)

**混合代理模式**：

| 数据源 | 获取方式 | 原因 |
|--------|---------|------|
| Jira Issue | `IssueManager` Java API 直接查 | 同进程内，最快 |
| Notion | `POST /proxy/notion/search` → AI Bridge | 代理解决公网+代理支持 |
| Google Drive | `POST /proxy/gdrive/list` → AI Bridge | 代理解决公网+代理支持 |
| DeepSeek AI | `POST api.deepseek.com` 直连 | HTTPS 通常可达，无需代理 |

**关键代码位置**:
- L87-99: Notion → Bridge 代理
- L103-117: GDrive → Bridge 代理（含 proxy 参数传递）
- L120-155: DeepSeek 直连

### 4.3 ChatDialogServlet (32行)

- **路由**: `/plugins/servlet/wb/chat-dialog`
- **鉴权**: 无需登录（公开端点）
- **功能**: 读取 `static/chat-dialog.html` 并输出
- **缓存**: `Cache-Control: public, max-age=3600`
- **DRY**: chat.js 和 admin.html 共同 fetch 此端点

### 4.4 ConfigService

18 个配置键：

| 键 | 类型 | 默认值 | 说明 |
|----|------|--------|------|
| `svn.url` | String | — | SVN 仓库地址 |
| `svn.user` | String | — | SVN 用户名 |
| `svn.pass` | String | — | SVN 密码 |
| `fisheye.url` | String | — | FishEye 地址 |
| `notion.key` | String | — | Notion API Key |
| `notion.db` | String | — | Notion 数据库 ID |
| `gdrive.key` | String | — | Google API Key |
| `gdrive.folders` | String | — | GDrive 文件夹ID（逗号分隔） |
| `ai.url` | String | `https://api.deepseek.com/v1/chat/completions` | AI API URL |
| `ai.model` | String | `deepseek-chat` | 模型名称 |
| `ai.key` | String | — | AI API Key |
| `ai.max_tokens` | int | 4096 | 最大输出Token |
| `ai.temp` | double | 1.0 | 温度参数 |
| `proxy.ip` | String | — | 代理IP |
| `proxy.port` | String | — | 代理端口 |
| `roles.config` | String | — | 角色配置JSON |
| `quick.config` | String | — | 快捷发言JSON |
| `bridge.url` | String | `http://localhost:9099` | **新增**: AI Bridge 地址 |

---

## 五、前端架构详解

### 5.1 chat-dialog.html (31KB, 唯一真相源)

**包含内容**：
- CSS 主题变量（`:root` 明色 + `.wb-dark` 暗色）
- 对话框完整 HTML 结构
- 角色切换菜单 + 快捷发言标签
- 消息渲染 (Markdown) + 代码复制 + 贴为评论
- 主题切换 + 字体调节 + 对话历史管理
- 所有 JS 全局函数 `wb` 前缀命名空间
- CSS 作用域 `.wb-dialog-scope` 类

**加载方式**：
1. chat.js → `fetch('/plugins/servlet/wb/chat-dialog')` → `innerHTML` 注入
2. admin.html → `fetch('/plugins/servlet/wb/chat-dialog')` → `innerHTML` 注入

### 5.2 chat.js (~100行, 薄壳)

```javascript
// 职责：生命周期管理
createFAB()        // 右下角 "💬 AI" 按钮
createOverlay()    // 670px 侧边栏容器
createCloseBtn()   // 独立关闭按钮
togglePanel()      // 切换显示/隐藏
loadDialog()       // fetch chat-dialog + innerHTML + 脚本重建

// 关键：innerHTML 不执行 <script>，需 createElement('script') 重建
```

### 5.3 admin.html (79KB)

- 3 标签页：基础配置 / 角色配置 / 快捷发言
- 左侧栏配置 + 右侧对话框（共用 chat-dialog.html）
- localStorage 存储临时配置 + PluginSettings 持久化

---

## 六、PRD 对照检查

| PRD 需求 | 状态 | 实现位置 |
|---------|------|---------|
| AI 对话面板 (670px侧栏) | ✅ | chat.js createOverlay() |
| 多轮对话 (2轮上下文) | ✅ | chat.js _conversationHistory |
| Markdown 渲染 | ✅ | chat-dialog.html renderMD() |
| 一键复制 | ✅ | chat-dialog.html copyToClipboard() |
| 贴为评论 | ✅ | POST /proxy/jira/comment |
| 明暗主题切换 | ✅ | chat-dialog.html wbToggleTheme() |
| 字体调节 (14/16/18/21px) | ✅ | chat-dialog.html wbSetFontSize() |
| 角色系统 (多角色+知识库开关) | ✅ | chat-dialog.html + PluginSettings |
| 快捷发言 (预设问题) | ✅ | chat-dialog.html + PluginSettings |
| 配置管理页 (仅管理员) | ✅ | AdminServlet checkAdmin() |
| Jira 本地数据自动获取 | ✅ | ChatEndpoint IssueManager |
| SVN/FishEye 代码提交 | ⚠️ | 通过 AI Bridge 代理（未在 ChatEndpoint 直接调用） |
| Notion 文档检索 | ✅ | ChatEndpoint → AI Bridge /proxy/notion/search |
| GDrive 文件检索 | ✅ | ChatEndpoint → AI Bridge /proxy/gdrive/list |
| 构建自动化 | ✅ | build_plugin.py (javac+jar) |
| 热部署 | ✅ | api_hotdeploy.py (5s生效) |
| 配置按实例隔离 | ✅ | PluginSettings |
| JS `wb` 命名空间 | ✅ | 全局函数 wb 前缀 |
| CSS `.wb-dialog-scope` 作用域 | ✅ | chat-dialog.html |

---

## 七、已知问题与优化建议

### 7.1 当前问题

| # | 严重度 | 问题 | 影响 |
|---|--------|------|------|
| 🔴 1 | 高 | SVN 提交未在 ChatEndpoint 直接获取 | 无 SVN 上下文喂给 AI（除非走 ai_bridge.py 的 /v1/chat/completions） |
| 🟡 2 | 中 | ChatEndpoint 无 L1/L2 分层检索 | 响应可能慢于 ai_bridge.py |
| 🟡 3 | 中 | ChatEndpoint 无缓存 | 同一 Issue 重复查询全量数据 |
| 🟡 4 | 中 | `bridge.url` 无 fallback 机制 | 若 Bridge 挂掉，Notion/GDrive 静默失败 |
| 🟠 5 | 低 | 构建依赖 .m2/repository/ 18个JAR | 若 .m2 被清需重建（已在 H:\workbuddy\jira\.m2\ 有备份） |

### 7.2 架构优化建议

| 优先级 | 建议 | 工作量 | 收益 |
|--------|------|--------|------|
| 🔴 P0 | ChatEndpoint 增加 SVN 获取 (通过 Bridge /proxy/jira/test → FishEye) | 10行 | AI 回答含代码变更上下文 |
| 🟡 P1 | ChatEndpoint 增加简单缓存 (HashMap, TTL 60s) | 15行 | 同一 Issue 重复查询加速 |
| 🟡 P1 | 增加 `bridge.url` 健康检查 + 降级提示 | 5行 | 前端显示"Bridge 不可用" |
| 🟢 P2 | 考虑将 ChatEndpoint 改为完全代理 ai_bridge.py 的 `/v1/chat/completions` | 30行 | 获得完整 L1/L2+缓存 |
| 🟢 P2 | admin.html 分离 CSS → 独立文件 | 提取CSS | 减小 HTML 体积 |

---

## 八、部署清单

### 8.1 首次部署

```bash
# 1. 构建
cd H:\workbuddy\jira\jira-workbuddy-plugin
python build_plugin.py

# 2. 确认 JAR
ls -lh target/jira-workbuddy-plugin-1.0.0.jar
# → ~303KB

# 3. 上传到 Jira 服务器
scp target/jira-workbuddy-plugin-1.0.0.jar root@192.168.8.34:/data/jiradata/plugins/installed-plugins/

# 4. 热部署
python api_hotdeploy.py

# 5. 验证
curl -s http://ctjira1.lmdgame.com:8080/plugins/servlet/wb/chat/ping
# → {"status":"ok"}
```

### 8.2 AI Bridge 部署（Jira 服务器侧）

```bash
# 若 Bridge 与 Jira 同机
cd /opt/ai-bridge
systemctl start ai-bridge  # 已配置 systemd

# 验证
curl http://localhost:9099/health
# → {"status":"ok"}
```

### 8.3 部署后配置

1. 访问 `http://ctjira1.lmdgame.com:8080/plugins/servlet/wb-admin`
2. 填入 AI API Key
3. 填入 Notion/GDrive Key（如需知识库集成）
4. 确认 `bridge.url` = `http://localhost:9099`
5. 点击保存
6. 打开任意 Issue 页面 → 右下角 "💬 AI" → 测试对话

---

## 九、版本轨迹

| 版本 | 日期 | 关键变更 |
|------|------|---------|
| v1.0.0 | 2026-05-26 | 初始JAR，JAX-RS框架，Maven构建 |
| v1.1.0-dev | 2026-05-27 | JAX-RS→HttpServlet, AdminServlet内联HTML, chat.js 18KB |
| v1.2.0-dev | 2026-05-28 01:51 | 混合代理模式, chat-dialog.html DRY, build_plugin.py, 热部署, 303KB JAR |

---

**文档结束。** 基于 TechDoc v1.0.0 + PRD v1.0.0 + 2026-05-28 02:17 代码扫描。
