# 爱丽丝项目 结构审计 + 精简方案

> 审计时间：2026-05-29 | 当前大小：~4.7G | 文件数：~47,000+

---

## 一、空间占用分析

| 目录 | 大小 | 文件数 | 分类 | 建议 |
|------|------|--------|------|------|
| `jira-workbuddy-plugin/target/` | **4.4G** | ~47,000 | Maven构建产物 | ❌ 删除（可重建） |
| `alice/node_modules/` | 305M | ~300 | Electron依赖 | ⚠️ 保留（可重建） |
| `jira-workbuddy-plugin/build/` | 524K | ~20 | 旧构建缓存 | ❌ 删除 |
| `jira-workbuddy-plugin/src/` | 252K | 12 | Java源码+静态文件 | ✅ 保留核心 |
| `wecom-jira-bridge/` | 190K | 15 | Python AI引擎 | ✅ 核心保留 |
| `alice/` (不含node_modules) | 168K | 6 | Electron桌面端 | ✅ 核心保留 |
| `archived/` | 80K | 12 | 历史遗留代码 | ❌ 删除/移出 |
| `artifacts/` | 48K | 3 | 设计文档 | ✅ 保留 |
| `prompts/` | 5K | 5 | 测试提示词 | ❌ 删除（已嵌入代码） |
| `queue/` | 0 | 0 | 空目录 | ❌ 删除 |
| `.m2/` | 7.1M | 18 | Maven本地缓存 | ⚠️ 可清理 |

**可立即释放：~4.4G（target目录）**

---

## 二、文件分类评估

### ✅ 核心资产（必须保留）

| 文件/目录 | 用途 | 大小 |
|----------|------|------|
| `alice/main.js` | Electron主进程 | 3.5K |
| `alice/preload.js` | IPC安全桥 | 2K |
| `alice/bridge-manager.js` | Python子进程管理 | 3K |
| `alice/conversations.js` | 多会话管理 | 3K |
| `alice/package.json` | 项目配置 | 1K |
| `wecom-jira-bridge/ai_bridge.py` | AI核心引擎 | 60K |
| `wecom-jira-bridge/jira_api.py` | Jira客户端 | 5K |
| `wecom-jira-bridge/jira_mcp_server.py` | MCP服务 | 12K |
| `wecom-jira-bridge/intent_classifier.py` | 意图分类 | 8K |
| `wecom-jira-bridge/jira_operation_manager.py` | 确认卡 | 14K |
| `wecom-jira-bridge/audit_gateway.py` | 审计网关 | 10K |
| `static/alice-index.html` | 桌面UI | 15K |
| `static/alice-styles.css` | 桌面样式 | 7K |
| `wecom-jira-bridge/.env` | 凭据配置 | 1K |

### ⚠️ 保留但待观察（Jira Plugin模式备份）

| 文件 | 用途 | 是否必需 |
|------|------|---------|
| `static/chat-dialog.html` | Jira Web聊天 | 🔄 桌面版替代后可移除 |
| `static/admin.html` | Jira Web设置 | 🔄 桌面版替代后可移除 |
| `src/.../ChatEndpoint.java` | Java透传网关 | 🔄 桌面preload替代后废弃 |
| `src/.../ChatDialogServlet.java` | Java Servlet | 🔄 同上 |
| `src/.../HttpUtil.java` | Java HTTP工具 | 🔄 同上 |
| `src/.../AdminServlet.java` | Java管理Servlet | 🔄 同上 |
| `src/.../ConfigService.java` | Java配置服务 | 🔄 同上 |

### ❌ 可删除

| 文件/目录 | 说明 | 释放 |
|----------|------|------|
| `jira-workbuddy-plugin/target/` | Maven构建输出 | **4.4G** |
| `jira-workbuddy-plugin/build/` | 旧构建缓存 | 524K |
| `archived/` | 12个历史文件 | 80K |
| `prompts/` | 5个测试提示词 | 5K |
| `queue/` | 空目录 | 0 |
| `.m2/` | Maven本地缓存 | 7.1M |

---

## 三、结构诊断

### 问题1：Java Plugin 层在桌面架构中冗余

```
当前结构：
jira-workbuddy-plugin/
├── pom.xml                    ← Maven构建（桌面端不需要）
├── build/                     ← 旧构建产物
├── target/                    ← 4.4G Maven输出
├── src/main/java/.../         ← 5个Java文件，桌面端用不上
│   ├── ChatEndpoint.java      ← preload.js替代
│   ├── ChatDialogServlet.java ← preload.js替代
│   ├── HttpUtil.java          ← proxy端点替代
│   ├── AdminServlet.java      ← 设置页替代
│   └── ConfigService.java     ← electron-store替代
├── src/main/resources/
│   ├── atlassian-plugin.xml   ← Jira插件描述符（桌面端不需要）
│   ├── css/chat.css           ← Jira Web样式
│   ├── js/chat.js             ← Jira Web脚本
│   └── static/                ← 唯一需要保留的
│       ├── alice-index.html   ✅ 桌面UI
│       ├── alice-styles.css   ✅ 桌面样式
│       ├── chat-dialog.html   🔄 Jira Web备份
│       └── admin.html         🔄 Jira Web备份
```

