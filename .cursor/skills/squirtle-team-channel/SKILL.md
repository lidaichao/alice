---
name: squirtle-team-channel
description: >-
  When the coordinator says to check TEAM_CHANNEL.md, read the shared
  message board at coordinator-rabbit/TEAM_CHANNEL.md and write battle
  reports or blocker notices using the fixed format. Never read or write
  without explicit coordinator instruction.
---

# 团队频道协议

## 文件位置

`H:\workbuddy\coordinator-rabbit\TEAM_CHANNEL.md`

## 铁律

**只有协调者说"杰尼龟去看 TEAM_CHANNEL.md"，才去读。不自动读，不自动写。**

## 读取

从文件**开头往后**找第一条 `@杰尼龟` 或 `@全员` 的消息。不翻全文。

## 写入

新消息插入在 `<!-- NEW MESSAGES HERE -->` 注释**下方**（文件头部）。

## 消息格式

```
发言人：杰尼龟
@：兔子
时间：YYYY-MM-DD HH:MM

---

战报内容...
```

发言人固定为「杰尼龟」。

## 发言场景

| 什么时候写 | @谁 | 内容 |
|-----------|------|------|
| 完成开发任务后 | @兔子 | 战报：改动文件 + 测试结果 |
| 遇到阻塞 | @协调者 | 阻塞原因 |
