# AliceV2 开发者上手

## 环境要求

- **Node.js** >= 18
- **npm**（随 Node.js 安装）
- **git**

## 克隆后第一步

```bash
cd aliceV2
npm install
```

安装完成后可以跑 `npm test` 确认环境正常（基线：35 files · 418 passed）。

## 三种启动方式

### 方式 A：双击 .bat 脚本（推荐新手）

| 脚本 | 作用 |
|------|------|
| `start-server.bat` | 启动 Hub，命令行窗口保持打开 |
| `stop-server.bat` | 停止 Hub（kill node.exe） |
| `restart-server.bat` | 重启 Hub |

### 方式 B：npm start（命令行）

```bash
npm start
```

### 方式 C：pm2 start（生产）

```bash
pm2 start npm --name "baize-hub" -- start
pm2 stop baize-hub
pm2 restart baize-hub
```

## 可用命令

| 命令 | 说明 |
|------|------|
| `npm test` | 运行全部 418 个测试 |
| `npm start` | 启动 Hub 服务端 |
| `npm run desktop:dev` | 启动 Electron 桌面客户端（开发模式） |
| `npm run desktop:dist` | 打包 .exe 安装包 |

## 必备配置

AliceV2 通过 `baize/config/` 下的 yaml 文件配置：

### jira.yaml

对内网 Jira 的读写凭证。开发环境可保持 `enabled: false`。

```yaml
enabled: true
baseURL: http://ctjira1.lmdgame.com:8080
apiToken: "<Jira PAT>"
projectKey: AL
issueType: Task
```

### claude.yaml

AI 提供商配置。默认 `provider: cursor`，无需额外配置即可使用。

### client-version.yaml

客户端自动更新配置：

```yaml
enabled: true
currentVersion: "0.2.36"
```

## 访问地址

| 环境 | 地址 |
|------|------|
| 本地开发 | `http://127.0.0.1:3000` |
| 生产 | `http://192.168.72.31:5000` |

## 验证

```bash
# 本地
curl http://127.0.0.1:3000/health

# 生产
curl http://192.168.72.31:5000/health
# 应返回 200
```
