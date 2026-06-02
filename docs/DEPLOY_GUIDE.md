# Alice V2.0 — 私有化部署指南

> 面向运维团队。适用于内网 Linux 服务器 + Windows 客户端环境。

## 1. 环境准备

| 组件 | 最低版本 | 用途 |
|------|:---:|------|
| Docker | 20.10+ | 容器运行时 |
| Docker Compose | 2.0+ | (可选) 编排多服务 |
| SVN CLI | 已内置在镜像中 | 代码 Diff 检索 |
| 内网 HTTPS 证书 | - | 可选，`global_config.json` 中配置 |

### 服务器端口放行

```
9099/tcp   AI Bridge HTTP API
```

### 准备配置目录

```bash
mkdir -p /opt/alice/config
```

---

## 2. 后端服务拉起

### 2.1 准备配置文件

创建 `/opt/alice/config/global_config.json`：

```json
{
  "JIRA_BASE_URL": "http://ctjira1.lmdgame.com:8080",
  "JIRA_PAT": "YOUR_JIRA_PERSONAL_ACCESS_TOKEN",
  "DEEPSEEK_KEY": "sk-YOUR_DEEPSEEK_API_KEY",
  "NOTION_KEY": "ntn_YOUR_NOTION_API_KEY",
  "GDRIVE_KEY": "YOUR_GOOGLE_DRIVE_API_KEY",
  "GDRIVE_FOLDERS": "folder_id_1,folder_id_2",
  "SVN_URL": "https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3",
  "SVN_USERNAME": "your-svn-user",
  "SVN_PASSWORD": "your-svn-password",
  "FISHEYE_URL": "http://192.168.8.34:8060",
  "ADMIN_PASS": "change-me-on-first-login"
}
```

### 2.2 启动容器

```bash
docker run -d \
  --name alice-ai-bridge \
  --restart unless-stopped \
  -p 9099:9099 \
  -v /opt/alice/config/global_config.json:/app/global_config.json:ro \
  harbor.lmdgame.com/alice/alice-ai-bridge:latest
```

### 2.3 验证

```bash
curl http://<服务器IP>:9099/health
# 预期: {"status":"ok","service":"ai-bridge-v5","engine":"deepseek-chat"}
```

---

## 3. 管理员初始化

### 3.1 登录 Admin Web

浏览器打开: `http://<服务器IP>:9099/admin`

密码: `global_config.json` 中配置的 `ADMIN_PASS`

### 3.2 录入关键凭据

| 配置项 | 路径 | 说明 |
|------|------|------|
| Jira PAT | 设置 → Jira 连接 | 用于查询任务元数据 |
| SVN 账密 | 设置 → SVN 配置 | 用于代码 Diff 检索 |
| Notion API Key | 设置 → 知识库 → Notion | 用于文档目录检索 |
| Google Drive Key | 设置 → 知识库 → GDrive | 用于 Google 文档检索 |
| FishEye 地址 | 设置 → 代码检索 | SVN 提交记录索引 |

> 所有配置实时生效，无需重启容器。

---

## 4. 客户端分发

### 4.1 下载安装

从内部文件服务器下载 `爱丽丝JiraAI Setup *.exe`，双击安装。

### 4.2 配置服务端地址

安装后首次启动前，在控制台执行：

```javascript
// 方法 1: 浏览器 DevTools Console (Electron 窗口中 Ctrl+Shift+I)
localStorage.setItem('alice_server_url', 'http://<服务器IP>:9099');
location.reload();
```

或者通过 IPC API：

```javascript
// 方法 2: 通过 preload 桥
window.desktopAPI.config.setServerURL('http://<服务器IP>:9099');
```

### 4.3 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt+Space` | 呼出/隐藏 Alice 窗口 |
| `Esc` | 关闭 Artifacts 分屏 |

---

## 5. 运维命令参考

```bash
# 查看日志
docker logs -f alice-ai-bridge

# 重启服务
docker restart alice-ai-bridge

# 升级镜像
docker pull harbor.lmdgame.com/alice/alice-ai-bridge:latest
docker stop alice-ai-bridge && docker rm alice-ai-bridge
# 重新执行 2.2 的 docker run 命令

# 健康检查
curl http://localhost:9099/health

# 查看缓存状态
curl http://localhost:9099/cache/stats
```

---

## 6. 故障排查

| 现象 | 排查步骤 |
|------|---------|
| 客户端无法连接 | `curl http://<IP>:9099/health` 确认端口可达；检查防火墙 |
| 返回 401 | `global_config.json` 中 `DEEPSEEK_KEY` 无效 |
| Jira 查询失败 | `JIRA_PAT` 过期，重新生成后更新 Admin 面板 |
| SVN Diff 为空 | 检查 `SVN_URL/USERNAME/PASSWORD`；确认 SVN 客户端在容器内可用 |
| 知识库无结果 | Notion Key 权限不足；GDrive 文件夹 ID 错误 |
