# Alice Jira AI — 灰度测试白皮书 (Graybox SOP)

> 版本：v1.1 | 日期：2026-06-04 | 作者：可达鸭 (Psyduck)

**相关文档**：[技术架构](Alice_Master_Architecture_v1.0.md) · [白泽 Baize 架构](Baize_Architecture_v1.0.md)

---

## 一、什么是 Alice？

Alice 是一款面向游戏研发团队的 AI 工作助手。

- 一句话查 Jira 任务、SVN 提交、代码 Diff
- 自动关联 Notion 策划文档做 Code Review
- 反幻觉设计：数据溯源 + 防编造

**当前版本**：v1.0.0-beta（灰度测试）

---

## 二、如何安装

### macOS

1. 从内部 Release 页面下载 `Alice-Jira-AI-v1.0.0-beta-darwin-arm64.dmg`
2. 双击 `.dmg`，将 Alice 拖入 `Applications`
3. **⚠️ 第一次打开时**：系统会提示"未验证的开发者"
   - 打开 **系统设置 → 隐私与安全性**
   - 在底部找到"Alice Jira AI 已被阻止"，点击 **"仍要打开"**
   - 确认后即可正常启动

### Windows

1. 下载 `Alice-Jira-AI-Setup-v1.0.0-beta.exe`
2. 双击安装，选择安装路径
3. 桌面会出现快捷方式 "Alice Jira AI"

---

## 三、配置指南

### 3.1 获取 Jira Personal Access Token (PAT)

1. 登录 Jira：`http://ctjira1.lmdgame.com:8080`
2. 右上角头像 → **个人设置** → **Personal Access Tokens**
3. 点击 **创建 Token**，名称随意（如 `Alice-Graybox`），过期时间设为 90 天
4. 复制生成的 Token（只显示一次！）

### 3.2 配置 Alice

1. 启动 Alice 桌面应用
2. 点击左下角 ⚙️ **设置**
3. 填入：
   - **Jira 地址**：`http://ctjira1.lmdgame.com:8080`
   - **PAT**：粘贴你的 Token
   - **DeepSeek Key**：联系管理员获取
4. 点击 **Test Connection**，看到 ✅ 绿色即配置成功

### 3.3 管理员：Web 后台（可选）

浏览器打开 `http://<服务器>:9099/admin`（需管理员 Bearer Token）。

| 操作 | 说明 |
|------|------|
| 默认对话模型 | 下拉选择后立即生效，写入 `global_config.json` |
| 编辑 API 配置 | 仅修改 DeepSeek API 地址与 Key |
| 周报字段映射 | Jira 区配置 `JIRA_DEADLINE_FIELD_BY_PROJECT`（如 CT → End date） |

刷新页面后模型选择应保持不变；若变回 `deepseek-chat`，请确认后端已更新至含加载守卫的版本。

---

## 四、如何使用

### 常用对话

| 你说 | Alice 回答 |
|------|-----------|
| "CT-10888 最近提交了啥？" | SVN 提交列表（版本/作者/时间） |
| "帮我分析一下 r40538 的 diff" | Code Review + 关联策划文档 |
| "有哪些阵型相关的设计案？" | Notion 文档列表 |
| "写一下本周 CT 项目周报（6/1-6/5）" | Jira 按截止时间字段汇总 + PM 周报 |

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt + Space` | 显示/隐藏 Alice 窗口 |

---

## 五、遇到 Bug 怎么办？🐞

### 5.1 一键反馈

1. 点击 Alice 左下角的 **🐞 反馈** 按钮
2. 在弹窗中描述问题（越详细越好）
3. 点击 **"生成诊断报告"**（自动抓取后端日志 + 客户端环境）
4. 点击 **"📋 复制到剪贴板"** 或 **"💾 下载 .txt"**

### 5.2 提交给 IT 支持

将生成的诊断报告通过以下任一方式提交：

| 方式 | 地址 |
|------|------|
| **Jira** | 在 CT 项目下新建 Bug，粘贴报告内容 |
| **企业微信** | 发送到 "Alice 灰度测试群" |
| **直接联系** | 找李大超 (lidaichao@lmdgame.com) |

### 5.3 常见问题自助

| 问题 | 解决方法 |
|------|----------|
| "无法连接后端" | 重启 Alice 应用 |
| "Jira 连接失败" | 点击 Test Connection 检查 PAT 是否有效 |
| "查询无结果" | 确认 Jira 地址正确、VPN 已连接 |
| Window 窗口卡死 | `Alt+Space` 隐藏再显示 |

---

## 六、灰度测试目标

| 目标 | 验收标准 |
|------|----------|
| 安装成功率 | 95% 以上用户一次安装成功 |
| 核心对话 | 查任务、看提交、分析 Diff 三个场景跑通 |
| Bug 反馈 | 每份反馈含完整诊断日志 |
| 稳定性 | 连续使用 2 小时无崩溃 |

---

## 七、OTA 自动更新

Alice 内置 OTA 更新机制：

- 每次启动自动检查新版本（静默，不打断工作）
- 有更新时后台下载
- **下次重启 Alice 时自动生效**

---

## 八、联系方式

| 角色 | 联系方式 |
|------|----------|
| 技术负责人 | 李大超 — lidaichao@lmdgame.com |
| 架构师 | 兔子 — 企业微信 "Alice 架构讨论群" |
| Bug 提交 | Jira CT 项目 → 新建 Bug → 粘贴诊断报告 |
