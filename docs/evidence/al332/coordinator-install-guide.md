# 协调者跟装一页纸 · 白泽 Windows 客户端（八步 ④）

> 试装人 1：杰尼龟 · 2026-06-29 · 包版本 SHA256 `60529A24…3649`

## 1. 下载安装包

| 项 | 值 |
|----|-----|
| 服务器 | `alice@192.168.72.31`（SSH 别名 `alice-server`） |
| 路径 | `/tmp/alicev2-releases/白泽 Setup.exe` |
| 大小 | 217,738,670 bytes (~207.6 MiB) |

**内网取包（任选其一）**

```bash
# 从开发机 scp 到本机（示例）
scp alice@192.168.72.31:/tmp/alicev2-releases/白泽\ Setup.exe ./

# 或在 31 本机直接复制
ls -la /tmp/alicev2-releases/
```

## 2. 安装步骤

1. 双击 `白泽 Setup.exe`
2. 安装向导 → 可选安装目录 → 完成
3. 桌面 / 开始菜单应出现 **「白泽」** 快捷方式
4. 首次启动 **无需手改 Hub** — 默认已指向 `http://192.168.72.31:5000`

> 若本机曾装旧版，建议先卸载再装。

## 3. 验收清单（协调者试装人 2）

| # | 检查 | 预期 |
|---|------|------|
| 1 | 安装完成 | 快捷方式可启动 |
| 2 | Hub 地址 | 内置默认 `.31:5000`（无需设置页手改） |
| 3 | 探活 | `curl http://192.168.72.31:5000/health` → **200** |
| 4 | 登录/聊天 | **当前 .31 仍为 v3.2 ai-bridge**，Baize `/auth/*` 在步⑦ Node Hub 部署后可用；步④以 health + 客户端可启动为准 |

## 4. 探活命令

```bash
curl -s http://192.168.72.31:5000/health
```

预期：`status` 字段存在且 HTTP 200（当前 service=`ai-bridge-v5`）。

## 5. 失败联系

| 角色 | 负责 |
|------|------|
| 杰尼龟 | 安装包 / 客户端 / asar Hub 地址 |
| 兔子 | 服务器网络 / 步⑤～⑦ 清场部署 |
| 协调者 | 试装组织 / 公告 |

## 6. 证据索引

- 包 manifest：`docs/evidence/al327/release-manifest.md`
- asar Hub 抽检：`docs/evidence/al327/asar-hub-check.txt`
- 试装人 1：`docs/evidence/al332/`（health JSON + 客户端截图）
