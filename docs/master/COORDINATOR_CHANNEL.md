# 协调者双频道说明

Alice 仓库内 **只加载杰尼龟规则**（`.cursor/rules/squirtle-*.mdc`）。  
架构师「兔子」在 **独立工作区**，避免同一窗口双角色冲突。

## 怎么用

| 你要找谁 | 在 Cursor 打开哪个文件夹 |
|----------|--------------------------|
| **兔子**（审战报、下指令） | `H:\workbuddy\coordinator-rabbit` |
| **杰尼龟**（写代码、跑测试） | `H:\workbuddy\alice`（本仓库） |

协调者手册：`H:\workbuddy\coordinator-rabbit\COORDINATOR_PLAYBOOK.md`

## 不要做的事

- 不要把 `rabbit-*.mdc` 放进本仓库的 `.cursor/rules/`（会与杰尼龟 `alwaysApply` 重叠）
- 不要在 Alice 窗口让 AI「既当兔子又当杰尼龟」