**诊断：jira-workbuddy-plugin 目录有 95% 的内容对桌面端无用。**

### 问题2：静态文件位置不合理

`alice-index.html` 和 `alice-styles.css` 放在 `jira-workbuddy-plugin/src/main/resources/static/` 下，与 Jira Plugin 目录耦合。应该移到 `alice/` 或独立的 `ui/` 目录。

### 问题3：Python 引擎缺少入口文档

`wecom-jira-bridge/` 下有 15 个文件，但没有 `requirements.txt` 或启动说明，新人难以理解启动方式。

### 问题4：项目根目录散落文件

虽然有清理，但 artifacts/ 文档和 archived/ 旧代码混在一起。

---

## 四、推荐结构（精简后）

```
H:\workbuddy\jira\
│
├── alice/                          # 🖥️ Electron 桌面端（核心）
│   ├── main.js                     # 主进程
│   ├── preload.js                  # IPC安全桥
│   ├── bridge-manager.js           # Python子进程
│   ├── conversations.js            # 多会话
│   ├── package.json                # 依赖+打包配置
│   ├── ui/                         # 桌面UI
│   │   ├── index.html              # 主窗口
│   │   └── styles.css              # 样式
│   └── node_modules/               # npm依赖（gitignore）
│
├── bridge/                         # 🧠 Python AI引擎（核心）
│   ├── ai_bridge.py                # 主服务
│   ├── jira_api.py                 # Jira客户端
│   ├── jira_mcp_server.py          # MCP服务
│   ├── intent_classifier.py        # 意图分类
│   ├── jira_operation_manager.py   # 确认卡
│   ├── audit_gateway.py            # 审计
│   ├── skills/registry.yaml        # 插件注册表
│   ├── requirements.txt            # Python依赖
│   └── .env.example                # 配置模板
│
├── plugin/                         # 🔌 Jira Plugin（维护模式）
│   └── src/main/resources/static/
│       ├── chat-dialog.html        # Jira Web聊天（备份）
│       └── admin.html              # Jira Web设置（备份）
│
├── docs/                           # 📄 文档
│   ├── desktop_app_plan.md
│   ├── alice_ux_optimization.md
│   ├── config_ux_optimization.md
│   └── project_audit.md
│
├── .gitignore
└── README.md
```

---

## 五、精简执行计划

### Phase 1：立即清理（安全，可逆）

| 操作 | 命令 | 释放 |
|------|------|------|
| 删除 Maven target | `rm -rf jira-workbuddy-plugin/target` | 4.4G |
| 删除构建缓存 | `rm -rf jira-workbuddy-plugin/build` | 524K |
| 删除历史代码 | `git rm -r archived` | 80K |
| 删除测试提示词 | `git rm -r prompts` | 5K |
| 删除空目录 | `rmdir queue` | 0 |

**释放总计：~4.4G**

### Phase 2：结构重组（需 git mv）

| 操作 | 说明 |
|------|------|
| `alice-index.html` → `alice/ui/index.html` | UI文件移到桌面端目录 |
| `alice-styles.css` → `alice/ui/styles.css` | 同上 |
| `artifacts/*.md` → `docs/` | 文档统一管理 |
| 更新 `main.js` 中的 `loadFile` 路径 | 指向新位置 |
| 更新 `index.html` 中的 CSS 引用 | 指向新位置 |

### Phase 3：Java Plugin 瘦身（待桌面版稳定后）

| 操作 | 说明 |
|------|------|
| 删除 `ChatEndpoint.java` | preload 替代 |
| 删除 `ChatDialogServlet.java` | preload 替代 |
| 删除 `HttpUtil.java` | proxy 端点替代 |
| 删除 `AdminServlet.java` | 设置页替代 |
| 删除 `ConfigService.java` | electron-store 替代 |
| 删除 `atlassian-plugin.xml` | 桌面端不需要 |
| 删除 `pom.xml` | 桌面端不需要 Maven |

### Phase 4：Python 引擎目录重命名

| 当前 | 建议 | 说明 |
|------|------|------|
| `wecom-jira-bridge/` | `bridge/` | 简洁，无"wecom"误导 |

---

## 六、.gitignore 建议

```
# 构建产物（可重建）
jira-workbuddy-plugin/target/
jira-workbuddy-plugin/build/
alice/node_modules/
alice/dist/

# 凭据
.env
*.pem
*.key

# IDE
.idea/
.vscode/
*.swp

# Maven
.m2/

# 测试产物
test_screenshots/
*.log
*.hprof
```

---

## 七、精简约比

| 指标 | 当前 | Phase1后 | Phase2后 | Phase3后 |
|------|------|---------|---------|---------|
| 磁盘占用 | ~4.7G | ~300M | ~300M | ~200M |
| 文件数 | ~47,000 | ~500 | ~500 | ~400 |
| 目录层级 | 7层 | 4层 | 4层 | 3层 |
| Java文件 | 5 | 5 | 5 | **0** |
| Python文件 | 9 | 9 | 9 | 9 |
| JS文件 | 4 | 4 | 4 | 4 |
| HTML文件 | 4 | 4 | 4 | **2** |
