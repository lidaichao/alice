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

## 密钥注入（安全要求）

Cursor SDK Key 不写入仓库 `.env`，部署时通过环境变量注入。`.env` 中保留为占位符 `CURSOR_SDK_KEY=请通过系统环境变量或 PM2 启动时注入（详见 docs/SETUP.md）`。

### 方式一：直接环境变量

```bash
# Windows
set CURSOR_SDK_KEY=crsr_你的实际Key && npm start

# Linux (含 .31 服务器)
CURSOR_SDK_KEY=crsr_你的实际Key npm start
```

### 方式二：PM2 ecosystem.config.js

```js
module.exports = {
  apps: [{
    name: 'alice-hub',
    script: 'src/server.js',
    env: {
      NODE_ENV: 'production',
      PORT: 5000,
      CURSOR_SDK_KEY: 'crsr_你的实际Key'
    }
  }]
};
```

启动：`pm2 start ecosystem.config.js`

### Key 轮换流程

1. 在 Cursor Dashboard 生成新 Key
2. 更新环境变量中的 `CURSOR_SDK_KEY`
3. 重启服务
4. 验证：`curl http://192.168.72.31:5000/health` → 200
5. 吊销旧 Key
